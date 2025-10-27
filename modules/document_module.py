#!/usr/bin/env python3
"""
from app.core.logging import get_logger
문서 처리 모듈 - Perfect RAG에서 분리된 문서 처리 기능
2025-09-29 리팩토링

이 모듈은 PDF/TXT 문서 처리, 텍스트 추출, 메타데이터 추출 등
문서 관련 기능을 담당합니다.
"""

import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber
import hashlib
import json

# OCR 처리 (선택적)
try:
    from ocr_processor import OCRProcessor
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = get_logger(__name__)


class DocumentModule:
    """문서 처리 통합 모듈"""

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}

        # 캐시 설정
        self.pdf_text_cache = OrderedDict()
        self.MAX_PDF_CACHE = self.config.get('max_pdf_cache', 50)
        self.MAX_TEXT_LENGTH = self.config.get('max_text_length', 8000)
        self.MAX_PDF_PAGES = self.config.get('max_pdf_pages', 10)

        # OCR 프로세서
        self.ocr_processor = None
        if OCR_AVAILABLE and self.config.get('enable_ocr', False):
            try:
                self.ocr_processor = OCRProcessor()
                logger.info("OCR processor initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OCR: {e}")

    def extract_pdf_text(self, pdf_path: Path, use_cache: bool = True) -> Dict[str, Any]:
        """
        PDF 파일에서 텍스트 추출 (캐싱 포함)

        Args:
            pdf_path: PDF 파일 경로
            use_cache: 캐시 사용 여부

        Returns:
            추출된 정보 딕셔너리
        """
        # 캐시 키 생성
        cache_key = str(pdf_path)

        # 캐시 확인
        if use_cache and cache_key in self.pdf_text_cache:
            # LRU를 위해 맨 뒤로 이동
            cached_result = self.pdf_text_cache.pop(cache_key)
            self.pdf_text_cache[cache_key] = cached_result
            return cached_result

        info = {}
        text = ""

        try:
            with pdfplumber.open(pdf_path) as pdf:
                # 문서 전체 또는 설정된 최대 페이지 읽기
                pages_to_read = min(len(pdf.pages), self.MAX_PDF_PAGES)

                for page in pdf.pages[:pages_to_read]:
                    try:
                        page_text = page.extract_text() or ""
                        if page_text:
                            text += page_text + "\n"
                            # 충분한 텍스트가 추출되면 중단
                            if len(text) > self.MAX_TEXT_LENGTH:
                                break
                    except Exception:
                        continue

            # 텍스트가 없으면 OCR 시도
            if not text and self.ocr_processor:
                try:
                    text = self.ocr_processor.process_pdf(pdf_path)
                except Exception as e:
                    logger.debug(f"OCR failed for {pdf_path}: {e}")

            if text:
                info['text'] = text[:self.MAX_TEXT_LENGTH]
                info['length'] = len(text)

                # 메타데이터 추출
                metadata = self._extract_metadata_from_text(text)
                info.update(metadata)

                # 파일명에서 정보 추출
                filename_info = self._extract_info_from_filename(pdf_path.name)
                info.update(filename_info)

        except Exception as e:
            logger.error(f"Error extracting PDF text from {pdf_path}: {e}")
            return {}

        # 캐시에 저장
        if use_cache:
            if len(self.pdf_text_cache) >= self.MAX_PDF_CACHE:
                # 가장 오래된 항목 제거
                self.pdf_text_cache.popitem(last=False)
            self.pdf_text_cache[cache_key] = info

        return info

    def extract_pdf_text_with_retry(self, pdf_path: Path, max_retries: int = 3) -> Dict[str, Any]:
        """재시도 로직이 포함된 PDF 텍스트 추출"""

        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                return self.extract_pdf_text(pdf_path)
            except Exception as e:
                last_error = e
                retry_count += 1
                time.sleep(0.5 * retry_count)  # 점진적 대기

                if retry_count < max_retries:
                    logger.debug(f"Retrying PDF extraction ({retry_count}/{max_retries}): {pdf_path}")

        logger.error(f"Failed to extract PDF after {max_retries} retries: {last_error}")
        return {}

    def extract_txt_content(self, txt_path: Path) -> Dict[str, Any]:
        """TXT 파일에서 내용 추출"""

        info = {}

        try:
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()

            if text:
                info['text'] = text[:self.MAX_TEXT_LENGTH]
                info['length'] = len(text)

                # 메타데이터 추출
                metadata = self._extract_metadata_from_text(text)
                info.update(metadata)

        except Exception as e:
            logger.error(f"Error reading TXT file {txt_path}: {e}")

        return info

    def process_documents_parallel(self, file_paths: List[Path],
                                 process_func=None,
                                 max_workers: int = 4) -> List[Dict]:
        """
        여러 문서를 병렬로 처리

        Args:
            file_paths: 처리할 파일 경로 리스트
            process_func: 각 파일에 적용할 함수
            max_workers: 최대 워커 수

        Returns:
            처리 결과 리스트
        """
        if not process_func:
            process_func = self.extract_pdf_text

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_func, path): path
                for path in file_paths
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing document: {e}")

        return results

    def optimize_context(self, text: str, query: str, max_length: int = 3000) -> str:
        """
        쿼리에 맞게 텍스트 컨텍스트 최적화

        Args:
            text: 원본 텍스트
            query: 검색 쿼리
            max_length: 최대 컨텍스트 길이

        Returns:
            최적화된 텍스트
        """
        if len(text) <= max_length:
            return text

        # 쿼리 키워드 추출
        keywords = query.lower().split()

        # 키워드가 포함된 문장 우선 선택
        sentences = text.split('.')
        relevant_sentences = []
        other_sentences = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in keywords):
                relevant_sentences.append(sentence)
            else:
                other_sentences.append(sentence)

        # 관련 문장부터 추가
        optimized = ""
        for sentence in relevant_sentences:
            if len(optimized) + len(sentence) < max_length:
                optimized += sentence + ". "
            else:
                break

        # 공간이 남으면 다른 문장도 추가
        for sentence in other_sentences:
            if len(optimized) + len(sentence) < max_length:
                optimized += sentence + ". "
            else:
                break

        return optimized.strip()

    def extract_context_window(self, text: str, keyword: str, window_size: int = 200) -> str:
        """
        키워드 주변 컨텍스트 추출

        Args:
            text: 원본 텍스트
            keyword: 검색 키워드
            window_size: 컨텍스트 창 크기 (앞뒤 글자 수)

        Returns:
            키워드 주변 텍스트
        """
        text_lower = text.lower()
        keyword_lower = keyword.lower()

        # 키워드 위치 찾기
        pos = text_lower.find(keyword_lower)

        if pos == -1:
            # 키워드가 없으면 텍스트 시작 부분 반환
            return text[:window_size * 2]

        # 시작과 끝 위치 계산
        start = max(0, pos - window_size)
        end = min(len(text), pos + len(keyword) + window_size)

        # 문장 경계 찾기 (더 자연스러운 컨텍스트를 위해)
        while start > 0 and text[start] not in '.!?\n':
            start -= 1
        while end < len(text) and text[end] not in '.!?\n':
            end += 1

        context = text[start:end].strip()

        # 말줄임표 추가
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    def _extract_metadata_from_text(self, text: str) -> Dict[str, Any]:
        """텍스트에서 메타데이터 추출"""

        metadata = {}

        # 기안자 추출
        patterns = [
            r'기안자[\s:：]*([가-힣]+)',
            r'작성자[\s:：]*([가-힣]+)',
            r'담당자[\s:：]*([가-힣]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                metadata['drafter'] = match.group(1).strip()
                break

        # 날짜 추출
        date_patterns = [
            r'기안일[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'시행일자[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)'
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['date'] = match.group(1).strip()
                break

        # 부서 추출
        dept_patterns = [
            r'부서[\s:：]*([가-힣]+팀)',
            r'([가-힣]+팀)\s*기안',
            r'([가-힣]+부)\s*'
        ]

        for pattern in dept_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['department'] = match.group(1).strip()
                break

        # 제목 추출
        title_match = re.search(r'제목[\s:：]*([^\n]+)', text)
        if title_match:
            metadata['title'] = title_match.group(1).strip()

        # 금액 추출
        amount_patterns = [
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'금액[\s:：]*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
        ]

        amounts = []
        for pattern in amount_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    amount = int(match.replace(',', ''))
                    amounts.append(amount)
                except:
                    pass

        if amounts:
            metadata['amount'] = max(amounts)  # 가장 큰 금액

        return metadata

    def _extract_info_from_filename(self, filename: str) -> Dict[str, Any]:
        """파일명에서 정보 추출"""

        info = {}

        # 날짜 추출 (2024-08-13 형식)
        date_match = re.search(r'(\d{4}[-_]\d{2}[-_]\d{2})', filename)
        if date_match:
            info['file_date'] = date_match.group(1).replace('_', '-')

        # 카테고리 추출
        if '구매' in filename:
            info['category'] = '구매'
        elif '수리' in filename or '보수' in filename:
            info['category'] = '수리'
        elif '검토' in filename:
            info['category'] = '검토'
        elif '폐기' in filename:
            info['category'] = '폐기'

        # 부서 추출
        if '중계' in filename:
            info['dept_from_filename'] = '중계'
        elif '카메라' in filename:
            info['dept_from_filename'] = '카메라'
        elif '조명' in filename:
            info['dept_from_filename'] = '조명'

        return info

    def get_document_stats(self, file_path: Path) -> Dict[str, Any]:
        """문서 통계 정보 반환"""

        stats = {
            'filename': file_path.name,
            'size': file_path.stat().st_size,
            'extension': file_path.suffix,
            'modified': file_path.stat().st_mtime
        }

        if file_path.suffix.lower() == '.pdf':
            try:
                with pdfplumber.open(file_path) as pdf:
                    stats['pages'] = len(pdf.pages)
            except:
                stats['pages'] = 0

        return stats

    def clear_cache(self):
        """문서 캐시 초기화"""
        self.pdf_text_cache.clear()
        logger.info("Document cache cleared")