"""
PDF Parallel Processor - PDF 파일 병렬 처리 모듈
여러 PDF 파일과 페이지를 동시에 처리하여 성능 향상
"""

import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber
import time
import logging
from functools import partial
import hashlib

# OCR 처리를 위한 import
try:
    from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFParallelProcessor:
    """PDF 병렬 처리 클래스"""

    def __init__(self, config_manager=None):
        """
        초기화
        Args:
            config_manager: ConfigManager 인스턴스
        """
        self.config = config_manager

        # 설정값 로드
        if self.config:
            self.max_workers = self.config.get('parallel_processing.pdf.max_workers', 4)
            self.page_chunk_size = self.config.get('parallel_processing.pdf.page_chunk_size', 5)
            self.timeout_per_file = self.config.get('parallel_processing.pdf.timeout_per_file', 30)
            self.enable_ocr = self.config.get('error_handling.fallback.enable_ocr_fallback', True)
        else:
            # 기본값
            self.max_workers = min(mp.cpu_count(), 4)
            self.page_chunk_size = 5
            self.timeout_per_file = 30
            self.enable_ocr = True

        # OCR 프로세서 초기화
        self.ocr_processor = EnhancedOCRProcessor() if OCR_AVAILABLE and self.enable_ocr else None

        # 캐시
        self.extraction_cache = {}

    def process_multiple_pdfs(self, pdf_paths: List[Path],
                            progress_callback=None) -> Dict[str, Dict]:
        """
        여러 PDF를 병렬로 처리

        Args:
            pdf_paths: PDF 파일 경로 리스트
            progress_callback: 진행 상황 콜백 함수

        Returns:
            {파일경로: {text, page_count, metadata, error}} 형태의 딕셔너리
        """
        results = {}
        total_files = len(pdf_paths)
        completed = 0

        logger.info(f"🚀 {total_files}개 PDF 파일 병렬 처리 시작 (워커: {self.max_workers})")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 각 PDF에 대한 Future 생성
            future_to_path = {
                executor.submit(self._process_single_pdf_safe, path): path
                for path in pdf_paths
            }

            # Future가 완료되면 결과 수집
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result(timeout=self.timeout_per_file)
                    results[str(path)] = result
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total_files)

                    logger.debug(f"✅ 완료 ({completed}/{total_files}): {path.name}")

                except TimeoutError:
                    results[str(path)] = {
                        "error": "처리 시간 초과",
                        "text": "",
                        "page_count": 0
                    }
                    logger.warning(f"⏱️ 타임아웃: {path.name}")

                except Exception as e:
                    results[str(path)] = {
                        "error": str(e),
                        "text": "",
                        "page_count": 0
                    }
                    logger.error(f"❌ 처리 실패: {path.name} - {e}")

        logger.info(f"✅ PDF 병렬 처리 완료: {completed}/{total_files} 성공")
        return results

    def _process_single_pdf_safe(self, pdf_path: Path) -> Dict:
        """
        단일 PDF 안전하게 처리 (에러 핸들링 포함)
        """
        # 캐시 확인
        cache_key = self._get_cache_key(pdf_path)
        if cache_key in self.extraction_cache:
            logger.debug(f"📋 캐시 히트: {pdf_path.name}")
            return self.extraction_cache[cache_key]

        try:
            result = self._process_single_pdf(pdf_path)
            # 캐시 저장
            self.extraction_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"PDF 처리 오류: {pdf_path.name} - {e}")
            # OCR 폴백 시도
            if self.enable_ocr and self.ocr_processor:
                return self._try_ocr_fallback(pdf_path)
            raise

    def _process_single_pdf(self, pdf_path: Path) -> Dict:
        """
        단일 PDF의 페이지들을 병렬 처리
        """
        start_time = time.time()

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

            # 페이지를 청크로 나누기
            page_chunks = [
                pdf.pages[i:i + self.page_chunk_size]
                for i in range(0, total_pages, self.page_chunk_size)
            ]

            # 청크별로 병렬 처리 (메모리 효율적)
            all_texts = []
            with ThreadPoolExecutor(max_workers=min(2, self.max_workers)) as executor:
                chunk_results = list(executor.map(
                    self._extract_chunk_text,
                    page_chunks
                ))
                all_texts = [text for text in chunk_results if text]

            # 메타데이터 추출
            metadata = self._extract_metadata(pdf)

            processing_time = time.time() - start_time

            result = {
                "text": "\n\n".join(all_texts),
                "page_count": total_pages,
                "metadata": metadata,
                "processing_time": processing_time,
                "method": "pdfplumber"
            }

            logger.debug(f"📄 처리 완료: {pdf_path.name} "
                        f"({total_pages}페이지, {processing_time:.2f}초)")

            return result

    def _extract_chunk_text(self, pages) -> str:
        """
        페이지 청크에서 텍스트 추출
        """
        texts = []
        for page in pages:
            try:
                text = page.extract_text()
                if text:
                    texts.append(text.strip())
            except Exception as e:
                logger.warning(f"페이지 텍스트 추출 실패: {e}")
                continue

        return "\n".join(texts)

    def _extract_metadata(self, pdf) -> Dict:
        """
        PDF 메타데이터 추출
        """
        try:
            metadata = pdf.metadata or {}
            return {
                "title": metadata.get('Title', ''),
                "author": metadata.get('Author', ''),
                "subject": metadata.get('Subject', ''),
                "creator": metadata.get('Creator', ''),
                "producer": metadata.get('Producer', ''),
                "creation_date": str(metadata.get('CreationDate', '')),
                "modification_date": str(metadata.get('ModDate', '')),
                "pages": len(pdf.pages)
            }
        except Exception as e:
            logger.warning(f"메타데이터 추출 실패: {e}")
            return {}

    def _try_ocr_fallback(self, pdf_path: Path) -> Dict:
        """
        OCR을 사용한 폴백 처리
        """
        if not self.ocr_processor:
            return {
                "error": "OCR 프로세서 사용 불가",
                "text": "",
                "page_count": 0
            }

        try:
            logger.info(f"🔍 OCR 폴백 시도: {pdf_path.name}")
            text = self.ocr_processor.process_pdf(str(pdf_path))

            return {
                "text": text,
                "page_count": 0,  # OCR에서는 정확한 페이지 수를 알기 어려움
                "metadata": {},
                "method": "ocr"
            }
        except Exception as e:
            logger.error(f"OCR 폴백 실패: {e}")
            return {
                "error": f"OCR 실패: {str(e)}",
                "text": "",
                "page_count": 0
            }

    def _get_cache_key(self, pdf_path: Path) -> str:
        """
        파일의 캐시 키 생성
        """
        stat = pdf_path.stat()
        key_string = f"{pdf_path}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def process_pages_in_parallel(self, pdf_path: Path,
                                 page_numbers: List[int]) -> Dict[int, str]:
        """
        특정 페이지들만 병렬로 처리

        Args:
            pdf_path: PDF 파일 경로
            page_numbers: 처리할 페이지 번호 리스트 (0-indexed)

        Returns:
            {페이지번호: 텍스트} 형태의 딕셔너리
        """
        results = {}

        with pdfplumber.open(pdf_path) as pdf:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 각 페이지에 대한 작업 제출
                future_to_page = {
                    executor.submit(self._extract_single_page, pdf, page_num): page_num
                    for page_num in page_numbers
                    if 0 <= page_num < len(pdf.pages)
                }

                # 결과 수집
                for future in as_completed(future_to_page):
                    page_num = future_to_page[future]
                    try:
                        text = future.result(timeout=10)
                        results[page_num] = text
                    except Exception as e:
                        logger.error(f"페이지 {page_num} 처리 실패: {e}")
                        results[page_num] = ""

        return results

    def _extract_single_page(self, pdf, page_number: int) -> str:
        """
        단일 페이지에서 텍스트 추출
        """
        try:
            page = pdf.pages[page_number]
            text = page.extract_text()
            return text.strip() if text else ""
        except Exception as e:
            logger.error(f"페이지 {page_number} 추출 실패: {e}")
            return ""

    def get_cache_stats(self) -> Dict:
        """
        캐시 통계 반환
        """
        return {
            "cache_size": len(self.extraction_cache),
            "cached_files": list(self.extraction_cache.keys())
        }

    def clear_cache(self):
        """
        캐시 초기화
        """
        self.extraction_cache.clear()
        logger.info("PDF 추출 캐시 초기화 완료")


# 유틸리티 함수
def batch_process_pdfs(pdf_paths: List[Path],
                       batch_size: int = 10,
                       config_manager=None) -> Dict[str, Dict]:
    """
    대량의 PDF를 배치로 나누어 처리

    Args:
        pdf_paths: PDF 파일 경로 리스트
        batch_size: 배치 크기
        config_manager: ConfigManager 인스턴스

    Returns:
        처리 결과 딕셔너리
    """
    processor = PDFParallelProcessor(config_manager)
    all_results = {}

    # 배치로 나누기
    for i in range(0, len(pdf_paths), batch_size):
        batch = pdf_paths[i:i + batch_size]
        logger.info(f"배치 {i//batch_size + 1} 처리 중 ({len(batch)}개 파일)")

        batch_results = processor.process_multiple_pdfs(batch)
        all_results.update(batch_results)

        # 메모리 관리를 위해 캐시 정리
        if len(processor.extraction_cache) > 50:
            processor.clear_cache()

    return all_results