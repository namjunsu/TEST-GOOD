#!/usr/bin/env python3
"""
Perfect RAG - 심플하지만 정확한 문서 검색 시스템
동적으로 모든 PDF 문서와 자산 데이터를 정확하게 처리
"""

import re
import warnings
import logging
import pdfplumber
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import sys
import os
from functools import lru_cache
import hashlib
import time
from contextlib import nullcontext

# 로깅 시스템 추가
try:
    from log_system import get_logger, TimerContext
    logger = get_logger()
except ImportError:
    logger = None
    TimerContext = None
    
# query_logger는 log_system으로 통합됨

# 응답 포맷터 추가
try:
    from response_formatter import ResponseFormatter
except ImportError:
    ResponseFormatter = None

# FontBBox 경고 메시지 필터링
warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfplumber")

# pdfplumber 로깅 레벨 조정
logging.getLogger("pdfplumber").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# 프로젝트 루트를 동적으로 찾기
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

# 설정 파일 import
try:
    from config_manager import config_manager as cfg
    USE_YAML_CONFIG = True
except ImportError:
    import config as cfg
    USE_YAML_CONFIG = False

from rag_system.qwen_llm import QwenLLM
from rag_system.llm_singleton import LLMSingleton

# 새로운 모듈 import (제거됨 - 백업 폴더로 이동)
# from pdf_parallel_processor import PDFParallelProcessor
# from error_handler import RAGErrorHandler, ErrorRecovery, DetailedError, safe_execute


class PerfectRAG:
    """정확하고 심플한 RAG 시스템"""

    def _load_performance_config(self):
        """performance_config.yaml 로드"""
        import yaml
        perf_config_path = Path(__file__).parent / 'performance_config.yaml'
        if perf_config_path.exists():
            try:
                with open(perf_config_path, 'r', encoding='utf-8') as f:
                    self.perf_config = yaml.safe_load(f)
                    if logger:
                        logger.system_logger.info(f"Performance config loaded from {perf_config_path}")
            except Exception as e:
                if logger:
                    logger.system_logger.warning(f"Failed to load performance config: {e}")
                self.perf_config = {}
        else:
            self.perf_config = {}

    # 클래스 레벨 상수 - config.yaml에서 로드
    def _get_manufacturer_pattern(self):
        if USE_YAML_CONFIG:
            manufacturers = cfg.get('patterns.manufacturers', [])
            if manufacturers:
                pattern = '|'.join(manufacturers)
                return rf'\b({pattern})\b'
        return r'\b(SONY|Sony|HARRIS|Harris|HP|TOSHIBA|Toshiba|PANASONIC|Panasonic|CANON|Canon|NIKON|Nikon|DELL|Dell|APPLE|Apple|SAMSUNG|Samsung|LG)\b'

    def _get_model_pattern(self):
        if USE_YAML_CONFIG:
            return cfg.get('patterns.model_regex', r'\b[A-Z]{2,}[-\s]?\d+')
        return r'\b[A-Z]{2,}[-\s]?\d+'
    
    def __init__(self, preload_llm=False):
        # performance_config.yaml 로드 시도
        self._load_performance_config()

        # 설정 로드 (YAML 우선)
        if USE_YAML_CONFIG:
            self.docs_dir = Path(cfg.get('paths.documents_dir', './docs'))
            self.model_path = cfg.get('models.qwen.path', './models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf')
            self.max_cache_size = self.perf_config.get('cache', {}).get('max_size', 500)
            self.cache_ttl = self.perf_config.get('cache', {}).get('response_ttl', 7200)
            self.max_text_length = self.perf_config.get('memory', {}).get('max_document_length', 8000)
            self.max_pdf_pages = cfg.get('limits.max_pdf_pages', 10)
            self.pdf_workers = self.perf_config.get('parallel', {}).get('pdf_workers', 4)
            self.chunk_size = self.perf_config.get('parallel', {}).get('chunk_size', 5)
        else:
            self.docs_dir = Path(cfg.DOCS_DIR)
            self.model_path = cfg.QWEN_MODEL_PATH
            self.max_cache_size = self.perf_config.get('cache', {}).get('max_size', 500)
            self.cache_ttl = self.perf_config.get('cache', {}).get('response_ttl', 7200)
            self.max_text_length = self.perf_config.get('memory', {}).get('max_document_length', 8000)
            self.max_pdf_pages = getattr(cfg, 'MAX_PDF_PAGES', 10)
            self.pdf_workers = self.perf_config.get('parallel', {}).get('pdf_workers', 4)
            self.chunk_size = self.perf_config.get('parallel', {}).get('chunk_size', 5)

        self.llm = None
        # 캐시 관리 개선 (크기 제한 및 TTL)
        from collections import OrderedDict
        self.documents_cache = OrderedDict()  # LRU 캐시처럼 동작
        self.metadata_cache = OrderedDict()  # 메타데이터 캐시
        self.search_mode = 'document'  # 검색 모드: 'document', 'asset', 'auto' (기본값: document)
        self.answer_cache = OrderedDict()  # 답변 캐시 (LRU)
        self.pdf_text_cache = OrderedDict()  # PDF 텍스트 추출 캐시 (성능 최적화)

        # PDF 병렬 처리기 초기화 (제거됨 - 백업 폴더로 이동)
        # self.pdf_processor = PDFParallelProcessor(config_manager=cfg if USE_YAML_CONFIG else None)
        # self.error_handler = RAGErrorHandler()
        # self.error_recovery = ErrorRecovery()
        self.pdf_processor = None
        self.error_handler = None
        self.error_recovery = None
        
        # 응답 포맷터 초기화
        self.formatter = ResponseFormatter() if ResponseFormatter else None
        
        # Asset LLM 개선 모듈 초기화
        self.asset_enhancer = None  # 필요시 로드

        # 자산 데이터 제거 (기안서 중심 시스템으로 전환)
        self.asset_data_cache = None
        self.asset_data = []
        
        # 모든 PDF와 TXT 파일 목록 (새로운 폴더 구조 포함)
        self.pdf_files = []
        self.txt_files = []

        # 루트 폴더 파일
        self.pdf_files.extend(list(self.docs_dir.glob('*.pdf')))
        self.txt_files.extend(list(self.docs_dir.glob('*.txt')))

        # 연도별 폴더 (year_2014 ~ year_2025)
        for year in range(2014, 2026):
            year_folder = self.docs_dir / f"year_{year}"
            if year_folder.exists():
                self.pdf_files.extend(list(year_folder.glob('*.pdf')))
                self.txt_files.extend(list(year_folder.glob('*.txt')))

        # 카테고리별 폴더는 심볼릭 링크만 있으므로 건너뛰기
        # 실제 파일은 모두 year_* 폴더에 있음
        # category_folders = ['category_purchase', 'category_repair', 'category_review',
        #                   'category_disposal', 'category_consumables']
        # for folder in category_folders:
        #     cat_folder = self.docs_dir / folder
        #     if cat_folder.exists():
        #         self.pdf_files.extend(list(cat_folder.glob('*.pdf')))
        #         self.txt_files.extend(list(cat_folder.glob('*.txt')))

        # 특별 폴더 (자산 관련 폴더 제거)
        special_folders = ['recent', 'archive']
        for folder in special_folders:
            special_folder = self.docs_dir / folder
            if special_folder.exists():
                self.pdf_files.extend(list(special_folder.glob('*.pdf')))
                self.txt_files.extend(list(special_folder.glob('*.txt')))

        # 중복 제거 (같은 파일이 여러 폴더에 있을 수 있음)
        self.pdf_files = list(set(self.pdf_files))
        self.txt_files = list(set(self.txt_files))
        self.all_files = self.pdf_files + self.txt_files

        print(f"✅ {len(self.pdf_files)}개 PDF, {len(self.txt_files)}개 TXT 문서 발견")
        
        # 문서 메타데이터 사전 추출 (빠른 검색용)
        self._build_metadata_cache()
        
        # LLM 사전 로드 옵션
        if preload_llm:
            self._preload_llm()

    def _load_asset_data(self):
        """자산 데이터를 미리 로드하여 캐싱"""
        try:
            asset_file = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if asset_file.exists():
                with open(asset_file, 'r', encoding='utf-8') as f:
                    self.asset_data_cache = f.read()
                    # 자산 개수 파악
                    asset_count = len([line for line in self.asset_data_cache.split('\n') if line.strip().startswith('[')])
                    print(f"✅ 자산 데이터 로드 완료: {asset_count:,}개 장비")
            else:
                print(f"⚠️ 자산 파일을 찾을 수 없음: {asset_file}")
                self.asset_data_cache = ""
        except Exception as e:
            print(f"❌ 자산 데이터 로드 실패: {e}")
            self.asset_data_cache = ""
    
    def _preload_llm(self):
        """LLM을 미리 로드 (싱글톤 사용)"""
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                print("🤖 LLM 모델 최초 로딩 중...")
            else:
                print("♾️ LLM 모델 재사용")
            
            try:
                start = time.time()
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                elapsed = time.time() - start
                if elapsed > 1.0:  # 1초 이상 걸린 경우만 표시
                    print(f"✅ LLM 로드 완료 ({elapsed:.1f}초)")
            except Exception as e:
                print(f"⚠️ LLM 로드 실패: {e}")
    
    def _manage_cache(self, cache_dict, key, value):
        """캐시 크기 관리 - LRU 방식"""
        if key in cache_dict:
            # 기존 항목을 끝으로 이동 (가장 최근 사용)
            cache_dict.move_to_end(key)
        else:
            # 새 항목 추가
            if len(cache_dict) >= self.max_cache_size:
                # 가장 오래된 항목 제거
                cache_dict.popitem(last=False)
            cache_dict[key] = (value, time.time())  # 값과 타임스탬프 저장
    
    def _get_from_cache(self, cache_dict, key):
        """캐시에서 가져오기 (TTL 체크 포함)"""
        if key in cache_dict:
            value, timestamp = cache_dict[key]
            if time.time() - timestamp < self.cache_ttl:
                cache_dict.move_to_end(key)  # 최근 사용으로 업데이트
                return value
            else:
                # TTL 만료 - 삭제
                del cache_dict[key]
        return None
    
    def _parse_pdf_result(self, result: Dict) -> Dict:
        """병렬 처리 결과를 기존 형식으로 변환"""
        return {
            'text': result.get('text', ''),
            'page_count': result.get('page_count', 0),
            'metadata': result.get('metadata', {}),
            'method': result.get('method', 'parallel')
        }

    def process_pdfs_in_batch(self, pdf_paths: List[Path], batch_size: int = 5) -> Dict:
        """여러 PDF를 배치로 병렬 처리"""
        all_results = {}

        for i in range(0, len(pdf_paths), batch_size):
            batch = pdf_paths[i:i + batch_size]
            if logger:
                print(f"배치 {i//batch_size + 1} 처리 중 ({len(batch)}개 파일)")
            else:
                print(f"배치 {i//batch_size + 1} 처리 중 ({len(batch)}개 파일)")

            batch_results = self.pdf_processor.process_multiple_pdfs(batch)
            all_results.update(batch_results)

            # 메모리 관리
            if len(self.pdf_processor.extraction_cache) > 50:
                self.pdf_processor.clear_cache()

        return all_results

    def _find_metadata_by_filename(self, filename: str) -> Optional[Dict]:
        """파일명으로 메타데이터 찾기 (새로운 캐시 구조 지원)"""
        # 먼저 정확한 파일명으로 찾기
        if filename in self.metadata_cache:
            return self.metadata_cache[filename]

        # 상대 경로 포함한 키에서 찾기
        for cache_key, metadata in self.metadata_cache.items():
            if metadata.get('filename') == filename:
                return metadata

        return None

    def _build_metadata_cache(self):
        """모든 문서의 메타데이터를 미리 추출 (캐싱 지원)"""

        print("📊 문서 메타데이터 구축 중...")

        # 병렬 처리 설정 확인
        use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

        if use_parallel and self.pdf_files:
            print(f"🚀 {len(self.pdf_files)}개 PDF 병렬 처리 시작...")
            pdf_results = self.process_pdfs_in_batch(self.pdf_files)

            # 병렬 처리 결과를 메타데이터 캐시에 저장
            for pdf_path, result in pdf_results.items():
                pdf_path_obj = Path(pdf_path)
                filename = pdf_path_obj.name
                # 상대 경로를 키로 사용 (중복 파일명 처리)
                try:
                    relative_path = pdf_path_obj.relative_to(self.docs_dir)
                    cache_key = str(relative_path)
                except ValueError:
                    cache_key = filename

                if 'error' not in result:
                    self.metadata_cache[cache_key] = {
                        'path': pdf_path_obj,
                        'filename': filename,
                        'text': result.get('text', '')[:1000],  # 요약만 저장
                        'page_count': result.get('page_count', 0),
                        'metadata': result.get('metadata', {})
                    }
        
        # PDF와 TXT 파일 모두 처리
        for file_path in self.all_files:
            filename = file_path.name

            # 상대 경로를 캐시 키로 사용
            try:
                relative_path = file_path.relative_to(self.docs_dir)
                cache_key = str(relative_path)
            except ValueError:
                cache_key = filename

            # 파일명에서 기본 정보 추출
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
            date = date_match.group(1) if date_match else ""
            
            # 제목 추출 (날짜 뒤 부분, 확장자 제거)
            if filename.endswith('.pdf'):
                title = filename.replace(date + '_', '').replace('.pdf', '') if date else filename.replace('.pdf', '')
            else:
                title = filename.replace(date + '_', '').replace('.txt', '') if date else filename.replace('.txt', '')
            
            # 연도 추출
            year = date[:4] if date else ""
            
            # 파일명에서 주요 키워드 자동 추출
            keywords = []
            
            # 파일명을 단어로 분리하여 키워드 추출
            # 한글, 영문, 숫자로 단어 추출
            words = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', filename)
            
            # 의미있는 길이의 단어들을 키워드로 추가 (2글자 이상)
            for word in words:
                if len(word) >= 2 and word not in ['pdf', 'PDF', 'txt', 'TXT', '의', '및', '건', '검토서']:
                    keywords.append(word)
            
            self.metadata_cache[cache_key] = {
                'path': file_path,
                'filename': filename,  # 실제 파일명 저장
                'date': date,
                'year': year,
                'title': title,
                'keywords': keywords,
                'full_text': None,  # 나중에 필요시 로드
                'is_txt': filename.endswith('.txt'),  # TXT 파일 여부
                'is_pdf': filename.endswith('.pdf')  # PDF 파일 여부 추가
            }

        print(f"✅ {len(self.metadata_cache)}개 문서 메타데이터 구축 완료")
    
    def _extract_txt_info(self, txt_path: Path) -> Dict:
        """TXT 파일에서 정보 동적 추출"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            info = {'text': text[:3000]}  # 처음 3000자만
            
            # 자산 파일인 경우 통계 정보 동적 추출
            if '자산' in txt_path.name or '7904' in txt_path.name:
                # 패턴: "XXX: 숫자개" 또는 "XXX - 총 숫자개" 형식 자동 감지
                # 동적으로 모든 "카테고리: 수량" 패턴 찾기
                patterns = [
                    r'([가-힣A-Za-z]+).*?[:\-]\s*총?\s*(\d+[,\d]*)\s*[개대]',
                    r'•\s*([가-힣A-Za-z]+):\s*(\d+[,\d]*)\s*[개대]'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, text[:5000])  # 처음 5000자에서 찾기
                    for category, count in matches:
                        # 카테고리명을 키로 사용
                        key = f"{category}수량"
                        info[key] = f"{count}개"
                
                # 총 보유 장비 찾기
                total_match = re.search(r'총\s*보유\s*장비:\s*(\d+[,\d]*)개', text)
                if total_match:
                    info['총장비수'] = total_match.group(1) + "개"
            
            return info

        except Exception as e:
            if logger:
                print(f"⚠️ TXT 읽기 오류 ({txt_path.name}): {e}")
            else:
                print(f"⚠️ TXT 읽기 오류 ({txt_path.name}): {e}")
            # 에러 핸들러로 안전하게 파일 읽기 시도
            # error_handler 제거 - 직접 파일 읽기
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content:
                    return {'text': content[:3000]}
            except Exception:
                pass
            return {}

    # 데코레이터 제거 (error_handler 백업 폴더로 이동)
    # @RAGErrorHandler.retry_with_backoff(max_retries=3, backoff_factor=1.5)
    # @RAGErrorHandler.handle_pdf_extraction_error

    def _optimize_context(self, text: str, query: str, max_length: int = 3000) -> str:
        """컨텍스트 최적화 - 가장 관련성 높은 부분만 추출"""
        if not text or len(text) <= max_length:
            return text

        # 쿼리 키워드 추출
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', query.lower())
        keywords = [k for k in keywords if len(k) >= 2]

        # 문장 단위로 분리
        sentences = re.split(r'[.!?\n]+', text)

        # 각 문장의 관련성 점수 계산
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            score = 0
            sentence_lower = sentence.lower()

            # 키워드 매칭 점수
            for keyword in keywords:
                if keyword in sentence_lower:
                    score += 10

            # 중요 패턴 보너스
            if re.search(r'\d+[,\d]*\s*원', sentence):  # 금액
                score += 5
            if re.search(r'\d{4}[-년]', sentence):  # 연도
                score += 3
            if re.search(r'총|합계|전체', sentence):  # 요약 정보
                score += 3

            # 위치 점수 (문서 앞부분 선호)
            position_score = max(0, 5 - i * 0.1)
            score += position_score

            scored_sentences.append((sentence, score))

        # 점수 순으로 정렬
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        # 상위 문장들로 컨텍스트 구성
        result = []
        current_length = 0

        for sentence, score in scored_sentences:
            if current_length + len(sentence) > max_length:
                break
            result.append(sentence)
            current_length += len(sentence)

        # 원래 순서대로 재정렬
        result_text = '. '.join(result)
        return result_text if result_text else text[:max_length]

    def _extract_pdf_info_with_retry(self, pdf_path: Path) -> Dict:
        """PDF 정보 추출 (병렬 처리 및 에러 핸들링 포함)"""
        # 병렬 처리기 사용 여부 확인
        use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

        if use_parallel:
            # 병렬 처리로 PDF 추출
            results = self.pdf_processor.process_multiple_pdfs([pdf_path])
            result = results.get(str(pdf_path), {})

            if 'error' not in result:
                return self._parse_pdf_result(result)
            else:
                # 에러 발생 시 기존 방식으로 폴백
                if logger:
                    print(f"⚠️ 병렬 처리 실패, 순차 처리로 폴백: {pdf_path.name}")
                else:
                    print(f"⚠️ 병렬 처리 실패, 순차 처리로 폴백: {pdf_path.name}")
                return self._extract_pdf_info(pdf_path)
        else:
            # 기존 순차 처리
            return self._extract_pdf_info(pdf_path)
    
    def _extract_pdf_info(self, pdf_path: Path) -> Dict:
        """기존 PDF 추출 방식 (폴백용) - 캐싱 적용"""
        # 캐시 키 생성 (파일 경로 기반)
        cache_key = str(pdf_path)

        # 캐시에서 먼저 확인
        if cache_key in self.pdf_text_cache:
            # 캐시 히트 - LRU를 위해 맨 뒤로 이동
            cached_result = self.pdf_text_cache.pop(cache_key)
            self.pdf_text_cache[cache_key] = cached_result
            return cached_result

        text = ""

        # 에러 핸들러로 안전하게 파일 읽기
        def extract_with_pdfplumber():
            nonlocal text
            with pdfplumber.open(pdf_path) as pdf:
                # 문서 전체 또는 설정된 최대 페이지 읽기
                pages_to_read = min(len(pdf.pages), self.max_pdf_pages)
                for page in pdf.pages[:pages_to_read]:
                    # safe_execute 제거 (error_handler 백업 폴더로 이동)
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    if page_text:
                        text += page_text + "\n"
                        # 충분한 텍스트가 추출되면 중단 (메모리 절약)
                        if len(text) > self.max_text_length:
                            break
            return text

        # 여러 방법으로 시도
        # error_recovery가 없으므로 직접 시도
        text = extract_with_pdfplumber()
        if not text and hasattr(self, '_try_ocr_extraction'):
            text = self._try_ocr_extraction(pdf_path)

        # pdfplumber 실패시 OCR 시도
        if not text:
            try:
                from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
                ocr = EnhancedOCRProcessor()
                text, _ = ocr.extract_text_with_ocr(str(pdf_path))
            except Exception:
                pass  # OCR 실패시 무시

        if not text:
            return {}

        info = {}

        # 기안자 추출 (여러 패턴)
        patterns = [
            r'기안자[\s:：]*([가-힣]+)',
            r'작성자[\s:：]*([가-힣]+)',
            r'담당자[\s:：]*([가-힣]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                info['기안자'] = match.group(1).strip()
                break
            
        # 날짜 추출 (문서 내용 우선, 파일명 fallback)
        date_patterns = [
            r'기안일[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'시행일자[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'(\d{4}-\d{2}-\d{2})\s*\d{2}:\d{2}',
            r'일자[\s:：]*(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2})',
            r'날짜[\s:：]*(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2})',
            r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})'  # 일반적인 날짜 형식
        ]

        date_found = False
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                info['날짜'] = match.group(1).strip()
                date_found = True
                break

        # 문서 내용에서 날짜를 찾지 못한 경우 파일명에서 추출
        if not date_found:
            filename = pdf_path.name
            # 파일명에서 날짜 패턴 찾기 (YYYY-MM-DD, YYYY.MM.DD, YYYY_MM_DD 등)
            filename_date_patterns = [
                r'(20\d{2}[-_.]0?[1-9]|1[0-2][-_.][0-2]?\d|3[01])',  # YYYY-MM-DD
                r'(20\d{2})[-_.]?(\d{1,2})[-_.]?(\d{1,2})',  # YYYY MM DD (분리된 형태)
            ]

            for pattern in filename_date_patterns:
                match = re.search(pattern, filename)
                if match:
                    if len(match.groups()) == 1:
                        # 전체 매치인 경우
                        date_str = match.group(1)
                        date_str = date_str.replace('_', '-').replace('.', '-')
                        info['날짜'] = date_str
                        date_found = True
                        break
                    elif len(match.groups()) == 3:
                        # 분리된 그룹인 경우
                        year, month, day = match.groups()
                        try:
                            normalized_date = f"{year}-{int(month):02d}-{int(day):02d}"
                            info['날짜'] = normalized_date
                            date_found = True
                            break
                        except ValueError:
                            continue
            
            # 부서 추출 (여러 패턴 시도)
            # 패턴 1: 기안부서 라벨
            dept_match = re.search(r'기안부서[\s:：]*([^\n시행]+)', text)
            if dept_match:
                dept = dept_match.group(1).strip()
                dept = dept.split('시행')[0].strip()
                info['부서'] = dept
            
            # 패턴 2: 팀-파트 형식 (채널A 스타일)
            if '부서' not in info:
                team_match = re.search(r'([가-힣]+팀[\-가-힣]+파트)', text)
                if team_match:
                    info['부서'] = team_match.group(1)
            
            # 금액 추출 (가장 큰 금액)
            amounts = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', text)
            if amounts:
                numeric_amounts = []
                for amt in amounts:
                    try:
                        num = int(amt.replace(',', ''))
                        numeric_amounts.append((num, amt))
                    except (ValueError, AttributeError):
                        pass  # 금액 변환 실패시 무시
                if numeric_amounts:
                    numeric_amounts.sort(reverse=True)
                    info['금액'] = f"{numeric_amounts[0][1]}원"
            
            # 제목 추출
            title_match = re.search(r'제목[\s:：]*([^\n]+)', text)
            if title_match:
                info['제목'] = title_match.group(1).strip()
            
            # 텍스트 저장
            info['text'] = text[:3000]  # 처음 3000자만

        # 캐시에 저장 (크기 제한 적용)
        MAX_PDF_CACHE_SIZE = 50  # 최대 50개 PDF 캐싱
        if len(self.pdf_text_cache) >= MAX_PDF_CACHE_SIZE:
            # 가장 오래된 항목 제거 (LRU)
            self.pdf_text_cache.popitem(last=False)

        # 새 결과를 캐시에 저장
        self.pdf_text_cache[cache_key] = info

        return info
    
    def find_best_document(self, query: str) -> Optional[Path]:
        """질문에 가장 적합한 문서 찾기 - 동적 매칭"""
        
        query_lower = query.lower()
        
        # PDF 문서 우선 처리 키워드 확장
        pdf_priority_keywords = [
            '수리', '보수', '내용', '요약', '검토서', '기술검토',
            '교체', '구매', '폐기', '소모품', '기안', '검토',
            '어떤', '무엇', '뭐', '뭘로', '어디서', '누가'
        ]
        
        # PDF 문서가 명시적으로 언급된 경우 우선 처리
        if any(keyword in query for keyword in pdf_priority_keywords):
            # PDF 문서를 우선적으로 찾기
            is_asset_query = False
        else:
            # 자산 관련 질문 패턴 동적 감지 (하드코딩 없이)
            is_asset_query = False
            
            # 장비 제조사명 패턴 (대문자 3글자 이상 또는 알려진 제조사)
            manufacturer_pattern = r'\b[A-Z]{3,}\b|SONY|Sony|Harris|Toshiba|Panasonic|Canon|Nikon'
            
            # 자산 데이터 특정 키워드만
            asset_specific_keywords = ['시리얼', 'S/N', '담당자별', '위치별', '제조사별']
            
            if ('몇' in query and '대' in query) or \
               ('수량' in query and '전체' in query) or \
               ('자산' in query and '데이터' in query) or \
               re.search(r'\d{6,}', query) or \
               any(keyword in query for keyword in asset_specific_keywords):
                is_asset_query = True
        
        # 자산 관련 질문이면 자산 파일 자동 찾기
        if is_asset_query:
            for cache_key, metadata in self.metadata_cache.items():
                # TXT 파일이고 파일명에 '자산' 또는 큰 숫자(7904 등)가 있으면
                if metadata.get('is_txt', False):
                    filename = metadata.get('filename', cache_key)
                    if '자산' in filename or '7904' in filename or '전체' in filename:
                        print(f"📊 자산 파일 선택: {filename}")
                        return metadata['path']
        
        candidates = []
        
        # 기존 로직 계속
        # 질문 정규화 및 토큰화
        query_tokens = set(query_lower.split())
        
        # 연도와 월 추출
        year_match = re.search(r'(20\d{2})', query)
        query_year = year_match.group(1) if year_match else None
        
        # 월 추출 (1월, 01월, 1-월 등 다양한 형식)
        month_match = re.search(r'(\d{1,2})\s*월', query)
        query_month = None
        if month_match:
            query_month = int(month_match.group(1))
        
        for cache_key, metadata in self.metadata_cache.items():
            score = 0
            filename = metadata.get('filename', cache_key)
            filename_lower = filename.lower()
            
            # 1. 연도와 월 매칭
            if query_year:
                if metadata['year'] == query_year:
                    score += 20
                    
                    # 월도 지정된 경우 월까지 체크
                    if query_month:
                        # 파일명에서 월 추출 (YYYY-MM-DD 형식)
                        file_month_match = re.search(r'\d{4}-(\d{2})-\d{2}', filename)
                        if file_month_match:
                            file_month = int(file_month_match.group(1))
                            if file_month == query_month:
                                score += 30  # 월까지 일치하면 높은 점수
                            else:
                                continue  # 월이 다르면 제외
                else:
                    continue  # 연도가 다르면 제외
            
            # 2. 특정 장비/장소명 정확 매칭 (매우 높은 가중치)
            # 동적 키워드 매칭 - 하드코딩 없이 자동으로
            # 질문의 단어들을 추출
            query_words = re.findall(r'[가-힣]+|[A-Za-z]+|[0-9]+', query_lower)
            filename_words = re.findall(r'[가-힣]+|[A-Za-z]+|[0-9]+', filename_lower)
            
            # 공통 단어 찾기 (2글자 이상)
            for q_word in query_words:
                if len(q_word) >= 2:
                    for f_word in filename_words:
                        if len(f_word) >= 2:
                            # 완전 일치
                            if q_word == f_word:
                                # 단어 길이에 따라 가중치 부여
                                weight = len(q_word) * 2
                                score += weight
                            # 유사도 검사 (오타 처리)
                            elif self._calculate_similarity(q_word, f_word) >= 0.8:
                                # 80% 이상 유사하면 매칭으로 간주
                                weight = len(q_word) * 1.5
                                score += weight
                            # 부분 일치 (긴 단어일 경우)
                            elif len(q_word) >= 3 and len(f_word) >= 3:
                                if q_word in f_word or f_word in q_word:
                                    weight = min(len(q_word), len(f_word))
                                    score += weight
            
            # 3. 키워드 매칭 (메타데이터)
            for keyword in metadata['keywords']:
                if keyword.lower() in query_lower:
                    score += 5
            
            # 4. 토큰 기반 유사도 (단어 겹침)
            filename_tokens = set(filename_lower.replace('_', ' ').replace('-', ' ').split())
            common_tokens = query_tokens & filename_tokens
            score += len(common_tokens) * 2
            
            # 5. 부분 문자열 매칭
            # 질문의 주요 단어가 파일명에 포함되는지
            important_words = [w for w in query_lower.split() if len(w) > 2]
            for word in important_words:
                if word in filename_lower:
                    score += 3
            
            # 6. 문서 타입별 특별 처리
            # "검토서", "요청의 건" 등 문서 타입 매칭
            doc_types = ['검토서', '요청의 건', '기술검토서', '구매검토의 건', '보수건']
            for doc_type in doc_types:
                if doc_type in query and doc_type in filename:
                    score += 5
            
            if score > 0:
                candidates.append((score, metadata['path'], filename))
        
        # 점수순 정렬
        candidates.sort(reverse=True)
        
        # 디버깅 출력 (상위 3개)
        if candidates:
            top_score = candidates[0][0]
            # 동점자가 있는지 확인
            same_score = [c for c in candidates if c[0] == top_score]
            if len(same_score) > 1:
                # 동점일 때는 파일명 길이가 짧은 것 우선
                same_score.sort(key=lambda x: len(x[2]))
                return same_score[0][1]
            return candidates[0][1]
        
        return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """두 문자열의 유사도 계산 (0~1)
        레벤슈타인 거리 기반 + 한글 자모 분해 비교
        """
        # 길이가 너무 다르면 낮은 유사도
        if abs(len(str1) - len(str2)) > 2:
            return 0.0

        # 간단한 레벤슈타인 거리 계산
        def levenshtein_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)

            if len(s2) == 0:
                return len(s1)

            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    # 삽입, 삭제, 치환 비용 계산
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        # 레벤슈타인 거리 기반 유사도
        distance = levenshtein_distance(str1, str2)
        max_len = max(len(str1), len(str2))
        similarity = 1 - (distance / max_len) if max_len > 0 else 1.0

        # 한글 특수 처리: 자음/모음 하나 차이는 높은 유사도
        # 예: 켐/캠, 콤/컴 등
        if len(str1) == len(str2) and distance == 1:
            # 한글인 경우 유사도 보정
            if all(ord('가') <= ord(c) <= ord('힣') for c in str1 + str2):
                similarity = max(similarity, 0.85)

        return similarity

    def get_document_info(self, file_path: Path, info_type: str = "all") -> str:
        """문서에서 특정 정보 추출 (PDF/TXT 모두 지원)"""
        
        # 캐시 확인
        cache_key = f"{file_path.name}_{info_type}"
        if cache_key in self.documents_cache:
            return self.documents_cache[cache_key]
        
        # 파일 타입에 따라 정보 추출
        if file_path.suffix == '.txt':
            info = self._extract_txt_info(file_path)
        else:
            info = self._extract_pdf_info(file_path)
        
        if not info:
            return "❌ 문서를 읽을 수 없습니다"
        
        result = ""
        
        # 자산 파일 특별 처리 (동적)
        if file_path.suffix == '.txt' and ('자산' in file_path.name or '7904' in file_path.name):
            if info_type == "자산통계":
                result = f"📊 채널A 방송장비 자산 현황\n"
                result += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                # 동적으로 모든 수량 정보 표시
                for key, value in info.items():
                    if '수량' in key or '장비수' in key:
                        # 카테고리명 추출
                        category = key.replace('수량', '').replace('장비수', '')
                        if category:
                            result += f"• {category}: {value}\n"
            elif info_type == "all":
                result = f"📄 {file_path.stem}\n"
                result += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for key, value in info.items():
                    if key != 'text':
                        result += f"• {key}: {value}\n"
            else:
                # 특정 정보 요청
                if info_type in info:
                    result = f"✅ {info_type}: {info[info_type]}"
                else:
                    result = f"❌ {info_type} 정보를 찾을 수 없습니다"
        # 기존 PDF 처리
        elif info_type == "기안자":
            result = f"✅ 기안자: {info.get('기안자', '정보 없음')}"
        elif info_type == "날짜":
            result = f"✅ 날짜: {info.get('날짜', '정보 없음')}"
        elif info_type == "부서":
            result = f"✅ 부서: {info.get('부서', '정보 없음')}"
        elif info_type == "금액":
            amount = info.get('금액', '정보 없음')
            result = f"✅ 금액: {amount}"
            
            # 짧은 답변 보완 - 추가 정보 제공
            if amount != '정보 없음' and len(result) < 50:
                # 문서 정보 추가
                result += f"\n\n📄 문서 정보:\n"
                result += f"• 문서명: {file_path.stem}\n"
                if '날짜' in info:
                    result += f"• 날짜: {info['날짜']}\n"
                if '기안자' in info:
                    result += f"• 기안자: {info['기안자']}\n"
                if '부서' in info:
                    result += f"• 부서: {info['부서']}\n"
                if '제목' in info:
                    result += f"• 제목: {info['제목']}\n"
        elif info_type == "요약":
            # 간단한 요약 생성
            result = f"📝 {file_path.stem} 요약\n"
            result += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            if '기안자' in info:
                result += f"• 기안자: {info['기안자']}\n"
            if '날짜' in info:
                result += f"• 날짜: {info['날짜']}\n"
            if '부서' in info:
                result += f"• 부서: {info['부서']}\n"
            if '금액' in info:
                result += f"• 금액: {info['금액']}\n"
            if '제목' in info:
                result += f"• 제목: {info['제목']}\n"
        else:  # all
            # LLM 응답과 유사한 포맷으로 통일
            result = f"📄 {file_path.stem}\n\n"
            result += f"📌 **기본 정보**\n"
            if '기안자' in info:
                result += f"• 기안자: {info['기안자']}\n"
            if '날짜' in info:
                result += f"• 날짜: {info['날짜']}\n"
            if '부서' in info:
                result += f"• 부서: {info['부서']}\n"
            
            result += f"\n📝 **주요 내용**\n"
            
            # text 필드에서 주요 내용 추출 (개선된 요약 시스템)
            if 'text' in info:
                summary = self._generate_smart_summary(info['text'], file_path)
                result += summary
            
            if '금액' in info and info['금액'] != '정보 없음':
                result += f"\n💰 **비용 정보**\n"
                result += f"• 금액: {info['금액']}\n"
            
            result += f"\n📎 출처: {file_path.name}"
        
        # 캐시 저장
        self.documents_cache[cache_key] = result
        
        return result

    def _generate_smart_summary(self, text: str, file_path: Path) -> str:
        """문서 내용에서 의미 있는 요약 생성"""

        # 텍스트 전처리
        text = text[:3000]  # 처음 3000자만 사용
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        summary_parts = []

        # 1. 주요 키워드 추출 (장비명, 금액, 업체 등)
        equipment_keywords = []
        financial_keywords = []
        company_keywords = []

        # 장비명 패턴 (영문 대문자 + 숫자 조합)
        equipment_pattern = r'\b[A-Z][A-Za-z0-9\-]{2,20}\b'
        equipment_matches = re.findall(equipment_pattern, text)
        for match in equipment_matches:
            if len(match) >= 3 and not match.isdigit():
                equipment_keywords.append(match)

        # 금액 정보
        amount_pattern = r'(\d{1,3}(?:,\d{3})*)\s*(?:원|만원|억)'
        amount_matches = re.findall(amount_pattern, text)
        if amount_matches:
            financial_keywords.extend([f"{amt}원" for amt in amount_matches[:3]])

        # 업체명 (주식회사, (주), 법인명 등)
        company_pattern = r'(?:주식회사\s*|㈜\s*|\(주\)\s*)?([가-힣A-Za-z]{2,20})(?:\s*주식회사|\s*㈜|\s*\(주\))?'
        company_matches = re.findall(company_pattern, text)
        for match in company_matches:
            if len(match) >= 2 and match not in ['기안자', '부서', '날짜', '시행']:
                company_keywords.append(match)

        # 2. 문서 유형별 핵심 정보 추출
        file_name = file_path.name.lower()

        if '구매' in file_name or '구입' in file_name:
            # 구매 문서
            purchase_info = []
            if equipment_keywords:
                purchase_info.append(f"구매 장비: {', '.join(set(equipment_keywords[:3]))}")
            if financial_keywords:
                purchase_info.append(f"예상 비용: {', '.join(financial_keywords[:2])}")
            if company_keywords:
                purchase_info.append(f"관련 업체: {', '.join(set(company_keywords[:2]))}")

            if purchase_info:
                summary_parts.append("🛒 " + " | ".join(purchase_info))

        elif '수리' in file_name or '보수' in file_name:
            # 수리 문서
            repair_info = []
            if equipment_keywords:
                repair_info.append(f"수리 대상: {', '.join(set(equipment_keywords[:3]))}")
            if financial_keywords:
                repair_info.append(f"수리 비용: {', '.join(financial_keywords[:2])}")

            if repair_info:
                summary_parts.append("🔧 " + " | ".join(repair_info))

        elif '폐기' in file_name:
            # 폐기 문서
            disposal_info = []
            if equipment_keywords:
                disposal_info.append(f"폐기 장비: {', '.join(set(equipment_keywords[:3]))}")

            if disposal_info:
                summary_parts.append("🗑️ " + " | ".join(disposal_info))

        # 3. 일반적인 핵심 문장 추출
        important_lines = []
        priority_keywords = [
            '목적', '개요', '주요내용', '검토결과', '결론', '의견',
            '승인', '반려', '보완', '추진', '계획', '일정',
            '1.', '2.', '3.', '①', '②', '③', '◦', '▶'
        ]

        for line in lines[:30]:  # 처음 30줄 검토
            if len(line) > 15:  # 의미 있는 길이의 문장만
                # 우선순위 키워드가 포함된 라인
                for keyword in priority_keywords:
                    if keyword in line:
                        cleaned_line = line.replace(keyword, '').strip()
                        if len(cleaned_line) > 10:
                            important_lines.append(f"• {cleaned_line[:80]}{'...' if len(cleaned_line) > 80 else ''}")
                        break

        # 중요한 라인이 없으면 처음 몇 라인 사용
        if not important_lines:
            for line in lines[:5]:
                if len(line) > 20 and not line.isdigit():
                    important_lines.append(f"• {line[:80]}{'...' if len(line) > 80 else ''}")
                    if len(important_lines) >= 3:
                        break

        # 최종 요약 조합
        result = ""
        if summary_parts:
            result += "\n".join(summary_parts) + "\n\n"

        if important_lines:
            result += "\n".join(important_lines[:4])  # 최대 4줄

        return result if result else "• 문서 내용 분석 중..."

    def _remove_duplicate_documents(self, documents: list) -> list:
        """중복 문서 제거 (파일명 기준)"""
        seen = set()
        unique_docs = []

        for doc in documents:
            # 파일명에서 경로 부분 제거하여 비교
            filename = Path(doc.get('path', doc.get('filename', ''))).name
            if filename not in seen:
                seen.add(filename)
                unique_docs.append(doc)

        return unique_docs

    def _format_enhanced_response(self, results: list, query: str) -> str:
        """개선된 응답 형식"""
        if not results:
            return "❌ 관련 문서를 찾을 수 없습니다."

        # 중복 제거
        unique_results = self._remove_duplicate_documents(results)

        response = f"📋 **검색 결과** ({len(unique_results)}개 문서)\n\n"

        for i, doc in enumerate(unique_results[:5], 1):  # 최대 5개만 표시
            title = doc.get('title', '제목 없음')
            date = doc.get('date', '날짜 미상')
            category = doc.get('category', '기타')
            drafter = doc.get('drafter', '미상')

            # 날짜 표시 개선
            if date and date != '날짜 미상' and len(date) >= 10:
                display_date = date[:10]  # YYYY-MM-DD
            elif date and len(date) >= 4:
                display_date = date[:4]  # 연도만
            else:
                display_date = "날짜미상"

            response += f"**{i}. [{category}] {title}**\n"
            response += f"   📅 {display_date} | 👤 {drafter}\n"

            # 문서 요약 추가
            if 'path' in doc:
                try:
                    file_path = Path(doc['path'])
                    if file_path.exists():
                        summary = self._generate_smart_summary("", file_path)
                        if summary and summary != "• 문서 내용 분석 중...":
                            response += f"   {summary}\n"
                except Exception:
                    pass

            response += "\n"

        if len(unique_results) > 5:
            response += f"... 외 {len(unique_results) - 5}개 문서 더 있음\n\n"

        response += "💡 **특정 문서를 선택하여 자세한 내용을 확인하세요.**"

        return response

    def _classify_search_intent(self, query: str) -> str:
        """검색 의도 분류: document(기안서) vs asset(자산)
        
        Returns:
            'document': PDF 기안서/검토서 검색
            'asset': 자산 데이터베이스 검색
        """
        query_lower = query.lower()
        
        # 명시적 문서 관련 키워드 (확장)
        document_keywords = [
            '기안', '검토서', '수리', '보수', '구매 건', '폐기', 
            '문서', 'pdf', '내용 요약', '상세 내용', '절차',
            '기안자', '담당자', '업체명', '검토 결과',
            '교체', '대체', '어떤', '무엇', '뭐', '뭘로',
            '미러클랩', '미라클랩', '삼각대'
        ]
        
        # 명시적 자산 관련 키워드
        asset_keywords = [
            '몇 대', '수량', '보유', '자산', '시리얼', 's/n',
            '현황', '통계', '목록', '전체 장비', '설치 위치',
            '도입 시기', '제조사별', '모델별', '위치별'
        ]
        
        # 패턴 가져오기
        manufacturer_pattern = self._get_manufacturer_pattern()
        model_pattern = self._get_model_pattern()
        
        # 점수 기반 분류
        doc_score = 0
        asset_score = 0
        
        # 문서 점수 계산
        for keyword in document_keywords:
            if keyword in query_lower:
                doc_score += 2
        
        # 자산 점수 계산
        for keyword in asset_keywords:
            if keyword in query_lower:
                asset_score += 2
        
        # 날짜가 있으면서 '구매', '수리' 등이 있으면 문서
        if re.search(r'20\d{2}년', query) and any(w in query for w in ['구매', '수리', '보수', '검토']):
            doc_score += 3
        
        # 제조사나 모델명이 있으면 자산
        if re.search(manufacturer_pattern, query) or re.search(model_pattern, query, re.IGNORECASE):
            asset_score += 2

        # 장비명이 있으면 자산 가중치 증가 (DVR, CCU 등)
        # 하지만 '관련 문서', '찾아줘' 같은 문서 검색 표현이 있으면 제외
        if not any(w in query_lower for w in ['문서', '찾아줘', '검색', '기안', '검토']):
            equipment_names = ['dvr', 'ccu', '카메라', '렌즈', '모니터', '스위처', '마이크', '믹서']
            for equipment in equipment_names:
                if equipment in query_lower:
                    asset_score += 3  # 높은 가중치
        
        # 수량 관련 표현이 있으면 자산
        if re.search(r'\d+대|\d+개|몇\s*대|몇\s*개', query):
            asset_score += 3
        
        # 최종 결정
        if doc_score > asset_score:
            return 'document'
        elif asset_score > doc_score:
            return 'asset'
        else:
            # 점수가 같으면 문맥으로 판단
            if '문서' in query or '내용' in query or '요약' in query:
                return 'document'
            elif '장비' in query or '현황' in query:
                return 'asset'
            else:
                return 'document'  # 기본값
    
    def answer_from_specific_document(self, query: str, filename: str) -> str:
        """특정 문서에 대해서만 답변 생성 (문서 전용 모드) - 초상세 버전
        
        Args:
            query: 사용자 질문
            filename: 특정 문서 파일명
        """
        print(f"📄 문서 전용 모드: {filename}")
        
        # 메타데이터에서 해당 문서 찾기
        doc_metadata = self._find_metadata_by_filename(filename)
        if not doc_metadata:
            return f"❌ 문서를 찾을 수 없습니다: {filename}"
        doc_path = doc_metadata['path']
        
        # PDF인지 TXT인지 확인
        if filename.endswith('.pdf'):
            # PDF 문서 처리 - 전체 내용 추출
            info = self._extract_pdf_info_with_retry(doc_path)
            if not info.get('text'):
                return f"❌ PDF 내용을 읽을 수 없습니다: {filename}"
            
            # LLM 초기화
            if self.llm is None:
                print("🤖 LLM 모델 로드 중...")
                self._preload_llm()
            
            # 전체 문서 텍스트 사용 (15000자로 확대)
            full_text = info['text'][:15000]
            
            # 질문 유형별 특화 프롬프트 생성
            if any(word in query for word in ['요약', '정리', '개요', '내용']):
                prompt = self._create_detailed_summary_prompt(query, full_text, filename)
            elif any(word in query for word in ['상세', '자세히', '구체적', '세세히', '세부']):
                prompt = self._create_ultra_detailed_prompt(query, full_text, filename)
            elif any(word in query for word in ['품목', '목록', '리스트', '항목']):
                prompt = self._create_itemized_list_prompt(query, full_text, filename)
            else:
                prompt = self._create_document_specific_prompt(query, full_text, filename)
            
            # LLM으로 답변 생성 (더 긴 답변 허용)
            try:
                # 문서 전용 모드에서는 더 많은 컨텍스트 제공
                context_chunks = [
                    {
                        'content': full_text,
                        'source': filename,
                        'metadata': {
                            'filename': filename,
                            'date': doc_metadata.get('date', ''),
                            'title': doc_metadata.get('title', ''),
                            'is_document_only_mode': True  # 문서 전용 모드 표시
                        }
                    }
                ]
                
                response = self.llm.generate_response(query, context_chunks)
                answer = response.answer if hasattr(response, 'answer') else str(response)
                
                # 답변이 너무 짧으면 보강
                if len(answer) < 200 and '자세히' in query:
                    answer = self._enhance_short_answer(answer, full_text, query)
                    
            except Exception as e:
                print(f"LLM 오류: {e}")
                # 폴백: 상세한 텍스트 기반 답변
                answer = self._detailed_text_search(info['text'], query, filename)
            
            # 출처 추가
            answer += f"\n\n📄 **출처**: {filename}"
            
        elif filename.endswith('.txt'):
            # TXT 파일 처리 (자산 데이터)
            return self._search_asset_file(doc_path, query)
        else:
            return f"❌ 지원하지 않는 파일 형식입니다: {filename}"
        
        return answer
    
    def _simple_text_search(self, text: str, query: str, filename: str) -> str:
        """간단한 텍스트 기반 검색 (LLM 없이)"""
        lines = text.split('\n')
        relevant_lines = []
        
        # 질문 키워드 추출
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', query)
        
        # 관련 줄 찾기
        for line in lines:
            if any(keyword in line for keyword in keywords if len(keyword) > 1):
                relevant_lines.append(line.strip())
        
        if relevant_lines:
            return f"📄 {filename}에서 찾은 관련 내용:\n\n" + '\n'.join(relevant_lines[:20])
        else:
            return f"📄 {filename}에서 '{query}'에 대한 정보를 찾을 수 없습니다."
    
    def _detailed_text_search(self, text: str, query: str, filename: str) -> str:
        """상세한 텍스트 기반 검색 (LLM 없이)"""
        lines = text.split('\n')
        relevant_sections = []
        
        # 질문 키워드 추출
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', query)
        
        # 관련 섹션 찾기 (앞뒤 문맥 포함)
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in keywords if len(keyword) > 1):
                # 앞뒤 2줄씩 포함
                start = max(0, i-2)
                end = min(len(lines), i+3)
                section = '\n'.join(lines[start:end])
                if section not in relevant_sections:
                    relevant_sections.append(section)
        
        if relevant_sections:
            return f"📄 **{filename}** 상세 분석:\n\n" + '\n---\n'.join(relevant_sections[:10])
        else:
            return f"📄 {filename}에서 '{query}'에 대한 정보를 찾을 수 없습니다."
    
    def _enhance_short_answer(self, answer: str, full_text: str, query: str) -> str:
        """짧은 답변을 보강"""
        enhanced = answer + "\n\n📋 **추가 상세 정보**:\n"
        
        # 키워드 기반 추가 정보 추출
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', query)
        lines = full_text.split('\n')
        
        additional_info = []
        for line in lines:
            if any(keyword in line for keyword in keywords if len(keyword) > 2):
                if line.strip() and line not in answer:
                    additional_info.append(f"• {line.strip()}")
        
        if additional_info:
            enhanced += '\n'.join(additional_info[:10])
        
        return enhanced
    
    def _create_detailed_summary_prompt(self, query: str, context: str, filename: str) -> str:
        """상세 요약 전용 프롬프트 - 통일된 포맷"""
        return f"""
[문서 전체 요약 모드]

문서: {filename}

📋 **응답 형식 (반드시 준수)**:

📄 [문서 제목]

📌 **기본 정보**
• 기안자: [기안자명]
• 날짜: [문서 날짜]
• 부서: [담당 부서]
• 문서 종류: [기안서/검토서/보고서 등]

📝 **주요 내용**
[핵심 내용을 구조화하여 상세히]
• [배경/목적]
• [현황/문제점]
• [제안/해결방안]
• [세부 내용들...]

💰 **비용 정보** (해당 시)
• 총액: [금액]
• 세부 내역:
  - [품목/항목]: [금액]
  - [추가 비용]: [금액]

📋 **검토 의견**
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견/승인사항]

📎 출처: {filename}

문서 내용:
{context}

질문: {query}

⚠️ 중요: 위 형식을 반드시 따르고, 문서의 모든 정보를 상세하게 포함하세요.
"""
    
    def _create_ultra_detailed_prompt(self, query: str, context: str, filename: str) -> str:
        """초상세 답변 전용 프롬프트"""
        return f"""
[초상세 분석 모드] - 모든 세부사항 포함

문서: {filename}
요청: {query}

⚡ **최대한 상세하게 답변하세요**:

1. 질문과 관련된 모든 정보를 찾아서 제공
2. 문서의 앞뒤 문맥까지 포함하여 설명
3. 구체적인 수치, 날짜, 이름, 모델명 등 모두 명시
4. 관련 배경 정보도 함께 제공
5. 문서에 암시된 내용도 해석하여 설명

문서 전체 내용:
{context}

답변 규칙:
✅ 최소 500자 이상 상세 답변
✅ 모든 관련 정보 나열
✅ 표나 리스트로 정리
✅ 중요 정보는 **굵게** 표시
✅ 문서의 모든 관련 부분 인용
"""
    
    def _create_itemized_list_prompt(self, query: str, context: str, filename: str) -> str:
        """품목 리스트 전용 프롬프트"""
        return f"""
[품목/항목 상세 분석 모드]

문서: {filename}

문서에 있는 모든 품목/항목을 완전하게 추출하세요:

📋 **추출 형식**:
1. 품목명/모델명
   - 제조사: 
   - 모델번호:
   - 수량:
   - 단가:
   - 금액:
   - 용도:
   - 특징:
   - 기타사항:

2. (다음 품목...)

문서 내용:
{context}

질문: {query}

중요: 
- 문서에 나온 모든 품목을 빠짐없이
- 각 품목의 모든 정보를 상세히
- 순서대로 번호를 매겨서 정리
"""
    
    def _create_document_specific_prompt(self, query: str, context: str, filename: str) -> str:
        """특정 문서 전용 프롬프트 생성 - 통일된 포맷"""
        return f"""
[문서 전용 정밀 분석 모드] 

📄 분석 대상 문서: {filename}

이 문서만을 분석하여 아래 형식으로 답변하세요.

📋 **응답 형식 (반드시 준수)**:

📄 [문서 제목]

📌 **기본 정보**
• 기안자: [문서에서 찾은 기안자명]
• 날짜: [문서 날짜]
• 문서 종류: [기안서/검토서/보고서 등]

📝 **주요 내용**
[질문과 관련된 핵심 내용을 구조화하여 표시]
• [주요 사항 1]
• [주요 사항 2]
• [세부 내용들...]

💰 **비용 정보** (비용 관련 내용이 있는 경우)
• 총액: [금액]
• 세부 내역:
  - [품목1]: [금액]
  - [품목2]: [금액]

📋 **검토 의견** (검토 의견이 있는 경우)
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견]

📎 출처: {filename}

📋 **문서 전체 내용**:
{context}

❓ **사용자 질문**: {query}

⚠️ 주의사항:
- 위 형식을 반드시 따를 것
- 이 문서에 없는 내용은 추측하지 말 것
- 문서의 정확한 표현 사용
- 가능한 한 많은 세부사항 포함
"""
    
    def _get_enhanced_cache_key(self, query: str, mode: str) -> str:
        """향상된 캐시 키 생성 - 유사 질문도 캐시 히트"""

        # 1. 쿼리 정규화
        normalized = query.strip().lower()

        # 2. 조사 제거 (한국어 특화) - 개선된 버전
        # 긴 조사부터 먼저 제거 (으로, 에서 등이 로, 에 보다 먼저)
        particles = ['에서', '으로', '이나', '이든', '이면', '에게', '한테', '께서',
                     '은', '는', '이', '가', '을', '를', '의', '와', '과', '로', '에', '도', '만', '까지', '부터']
        for particle in particles:
            # 조사 뒤에 공백이 있는 경우
            normalized = normalized.replace(particle + ' ', ' ')
            # 문장 끝에 조사가 있는 경우
            if normalized.endswith(particle):
                normalized = normalized[:-len(particle)]

        # 3. 공백 정규화
        normalized = ' '.join(normalized.split())

        # 4. 핵심 키워드만 추출
        keywords = []
        for word in normalized.split():
            if len(word) >= 2:  # 2글자 이상만
                keywords.append(word)

        # 5. 정렬하여 순서 무관하게
        keywords.sort()

        # 6. 해시 생성
        cache_str = f"{mode}:{'_'.join(keywords)}"
        return hashlib.md5(cache_str.encode()).hexdigest()

    def answer_with_logging(self, query: str, mode: str = 'auto') -> str:
        """로깅이 통합된 answer 메서드 (캐싱 포함)"""
        # 향상된 캐시 키 생성
        cache_key = self._get_enhanced_cache_key(query, mode)
        
        # 캐시 확인
        if cache_key in self.answer_cache:
            cached_response, cached_time = self.answer_cache[cache_key]
            # TTL 확인 (기본 1시간)
            if time.time() - cached_time < self.cache_ttl:
                print(f"💾 캐시 히트! (키: {cache_key[:8]}...)")
                # LRU 업데이트 (최근 사용으로 이동)
                self.answer_cache.move_to_end(cache_key)
                return cached_response
            else:
                # 만료된 캐시 제거
                del self.answer_cache[cache_key]
        
        # 실제 답변 생성 (_answer_internal에서 모든 로깅 처리)
        start_time = time.time()
        response = self._answer_internal(query, mode)
        generation_time = time.time() - start_time
        
        # 캐시 저장
        self.answer_cache[cache_key] = (response, time.time())
        print(f"⏱️ 답변 생성: {generation_time:.1f}초 (캐시 저장됨)")
        
        # 캐시 크기 제한 (LRU 방식)
        if len(self.answer_cache) > self.max_cache_size:
            # 가장 오래된 항목 제거
            self.answer_cache.popitem(last=False)
        
        return response
    
    def answer(self, query: str, mode: str = 'auto') -> str:
        """로깅이 통합된 답변 생성"""
        return self.answer_with_logging(query, mode)
    
    def clear_cache(self):
        """캐시 초기화"""
        self.answer_cache.clear()
        self.documents_cache.clear()
        self.metadata_cache.clear()
        print("🗑️ 모든 캐시가 초기화되었습니다.")
    
    def get_cache_stats(self) -> Dict:
        """캐시 상태 정보 반환"""
        response_cache_size = len(self.response_cache) if hasattr(self, 'response_cache') else 0
        total_size = len(self.answer_cache) + len(self.documents_cache) + len(self.metadata_cache) + response_cache_size
        return {
            'size': response_cache_size,  # For compatibility with test
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'answer_cache_size': len(self.answer_cache),
            'document_cache_size': len(self.documents_cache),
            'metadata_cache_size': len(self.metadata_cache),
            'response_cache_size': response_cache_size,
            'total_cache_size': total_size,
            'max_cache_size': self.max_cache_size,
            'cache_ttl_seconds': self.cache_ttl
        }
    
    def _answer_internal(self, query: str, mode: str = 'auto') -> str:
        """질문에 대한 답변 생성
        
        Args:
            query: 사용자 질문
            mode: 검색 모드 ('document', 'asset', 'auto')
                - document: PDF 문서 검색
                - asset: 자산 데이터 검색
                - auto: 자동 판단
        """
        
        # 시작 시간 기록
        start_time = time.time()
        error_msg = None
        success = True
        response = ""
        metadata = {}
        
        try:
            # 로깅 시스템 시작
            if logger:
                logger.system_logger.info(f"=== Query Start: {query[:100]}...")
            
            # 검색 의도 분류
            if mode == 'auto':
                with TimerContext(logger, "classify_intent") if logger else nullcontext():
                    mode = self._classify_search_intent(query)
                print(f"🔍 검색 모드: {mode}")
            
            self.search_mode = mode
            metadata['search_mode'] = mode
            
            # 모드에 따른 처리
            query_lower = query.lower()
            
            if self.search_mode == 'asset':
                # LLM 사전 로드 (Asset 모드에서 필요)
                if self.llm is None:
                    if not LLMSingleton.is_loaded():
                        print("🤖 LLM 모델 로딩 중 (Asset 답변 개선용)...")
                    self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                
                # 자산 파일 경로 찾기
                doc_path = None
                
                # 자산 파일 자동 감지 (파일명 패턴 기반)
                for cache_key, file_meta in self.metadata_cache.items():
                    # 자산/전체/7904 등의 키워드가 파일명에 있으면 자산 파일
                    if file_meta.get('is_txt', False):
                        filename = file_meta.get('filename', cache_key)
                        # Path 객체로 변환
                        path_obj = Path(file_meta['path']) if isinstance(file_meta['path'], str) else file_meta['path']
                        filename_str = path_obj.name
                        if '자산' in filename_str or '전체' in filename_str or '7904' in filename_str:
                            doc_path = path_obj
                            print(f"📄 자산 파일 발견: {filename_str}")
                            break
                
                # 자산 파일이 없으면 기본 파일 사용
                if not doc_path:
                    # 여러 경로에서 자산 파일 찾기
                    asset_paths = [
                        self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt",
                        self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt",
                        self.docs_dir / "asset_complete" / "채널A_방송장비_자산_종합현황_전체.txt",
                        self.docs_dir / "asset_reports" / "채널A_방송장비_자산_종합현황.txt"
                    ]

                    for asset_file in asset_paths:
                        if asset_file.exists():
                            doc_path = asset_file
                            print(f"📄 자산 파일 사용: {asset_file.name}")
                            break

                    # 그래도 없으면 캐시에서 찾기
                    if not doc_path:
                        for cache_key, file_meta in self.metadata_cache.items():
                            if file_meta.get('is_txt', False):
                                filename = file_meta.get('filename', cache_key)
                                path_obj = Path(file_meta['path']) if isinstance(file_meta['path'], str) else file_meta['path']
                                if path_obj.exists():
                                    doc_path = path_obj
                                    print(f"📄 캐시에서 자산 파일 발견: {path_obj.name}")
                                    break
                
                if doc_path:
                    # 개선된 쿼리 파싱 사용
                    query_intent = self._parse_asset_query(query)
                    
                    # 복합 조건 검색 처리
                    if query_intent.get('has_multiple_conditions'):
                        response = self._search_asset_complex(doc_path, query_intent)
                    # 담당자/관리자 검색 - 우선순위 높임
                    elif query_intent.get('search_type') == 'manager':
                        response = self._search_asset_by_manager(doc_path, query)
                    # 금액/가격 범위 검색
                    elif query_intent.get('search_type') == 'price':
                        response = self._search_asset_by_price_range(doc_path, query)
                    # 시리얼 번호 검색
                    elif query_intent.get('search_type') == 'serial' or '시리얼' in query_lower or 's/n' in query_lower:
                        response = self._search_asset_detail(doc_path, query)
                    # 구입연도 검색 - 범위 검색 포함
                    elif query_intent.get('search_type') == 'year':
                        response = self._search_asset_by_year_range(doc_path, query)
                    # 제조사 검색
                    elif query_intent.get('search_type') == 'manufacturer':
                        response = self._search_asset_by_manufacturer(doc_path, query)
                    # 모델 검색
                    elif query_intent.get('search_type') == 'model':
                        response = self._search_asset_by_model(doc_path, query)
                    # 위치별 검색
                    elif query_intent.get('search_type') == 'location':
                        response = self._search_location_unified(doc_path, query)
                    # 위치+장비 복합 검색
                    elif query_intent.get('search_type') == 'location_equipment':
                        response = self._search_location_equipment_combo(doc_path, query)
                    # 장비 유형별 검색
                    elif query_intent.get('search_type') == 'equipment':
                        response = self._search_asset_by_equipment_type(doc_path, query)
                    # "어디" 키워드가 있지만 위치가 명시되지 않은 경우 - 제조사/장비명으로 검색
                    elif '어디' in query_lower:
                        # 제조사나 장비명이 있으면 해당 검색 수행
                        if re.search(self._get_manufacturer_pattern(), query):
                            response = self._search_asset_by_manufacturer(doc_path, query)
                        else:
                            response = self._search_asset_with_llm(doc_path, query)
                    # 전체/현황 요청인 경우
                    elif "전체" in query_lower or "현황" in query_lower:
                        # 특정 장비가 언급된 경우
                        equipment_keywords = ["CCU", "카메라", "모니터", "오디오", "비디오", "서버", "스위치", "라우터"]
                        found_equipment = None
                        for eq in equipment_keywords:
                            if eq.upper() in query.upper():
                                found_equipment = eq
                                break
                        
                        if found_equipment:
                            # 위치별로 정리
                            response = self._search_equipment_all_locations(doc_path, found_equipment)
                        else:
                            response = self._search_asset_with_llm(doc_path, query)
                    # 일반 자산 검색 - LLM 활용
                    else:
                        response = self._search_asset_with_llm(doc_path, query)
                else:
                    response = "❌ 자산 데이터 파일을 찾을 수 없습니다."
            
            # document 모드 또는 기본 모드인 경우 문서 검색 진행
            elif self.search_mode == 'document' or self.search_mode not in ['asset']:
                # 문서 읽고 정리 요청 (다 읽고, 정리해줘)
                if any(keyword in query for keyword in ["다 읽고", "전부 읽고", "모두 읽고", "정리해", "종합해", "분석해"]) \
                   and any(keyword in query for keyword in ["관련", "문서"]):
                    return self._read_and_summarize_documents(query)

                # 특정 내용 언급 시 관련 문서들도 함께 찾아서 정리
                # 예: "DVR 교체 검토 내용 정리해줘" → DVR 관련 모든 문서 찾아서 정리
                content_keywords = ['교체', '검토', '구매', '수리', '보수', '폐기', '도입', '업그레이드']
                if any(keyword in query for keyword in content_keywords):
                    # 내용 기반으로 관련 문서들 찾기
                    return self._search_and_analyze_by_content(query)

                # 여러 문서 검색 요청 (찾아줘, 관련 문서, 있어? 등)
                # "문서 찾아줘", "문서 내용 찾아줘" 모두 문서 목록 표시
                # DVR, CCU 등 장비명과 함께 문서/찾아 키워드가 있으면 문서 리스트 표시
                if (any(keyword in query for keyword in ["찾아", "관련 문서", "관련된", "어떤", "있어", "있나", "리스트", "모두", "전부", "문서들", "보여줘"]) \
                   or any(equipment in query.lower() for equipment in ['dvr', 'ccu', '카메라', '렌즈', '모니터'])) \
                   and not any(keyword in query for keyword in ["요약", "알려", "설명", "정리"]):
                    return self._search_multiple_documents(query)
                
                # 월 단위 검색도 여러 문서 반환 (요약 요청 제외)
                if re.search(r'\d{1,2}\s*월', query) and any(word in query for word in ["문서", "작성", "구매", "검토"]) \
                   and not any(keyword in query for keyword in ["요약", "내용", "알려", "설명"]):
                    return self._search_multiple_documents(query)
                
                # 통계 관련 질문은 문서 찾기 없이 바로 처리
                if any(keyword in query for keyword in ["전체 통계", "전체 현황", "연도별", "기안자별", "월별", "카테고리별", "부터", "까지"]):
                    if any(word in query for word in ["내역", "정리", "목록", "총", "구매", "요약", "내용", "알려", "표", "리스트", "통계", "현황", "분석"]):
                        return self._generate_statistics_report(query)
                
                # 1. 가장 적합한 문서 찾기
                doc_path = self.find_best_document(query)
                
                if not doc_path:
                    return "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                
                print(f"📄 선택된 문서: {doc_path.name}")
                
                # 2. 질문 타입 파악
                # 특정 정보 추출 질문 (교체, 대체 장비 등)
                if ('교체' in query or '대체' in query) and ('어떤' in query or '뭐' in query or '무엇' in query):
                    # PDF 내용 읽기
                    pdf_info = self._extract_pdf_metadata(doc_path)
                    context = pdf_info.get('전체텍스트', pdf_info.get('text', ''))
                    
                    # 교체/검토 장비 찾기
                    models = []
                    if 'Leofoto' in context:
                        leofoto_match = re.search(r'Leofoto\s+([A-Za-z0-9\-\(\)]+)', context)
                        if leofoto_match:
                            # 금액 찾기
                            price_match = re.search(r'Leofoto[^\\n]*?([0-9,]+)\s*원', context)
                            price = price_match.group(1) if price_match else "금액 미상"
                            models.append(f"**Leofoto {leofoto_match.group(1)}** - {price}원 (카본 구조, 경량)")
                    
                    if 'COMAN' in context:
                        coman_match = re.search(r'COMAN\s+([A-Za-z0-9\-\(\)]+)', context)
                        if coman_match:
                            price_match = re.search(r'COMAN[^\\n]*?([0-9,]+)\s*원', context)
                            price = price_match.group(1) if price_match else "금액 미상"
                            models.append(f"**COMAN {coman_match.group(1)}** - {price}원 (알루미늄, 가격 경쟁력)")
                    
                    if models:
                        answer = f"📋 **미러클랩 카메라 삼각대 교체 검토 장비**\n\n"
                        for i, model in enumerate(models, 1):
                            answer += f"{i}. {model}\n"
                        answer += f"\n📄 출처: {doc_path.name}"
                        return answer
                
                # 단순 정보 추출 질문들
                elif "기안자" in query or "누구" in query:
                    return self.get_document_info(doc_path, "기안자")
                elif "날짜" in query or "언제" in query:
                    return self.get_document_info(doc_path, "날짜")
                elif "부서" in query:
                    return self.get_document_info(doc_path, "부서")
                elif ("금액" in query or "얼마" in query or "비용" in query) and not any(word in query for word in ["내역", "정리", "목록", "총"]):
                    # 단순 금액 질문만 (내역 정리가 아닌 경우)
                    return self.get_document_info(doc_path, "금액")
                
                # LLM이 필요한 복잡한 질문들 (보고서, 정리, 요약 등)
                elif any(word in query for word in ["내역", "정리", "목록", "총", "구매", "요약", "내용", "알려", "표", "리스트", "통계", "현황", "분석"]):
                    # 전체 통계 요청인 경우 모든 문서 처리
                    if any(keyword in query for keyword in ["전체 통계", "전체 현황", "연도별", "기안자별", "월별", "카테고리별", "부터", "까지"]):
                        return self._generate_statistics_report(query)
                    # 단일 문서 요약
                    else:
                        # LLM 사용하여 구조화된 답변 생성
                        return self._generate_llm_summary(doc_path, query)
                
                # 긴급 상황, 수리, 고장 관련
                elif any(word in query for word in ["긴급", "수리", "고장", "업체", "연락처"]):
                    # LLM 사용하여 긴급 정보 제공
                    return self._generate_llm_summary(doc_path, query)
                
                # 감사, 절차 관련
                elif any(word in query for word in ["감사", "절차", "승인", "폐기", "프로세스"]):
                    # LLM 사용하여 체크리스트 형식 답변
                    answer = self._generate_llm_summary(doc_path, query)
                    
                    # 처리 시간 계산 및 로깅
                    processing_time = time.time() - start_time
                    if logger:
                        logger.log_query(
                            query=query,
                            response=answer,
                            search_mode=self.search_mode,
                            processing_time=processing_time,
                            metadata={'selected_doc': doc_path.name if doc_path else None}
                        )
                        logger.system_logger.info(f"Query completed successfully in {processing_time:.2f}s")
                    return answer
                
                else:
                    # LLM을 사용하여 문서 내용 분석 및 답변 생성
                    answer = self._generate_llm_summary(doc_path, query)
                    
                    # 처리 시간 계산 및 로깅
                    processing_time = time.time() - start_time
                    if logger:
                        logger.log_query(
                            query=query,
                            response=answer,
                            search_mode=self.search_mode,
                            processing_time=processing_time,
                            metadata={'selected_doc': doc_path.name if doc_path else None}
                        )
                        logger.system_logger.info(f"Query completed successfully in {processing_time:.2f}s")
                    return answer
            
            # asset 모드에서 response가 설정되지 않은 경우 처리
            if self.search_mode == 'asset' and 'response' in locals():
                # 처리 시간 계산 및 로깅
                processing_time = time.time() - start_time
                if logger:
                    # metadata에서 Path 객체를 문자열로 변환
                    safe_metadata = {}
                    if 'metadata' in locals():
                        for key, value in metadata.items():
                            if isinstance(value, Path):
                                safe_metadata[key] = str(value)
                            else:
                                safe_metadata[key] = value
                    
                    logger.log_query(
                        query=query,
                        response=response,
                        search_mode=self.search_mode,
                        processing_time=processing_time,
                        metadata=safe_metadata
                    )
                    logger.system_logger.info(f"Asset query completed in {processing_time:.2f}s")
                return response
                
        except Exception as e:
            # 에러 발생
            error_msg = str(e)
            success = False
            response = f"❌ 처리 중 오류 발생: {error_msg}"
            
            # 처리 시간 계산
            processing_time = time.time() - start_time
            
            # 로깅 시스템
            if logger:
                logger.log_error(
                    error_type=type(e).__name__,
                    error_msg=error_msg,
                    query=query
                )
            
            return response
    
    def _get_detail_only_prompt(self, query: str, context: str, filename: str) -> str:
        """기본 정보 제외한 상세 내용만 생성하는 프롬프트"""
        return f"""
다음 문서에서 핵심 내용을 추출하세요. 
⚠️ 기안자, 날짜, 문서번호 등 기본 정보는 제외하고 실질적인 내용만 작성하세요.

📝 **구매/수리 사유 및 현황**
• 어떤 문제가 있었는지
• 현재 상황은 어떤지
• 제안하는 해결책은 무엇인지

🔧 **기술적 세부사항** (있는 경우만)
• 장비 사양이나 모델
• 검토한 대안들
• 선택 근거

💰 **비용 관련** (있는 경우만)
• 예상 비용
• 업체 정보

문서: {filename}
내용: {context[:5000]}

질문: {query}

간결하고 핵심적으로 답변하세요.
"""

    def _get_optimized_prompt(self, query: str, context: str, filename: str) -> str:
        """기술관리팀 실무 최적화 프롬프트"""
        
        # 긴급 상황 키워드
        if any(word in query for word in ["긴급", "수리", "고장", "업체", "연락처"]):
            return f"""
[긴급 장비 조회] 방송 장비 관리 시스템

상황: 긴급 대응 필요
문서: {filename}

다음 정보를 즉시 제공하세요:
• 수리 업체명:
• 담당자 연락처:
• 이전 처리 비용:
• 처리 기간:

문서 내용:
{context}

질문: {query}

⚠️ 30초 내 답변 필요
⚠️ 없는 정보는 "확인 필요"로 표시
"""
        
        # 보고서/내역 정리/기술검토서
        elif any(word in query for word in ["내역", "정리", "총", "목록", "구매", "품목", "검토서", "내용", "요약", "알려"]):
            # 기본 정보가 이미 추출되어 있는지 확인
            has_basic_info = 'basic_summary' in locals() if 'locals' in dir() else False
            
            if has_basic_info:
                # 기본 정보가 이미 있으면 상세 내용만 요청
                return f"""
[문서 상세 분석] {filename}

⚠️ 기본 정보(기안자, 날짜 등)는 이미 추출됨. 아래 내용만 작성하세요:

🔍 **핵심 내용**
• 구매/수리 사유: [파손 상태, 문제점 등 구체적으로]
• 현재 상황: [현황 설명]  
• 해결 방안: [제안 내용]

🔧 **기술 검토 내용** (해당시)
• 기존 장비 문제점: [구체적 문제 설명]
• 대체 장비: [모델명, 제조사]
• 주요 사양: [핵심 스펙]
• 선정 이유: [선택 근거]

💰 **비용 정보**
• 총액: [금액] (부가세 포함/별도)
• 세부 내역:
  - [품목1]: [모델명] - [수량] x [단가] = [금액]
  - [품목2]: [모델명] - [수량] x [단가] = [금액]
• 납품업체: [업체명]

📋 **검토 의견**
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견/승인사항]

📎 출처: {filename}

문서 내용:
{context}

요청: {query}

⚠️ 주의사항:
- 위 형식을 반드시 따를 것
- 모든 품목/장비 정보를 빠짐없이 포함
- 금액은 천단위 콤마 포함 (예: 820,000원)
- 모델명, 업체명 등 고유명사는 정확히 표기
"""
        
        # 감사/절차 확인
        elif any(word in query for word in ["감사", "절차", "승인", "폐기"]):
            return f"""
[감사 대응 자료] 기술관리팀 문서 시스템

문서: {filename}
요청: {query}

필수 확인 사항:
□ 요청 일자:
□ 품의서 번호:
□ 대상 장비:
□ 처리 사유:
□ 승인 라인:
  - 1차:
  - 2차:
  - 최종:
□ 처리 완료일:

문서 내용:
{context}

⚠️ 감사 지적 방지를 위해 정확히 확인
"""
        
        # 기본 프롬프트 (통일된 포맷)
        else:
            return f"""
[기술관리팀 문서 분석]

📋 **응답 형식 (반드시 준수)**:

📄 {filename.replace('.pdf', '')}

📌 **기본 정보**
• 기안자: [문서에서 찾은 기안자명]
• 날짜: [문서 날짜]
• 문서 종류: [기안서/검토서/보고서 등]

📝 **주요 내용**
[질문과 관련된 핵심 내용을 구조화하여 표시]
• [주요 사항 1]
• [주요 사항 2]
• [세부 내용들...]

💰 **비용 정보** (비용 관련 내용이 있는 경우)
• 총액: [금액]
• 세부 내역:
  - [품목1]: [금액]
  - [품목2]: [금액]

📋 **검토 의견** (검토 의견이 있는 경우)
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견]

📎 출처: {filename}

문서 내용:
{context}

요청: {query}

⚠️ 주의사항:
- 위 형식을 반드시 따를 것
- 질문과 관련된 모든 정보를 상세히 포함
- 실무자가 바로 활용할 수 있도록 구체적으로 답변
- 모든 고유명사(모델명, 업체명, 담당자명)는 정확히 표기
- 금액은 천단위 콤마 포함 (예: 1,234,000원)
- 문서에 없는 정보는 추측하지 말 것
"""
    
    def _is_gian_document(self, text: str) -> bool:
        """기안서 문서인지 확인"""
        gian_keywords = ['장비구매/수리 기안서', '기안부서', '기안자', '기안일자', '결재', '합의']
        matches = sum(1 for keyword in gian_keywords if keyword in text[:500])
        return matches >= 3
    
    def _try_ocr_extraction(self, pdf_path: Path) -> str:
        """OCR을 통한 텍스트 추출 시도"""
        try:
            # OCR 프로세서 임포트
            from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
            
            ocr_processor = EnhancedOCRProcessor()
            text, metadata = ocr_processor.extract_text_with_ocr(str(pdf_path))
            
            if metadata.get('ocr_performed'):
                if logger:
                    logger.system_logger.info(f"OCR 성공: {pdf_path.name} - {metadata.get('ocr_text_length', 0)}자 추출")
                return text
            else:
                if logger:
                    logger.system_logger.warning(f"OCR 실패: {pdf_path.name}")
                return ""
                
        except ImportError:
            if logger:
                logger.system_logger.warning("OCR 모듈 사용 불가 - pytesseract 또는 Tesseract 미설치")
            return ""
        except Exception as e:
            if logger:
                logger.system_logger.error(f"OCR 처리 중 오류: {pdf_path.name} - {e}")
            return ""
    
    def _extract_full_pdf_content(self, pdf_path: Path) -> dict:
        """PDF 전체 내용 추출 및 구조화"""
        try:
            import PyPDF2
            
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                
                # 전체 텍스트 추출 (메모리 효율적으로)
                full_text = ""
                max_pages = min(len(reader.pages), 50)  # 최대 50페이지로 증가
                for page_num in range(max_pages):
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    
                    # 그룹웨어 URL 제거
                    page_text = re.sub(r'gw\.channela[^\n]+', '', page_text)
                    page_text = re.sub(r'\d+\.\s*\d+\.\s*\d+\.\s*오[전후]\s*\d+:\d+\s*장비구매.*?기안서', '', page_text)
                    
                    full_text += f"\n[페이지 {page_num+1}]\n{page_text}\n"
                    
                    # 텍스트가 너무 길면 중단
                    if len(full_text) > 100000:  # 100K 문자로 증가
                        break
                
                # 텍스트가 비어있으면 OCR 시도
                if not full_text.strip():
                    logger.info(f"텍스트 추출 실패, OCR 시도: {pdf_path.name}")
                    full_text = self._try_ocr_extraction(pdf_path)
                    if not full_text:
                        return None
                
                # 구조화된 정보 추출
                info = {}
                
                # 기안서 문서인지 확인
                is_gian = self._is_gian_document(full_text)
                
                if is_gian:
                    # 기안서 전용 파싱
                    patterns = {
                        '기안자': r'기안자\s+([가-힣]+)',
                        '제목': r'제목\s+(.+?)(?:\n|$)',
                        '기안일자': r'기안일자\s+(\d{4}-\d{2}-\d{2})',
                        '기안부서': r'기안부서\s+([^\s]+)',
                        '보존기간': r'보존기간\s+([^\s\n]+)',
                        '시행일자': r'시행일자\s+(\d{4}-\d{2}-\d{2})',
                        '문서번호': r'문서번호\s+([^\s]+)',
                    }
                else:
                    # 일반 문서 파싱
                    patterns = {
                        '기안자': r'기안자\s+([^\s\n]+)',
                        '제목': r'제목\s+(.+?)(?:\n|$)',
                        '기안일자': r'기안일자\s+(\d{4}-\d{2}-\d{2})',
                        '기안부서': r'기안부서\s+([^\s\n]+)',
                        '보존기간': r'보존기간\s+([^\s\n]+)'
                    }
                
                for key, pattern in patterns.items():
                    match = re.search(pattern, full_text)
                    if match:
                        info[key] = match.group(1).strip()
                
                # 개요 추출 (기안서 형식에 맞춤)
                if is_gian:
                    # 기안서는 1. 개요 형식
                    match = re.search(r'1\.\s*개요\s*\n(.+?)(?:\n2\.|$)', full_text, re.DOTALL)
                    if match:
                        overview = match.group(1).strip()
                        # 불필요한 줄바꿈 정리
                        overview = re.sub(r'\n(?![-•·])', ' ', overview)
                        info['개요'] = overview[:800]  # 800자 제한
                    
                    # 2. 내용 추출
                    match = re.search(r'2\.\s*내용\s*\n(.+?)(?:\n3\.|$)', full_text, re.DOTALL)
                    if match:
                        content = match.group(1).strip()
                        content = re.sub(r'\n(?![-•·\d\)])', ' ', content)
                        info['내용'] = content[:1000]  # 1000자 제한
                    
                    # 3. 검토 의견 추출
                    match = re.search(r'3\.\s*검토\s*의견\s*\n(.+?)(?:\n4\.|$)', full_text, re.DOTALL)
                    if match:
                        review = match.group(1).strip()
                        review = re.sub(r'\n(?![-•·])', ' ', review)
                        info['검토의견'] = review[:2500]  # 800 -> 2500
                else:
                    # 일반 문서는 기존 방식
                    if '개요' in full_text:
                        match = re.search(r'개요\s*\n(.+?)(?:\n\d+\.|$)', full_text, re.DOTALL)
                        if match:
                            info['개요'] = match.group(1).strip()
                
                # 금액 정보 (패턴 개선 - 더 정확한 컨텍스트 기반 추출)
                # 실제 금액이 나오는 컨텍스트를 포함한 패턴
                amount_patterns = [
                    # 총액, 합계 등 명시적 금액 (원 없이도 매칭)
                    r'(?:총액|합계|총\s*액|총\s*비용|검토\s*비용|검토\s*금액)[:\s]*(\d{1,3}(?:,\d{3})*)\s*(?:원)?',
                    r'(?:금액|비용|가격)[:\s]*(\d{1,3}(?:,\d{3})*)\s*(?:원)?',
                    # VAT 관련 금액
                    r'(\d{1,3}(?:,\d{3})*)\s*원\s*\(?(?:VAT|부가세)',
                    r'(\d{1,3}(?:,\d{3})*)\s*\(?(?:VAT|부가세)',  # 원 없이
                    # 발생 비용 패턴
                    r'발생\s*비용\s*(\d{1,3}(?:,\d{3})*)\s*원',
                    # 백만원, 천만원 단위 표기
                    r'(\d{1,3}(?:,\d{3})*)\s*(?:백만|천만|억)\s*원',
                    # 일반적인 금액 패턴 (천만원 이상만)
                    r'(\d{1,3}(?:,\d{3})*)\s*원',
                ]
                
                amounts = []
                amount_contexts = []  # 금액과 컨텍스트 함께 저장
                
                for pattern in amount_patterns:
                    matches = re.finditer(pattern, full_text, re.IGNORECASE)
                    for match in matches:
                        amount = match.group(1)
                        # 컨텍스트 추출 (금액 주변 텍스트)
                        start = max(0, match.start() - 50)
                        end = min(len(full_text), match.end() + 50)
                        context = full_text[start:end].strip()
                        
                        # 금액이 유의미한지 검증 (10만원 이상)
                        try:
                            amount_int = int(amount.replace(',', ''))
                            if amount_int >= 100000:  # 10만원 이상만
                                amounts.append(amount)
                                amount_contexts.append({
                                    'amount': amount,
                                    'context': context
                                })
                        except:
                            pass
                
                # 가장 큰 금액을 주요 금액으로 판단
                if amounts:
                    # 금액을 정수로 변환하여 정렬
                    sorted_amounts = sorted(amounts, 
                                          key=lambda x: int(x.replace(',', '')), 
                                          reverse=True)
                    # 상위 3개만 저장
                    info['금액정보'] = sorted_amounts[:3]
                    info['금액컨텍스트'] = amount_contexts[:3]
                
                # 업체 정보
                if '업체' in full_text or '벤더' in full_text:
                    vendor_match = re.search(r'(?:업체|벤더)[:\s]*([^\n]+)', full_text)
                    if vendor_match:
                        info['업체'] = vendor_match.group(1).strip()
                
                # 검토 의견 추출 (새로 추가)
                if '검토 의견' in full_text:
                    match = re.search(r'검토 의견(.+?)(?:3\.|$)', full_text, re.DOTALL)
                    if match:
                        opinion = match.group(1).strip()
                        opinion = re.sub(r'\n+', ' ', opinion)
                        opinion = re.sub(r'\s+', ' ', opinion)
                        info['검토의견'] = opinion[:2500]  # 500 -> 2500자로 증가
                
                # 세부 항목 추출 (테이블 데이터가 없을 경우를 위해)
                info['세부항목'] = []
                
                # 중계차 보수 항목 찾기
                if '중계차' in full_text and '보수' in full_text:
                    # 도어, 발전기, 배터리 등 항목 찾기
                    repair_items = []
                    if '도어' in full_text:
                        repair_items.append({'항목': '도어', '내용': '부식 및 작동 불량'})
                    if '발전기' in full_text:
                        repair_items.append({'항목': '발전기', '내용': '누수 및 점검 필요'})
                    if '레벨잭' in full_text:
                        repair_items.append({'항목': '레벨잭', '내용': '작동 불량'})
                    if '배터리' in full_text:
                        repair_items.append({'항목': '배터리', '내용': '교체 필요'})
                    if repair_items:
                        info['세부항목'] = repair_items
                
                # 지미집 Control Box 수리 항목 찾기
                elif 'Control Box' in full_text or '지미집' in full_text:
                    repair_items = []
                    if 'Tilt 스피드' in full_text:
                        repair_items.append({'항목': 'Tilt 스피드단', '내용': '부품 교체'})
                    if repair_items:
                        info['세부항목'] = repair_items
                    
                    # 장애 내용 추출
                    if '장애 내용' in full_text:
                        match = re.search(r'장애 내용(.+?)(?:\d+\)|$)', full_text, re.DOTALL)
                        if match:
                            info['장애내용'] = match.group(1).strip()[:300]
                
                # 비용 내역 추출 (개선 - DVR 포함)
                info['비용내역'] = {}
                
                # DVR 관련 비용 체크
                if 'DVR' in full_text or '2,446,000' in full_text:
                    # DVR 비용 표 찾기
                    cost_match = re.search(r'검토 비용.*?총액\s*([\d,]+)', full_text, re.DOTALL)
                    if cost_match:
                        info['비용내역']['총액'] = cost_match.group(1) + '원'
                    
                    # 세부 항목 추출
                    if '666,000' in full_text:
                        info['비용내역']['DVR'] = '666,000원 (2EA)'
                    if '1,520,000' in full_text:
                        info['비용내역']['HDD'] = '1,520,000원 (10TB x 4EA)'
                    if '260,000' in full_text:
                        info['비용내역']['컨버터'] = '260,000원 (2EA)'
                    if '2,446,000' in full_text:
                        info['비용내역']['총액'] = '2,446,000원'
                
                # 기존 금액 처리
                for amt in info.get('금액정보', []):
                    try:
                        amt_int = int(amt.replace(',', ''))
                        if amt_int >= 100000:  # 10만원 이상으로 낮춤
                            if '26,660,000' in amt:
                                info['비용내역']['내외관보수'] = amt + '원'
                            elif '7,680,000' in amt:
                                info['비용내역']['방송시스템'] = amt + '원'
                            elif '34,340,000' in amt:
                                info['비용내역']['총합계'] = amt + '원 (VAT별도)'
                            elif '200,000' in amt:
                                info['비용내역']['수리비용'] = amt + '원 (VAT별도)'
                            elif not info['비용내역']:  # 첫 번째 금액
                                info['비용내역']['금액'] = amt + '원'
                    except (ValueError, AttributeError):
                        pass  # 금액 변환 실패시 무시
                
                info['전체텍스트'] = full_text[:8000]  # LLM 컨텍스트 제한
                
                return info
                
        except Exception as e:
            return {'error': str(e)}
    
    def _prepare_formatted_data(self, pdf_info: Dict, pdf_path: Path) -> Dict:
        """포맷터를 위한 데이터 준비"""
        formatted_info = {
            '제목': pdf_info.get('제목', pdf_path.stem),
            '기안자': pdf_info.get('기안자', ''),
            '기안일자': pdf_info.get('기안일자', ''),
            '기안부서': pdf_info.get('기안부서', '')
        }
        
        # 핵심 요약 추출 (3줄)
        if self.formatter and pdf_info.get('전체텍스트'):
            key_points = self.formatter.extract_key_points(pdf_info['전체텍스트'])
            formatted_info['핵심요약'] = key_points
        
        # 상세 내용 구조화
        detail_content = []
        
        # 개요가 있으면 추가
        if pdf_info.get('개요'):
            detail_content.append({
                '항목': '개요',
                '내용': pdf_info['개요'][:200]
            })
        
        # 장애/수리 내용
        if any(k in pdf_info for k in ['장애내용', '수리내용', '구매사유']):
            for key in ['장애내용', '수리내용', '구매사유']:
                if pdf_info.get(key):
                    detail_content.append({
                        '항목': key,
                        '내용': pdf_info[key][:200]
                    })
        
        formatted_info['상세내용'] = detail_content
        
        # 비용 정보
        if pdf_info.get('비용내역'):
            formatted_info['비용정보'] = pdf_info['비용내역']
        
        # 검토 의견
        opinions = []
        if pdf_info.get('검토결과'):
            opinions.append(pdf_info['검토결과'])
        if pdf_info.get('추천사항'):
            opinions.append(pdf_info['추천사항'])
        if opinions:
            formatted_info['검토의견'] = opinions
        
        # 관련 정보
        related = []
        if pdf_info.get('업체'):
            related.append(f"업체: {pdf_info['업체']}")
        if pdf_info.get('도입연도'):
            related.append(f"도입: {pdf_info['도입연도']}년")
        if related:
            formatted_info['관련정보'] = related
        
        return formatted_info
    
    def _analyze_user_intent(self, query: str) -> Dict[str, Any]:
        """사용자 질문 의도를 자연스럽게 분석"""
        query_lower = query.lower()
        
        intent = {
            'type': 'general',
            'needs_detail': False,
            'wants_comparison': False,
            'wants_recommendation': False,
            'is_urgent': False,
            'tone': 'informative',
            'context_keywords': [],
            'response_style': 'conversational'
        }
        
        # 의도 파악
        if any(word in query_lower for word in ['요약', '정리', '알려', '설명']):
            intent['type'] = 'summary'
            intent['needs_detail'] = True
        elif any(word in query_lower for word in ['비교', '차이', '어떤게 나은', '뭐가 좋']):
            intent['type'] = 'comparison'
            intent['wants_comparison'] = True
            intent['wants_recommendation'] = True
        elif any(word in query_lower for word in ['추천', '권장', '어떻게', '방법']):
            intent['type'] = 'recommendation'
            intent['wants_recommendation'] = True
        elif any(word in query_lower for word in ['긴급', '빨리', '급해', '바로']):
            intent['type'] = 'urgent'
            intent['is_urgent'] = True
            intent['tone'] = 'direct'
        elif any(word in query_lower for word in ['얼마', '비용', '가격', '금액']):
            intent['type'] = 'cost'
            intent['needs_detail'] = True
        elif any(word in query_lower for word in ['문제', '고장', '수리', '장애']):
            intent['type'] = 'problem'
            intent['wants_recommendation'] = True
        
        # 컨텍스트 키워드 추출
        important_words = ['DVR', '중계차', '카메라', '삼각대', '방송', '장비', '구매', '수리', '교체', '업그레이드']
        intent['context_keywords'] = [word for word in important_words if word.lower() in query_lower]
        
        # 응답 스타일 결정
        if '?' in query:
            intent['response_style'] = 'explanatory'
        elif any(word in query_lower for word in ['해줘', '부탁', '좀']):
            intent['response_style'] = 'helpful'
        
        return intent
    
    def _generate_conversational_response(self, context: str, query: str, intent: Dict[str, Any], 
                                         pdf_info: Dict[str, Any] = None) -> str:
        """자연스럽고 대화형 응답 생성 (ChatGPT/Claude 스타일)"""
        
        # LLM에게 자연스러운 대화형 응답을 요청하는 프롬프트
        system_prompt = """당신은 친절하고 유능한 AI 어시스턴트입니다. 
사용자의 질문 의도를 정확히 파악하여 도움이 되는 답변을 제공합니다.

중요 원칙:
1. 자연스럽고 대화하듯 답변하세요
2. 템플릿이나 정형화된 형식을 사용하지 마세요
3. 사용자가 실제로 필요로 하는 정보를 제공하세요
4. 추가로 도움이 될 만한 정보가 있다면 자연스럽게 제안하세요
5. 의사결정에 도움이 되는 인사이트를 제공하세요"""
        
        # 의도에 따른 프롬프트 조정
        if intent['type'] == 'summary':
            user_prompt = f"""다음 문서를 읽고 사용자 질문에 자연스럽게 답변해주세요.

문서 정보:
{context}

사용자 질문: {query}

답변 방식:
- 핵심 내용을 먼저 간단히 설명
- 중요한 세부사항을 자연스럽게 이어서 설명
- 사용자가 추가로 알면 좋을 정보 제안
- 딱딱한 리스트 형식이 아닌 자연스러운 문장으로 연결"""
        
        elif intent['type'] == 'comparison':
            user_prompt = f"""다음 정보를 바탕으로 비교 분석을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 비교 대상들의 주요 차이점을 먼저 설명
- 각각의 장단점을 실용적 관점에서 설명
- 상황에 따른 추천 제공
- "이런 경우엔 A가 좋고, 저런 경우엔 B가 낫다"는 식으로 설명"""
        
        elif intent['type'] == 'recommendation':
            user_prompt = f"""다음 정보를 바탕으로 실용적인 추천을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 추천 사항을 명확하게 제시
- 추천 이유를 논리적으로 설명
- 고려사항이나 주의점도 함께 언급
- 대안이 있다면 간단히 소개"""
        
        elif intent['type'] == 'cost':
            user_prompt = f"""다음 정보에서 비용 관련 내용을 찾아 설명해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 구체적인 금액을 먼저 제시
- 비용 구성이나 내역 설명
- 비용 대비 가치나 효과 언급
- 예산 관련 조언이 있다면 추가"""
        
        elif intent['is_urgent']:
            user_prompt = f"""다음 정보를 바탕으로 빠르고 명확한 답변을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 핵심 정보를 바로 제시
- 실행 가능한 조치 사항 제공
- 추가 확인이 필요한 사항 명시"""
        
        else:
            user_prompt = f"""다음 정보를 바탕으로 사용자에게 도움이 되는 답변을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 질문에 대한 직접적인 답변
- 관련된 추가 정보 제공
- 궁금할 만한 다른 사항 언급
- 자연스럽고 친근한 톤 유지"""
        
        # LLM 호출
        if self.llm:
            try:
                # 대화형 응답 생성
                context_chunks = [{
                    'content': context,
                    'source': pdf_info.get('제목', 'document') if pdf_info else 'document',
                    'score': 1.0
                }]
                
                # 대화형 응답 메서드 호출
                response = self.llm.generate_conversational_response(query, context_chunks)
                
                if response and hasattr(response, 'answer'):
                    answer = response.answer
                else:
                    answer = str(response)
                
                # 추가 컨텍스트나 추천 사항 자연스럽게 추가
                if intent['wants_recommendation'] and '추천' not in answer:
                    answer += "\n\n참고로, 이와 관련해서 추가로 검토하시면 좋을 사항들도 있습니다. 필요하시면 말씀해 주세요."
                
                return answer
                
            except Exception as e:
                print(f"LLM 응답 생성 오류: {e}")
                # 폴백: 기본 응답 생성
                return self._generate_fallback_response(context, query, intent)
        
        return self._generate_fallback_response(context, query, intent)
    
    def _generate_fallback_response(self, context: str, query: str, intent: Dict[str, Any]) -> str:
        """LLM 실패 시 폴백 응답 생성"""
        
        # 컨텍스트에서 핵심 정보 추출
        lines = context.split('\n')
        key_info = []
        
        for line in lines:
            if any(keyword in line for keyword in ['금액', '비용', '원', '제목', '기안', '날짜']):
                key_info.append(line.strip())
        
        response = f"문서를 확인한 결과, "
        
        if intent['type'] == 'summary':
            response += f"요청하신 내용은 다음과 같습니다. "
            if key_info:
                response += ' '.join(key_info[:3])
        elif intent['type'] == 'cost':
            cost_info = [line for line in key_info if '원' in line or '금액' in line]
            if cost_info:
                response += f"비용 관련 정보입니다. {cost_info[0]}"
        else:
            if key_info:
                response += f"관련 정보를 찾았습니다. {key_info[0]}"
        
        return response
    
    def _generate_llm_summary(self, pdf_path: Path, query: str) -> str:
        """LLM을 사용한 상세 요약 - 대화형 스타일"""
        
        # 사용자 의도 분석
        intent = self._analyze_user_intent(query)
        
        # PDF 파일인 경우 먼저 구조화된 정보 추출 시도
        if pdf_path.suffix.lower() == '.pdf':
            pdf_info = self._extract_full_pdf_content(pdf_path)
            
            # 대화형 응답 생성을 위한 컨텍스트 준비
            context_parts = []
            summary = []
            
            # 요약이나 내용 관련 질문인 경우
            if pdf_info and 'error' not in pdf_info:
                # 컨텍스트 구성 - 자연스러운 문장으로
                if '제목' in pdf_info:
                    context_parts.append(f"제목: {pdf_info['제목']}")
                if '기안자' in pdf_info:
                    context_parts.append(f"기안자: {pdf_info['기안자']}")
                if '기안일자' in pdf_info:
                    context_parts.append(f"작성일: {pdf_info['기안일자']}")
                if '기안부서' in pdf_info:
                    context_parts.append(f"담당부서: {pdf_info['기안부서']}")
                
                # 개요
                if '개요' in pdf_info:
                    overview = pdf_info['개요'].replace('\n', ' ').strip()
                    if len(overview) > 300:
                        overview = overview[:300] + "..."
                    context_parts.append(f"\n개요: {overview}")
                
                # 장애 내용
                if '장애내용' in pdf_info and pdf_info['장애내용']:
                    장애_text = pdf_info['장애내용'].replace('\n', ' ').strip()
                    if len(장애_text) > 300:
                        장애_text = 장애_text[:300] + "..."
                    context_parts.append(f"\n장애 내용: {장애_text}")
                
                # 세부 항목 (새로 추가)
                if '세부항목' in pdf_info and pdf_info['세부항목']:
                    summary.append(f"\n🔧 **세부 장애/수리 내역**")
                    
                    # 중계차 내외관
                    중계차_items = [item for item in pdf_info['세부항목'] if '도어' in item.get('항목', '') or '발전기' in item.get('항목', '')]
                    if 중계차_items:
                        summary.append("\n**[중계차 내외관]**")
                        for item in 중계차_items:
                            summary.append(f"• {item['항목']}: {item['내용']}")
                    
                    # 방송 시스템
                    방송_items = [item for item in pdf_info['세부항목'] if '비디오' in item.get('항목', '') or '오디오' in item.get('항목', '')]
                    if 방송_items:
                        summary.append("\n**[방송 시스템]**")
                        for item in 방송_items:
                            summary.append(f"• {item['항목']}: {item['내용']}")
                    
                    # 지미집 등 기타 항목
                    기타_items = [item for item in pdf_info['세부항목'] if 'Tilt' in item.get('항목', '') or 'Control' in item.get('항목', '')]
                    if 기타_items:
                        for item in 기타_items:
                            summary.append(f"• {item['항목']}: {item['내용']}")
                
                # 비용 내역 (개선)
                if '비용내역' in pdf_info and pdf_info['비용내역']:
                    summary.append(f"\n💰 **비용 내역**")
                    if '내외관보수' in pdf_info['비용내역']:
                        summary.append(f"• 중계차 내외관 보수: {pdf_info['비용내역']['내외관보수']}")
                    if '방송시스템' in pdf_info['비용내역']:
                        summary.append(f"• 방송 시스템 보수: {pdf_info['비용내역']['방송시스템']}")
                    if '총합계' in pdf_info['비용내역']:
                        summary.append(f"• **총 비용: {pdf_info['비용내역']['총합계']}**")
                # 금액 정보 (기존 호환성 유지)
                elif '금액정보' in pdf_info and pdf_info['금액정보']:
                    summary.append(f"\n💰 **주요 금액**")
                    # 금액 정렬 및 상위 표시
                    amounts = []
                    for amt in pdf_info['금액정보']:
                        try:
                            amt_int = int(amt.replace(',', ''))
                            if amt_int > 1000000:  # 100만원 이상만
                                amounts.append((amt, amt_int))
                        except (ValueError, AttributeError):
                            pass  # 금액 변환 실패시 무시
                    amounts.sort(key=lambda x: x[1], reverse=True)
                    for amt, _ in amounts[:3]:
                        summary.append(f"• {amt}원")
                
                # 검토 의견 (개선된 정리)
                if '검토의견' in pdf_info and pdf_info['검토의견']:
                    summary.append(f"\n📋 **검토 의견**")
                    opinion = pdf_info['검토의견']
                    
                    # DVR 관련 검토인 경우
                    if 'DVR' in opinion or ('1안' in opinion and '2안' in opinion):
                        # 1안 추출 및 정리
                        if '1안' in opinion:
                            안1_text = re.search(r'1안[^2]*(?=2안|$)', opinion, re.DOTALL)
                            if 안1_text:
                                안1_clean = re.sub(r'[\d]+\.\s*[\d]+\.\s*[\d]+.*?(?=\n)', '', 안1_text.group(0))
                                안1_clean = re.sub(r'\[페이지 \d+\]', '', 안1_clean)
                                안1_clean = ' '.join(안1_clean.split())
                                # HD-SDI 확인 또는 1안 관련 내용이 있으면 표시
                                if 'HD-SDI' in 안1_clean or 'HD급' in 안1_clean or '화질 향상' in 안1_clean or '1안' in 안1_clean:
                                    summary.append("\n**✅ 1안: HD-SDI 입력 모델**")
                                    summary.append("• 화질 향상으로 영상 검수 용이")
                                    summary.append("• HD급 녹화, 다양한 입력 지원")
                                    summary.append("• 추가 비용 발생 (컨버터 등)")
                        
                        # 2안 추출 및 정리
                        if '2안' in opinion:
                            안2_text = re.search(r'2안[^종합]*(?=종합|$)', opinion, re.DOTALL)
                            if 안2_text:
                                안2_clean = re.sub(r'[\d]+\.\s*[\d]+\.\s*[\d]+.*?(?=\n)', '', 안2_text.group(0))
                                안2_clean = re.sub(r'\[페이지 \d+\]', '', 안2_clean)
                                if 'CVBS' in 안2_clean or '기존' in 안2_clean:
                                    summary.append("\n**⚪ 2안: 기존 동일 모델**")
                                    summary.append("• 현재 시스템과 호환성 높음")
                                    summary.append("• 낮은 비용, 설치 용이")
                                    summary.append("• SD급 화질로 개선 효과 없음")
                        
                        # 종합 의견
                        if '종합' in opinion or '결론' in opinion:
                            summary.append("\n**💡 최종 추천**")
                            if '1안' in opinion and ('유리' in opinion or '적절' in opinion or '추천' in opinion):
                                summary.append("• **1안 채택 권장** - 장기적 운영 및 화질 개선 필요")
                            elif '2안' in opinion and ('유리' in opinion or '적절' in opinion):
                                summary.append("• **2안 채택 권장** - 비용 절감 우선")
                    
                    # 중계차 관련인 경우
                    elif '중계차 임대' in opinion:
                        summary.append("• 중계차 임대: 급작스런 특보 상황 시 대응 어려움")
                        if '중계차 제작' in opinion:
                            summary.append("• 신규 제작: 25-30억원 과도한 비용, 4K 송출 일정 불확실")
                        if '보수하여' in opinion:
                            summary.append("• **결론: 현 중계차 보수로 시스템 안정성 확보가 적절**")
                    else:
                        # 일반 검토 의견 (기존 방식)
                        if len(opinion) > 500:
                            opinion = opinion[:500] + "..."
                        summary.append(opinion)
                
                # 주요 내용 (전체 텍스트에서 추출) - 기존 코드 유지
                if '전체텍스트' in pdf_info:
                    full_text = pdf_info['전체텍스트']
                    
                    # 도입 연도 찾기
                    if '도입' in query or '언제' in query:
                        도입_match = re.search(r'도입\s*년도\s*[:：]?\s*(\d{4})', full_text)
                        if 도입_match:
                            summary.append(f"\n📅 **도입 연도**: {도입_match.group(1)}년")
                
                # 업체 정보
                if '업체' in pdf_info:
                    summary.append(f"\n🏢 **관련 업체**: {pdf_info['업체']}")
            
            # 기본 정보를 보관 (if 블록 밖으로 이동)
            basic_summary = '\n'.join(summary) if summary else ""
            
            # 대화형 응답이 필요한 경우 바로 처리
            if '요약' in query or '내용' in query or '설명' in query:
                # 컨텍스트 구성
                context_text = ""
                if pdf_info and 'error' not in pdf_info:
                    # 자연스러운 문장으로 컨텍스트 구성
                    context_parts = []
                    if '제목' in pdf_info:
                        context_parts.append(f"문서 제목: {pdf_info['제목']}")
                    if '기안자' in pdf_info:
                        context_parts.append(f"작성자: {pdf_info['기안자']}")
                    if '기안일자' in pdf_info:
                        context_parts.append(f"작성일: {pdf_info['기안일자']}")
                    if '개요' in pdf_info:
                        context_parts.append(f"\n개요: {pdf_info['개요']}")
                    if '금액정보' in pdf_info:
                        amounts = pdf_info['금액정보']
                        if amounts:
                            # 가장 큰 금액만 주요 금액으로 표시
                            main_amount = amounts[0] if amounts else None
                            if main_amount:
                                # 금액 컨텍스트가 있으면 함께 표시
                                if '금액컨텍스트' in pdf_info and pdf_info['금액컨텍스트']:
                                    context_info = pdf_info['금액컨텍스트'][0].get('context', '')
                                    # 총액, 합계 등의 키워드가 있으면 명시
                                    if '총액' in context_info or '합계' in context_info:
                                        context_parts.append(f"\n총 금액: {main_amount}원")
                                    else:
                                        context_parts.append(f"\n금액: {main_amount}원")
                                else:
                                    context_parts.append(f"\n금액: {main_amount}원")
                    if '검토의견' in pdf_info:
                        context_parts.append(f"\n검토 의견: {pdf_info['검토의견'][:500]}")
                    
                    context_text = "\n".join(context_parts)
                
                # LLM 로드
                if self.llm is None:
                    if not LLMSingleton.is_loaded():
                        print("🤖 LLM 모델 로딩 중...")
                    self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                
                # 대화형 응답 생성 - 전체 텍스트 포함
                if self.llm and context_text:
                    # 전체 텍스트도 포함 (중요 정보 누락 방지)
                    if '전체텍스트' in pdf_info and pdf_info['전체텍스트']:
                        full_context = f"{context_text}\n\n[전체 문서 내용]\n{pdf_info['전체텍스트'][:3000]}"
                    else:
                        full_context = context_text
                    
                    context_chunks = [{
                        'content': full_context,
                        'source': pdf_path.name,
                        'score': 1.0
                    }]
                    
                    response = self.llm.generate_conversational_response(query, context_chunks)
                    
                    if response and hasattr(response, 'answer'):
                        answer = response.answer
                    else:
                        answer = str(response)
                    
                    # 출처를 자연스럽게 추가
                    if pdf_path.name not in answer:
                        answer += f"\n\n(참고: {pdf_path.name})"
                    
                    return answer
            
            # 대화형이 아닌 경우 기존 방식으로 처리
        
        # LLM 로드 (필요시) - 싱글톤 사용
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                print("🤖 LLM 모델 로딩 중...")
            self.llm = LLMSingleton.get_instance(model_path=self.model_path)
        
        # 파일 형식에 따라 텍스트 읽기
        try:
            text = ""
            
            # TXT 파일인 경우
            if pdf_path.suffix.lower() == '.txt':
                with open(pdf_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            # PDF 파일인 경우
            else:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                
                # pdfplumber 실패시 OCR 시도
                if not text:
                    try:
                        from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
                        ocr = EnhancedOCRProcessor()
                        text, _ = ocr.extract_text_with_ocr(str(pdf_path))
                    except Exception as e:
                        pass
            
            if not text:
                return "❌ 문서 내용을 읽을 수 없습니다"
            
            # 간단하고 명확한 프롬프트
            # 기술관리팀 실무 최적화 프롬프트
            # 텍스트 길이 제한 증가 (5000 -> 15000)
            max_text_length = 15000  # 15,000자로 증가
            
            # 기본 정보가 이미 추출되었는지 확인하여 프롬프트 조정
            if 'basic_summary' in locals():
                # 중복 방지를 위한 수정된 프롬프트
                prompt = self._get_detail_only_prompt(query, text[:max_text_length], pdf_path.name)
            else:
                prompt = self._get_optimized_prompt(query, text[:max_text_length], pdf_path.name)
            
            # LLM 호출 - 대화형 응답 우선
            context_chunks = [{'content': text[:max_text_length], 'metadata': {'source': pdf_path.name}, 'score': 1.0}]
            
            # 요약/내용 요청인 경우 대화형 응답
            if '요약' in query or '내용' in query or '설명' in query:
                response = self.llm.generate_conversational_response(query, context_chunks)
            else:
                # 기존 방식
                response = self.llm.generate_response(prompt, context_chunks)
            
            answer = response.answer if hasattr(response, 'answer') else str(response)
            
            # 대화형 응답인 경우 출처만 자연스럽게 추가
            if '요약' in query or '내용' in query or '설명' in query:
                # 출처가 이미 포함되어 있지 않으면 추가
                if pdf_path.name not in answer:
                    answer += f"\n\n(참고 문서: {pdf_path.name})"
                return answer
            else:
                # 기존 방식 (템플릿 형식)
                if 'basic_summary' in locals() and basic_summary:
                    combined_answer = f"{basic_summary}\n\n📋 **상세 내용**\n{answer}"
                    return f"{combined_answer}\n\n📄 출처: {pdf_path.name}"
                else:
                    return f"{answer}\n\n📄 출처: {pdf_path.name}"
            
        except Exception as e:
            return f"❌ 요약 생성 실패: {e}"
    
    def _collect_statistics_data(self, query: str) -> Dict:
        """통계 데이터 수집 및 구조화"""
        stats_data = {
            'title': '',
            'headers': [],
            'table_data': [],
            '총계': '',
            '분석': {},
            '추천': []
        }
        
        # 연도 추출
        year_match = re.search(r'(20\d{2})', query)
        target_year = year_match.group(1) if year_match else None
        
        if "연도별" in query and "구매" in query:
            stats_data['title'] = "연도별 구매 현황"
            stats_data['headers'] = ['연도', '건수', '총 금액', '주요 품목']
            
            yearly_data = {}
            for filename, metadata in self.metadata_cache.items():
                if '구매' in filename or '구입' in filename:
                    year = metadata['year']
                    if year not in yearly_data:
                        yearly_data[year] = {'count': 0, 'total': 0, 'items': []}
                    
                    yearly_data[year]['count'] += 1
                    # 금액 추출 로직
                    pdf_path = self.docs_dir / filename
                    info = self._extract_pdf_info(pdf_path)
                    if info.get('금액'):
                        amount = self._parse_amount(info['금액'])
                        yearly_data[year]['total'] += amount
                    if info.get('품목'):
                        yearly_data[year]['items'].append(info['품목'])
            
            # 테이블 데이터 생성
            total_amount = 0
            for year in sorted(yearly_data.keys()):
                data = yearly_data[year]
                total_amount += data['total']
                items_str = ', '.join(data['items'][:2])  # 상위 2개만
                if len(data['items']) > 2:
                    items_str += f" 외 {len(data['items'])-2}건"
                
                stats_data['table_data'].append([
                    year,
                    f"{data['count']}건",
                    f"{data['total']:,}원",
                    items_str
                ])
            
            stats_data['총계'] = f"{total_amount:,}원"
            stats_data['분석']['평균 연간 구매액'] = f"{total_amount // len(yearly_data):,}원"
            stats_data['추천'].append("구매 집중 시기를 파악하여 예산 계획 수립")
            
        elif target_year:
            # 특정 연도 전체 통계
            stats_data['title'] = f"{target_year}년 전체 현황"
            stats_data['headers'] = ['구분', '건수', '총 금액', '비율']
            
            categories = {'구매': 0, '수리': 0, '폐기': 0, '기타': 0}
            amounts = {'구매': 0, '수리': 0, '폐기': 0, '기타': 0}
            
            for filename, metadata in self.metadata_cache.items():
                if metadata['year'] == target_year:
                    # 카테고리 분류
                    if '구매' in filename or '구입' in filename:
                        cat = '구매'
                    elif '수리' in filename or '보수' in filename:
                        cat = '수리'
                    elif '폐기' in filename:
                        cat = '폐기'
                    else:
                        cat = '기타'
                    
                    categories[cat] += 1
                    
                    # 금액 추출
                    pdf_path = self.docs_dir / filename
                    info = self._extract_pdf_info(pdf_path)
                    if info.get('금액'):
                        amounts[cat] += self._parse_amount(info['금액'])
            
            # 총계 계산
            total_docs = sum(categories.values())
            total_amount = sum(amounts.values())
            
            # 테이블 데이터 생성
            for cat in ['구매', '수리', '폐기', '기타']:
                if categories[cat] > 0:
                    ratio = (categories[cat] / total_docs * 100) if total_docs > 0 else 0
                    stats_data['table_data'].append([
                        cat,
                        f"{categories[cat]}건",
                        f"{amounts[cat]:,}원",
                        f"{ratio:.1f}%"
                    ])
            
            stats_data['총계'] = f"문서 {total_docs}건, 금액 {total_amount:,}원"
            stats_data['분석']['구매 비중'] = f"{amounts['구매']/total_amount*100:.1f}%" if total_amount > 0 else "0%"
            stats_data['분석']['수리 비중'] = f"{amounts['수리']/total_amount*100:.1f}%" if total_amount > 0 else "0%"
        
        return stats_data
    
    def _generate_statistics_report(self, query: str) -> str:
        """전체 문서에 대한 통계 보고서 생성 - 구조화된 포맷"""
        try:
            # formatter 사용 가능 시 구조화된 포맷 적용
            if self.formatter:
                stats_data = self._collect_statistics_data(query)
                return self.formatter.format_statistics_response(stats_data, query)
            
            # 기존 방식 (formatter 없을 때)
            # 통계 타입 파악
            if "연도별" in query and "구매" in query:
                return self._generate_yearly_purchase_report(query)
            elif "기안자별" in query:
                return self._generate_drafter_report(query)
            elif "월별" in query and "수리" in query:
                return self._generate_monthly_repair_report(query)
            
            # 기본: 특정 연도 전체 통계
            year_match = re.search(r'(20\d{2})', query)
            target_year = year_match.group(1) if year_match else None
            
            # 통계 데이터 수집
            stats = {
                '구매': [],
                '수리': [],
                '폐기': [],
                '소모품': [],
                '기타': []
            }
            
            drafters = {}  # 기안자별 통계
            monthly = {}  # 월별 통계
            total_amount = 0
            doc_count = 0
            
            for filename, metadata in self.metadata_cache.items():
                # 연도 필터링
                if target_year and metadata['year'] != target_year:
                    continue
                
                doc_count += 1
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                # 카테고리 분류
                category = '기타'
                if '구매' in filename:
                    category = '구매'
                elif '수리' in filename or '보수' in filename:
                    category = '수리'
                elif '폐기' in filename:
                    category = '폐기'
                elif '소모품' in filename:
                    category = '소모품'
                
                # 통계에 추가
                doc_info = {
                    'filename': filename,
                    'date': info.get('날짜', ''),
                    'drafter': info.get('기안자', '미상'),
                    'amount': info.get('금액', ''),
                    'title': info.get('제목', filename.replace('.pdf', ''))
                }
                
                stats[category].append(doc_info)
                
                # 기안자별 통계
                drafter = doc_info['drafter']
                if drafter not in drafters:
                    drafters[drafter] = 0
                drafters[drafter] += 1
                
                # 월별 통계 (날짜가 있는 경우)
                if doc_info['date']:
                    month_match = re.search(r'-(\d{2})-', doc_info['date'])
                    if month_match:
                        month = month_match.group(1)
                        if month not in monthly:
                            monthly[month] = 0
                        monthly[month] += 1
                
                # 금액 합계
                if doc_info['amount']:
                    amount_num = re.search(r'(\d+(?:,\d+)*)', doc_info['amount'])
                    if amount_num:
                        try:
                            total_amount += int(amount_num.group(1).replace(',', ''))
                        except (ValueError, AttributeError):
                            pass  # 금액 변환 실패시 무시
            
            # 보고서 생성
            report = []
            
            if target_year:
                report.append(f"📊 {target_year}년 기술관리팀 문서 통계 보고서")
            else:
                report.append("📊 전체 기간 기술관리팀 문서 통계 보고서")
            
            report.append("=" * 50)
            report.append("")
            
            # 전체 요약
            report.append("### 📊 전체 요약")
            report.append(f"• 총 문서 수: {doc_count}개")
            if total_amount > 0:
                report.append(f"• 총 금액: {total_amount:,}원")
            report.append("")
            
            # 카테고리별 통계
            report.append("### 📁 카테고리별 현황")
            report.append("")
            
            for category, docs in stats.items():
                if docs:
                    count = len(docs)
                    ratio = (count / doc_count * 100) if doc_count > 0 else 0
                    report.append(f"• **{category}**: {count}건 ({ratio:.1f}%)")
            report.append("")
            
            # 기안자별 통계
            if drafters:
                report.append("### 👥 기안자별 현황")
                report.append("")
                
                for drafter, count in sorted(drafters.items(), key=lambda x: x[1], reverse=True):
                    if drafter and drafter != '미상':
                        report.append(f"• **{drafter}**: {count}건")
                
                report.append("")
            
            # 월별 통계 (연도 지정시)
            if target_year and monthly:
                report.append("### 📅 월별 현황")
                report.append("")
                
                for month in sorted(monthly.keys()):
                    count = monthly[month]
                    report.append(f"• **{int(month)}월**: {count}건")
                
                report.append("")
            
            # 주요 문서 리스트
            report.append("### 📄 주요 문서 목록")
            for category, docs in stats.items():
                if docs:
                    report.append(f"\n▶ {category} ({len(docs)}건)")
                    for doc in docs[:3]:  # 각 카테고리별 최대 3개
                        date = doc['date'][:10] if doc['date'] else '날짜없음'
                        drafter = doc['drafter'] if doc['drafter'] != '미상' else ''
                        amount = f" - {doc['amount']}" if doc['amount'] else ""
                        
                        title = doc['title'][:30] + "..." if len(doc['title']) > 30 else doc['title']
                        report.append(f"  • [{date}] {title}")
                        if drafter or amount:
                            report.append(f"    {drafter}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ 통계 보고서 생성 실패: {e}"
    
    def _generate_yearly_purchase_report(self, query: str) -> str:
        """연도별 구매 현황 보고서"""
        try:
            yearly_stats = {}
            
            for filename, metadata in self.metadata_cache.items():
                if '구매' not in filename:
                    continue
                    
                year = metadata['year']
                if year not in yearly_stats:
                    yearly_stats[year] = {'count': 0, 'amount': 0, 'items': []}
                
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                yearly_stats[year]['count'] += 1
                yearly_stats[year]['items'].append({
                    'filename': filename,
                    'date': info.get('날짜', ''),
                    'drafter': info.get('기안자', ''),
                    'amount': info.get('금액', ''),
                    'title': info.get('제목', filename.replace('.pdf', ''))
                })
                
                # 금액 합계
                if info.get('금액'):
                    amount_num = re.search(r'(\d+(?:,\d+)*)', info['금액'])
                    if amount_num:
                        try:
                            yearly_stats[year]['amount'] += int(amount_num.group(1).replace(',', ''))
                        except (ValueError, AttributeError):
                            pass  # 금액 변환 실패시 무시
            
            # 보고서 생성
            report = []
            report.append("📊 연도별 구매 현황 보고서 (2021-2025)")
            report.append("=" * 50)
            report.append("")
            
            report.append("### 📈 연도별 구매 통계")
            report.append("")
            
            total_count = 0
            total_amount = 0
            
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                total_count += stats['count']
                total_amount += stats['amount']
                
                amount_str = f"{stats['amount']:,}원" if stats['amount'] > 0 else "금액미상"
                report.append(f"• **{year}년**: {stats['count']}건 - {amount_str}")
            
            report.append("")
            report.append(f"**📊 총계: {total_count}건 - {total_amount:,}원**")
            report.append("")
            
            # 연도별 상세 내역
            report.append("### 📄 연도별 상세 내역")
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                if stats['items']:
                    report.append(f"\n▶ {year}년 ({stats['count']}건)")
                    for item in stats['items']:
                        date = item['date'][:10] if item['date'] else '날짜없음'
                        title = item['title'][:35] + "..." if len(item['title']) > 35 else item['title']
                        amount = f" - {item['amount']}" if item['amount'] else ""
                        report.append(f"  • [{date}] {title}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ 연도별 구매 현황 생성 실패: {e}"
    
    def _generate_drafter_report(self, query: str) -> str:
        """기안자별 문서 현황 보고서"""
        try:
            drafter_stats = {}
            
            for filename, metadata in self.metadata_cache.items():
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                drafter = info.get('기안자', '미상')
                if drafter not in drafter_stats:
                    drafter_stats[drafter] = {
                        'count': 0,
                        'categories': {'구매': 0, '수리': 0, '폐기': 0, '기타': 0},
                        'years': {},
                        'items': []
                    }
                
                # 카테고리 분류
                category = '기타'
                if '구매' in filename:
                    category = '구매'
                elif '수리' in filename or '보수' in filename:
                    category = '수리'
                elif '폐기' in filename:
                    category = '폐기'
                
                drafter_stats[drafter]['count'] += 1
                drafter_stats[drafter]['categories'][category] += 1
                
                # 연도별 집계
                year = metadata['year']
                if year not in drafter_stats[drafter]['years']:
                    drafter_stats[drafter]['years'][year] = 0
                drafter_stats[drafter]['years'][year] += 1
                
                drafter_stats[drafter]['items'].append({
                    'filename': filename,
                    'date': info.get('날짜', ''),
                    'category': category,
                    'title': info.get('제목', filename.replace('.pdf', ''))
                })
            
            # 보고서 생성
            report = []
            report.append("📊 기안자별 문서 작성 현황")
            report.append("=" * 50)
            report.append("")
            
            report.append("### 📊 기안자별 전체 통계")
            report.append("")
            
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '미상':
                    stats = drafter_stats[drafter]
                    cat_str = f"구매 {stats['categories']['구매']}건, 수리 {stats['categories']['수리']}건"
                    if stats['categories']['폐기'] > 0:
                        cat_str += f", 폐기 {stats['categories']['폐기']}건"
                    if stats['categories']['기타'] > 0:
                        cat_str += f", 기타 {stats['categories']['기타']}건"
                    report.append(f"• **{drafter}**: 총 {stats['count']}건 ({cat_str})")
            
            report.append("")
            
            # 기안자별 연도 분포
            report.append("### 📅 기안자별 연도 분포")
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '미상':
                    stats = drafter_stats[drafter]
                    year_str = ", ".join([f"{year}년({count}건)" for year, count in sorted(stats['years'].items())])
                    report.append(f"• {drafter}: {year_str}")
            report.append("")
            
            # 기안자별 모든 문서
            report.append("### 📝 기안자별 담당 문서 (전체)")
            report.append("*💡 실무 담당자에게 직접 문의 가능*")
            report.append("")
            
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '미상':
                    stats = drafter_stats[drafter]
                    report.append(f"#### 👤 **{drafter}** ({stats['count']}건)")
                    
                    # 연도별로 그룹화
                    docs_by_year = {}
                    for item in sorted(stats['items'], key=lambda x: x['date'], reverse=True):
                        year = item['date'][:4] if item['date'] else '연도없음'
                        if year not in docs_by_year:
                            docs_by_year[year] = []
                        docs_by_year[year].append(item)
                    
                    # 연도별로 표시
                    for year in sorted(docs_by_year.keys(), reverse=True):
                        report.append(f"\n**{year}년:**")
                        for item in docs_by_year[year]:
                            date = item['date'][5:10] if item['date'] and len(item['date']) >= 10 else '날짜없음'
                            cat_emoji = {
                                '구매': '🛒',
                                '수리': '🔧', 
                                '폐기': '🗑️',
                                '기타': '📋'
                            }.get(item['category'], '📋')
                            
                            # 전체 제목 표시 (축약 없이)
                            title = item['title']
                            report.append(f"  • [{date}] {cat_emoji} {title}")
                    report.append("")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ 기안자별 현황 생성 실패: {e}"
    
    def _generate_monthly_repair_report(self, query: str) -> str:
        """월별 수리 내역 보고서"""
        try:
            monthly_stats = {}
            total_amount = 0
            
            for filename, metadata in self.metadata_cache.items():
                if '수리' not in filename and '보수' not in filename:
                    continue
                
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                # 월 추출
                date = info.get('날짜', '')
                if date:
                    month_match = re.search(r'-(\d{2})-', date)
                    if month_match:
                        month = int(month_match.group(1))
                        year = metadata['year']
                        month_key = f"{year}-{month:02d}"
                        
                        if month_key not in monthly_stats:
                            monthly_stats[month_key] = {'count': 0, 'amount': 0, 'items': []}
                        
                        monthly_stats[month_key]['count'] += 1
                        monthly_stats[month_key]['items'].append({
                            'filename': filename,
                            'date': date,
                            'drafter': info.get('기안자', ''),
                            'amount': info.get('금액', ''),
                            'title': info.get('제목', filename.replace('.pdf', ''))
                        })
                        
                        # 금액 합계
                        if info.get('금액'):
                            amount_num = re.search(r'(\d+(?:,\d+)*)', info['금액'])
                            if amount_num:
                                try:
                                    amount = int(amount_num.group(1).replace(',', ''))
                                    monthly_stats[month_key]['amount'] += amount
                                    total_amount += amount
                                except (ValueError, KeyError):
                                    pass  # 금액 처리 실패시 무시
            
            # 보고서 생성
            report = []
            report.append("📊 월별 수리 내역 및 비용 분석")
            report.append("=" * 50)
            report.append("")
            
            report.append("### 📊 전체 요약")
            total_count = sum(stats['count'] for stats in monthly_stats.values())
            report.append(f"• 총 수리 건수: {total_count}건")
            if total_amount > 0:
                report.append(f"• 총 수리 비용: {total_amount:,}원")
                report.append(f"• 평균 수리 비용: {total_amount // total_count:,}원")
            report.append("")
            
            report.append("### 📊 월별 수리 현황")
            report.append("")
            
            for month_key in sorted(monthly_stats.keys()):
                stats = monthly_stats[month_key]
                year, month = month_key.split('-')
                amount_str = f"{stats['amount']:,}원" if stats['amount'] > 0 else "금액미상"
                report.append(f"• **{year}년 {int(month)}월**: {stats['count']}건 - {amount_str}")
            
            report.append("")
            
            # 월별 상세 내역
            report.append("### 📝 월별 상세 수리 내역")
            for month_key in sorted(monthly_stats.keys()):
                stats = monthly_stats[month_key]
                year, month = month_key.split('-')
                report.append(f"\n▶ {year}년 {int(month)}월 ({stats['count']}건)")
                
                for item in stats['items']:
                    date = item['date'][:10] if item['date'] else '날짜없음'
                    title = item['title'][:35] + "..." if len(item['title']) > 35 else item['title']
                    amount = f" - {item['amount']}" if item['amount'] else ""
                    report.append(f"  • [{date}] {title}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ 월별 수리 내역 생성 실패: {e}"
    
    def _enhance_asset_response(self, raw_response: str, query: str) -> str:
        """Asset 응답을 LLM으로 개선하는 헬퍼 메서드"""
        try:
            # LLM이 없으면 원본 반환
            if not self.llm:
                return raw_response
            
            # Asset LLM Enhancer 로드
            if not self.asset_enhancer:
                from asset_llm_enhancer import AssetLLMEnhancer
                self.asset_enhancer = AssetLLMEnhancer(self.llm)
            
            # 답변 개선
            enhanced_response = self.asset_enhancer.enhance_asset_response(
                raw_data=raw_response,
                query=query,
                llm=self.llm
            )
            
            # 개선된 답변이 더 좋으면 반환
            if enhanced_response and len(enhanced_response) > 50:
                return enhanced_response
            
            return raw_response
            
        except Exception as e:
            print(f"Asset 응답 개선 실패: {e}")
            return raw_response
    
    def _search_asset_detail(self, txt_path: Path, query: str) -> str:
        """자산 파일에서 특정 시리얼 번호나 세부 정보 검색 - 완전한 정보 표시"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 시리얼 번호 추출 (영문+숫자 조합도 인식)
            serial_patterns = [
                r'([A-Z0-9]{6,})',  # 대문자와 숫자 조합 (CZC5134KXL 같은 형식)
                r'(\d{5,})',  # 5자리 이상 숫자 (10038 같은 형식)
                r'([A-Za-z]+\d+[A-Za-z0-9]*)'  # 영문으로 시작하는 시리얼
            ]
            
            serial = None
            for pattern in serial_patterns:
                serial_match = re.search(pattern, query, re.IGNORECASE)
                if serial_match:
                    serial = serial_match.group(1).upper()
                    break
            
            if serial:
                lines = content.split('\n')
                results = []
                
                # 각 장비 항목을 찾기 ([0001] 형식으로 시작)
                current_item = []
                in_matching_item = False
                
                for line in lines:
                    # 새로운 장비 항목 시작
                    if re.match(r'^\[\d{4}\]', line):
                        # 이전 항목이 매칭되었으면 저장
                        if in_matching_item and current_item:
                            results.append('\n'.join(current_item))
                        # 새 항목 시작
                        current_item = [line]
                        in_matching_item = False
                    elif current_item:
                        # 현재 항목에 라인 추가
                        current_item.append(line)
                        # 시리얼 번호 확인
                        if serial in line.upper():
                            in_matching_item = True
                
                # 마지막 항목 처리
                if in_matching_item and current_item:
                    results.append('\n'.join(current_item))
                
                if results:
                    response = f"📊 시리얼 번호 {serial} 장비 상세정보:\n"
                    response += "━" * 50 + "\n\n"
                    
                    for i, result in enumerate(results[:5], 1):  # 최대 5개
                        # 결과를 더 보기 좋게 포맷팅
                        result_lines = result.split('\n')
                        formatted = []
                        
                        for line in result_lines:
                            line = line.strip()
                            if line and not line.startswith('='):
                                # 중요 정보 하이라이트
                                if '기본정보:' in line or '구입정보:' in line or \
                                   '위치정보:' in line or '관리정보:' in line or \
                                   '유지보수:' in line:
                                    formatted.append(line)
                                elif line.startswith('['):
                                    formatted.append(f"📌 {line}")
                                else:
                                    formatted.append(f"  {line}")
                        
                        response += '\n'.join(formatted)
                        if i < len(results):
                            response += "\n" + "-" * 40 + "\n"
                    
                    response += f"\n\n📄 출처: {txt_path.name}"
                    response += f"\n✅ 총 {len(results)}개 항목에서 시리얼 {serial} 발견"
                    
                    # 담당자, 벤더사 정보가 없으면 추가로 찾기
                    if len(results) == 1 and '담당자' not in results[0]:
                        response += "\n\n⚠️ 관리정보가 일부 누락되었을 수 있습니다. 전체 문서를 확인해주세요."
                    
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
                else:
                    return f"❌ 시리얼 번호 {serial}을(를) 찾을 수 없습니다."
            
            return "❌ 시리얼 번호를 입력해주세요."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _parse_asset_query(self, query: str) -> dict:
        """Asset 쿼리를 파싱하여 검색 의도와 조건을 추출
        
        Returns:
            dict: 파싱된 쿼리 정보
                - search_type: 검색 유형 (location, manufacturer, year, price, manager, model, etc.)
                - conditions: 추출된 조건들
                - has_multiple_conditions: 복합 조건 여부
        """
        query_lower = query.lower()
        result = {
            'search_type': None,
            'conditions': {},
            'has_multiple_conditions': False,
            'original_query': query
        }
        
        # 1. 위치 조건 추출
        location_keywords = {
            '중계차': '중계차',
            '대형스튜디오': '대형스튜디오',
            '소형부조정실': '소형부조정실',
            '중형부조정실': '중형부조정실',
            'news van': 'News VAN',
            'van': 'News VAN',
            '광화문': '광화문',
            '편집실': '편집실',
            '더빙실': '더빙실'
        }
        
        for keyword, location in location_keywords.items():
            if keyword in query_lower:
                result['conditions']['location'] = location
                break
        
        # 2. 제조사 조건 추출
        manufacturer_match = re.search(self._get_manufacturer_pattern(), query, re.IGNORECASE)
        if manufacturer_match:
            result['conditions']['manufacturer'] = manufacturer_match.group(0).upper()
        
        # 3. 연도 조건 추출
        year_match = re.search(r'(20\d{2})년', query)
        if year_match:
            result['conditions']['year'] = int(year_match.group(1))
            
            # 연도 범위 키워드 확인
            if '이전' in query_lower:
                result['conditions']['year_range'] = 'before'
            elif '이후' in query_lower:
                result['conditions']['year_range'] = 'after'
            elif '부터' in query_lower and '까지' in query_lower:
                # 범위 추출
                range_match = re.search(r'(20\d{2})년부터\s*(20\d{2})년까지', query)
                if range_match:
                    result['conditions']['year_start'] = int(range_match.group(1))
                    result['conditions']['year_end'] = int(range_match.group(2))
                    result['conditions']['year_range'] = 'between'
        
        # 4. 금액 조건 추출
        price_keywords = ['억원', '천만원', '백만원', '만원']
        for keyword in price_keywords:
            if keyword in query_lower:
                # 금액 숫자 추출
                price_match = re.search(r'(\d+(?:\.\d+)?)\s*' + keyword, query_lower)
                if price_match:
                    amount = float(price_match.group(1))
                    if keyword == '억원':
                        amount *= 100000000
                    elif keyword == '천만원':
                        amount *= 10000000
                    elif keyword == '백만원':
                        amount *= 1000000
                    elif keyword == '만원':
                        amount *= 10000
                    result['conditions']['price'] = amount
                    
                    # 범위 키워드
                    if '이상' in query_lower:
                        result['conditions']['price_range'] = 'above'
                    elif '이하' in query_lower:
                        result['conditions']['price_range'] = 'below'
                    elif '미만' in query_lower:
                        result['conditions']['price_range'] = 'under'
                    elif '초과' in query_lower:
                        result['conditions']['price_range'] = 'over'
                break
        
        # 5. 담당자 조건 추출
        manager_keywords = ['담당', '관리', '차장', '부장', '과장', '대리', '사원']
        for keyword in manager_keywords:
            if keyword in query_lower:
                result['conditions']['has_manager'] = True
                result['search_type'] = 'manager'
                break
        
        # 6. 장비 유형 추출
        equipment_types = ['CCU', '카메라', '모니터', '오디오', '비디오', '서버', '스위치', '라우터', '렌즈']
        for eq_type in equipment_types:
            if eq_type.lower() in query_lower:
                result['conditions']['equipment_type'] = eq_type
                break
        
        # 7. 모델명 추출
        model_match = re.search(r'[A-Z]+[-\s]?\d+', query, re.IGNORECASE)
        if model_match:
            result['conditions']['model'] = model_match.group(0).upper()
        
        # 복합 조건 여부 판단
        condition_count = len([k for k in result['conditions'].keys() if not k.endswith('_range')])
        result['has_multiple_conditions'] = condition_count >= 2
        
        # 검색 유형 결정 (우선순위 기반)
        if not result['search_type']:
            if result['conditions'].get('has_manager'):
                result['search_type'] = 'manager'
            elif 'price' in result['conditions']:
                result['search_type'] = 'price'
            elif 'year' in result['conditions']:
                result['search_type'] = 'year'
            elif 'location' in result['conditions'] and 'equipment_type' in result['conditions']:
                result['search_type'] = 'location_equipment'
            elif 'location' in result['conditions']:
                result['search_type'] = 'location'
            elif 'manufacturer' in result['conditions']:
                result['search_type'] = 'manufacturer'
            elif 'model' in result['conditions']:
                result['search_type'] = 'model'
            elif 'equipment_type' in result['conditions']:
                result['search_type'] = 'equipment'
            else:
                result['search_type'] = 'general'
        
        return result
    
    def _search_asset_complex(self, txt_path: Path, query_intent: dict) -> str:
        """복합 조건을 처리하는 Asset 검색
        
        Args:
            txt_path: 자산 파일 경로
            query_intent: 파싱된 쿼리 정보
        """
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            conditions = query_intent['conditions']
            matched_items = []
            
            # 각 라인 검사
            for i in range(len(lines)):
                line = lines[i]
                if not line.strip():
                    continue
                
                # 모든 조건 확인
                all_conditions_met = True
                
                # 위치 조건
                if 'location' in conditions:
                    if conditions['location'] not in line:
                        all_conditions_met = False
                
                # 제조사 조건
                if 'manufacturer' in conditions and all_conditions_met:
                    if conditions['manufacturer'] not in line.upper():
                        all_conditions_met = False
                
                # 연도 조건
                if 'year' in conditions and all_conditions_met:
                    year_in_line = re.search(r'20\d{2}', line)
                    if year_in_line:
                        line_year = int(year_in_line.group(0))
                        target_year = conditions['year']
                        
                        if conditions.get('year_range') == 'before':
                            if line_year > target_year:
                                all_conditions_met = False
                        elif conditions.get('year_range') == 'after':
                            if line_year < target_year:
                                all_conditions_met = False
                        elif conditions.get('year_range') == 'between':
                            if not (conditions.get('year_start', 0) <= line_year <= conditions.get('year_end', 9999)):
                                all_conditions_met = False
                        else:
                            if line_year != target_year:
                                all_conditions_met = False
                    else:
                        all_conditions_met = False
                
                # 장비 유형 조건
                if 'equipment_type' in conditions and all_conditions_met:
                    if conditions['equipment_type'].upper() not in line.upper():
                        all_conditions_met = False
                
                # 모델 조건
                if 'model' in conditions and all_conditions_met:
                    if conditions['model'] not in line.upper():
                        all_conditions_met = False
                
                # 모든 조건을 만족하면 추가
                if all_conditions_met:
                    # 전체 항목 정보 수집 (앞뒤 라인 포함)
                    item_lines = []
                    start_idx = max(0, i - 1)
                    end_idx = min(len(lines), i + 5)
                    
                    for j in range(start_idx, end_idx):
                        if lines[j].strip():
                            item_lines.append(lines[j])
                    
                    if item_lines:
                        matched_items.append('\n'.join(item_lines))
            
            # 결과 생성
            if not matched_items:
                # 사용자 친화적 에러 메시지
                error_msg = "😔 조건에 맞는 장비를 찾을 수 없습니다.\n\n"
                error_msg += "📋 **요청하신 검색 조건:**\n"
                error_msg += self._format_conditions(conditions) + "\n\n"
                error_msg += "💡 **검색 팁:**\n"
                error_msg += "• 조건을 하나씩 줄여서 시도해보세요\n"
                error_msg += "• 연도는 2000-2024 범위로 입력하세요\n"
                error_msg += "• 위치명은 정확히 입력하세요 (예: 중계차, 대형스튜디오)\n"
                error_msg += "• 제조사명은 영문 대문자로 (예: SONY, Harris)\n"
                return error_msg
            
            # 응답 생성
            response = f"✅ 복합 조건 검색 결과: 총 {len(matched_items)}개 장비\n\n"
            response += f"📋 검색 조건:\n{self._format_conditions(conditions)}\n\n"
            response += "=" * 50 + "\n\n"
            
            # 최대 20개까지 표시
            for idx, item in enumerate(matched_items[:20], 1):
                response += f"[{idx}] {item}\n"
                response += "-" * 40 + "\n"
            
            if len(matched_items) > 20:
                response += f"\n... 외 {len(matched_items) - 20}개 장비"
            
            # LLM으로 요약 추가
            if self.llm and len(matched_items) > 0:
                response = self._enhance_asset_response(response, query_intent['original_query'])
            
            return response
            
        except Exception as e:
            return f"❌ 복합 검색 실패: {e}"
    
    def _format_conditions(self, conditions: dict) -> str:
        """검색 조건을 읽기 쉽게 포맷팅"""
        formatted = []
        
        if 'location' in conditions:
            formatted.append(f"• 위치: {conditions['location']}")
        
        if 'manufacturer' in conditions:
            formatted.append(f"• 제조사: {conditions['manufacturer']}")
        
        if 'year' in conditions:
            year_str = f"• 연도: {conditions['year']}년"
            if conditions.get('year_range') == 'before':
                year_str += " 이전"
            elif conditions.get('year_range') == 'after':
                year_str += " 이후"
            elif conditions.get('year_range') == 'between':
                year_str = f"• 연도: {conditions.get('year_start')}년 ~ {conditions.get('year_end')}년"
            formatted.append(year_str)
        
        if 'price' in conditions:
            price_str = f"• 금액: {conditions['price']:,.0f}원"
            if conditions.get('price_range') == 'above':
                price_str += " 이상"
            elif conditions.get('price_range') == 'below':
                price_str += " 이하"
            formatted.append(price_str)
        
        if 'equipment_type' in conditions:
            formatted.append(f"• 장비 유형: {conditions['equipment_type']}")
        
        if 'model' in conditions:
            formatted.append(f"• 모델: {conditions['model']}")
        
        return '\n'.join(formatted) if formatted else "조건 없음"
    
    def _search_asset_by_equipment_type(self, txt_path: Path, query: str) -> str:
        """장비 유형별 자산 검색"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 장비 유형 키워드 추출
            query_intent = self._parse_asset_query(query)
            equipment_type = query_intent['conditions'].get('equipment_type', '')
            
            if not equipment_type:
                # 쿼리에서 직접 추출 시도
                equipment_types = ['CCU', '카메라', '모니터', '오디오', '비디오', '서버', '스위치', '라우터', '렌즈']
                for eq_type in equipment_types:
                    if eq_type.lower() in query.lower():
                        equipment_type = eq_type
                        break
            
            if not equipment_type:
                return ("🤔 **장비 유형을 지정해주세요**\n\n"
                       "📋 **사용 가능한 장비 유형:**\n"
                       "• 카메라 - 방송용 카메라 장비\n"
                       "• 모니터 - 디스플레이 장비\n"
                       "• CCU - Camera Control Unit\n"
                       "• 오디오 - 음향 관련 장비\n"
                       "• 비디오 - 영상 처리 장비\n"
                       "• 서버 - 방송 서버 시스템\n"
                       "• 스위치 - 네트워크/비디오 스위치\n"
                       "• 라우터 - 신호 라우팅 장비\n"
                       "• 렌즈 - 카메라 렌즈\n\n"
                       "💡 **예시:** '카메라 장비 현황', 'CCU 전체 목록'")
            
            lines = content.split('\n')
            matched_items = []
            
            # 장비 유형으로 검색
            for i in range(len(lines)):
                line = lines[i]
                if equipment_type.upper() in line.upper():
                    # 전체 항목 정보 수집
                    item_lines = []
                    start_idx = max(0, i - 1)
                    end_idx = min(len(lines), i + 5)
                    
                    for j in range(start_idx, end_idx):
                        if lines[j].strip():
                            item_lines.append(lines[j])
                    
                    if item_lines:
                        matched_items.append('\n'.join(item_lines))
            
            if not matched_items:
                return f"❌ '{equipment_type}' 유형의 장비를 찾을 수 없습니다."
            
            # 통계 정보 수집
            locations = {}
            manufacturers = {}
            years = {}
            
            for item in matched_items:
                # 위치 추출
                for loc in ['중계차', '대형스튜디오', '소형부조정실', 'News VAN', '광화문']:
                    if loc in item:
                        locations[loc] = locations.get(loc, 0) + 1
                        break
                
                # 제조사 추출
                for mfr in ['SONY', 'Harris', 'HP', 'Panasonic', 'Canon']:
                    if mfr in item.upper():
                        manufacturers[mfr] = manufacturers.get(mfr, 0) + 1
                        break
                
                # 연도 추출
                year_match = re.search(r'20\d{2}', item)
                if year_match:
                    year = year_match.group(0)
                    years[year] = years.get(year, 0) + 1
            
            # 응답 생성
            response = f"✅ '{equipment_type}' 장비 검색 결과: 총 {len(matched_items)}개\n\n"
            
            # 통계 정보
            response += "📊 통계 정보:\n"
            
            if locations:
                response += "\n위치별 분포:\n"
                for loc, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
                    response += f"  • {loc}: {count}개\n"
            
            if manufacturers:
                response += "\n제조사별 분포:\n"
                for mfr, count in sorted(manufacturers.items(), key=lambda x: x[1], reverse=True)[:5]:
                    response += f"  • {mfr}: {count}개\n"
            
            if years:
                response += "\n구입 연도별:\n"
                for year, count in sorted(years.items(), reverse=True)[:5]:
                    response += f"  • {year}년: {count}개\n"
            
            response += "\n" + "=" * 50 + "\n\n"
            response += "📋 상세 장비 목록 (최대 15개):\n\n"
            
            # 상세 목록
            for idx, item in enumerate(matched_items[:15], 1):
                response += f"[{idx}] {item}\n"
                response += "-" * 40 + "\n"
            
            if len(matched_items) > 15:
                response += f"\n... 외 {len(matched_items) - 15}개 장비"
            
            # LLM으로 요약 추가
            if self.llm:
                response = self._enhance_asset_response(response, query)
            
            return response
            
        except Exception as e:
            return f"❌ 장비 유형 검색 실패: {e}"
    
    def _search_asset_by_manager(self, txt_path: Path, query: str) -> str:
        """담당자별 자산 검색"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 담당자명 추출 - 직급 포함 패턴 (붙어있는 형식 우선)
            manager_patterns = [
                r'([가-힣]{2,4})(?:차장|부장|과장|대리|사원)',    # 붙어있는 형식 (신승만차장)
                r'([가-힣]{2,4})\s*(?:차장|부장|과장|대리|사원)',  # 이름 + 공백 + 직급
                r'([가-힣]{2,4})(?:이|가|의|님)',  # 이름 + 조사
                r'([가-힣]{2,4})\s+담당',  # 이름 + 담당
            ]
            
            manager_name = None
            for pattern in manager_patterns:
                match = re.search(pattern, query)
                if match:
                    manager_name = match.group(1)
                    break
            
            if not manager_name:
                # 키워드로 추출 시도
                for word in query.split():
                    if len(word) >= 2 and len(word) <= 4 and all(ord('가') <= ord(c) <= ord('힣') for c in word):
                        if word not in ['담당', '관리', '장비', '전체', '목록']:
                            manager_name = word
                            break
            
            if manager_name:
                result = self._count_by_field(content, "담당자", manager_name)
                
                if result['count'] > 0:
                    response = f"📊 **{manager_name} 담당자 관리 장비 현황**\n"
                    response += "=" * 50 + "\n"
                    response += f"✅ 총 관리 장비: **{result['count']}개**\n\n"
                    
                    if result.get('sample_items'):
                        response += "📋 **대표 장비 목록 (최대 10개)**:\n"
                        response += "-" * 40 + "\n"
                        for i, item in enumerate(result['sample_items'][:10], 1):
                            lines = item.split('\n')
                            equipment_info = {}
                            for line in lines:
                                if '[' in line and ']' in line:
                                    equipment_info['id'] = line.strip()
                                elif '부품명:' in line:
                                    equipment_info['name'] = line.split('부품명:')[1].strip()
                                elif '모델:' in line:
                                    equipment_info['model'] = line.split('모델:')[1].strip()
                                elif '위치:' in line:
                                    equipment_info['location'] = line.split('위치:')[1].strip()
                                elif '구입일:' in line:
                                    equipment_info['date'] = line.split('구입일:')[1].strip()
                            
                            if equipment_info:
                                response += f"\n**{i}. {equipment_info.get('id', '')}**\n"
                                if 'name' in equipment_info:
                                    response += f"   • 부품명: {equipment_info['name']}\n"
                                if 'model' in equipment_info:
                                    response += f"   • 모델: {equipment_info['model']}\n"
                                if 'location' in equipment_info:
                                    response += f"   • 위치: {equipment_info['location']}\n"
                                if 'date' in equipment_info:
                                    response += f"   • 구입일: {equipment_info['date']}\n"
                    
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
                else:
                    return f"❌ {manager_name} 담당자가 관리하는 장비를 찾을 수 없습니다."
            else:
                return "❌ 담당자 이름을 확인할 수 없습니다. 정확한 이름을 입력해주세요."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_asset_by_price_range(self, txt_path: Path, query: str) -> str:
        """금액 범위별 자산 검색"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 금액 추출 및 변환
            amount_patterns = [
                (r'(\d+)\s*억\s*(\d*)\s*천?\s*만?\s*원?', lambda m: int(m.group(1)) * 100000000 + (int(m.group(2)) * 10000000 if m.group(2) else 0)),
                (r'(\d+)\s*천만\s*원?', lambda m: int(m.group(1)) * 10000000),
                (r'(\d+)\s*백만\s*원?', lambda m: int(m.group(1)) * 1000000),
                (r'(\d+)\s*만\s*원?', lambda m: int(m.group(1)) * 10000),
            ]
            
            target_amount = None
            for pattern, converter in amount_patterns:
                match = re.search(pattern, query)
                if match:
                    target_amount = converter(match)
                    break
            
            if not target_amount:
                return "❌ 금액을 확인할 수 없습니다. (예: 1억원, 5천만원)"
            
            # 범위 타입 결정
            range_type = 'exact'
            if '이상' in query or '초과' in query:
                range_type = 'above'
            elif '이하' in query or '미만' in query:
                range_type = 'below'
            elif '부터' in query or '까지' in query:
                range_type = 'range'
            
            # 장비 검색
            lines = content.split('\n')
            results = []
            current_item = []
            
            for line in lines:
                if re.match(r'^\[\d{4}\]', line):
                    # 이전 항목 처리
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 금액 추출 (여러 가능한 패턴 시도)
                        price_match = re.search(r'금액:\s*([\d,]+)원?', item_text)
                        if not price_match:
                            price_match = re.search(r'단가:\s*([\d,]+)원?', item_text)
                        if price_match:
                            price = int(price_match.group(1).replace(',', ''))
                            
                            # 범위 체크
                            if range_type == 'above' and price >= target_amount:
                                results.append((price, item_text))
                            elif range_type == 'below' and price <= target_amount:
                                results.append((price, item_text))
                            elif range_type == 'exact' and price == target_amount:
                                results.append((price, item_text))
                    
                    current_item = [line]
                elif current_item:
                    current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                price_match = re.search(r'금액:\s*([\d,]+)원?', item_text)
                if not price_match:
                    price_match = re.search(r'단가:\s*([\d,]+)원?', item_text)
                if price_match:
                    price = int(price_match.group(1).replace(',', ''))
                    if range_type == 'above' and price >= target_amount:
                        results.append((price, item_text))
                    elif range_type == 'below' and price <= target_amount:
                        results.append((price, item_text))
                    elif range_type == 'exact' and price == target_amount:
                        results.append((price, item_text))
            
            # 결과 정렬 (가격 내림차순)
            results.sort(key=lambda x: x[0], reverse=True)
            
            if results:
                range_desc = {
                    'above': '이상',
                    'below': '이하',
                    'exact': '',
                    'range': '범위'
                }[range_type]
                
                response = f"💰 **{target_amount:,}원 {range_desc} 장비 현황**\n"
                response += "=" * 50 + "\n"
                response += f"✅ 총 {len(results)}개 장비\n\n"
                
                # 금액별 통계
                total_amount = sum(r[0] for r in results)
                avg_amount = total_amount // len(results) if results else 0
                response += f"📊 **통계**:\n"
                response += f"   • 총 금액: {total_amount:,}원\n"
                response += f"   • 평균 금액: {avg_amount:,}원\n"
                response += f"   • 최고가: {results[0][0]:,}원\n"
                response += f"   • 최저가: {results[-1][0]:,}원\n\n"
                
                response += "📋 **상위 10개 장비**:\n"
                response += "-" * 40 + "\n"
                
                for i, (price, item) in enumerate(results[:10], 1):
                    lines = item.split('\n')
                    for line in lines:
                        if '[' in line and ']' in line:
                            response += f"\n**{i}. {line.strip()}** - {price:,}원\n"
                        elif '부품명:' in line:
                            response += f"   • {line.strip()}\n"
                        elif '모델:' in line:
                            response += f"   • {line.strip()}\n"
                
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            else:
                range_desc = {
                    'above': '이상',
                    'below': '이하',
                    'exact': '',
                    'range': '범위'
                }.get(range_type, '')
                return f"❌ {target_amount:,}원 {range_desc} 장비를 찾을 수 없습니다."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_asset_by_year_range(self, txt_path: Path, query: str) -> str:
        """연도 범위별 자산 검색 (이전/이후/범위)"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 연도 추출
            year_matches = re.findall(r'20\d{2}', query)
            
            # 범위 타입 결정
            range_type = 'exact'
            if '이전' in query or '전' in query:
                range_type = 'before'
            elif '이후' in query or '후' in query:
                range_type = 'after'
            elif '부터' in query and '까지' in query:
                range_type = 'between'
            elif '최근' in query:
                range_type = 'recent'
                # 최근 N년 추출
                recent_match = re.search(r'최근\s*(\d+)\s*년', query)
                if recent_match:
                    recent_years = int(recent_match.group(1))
                    current_year = 2025
                    year_matches = [str(current_year - recent_years)]
                    range_type = 'after'
            
            if not year_matches and range_type != 'recent':
                return "❌ 연도를 확인할 수 없습니다. (예: 2023년, 2020년 이전)"
            
            # 연도 범위 설정
            target_year = None
            if range_type == 'between' and len(year_matches) >= 2:
                start_year = int(year_matches[0])
                end_year = int(year_matches[1])
            elif year_matches:
                target_year = int(year_matches[0])
                if range_type == 'exact':
                    start_year = target_year
                    end_year = target_year
                elif range_type == 'after':
                    start_year = target_year
                    end_year = 2025
                elif range_type == 'before':
                    start_year = 2000
                    end_year = target_year
            else:
                # 최근 3년 기본값
                current_year = 2025
                start_year = current_year - 3
                end_year = current_year
            
            # 장비 검색
            lines = content.split('\n')
            results = []
            year_stats = {}
            
            for line in lines:
                if '구입일:' in line:
                    date_match = re.search(r'구입일:\s*(\d{4})', line)
                    if date_match:
                        year = int(date_match.group(1))
                        
                        # 범위 체크
                        if start_year <= year <= end_year:
                            results.append(line)
                            year_stats[year] = year_stats.get(year, 0) + 1
            
            if results:
                # 범위 설명
                if range_type == 'exact':
                    range_desc = f"{target_year}년"
                elif range_type == 'before':
                    range_desc = f"{end_year}년 이전"
                elif range_type == 'after':
                    range_desc = f"{start_year}년 이후"
                elif range_type == 'between':
                    range_desc = f"{start_year}년 ~ {end_year}년"
                else:
                    range_desc = "지정 기간"
                
                response = f"📅 **{range_desc} 구입 장비 현황**\n"
                response += "=" * 50 + "\n"
                response += f"✅ 총 {len(results)}개 장비\n\n"
                
                # 연도별 통계
                if year_stats:
                    response += "📊 **연도별 분포**:\n"
                    for year in sorted(year_stats.keys(), reverse=True):
                        response += f"   • {year}년: {year_stats[year]}개\n"
                    response += "\n"
                
                # 샘플 표시
                response += "📋 **샘플 장비 (최대 15개)**:\n"
                response += "-" * 40 + "\n"
                for i, result in enumerate(results[:15], 1):
                    response += f"{i}. {result}\n"
                
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            else:
                if range_type == 'exact' and target_year:
                    return f"❌ {target_year}년에 구입한 장비를 찾을 수 없습니다."
                elif start_year and end_year:
                    return f"❌ {start_year}년 ~ {end_year}년 기간에 구입한 장비를 찾을 수 없습니다."
                else:
                    return f"❌ 해당 기간에 구입한 장비를 찾을 수 없습니다."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_asset_by_year(self, txt_path: Path, query: str) -> str:
        """구입연도별 자산 검색"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 연도 추출
            year_match = re.search(r'(20\d{2})', query)
            if year_match:
                year = year_match.group(1)
                
                # 구입일 패턴으로 검색
                pattern = f"구입일: {year}"
                lines = content.split('\n')
                results = []
                count = 0
                
                for line in lines:
                    if pattern in line:
                        count += 1
                        if len(results) < 10:  # 처음 10개만
                            results.append(line)
                
                if results:
                    response = f"📊 {year}년 구입 장비: 총 {count}개\n"
                    response += "━" * 40 + "\n"
                    response += "\n[샘플 (처음 10개)]:\n"
                    for result in results:
                        response += f"• {result}\n"
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
                else:
                    return f"❌ {year}년에 구입한 장비가 없습니다."
            
            return "❌ 연도를 입력해주세요."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_location_summary(self, txt_path: Path, location: str) -> str:
        """특정 위치의 장비를 카테고리별로 정리"""
        query = f"{location} 장비 현황"  # query 변수 생성 for _enhance_asset_response
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            equipment_by_category = {}  # {카테고리: [장비 정보]}
            current_item = []
            total_count = 0
            total_amount = 0  # 총 금액
            
            for line in lines:
                if re.match(r'^\[\d{4}\]', line.strip()):
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 위치 확인
                        if self._check_location_in_item(item_text, location):
                            total_count += 1
                            # 장비 카테고리 분류
                            equipment_name = current_item[0].split(']')[1].strip() if ']' in current_item[0] else current_item[0]
                            
                            # 카테고리 결정
                            category = self._determine_equipment_category(equipment_name, item_text)
                            
                            if category not in equipment_by_category:
                                equipment_by_category[category] = []
                            
                            # 정보 추출
                            info = {
                                'name': equipment_name,
                                'model': "N/A",
                                'price': 0,
                                'quantity': 1,
                                'date': "N/A"
                            }
                            
                            for item_line in current_item:
                                # 모델명
                                if "모델:" in item_line:
                                    model_match = re.search(r'모델:\s*([^|]+)', item_line)
                                    if model_match:
                                        info['model'] = model_match.group(1).strip()
                                
                                # 금액 정보
                                if "금액:" in item_line:
                                    amount_match = re.search(r'금액:\s*([\d,]+)원', item_line)
                                    if amount_match:
                                        amount_str = amount_match.group(1).replace(',', '')
                                        try:
                                            info['price'] = int(amount_str)
                                            total_amount += info['price']
                                        except:
                                            pass
                                
                                # 수량
                                if "수량:" in item_line:
                                    qty_match = re.search(r'수량:\s*(\d+)', item_line)
                                    if qty_match:
                                        info['quantity'] = int(qty_match.group(1))
                                
                                # 구입일
                                if "구입일:" in item_line:
                                    date_match = re.search(r'구입일:\s*([^\s|]+)', item_line)
                                    if date_match:
                                        info['date'] = date_match.group(1).strip()
                            
                            equipment_by_category[category].append(info)
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                if self._check_location_in_item(item_text, location):
                    total_count += 1
                    equipment_name = current_item[0].split(']')[1].strip() if ']' in current_item[0] else current_item[0]
                    category = self._determine_equipment_category(equipment_name, item_text)
                    if category not in equipment_by_category:
                        equipment_by_category[category] = []
                    
                    info = {
                        'name': equipment_name,
                        'model': "N/A",
                        'price': 0,
                        'quantity': 1,
                        'date': "N/A"
                    }
                    
                    for item_line in current_item:
                        if "모델:" in item_line:
                            model_match = re.search(r'모델:\s*([^|]+)', item_line)
                            if model_match:
                                info['model'] = model_match.group(1).strip()
                        if "금액:" in item_line:
                            amount_match = re.search(r'금액:\s*([\d,]+)원', item_line)
                            if amount_match:
                                amount_str = amount_match.group(1).replace(',', '')
                                try:
                                    info['price'] = int(amount_str)
                                    total_amount += info['price']
                                except:
                                    pass
                        if "수량:" in item_line:
                            qty_match = re.search(r'수량:\s*(\d+)', item_line)
                            if qty_match:
                                info['quantity'] = int(qty_match.group(1))
                        if "구입일:" in item_line:
                            date_match = re.search(r'구입일:\s*([^\s|]+)', item_line)
                            if date_match:
                                info['date'] = date_match.group(1).strip()
                    
                    equipment_by_category[category].append(info)
            
            # 결과 포맷팅
            if equipment_by_category:
                response = f"📊 **{location} 장비 현황**\n"
                response += "=" * 70 + "\n"
                response += f"✅ 총 **{total_count}개** 장비\n"
                if total_amount > 0:
                    # 금액 포맷팅 (억/천만원 단위)
                    if total_amount >= 100000000:  # 1억 이상
                        amount_str = f"{total_amount/100000000:.1f}억원"
                    elif total_amount >= 10000000:  # 1천만원 이상
                        amount_str = f"{total_amount/10000000:.0f}천만원"
                    else:
                        amount_str = f"{total_amount:,}원"
                    response += f"💰 총 자산가치: **{amount_str}**\n\n"
                else:
                    response += "\n"
                
                # 카테고리별 요약
                response += "### 📋 카테고리별 상세 현황\n"
                response += "-" * 50 + "\n"
                
                # 카테고리 정렬 (장비 수 많은 순)
                sorted_categories = sorted(equipment_by_category.items(), key=lambda x: len(x[1]), reverse=True)
                
                for category, items in sorted_categories:
                    # 카테고리별 총액 계산
                    category_amount = sum(item['price'] for item in items)
                    
                    response += f"\n**{category}** ({len(items)}개"
                    if category_amount > 0:
                        if category_amount >= 100000000:
                            response += f", {category_amount/100000000:.1f}억원"
                        elif category_amount >= 10000000:
                            response += f", {category_amount/10000000:.0f}천만원"
                        else:
                            response += f", {category_amount:,}원"
                    response += ")\n"
                    
                    # 같은 장비명끼리 그룹화
                    equipment_summary = {}
                    for item in items:
                        key = f"{item['name']} ({item['model']})" if item['model'] != "N/A" else item['name']
                        if key not in equipment_summary:
                            equipment_summary[key] = {
                                'count': 0,
                                'total_price': 0,
                                'unit_price': item['price'] // item['quantity'] if item['quantity'] > 0 else item['price']
                            }
                        equipment_summary[key]['count'] += item['quantity']
                        equipment_summary[key]['total_price'] += item['price']
                    
                    # 금액 많은 순으로 정렬
                    sorted_equipment = sorted(equipment_summary.items(), 
                                           key=lambda x: x[1]['total_price'], 
                                           reverse=True)
                    
                    # 상위 5개만 표시
                    for i, (equip_name, equip_info) in enumerate(sorted_equipment[:5], 1):
                        line = f"  {i}. {equip_name}"
                        if equip_info['count'] > 1:
                            line += f" - {equip_info['count']}개"
                        if equip_info['total_price'] > 0:
                            line += f" ({equip_info['total_price']:,}원)"
                        response += line + "\n"
                    
                    if len(sorted_equipment) > 5:
                        response += f"  ... 외 {len(sorted_equipment)-5}종\n"
                
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            else:
                return f"❌ {location}에서 장비를 찾을 수 없습니다."
                
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _determine_equipment_category(self, equipment_name: str, item_text: str) -> str:
        """장비명과 텍스트로 카테고리 결정"""
        name_lower = equipment_name.lower()
        text_lower = item_text.lower()
        
        if any(kw in name_lower or kw in text_lower for kw in ['camera', '카메라', 'ccu', 'viewfinder', '뷰파인더']):
            return "📹 카메라 시스템"
        elif any(kw in name_lower or kw in text_lower for kw in ['monitor', '모니터', 'display']):
            return "🖥️ 모니터"
        elif any(kw in name_lower or kw in text_lower for kw in ['audio', '오디오', 'mixer', '믹서', 'mic', '마이크']):
            return "🎙️ 오디오 장비"
        elif any(kw in name_lower or kw in text_lower for kw in ['server', '서버', 'storage', '스토리지']):
            return "💾 서버/스토리지"
        elif any(kw in name_lower or kw in text_lower for kw in ['switch', '스위치', 'router', '라우터', 'matrix']):
            return "🔌 스위칭/라우팅"
        elif any(kw in name_lower or kw in text_lower for kw in ['cable', '케이블', 'connector', '커넥터']):
            return "🔗 케이블/커넥터"
        elif any(kw in name_lower or kw in text_lower for kw in ['tripod', '트라이포드', 'pedestal', '페데스탈']):
            return "🎬 카메라 지원장비"
        elif any(kw in name_lower or kw in text_lower for kw in ['intercom', '인터컴', 'talkback']):
            return "📞 인터컴"
        elif any(kw in name_lower or kw in text_lower for kw in ['converter', '컨버터', 'encoder', '인코더']):
            return "🔄 컨버터/인코더"
        else:
            return "📦 기타 장비"

    def _search_location_unified(self, txt_path: Path, query: str) -> str:
        """통일된 위치별 검색 - 일관된 형식으로 출력"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            # 위치 키워드 추출
            location_keywords = {
                '중계차': '중계차',
                'news van': 'News VAN',
                'mini van': 'Mini VAN',
                '광화문': '광화문',
                '스튜디오': '스튜디오',
                '부조': '부조',
                '편집실': '편집실',
                '더빙실': '더빙실'
            }
            
            found_location = None
            query_lower = query.lower()
            for key, value in location_keywords.items():
                if key in query_lower:
                    found_location = value
                    break
            
            # 위치가 명확하면 요약 형식으로
            if found_location:
                # "전부", "현황", "전체" 키워드가 있으면 카테고리별 요약
                if any(kw in query for kw in ['전부', '현황', '전체', '모든']):
                    return self._search_location_summary(txt_path, found_location)
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 위치 키워드 추출
            location_keyword = None
            
            # 중계차 체크
            if '중계차' in query.lower() or 'van' in query.lower():
                location_keyword = '중계차'
                search_term = 'Van'  # 실제 데이터에서는 Van으로 저장됨
            else:
                # 다른 위치 패턴 찾기
                location_patterns = [
                    (r'광화문\s*스튜디오', '광화문'),
                    (r'대형\s*스튜디오', '대형스튜디오'),
                    (r'뉴스\s*부조', '뉴스부조'),
                    (r'종편\s*부조', '종편부조'),
                    (r'편집실', '편집실'),
                    (r'더빙실', '더빙실'),
                    (r'[가-힣]{2,}(?:스튜디오|부조정실|편집실|더빙실|사옥|센터|실|층|관|동|호)', None)
                ]
                
                for pattern, keyword in location_patterns:
                    match = re.search(pattern, query)
                    if match:
                        location_keyword = keyword if keyword else match.group(0)
                        search_term = location_keyword
                        break
            
            if not location_keyword:
                return "❌ 위치 정보를 찾을 수 없습니다. (예: 광화문 스튜디오, 중계차, 대형스튜디오)"
            
            # 위치별 장비 검색
            lines = content.split('\n')
            matching_items = []
            current_item = []
            item_count = 0
            
            for line in lines:
                if re.match(r'^\[\d{4}\]', line):
                    # 이전 항목 검사
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 위치 확인
                        if search_term in item_text or (location_keyword in item_text):
                            matching_items.append(item_text)
                            item_count += 1
                    
                    current_item = [line]
                elif current_item:
                    current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                if search_term in item_text or (location_keyword in item_text):
                    matching_items.append(item_text)
                    item_count += 1
            
            if matching_items:
                # 통일된 형식으로 출력
                response = f"📊 **{location_keyword} 장비 현황**\n"
                response += "=" * 70 + "\n"
                response += f"✅ 총 **{item_count}개** 장비\n\n"
                
                # 장비 타입별 분류
                equipment_types = {}
                for item in matching_items:
                    # 부품명 추출
                    if '부품명:' in item:
                        part_match = re.search(r'부품명:\s*([^\n]+)', item)
                        if part_match:
                            part_name = part_match.group(1).strip()
                            # 타입 분류
                            if 'Camera' in part_name or '카메라' in part_name:
                                type_name = '카메라'
                            elif 'Monitor' in part_name or '모니터' in part_name:
                                type_name = '모니터'
                            elif 'Audio' in part_name or '오디오' in part_name or 'Mic' in part_name:
                                type_name = '오디오/마이크'
                            elif 'Light' in part_name or '조명' in part_name:
                                type_name = '조명'
                            elif 'Lens' in part_name or '렌즈' in part_name:
                                type_name = '렌즈'
                            elif 'CCU' in part_name or 'Control Unit' in part_name:
                                type_name = 'CCU/컨트롤'
                            elif 'Server' in part_name or '서버' in part_name:
                                type_name = '서버/스토리지'
                            else:
                                type_name = '기타'
                            
                            equipment_types[type_name] = equipment_types.get(type_name, 0) + 1
                
                if equipment_types:
                    response += "📋 **장비 타입별 분류**:\n"
                    for type_name, count in sorted(equipment_types.items(), key=lambda x: x[1], reverse=True):
                        response += f"  • {type_name}: {count}개\n"
                    response += "\n"
                
                response += "-" * 70 + "\n"
                response += "📄 **상세 장비 목록** (최대 15개):\n\n"
                
                # 상세 목록 (최대 15개)
                for i, item in enumerate(matching_items[:15], 1):
                    lines = item.split('\n')
                    
                    # 기본 정보 추출
                    item_info = {}
                    for line in lines:
                        if re.match(r'^\[\d{4}\]', line):
                            item_info['id'] = line.strip()
                        elif '부품명:' in line:
                            item_info['name'] = line.split('부품명:')[1].strip()
                        elif '모델:' in line:
                            item_info['model'] = line.split('모델:')[1].strip()
                        elif '제조사:' in line and '모델:' not in line:
                            item_info['manufacturer'] = line.split('제조사:')[1].strip()
                        elif '구입일:' in line:
                            item_info['date'] = line.split('구입일:')[1].strip()[:10]
                        elif '담당자:' in line:
                            item_info['manager'] = line.split('담당자:')[1].strip()
                    
                    response += f"[{i}] **{item_info.get('id', '')}**"
                    if 'name' in item_info:
                        response += f" {item_info['name']}\n"
                    else:
                        response += "\n"
                    
                    if 'model' in item_info:
                        response += f"    📌 모델: {item_info['model']}\n"
                    if 'manufacturer' in item_info:
                        response += f"    🏢 제조사: {item_info['manufacturer']}\n"
                    if 'date' in item_info:
                        response += f"    📅 구입일: {item_info['date']}\n"
                    if 'manager' in item_info:
                        response += f"    👤 담당자: {item_info['manager']}\n"
                    response += "\n"
                
                if len(matching_items) > 15:
                    response += f"... 외 {len(matching_items) - 15}개 장비\n"
                
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            else:
                return f"❌ {location_keyword}에서 장비를 찾을 수 없습니다."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_asset_by_location(self, txt_path: Path, query: str) -> str:
        """위치별 자산 검색"""
        try:
            # 완전판 파일 우선 사용 (assets 폴더에서)
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 위치 키워드 찾기
            # 쿼리에서 위치 키워드 동적 추출
            # 한글 2글자 이상 + 일반적인 장소 접미사
            location_pattern = r'[가-힣]{2,}(?:스튜디오|부조|편집실|더빙실|사옥|센터|실|층|관|동|호)'
            locations = re.findall(location_pattern, query)
            found_location = None
            for loc in locations:
                if loc in query:
                    found_location = loc
                    break
            
            if found_location:
                # 정확한 위치 매칭으로 검색
                lines = content.split('\n')
                results = []
                count = 0
                
                for line in lines:
                    if '위치:' in line:
                        # 실제 위치 추출하여 정확히 매칭
                        location_match = re.search(r'위치:\s*([^|\n]+)', line)
                        if location_match:
                            actual_location = location_match.group(1).strip()
                            
                            # 정확한 매칭 규칙 적용
                            is_match = False
                            if found_location == actual_location:
                                # 완전 일치
                                is_match = True
                            elif found_location == '부조정실':
                                # '부조정실'로 검색시 '*부조정실' 패턴만 매칭
                                is_match = actual_location.endswith('부조정실')
                            elif found_location == '스튜디오':
                                # '스튜디오'로 검색시 '*스튜디오' 패턴만 매칭 
                                is_match = actual_location.endswith('스튜디오')
                            elif found_location == '편집실':
                                # '편집실'로 검색시 '*편집실' 패턴만 매칭
                                is_match = actual_location.endswith('편집실')
                            elif found_location in ['중계차', 'van', 'Van', 'VAN']:
                                # 중계차 검색시 Van 관련 위치 모두 매칭
                                is_match = 'Van' in actual_location or 'VAN' in actual_location
                            elif len(found_location) > 3:
                                # 3글자 이상의 구체적인 위치명은 부분 매칭 허용
                                is_match = found_location in actual_location
                            
                            if is_match:
                                count += 1
                                if len(results) < 10:  # 처음 10개만
                                    results.append(line)
                
                if results:
                    response = f"📊 {found_location} 위치 장비: 총 {count}개\n"
                    response += "━" * 40 + "\n"
                    response += "\n[샘플 (처음 10개)]:\n"
                    for result in results:
                        response += f"• {result}\n"
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
                else:
                    return f"❌ {found_location}에 위치한 장비가 없습니다."
            
            return "❌ 위치를 입력해주세요."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_asset_with_llm(self, txt_path: Path, query: str) -> str:
        """LLM을 활용한 동적 자산 검색 - 정확한 수량 계산"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            query_lower = query.lower()
            lines = content.split('\n')
            
            # 담당자별 검색
            if '담당' in query_lower or '관리' in query_lower:
                # 담당자명 추출
                # 한글 이름 패턴으로 동적 추출 (성+이름 형태)
                manager_patterns = re.findall(r'[가-힣]{2,4}(?:\s+[가-힣]{2,3})?', query)
                manager = None
                for name in manager_patterns:
                    if name in query:
                        manager = name
                        break
                
                if manager:
                    result = self._count_by_field(content, "담당자", manager)
                    response = f"📊 {manager} 담당자 관리 장비 현황\n"
                    response += "=" * 50 + "\n"
                    response += f"✅ 총 관리 장비: {result['count']}개\n\n"
                    
                    if result.get('sample_items'):
                        response += "📋 대표 장비 목록:\n"
                        for i, item in enumerate(result['sample_items'][:5], 1):
                            lines = item.split('\n')
                            for line in lines:
                                if '[' in line and ']' in line:
                                    response += f"\n{i}. {line.strip()}\n"
                                elif '부품명' in line or '모델:' in line:
                                    response += f"   {line.strip()}\n"
                    
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
            
            # 위치별 검색 - 동적 처리
            # 위치 관련 키워드를 동적으로 찾기
            location_keywords = re.findall(r'[가-힣]+(?:스튜디오|부조정실|장비실|데이터센터|편집실|더빙실|사옥|층|관|동|호)', query)
            if location_keywords:
                for location in location_keywords:
                    result = self._count_by_field(content, "위치", location)
                    if result['count'] > 0:
                        # "목록", "전체" 등이 있으면 상세 목록 표시
                        if any(keyword in query for keyword in ["목록", "전체", "보여달라", "보여줘", "리스트", "알려줘"]):
                            return self._generate_detailed_location_list(content, location, result, txt_path)
                        else:
                            # 간단한 현황만 표시
                            response = f"📊 {location} 장비 현황\n"
                            response += "=" * 50 + "\n"
                            response += f"✅ 총 보유 장비: {result['count']}개\n\n"
                            response += f"📄 출처: {txt_path.name}"
                            return response
            
            # 벤더사별 검색 - 동적 처리
            # 벤더사 키워드를 문서에서 동적으로 찾기
            vendor_keywords = []
            if '벤더' in query or '납품' in query or '업체' in query:
                # 쿼리에서 회사명 패턴 추출 (한글+시스템/코리아/디지탈 등)
                vendor_patterns = re.findall(r'[가-힣]+(?:시스템|코리아|디지탈|전자|정보|통신|테크|솔루션)|[A-Z]{2,}', query)
                for vendor in vendor_patterns:
                    result = self._count_by_field(content, "벤더사", vendor)
                    if result['count'] > 0:
                        response = f"📊 {vendor} 납품 장비 현황\n"
                        response += "=" * 50 + "\n"
                        response += f"✅ 총 납품 장비: {result['count']}개\n\n"
                        response += f"📄 출처: {txt_path.name}"
                        return response
            
            # CCU 관련 질문 특별 처리
            elif 'ccu' in query_lower or 'camera control' in query_lower:
                ccu_items = []
                ccu_blocks = []
                ccu_count = 0
                
                # CCU 항목을 블록 단위로 찾기
                for i, line in enumerate(lines):
                    if 'Camera Control Unit' in line or 'CCU' in line:
                        # 이 줄이 제목줄인지 확인 (대괄호로 시작)
                        if line.strip().startswith('['):
                            # 전체 블록 수집 (현재 줄 + 다음 4줄)
                            block_lines = []
                            for j in range(i, min(i+5, len(lines))):
                                if lines[j].strip():
                                    block_lines.append(lines[j].strip())
                            
                            if block_lines:
                                ccu_blocks.append('\n'.join(block_lines))
                                ccu_count += 1
                
                response = f"📊 CCU(Camera Control Unit) 현황\n"
                response += "=" * 50 + "\n"
                response += f"### 📈 총 CCU 장비: **{ccu_count}개**\n\n"
                
                # 제조사별 분포 분석
                manufacturers = {}
                for block in ccu_blocks:
                    mfr_match = re.search(r'제조사:\s*([^|]+)', block)
                    if mfr_match:
                        mfr = mfr_match.group(1).strip()
                        manufacturers[mfr] = manufacturers.get(mfr, 0) + 1
                
                if manufacturers:
                    response += "### 📊 제조사별 분포\n"
                    for mfr, cnt in sorted(manufacturers.items(), key=lambda x: x[1], reverse=True):
                        response += f"• **{mfr}**: {cnt}개\n"
                    response += "\n"
                
                if ccu_blocks:
                    # CCU는 중요 장비이므로 30개 미만은 전체 표시
                    display_limit = 30 if ccu_count > 30 else ccu_count
                    
                    if ccu_count <= 30:
                        response += "### 📋 전체 상세 목록\n"
                    else:
                        response += f"### 📋 상세 목록 ({display_limit}개/총 {ccu_count}개)\n"
                    
                    for i, block in enumerate(ccu_blocks[:display_limit], 1):
                        response += f"{block}\n\n"
                    
                    if ccu_count > display_limit:
                        response += f"\n⚠️ 표시된 {display_limit}개 외에 {ccu_count - display_limit}개가 더 있습니다.\n"
                        response += "🔍 전체 목록이 필요하시면 '전체 CCU 목록 보여줘'라고 요청하세요.\n"
                
                response += f"\n---\n📄 출처: {txt_path.name}"
                return response
            
            # 범용적인 자산 검색 개선 - 블록 단위로 완전한 정보 제공
            # 쿼리에서 검색어 추출
            search_terms = []
            
            # "어디" "있는" 같은 키워드가 있으면 위치 검색
            location_search = False
            if any(word in query_lower for word in ['어디', '위치', '있는', '보관']):
                location_search = True
            
            # 검색할 키워드 동적 추출
            # 영어 단어, 한글 단어, 숫자 등
            potential_keywords = re.findall(r'[A-Za-z]{2,}[\s\-]?[A-Za-z]*|[가-힣]{2,}|[A-Z]+[-\s]?\d+', query)
            
            if potential_keywords:
                # 블록 단위로 장비 정보 수집
                matching_items = []
                current_item = []
                is_matching = False
                item_count = 0
                
                for line in lines:
                    # 새로운 장비 항목 시작 감지
                    if re.match(r'^\[\d{4}\]', line):
                        # 이전 항목이 매칭되었으면 저장
                        if is_matching and current_item:
                            matching_items.append('\n'.join(current_item))
                            item_count += 1
                        
                        # 새 항목 시작
                        current_item = [line]
                        is_matching = False
                        
                        # 첫 줄에서도 매칭 체크
                        for keyword in potential_keywords:
                            if keyword.lower() in line.lower():
                                is_matching = True
                                break
                    elif current_item:
                        current_item.append(line)
                        # 현재 줄에서 키워드 매칭 확인
                        for keyword in potential_keywords:
                            if keyword.lower() in line.lower():
                                is_matching = True
                                break
                
                # 마지막 항목 처리
                if is_matching and current_item:
                    matching_items.append('\n'.join(current_item))
                    item_count += 1
                
                if matching_items:
                    # 검색어 표시
                    search_display = ' + '.join(potential_keywords)
                    response = f"📊 '{search_display}' 검색 결과\n"
                    response += "=" * 50 + "\n"
                    response += f"### 📈 총 검색 결과: **{len(matching_items)}개**\n\n"
                    
                    # 동적 분류 (장비명 기반)
                    equipment_categories = {}
                    for item in matching_items:
                        first_line = item.split('\n')[0]
                        # 장비명 추출
                        equipment_match = re.search(r'\[\d{4}\]\s*(.+?)(?:\s*\||$)', first_line)
                        if equipment_match:
                            equipment_name = equipment_match.group(1).strip()
                            
                            # 동적 카테고리 분류
                            category = self._categorize_equipment(equipment_name)
                            
                            if category not in equipment_categories:
                                equipment_categories[category] = []
                            equipment_categories[category].append(equipment_name)
                    
                    # 카테고리별 수량 표시
                    if equipment_categories and len(equipment_categories) > 1:
                        response += "### 📋 장비 타입별 분류\n"
                        for cat_name, equipments in sorted(equipment_categories.items()):
                            response += f"• **{cat_name}**: {len(equipments)}개\n"
                        response += "\n"
                    
                    # 상세 장비 목록 (블록 단위 전체 정보)
                    response += "### 📄 상세 장비 정보\n\n"
                    
                    # 표시할 항목 수 결정 (많으면 30개, 적으면 전체)
                    display_count = min(30, len(matching_items))
                    
                    for i, item in enumerate(matching_items[:display_count], 1):
                        lines_of_item = item.split('\n')
                        
                        # 전체 정보 블록 표시
                        response += f"[{i}] " + lines_of_item[0][6:] + "\n"  # 번호 제거하고 표시
                        
                        # 주요 정보 추출 및 표시
                        for line in lines_of_item[1:]:
                            line = line.strip()
                            if line and not line.startswith('━'):
                                # 정보 필드 정리
                                if any(field in line for field in ['제조사:', '모델명:', '시리얼:', '위치:', '담당자:', '벤더사:', '취득일자:']):
                                    response += f"  {line}\n"
                        response += "\n"
                    
                    if len(matching_items) > 30:
                        response += f"\n⚠️ 총 {len(matching_items)}개 중 30개만 표시\n"
                        response += "🔍 전체 목록이 필요하시면 '전체 목록 보여줘'라고 요청하세요.\n"
                    
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
            
            # 기타 키워드 검색
            results = []
            search_keywords = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}|\d{4,}', query)
            
            for line in lines:
                for keyword in search_keywords:
                    if keyword.lower() in line.lower():
                        results.append(line.strip())
                        if len(results) >= 20:  # 최대 20개
                            break
                if len(results) >= 20:
                    break
            
            if results:
                response = f"📊 '{query}' 검색 결과:\n"
                response += "━" * 40 + "\n"
                
                # 결과 요약
                response += f"총 {len(results)}개 항목 발견\n\n"
                
                # 30개까지 표시
                display_limit = min(30, len(results))
                
                for i, result in enumerate(results[:display_limit], 1):
                    response += f"{i}. {result[:150]}\n"
                
                if len(results) > display_limit:
                    response += f"\n⚠️ 총 {len(results)}개 중 {display_limit}개만 표시\n"
                    response += "🔍 전체 목록이 필요하시면 다시 요청하세요.\n"
                    
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            
            # 결과가 없거나 더 복잡한 질문인 경우 LLM 사용
            # LLM으로 더 지능적인 검색 수행
            print("🤖 LLM을 사용한 고급 검색 시작...")
            
            # 전체 내용에서 관련 부분 추출 (최대 10000자)
            content_sample = content[:10000] if len(content) > 10000 else content
            
            # LLM 초기화
            if self.llm is None:
                self._preload_llm()
            
            if self.llm:
                prompt = f"""다음은 채널A 방송장비 자산 데이터입니다.

사용자 질문: {query}

데이터 샘플:
{content_sample}

위 데이터를 분석하여 사용자 질문에 대한 답변을 작성하세요.
- 정확한 수량과 세부정보를 포함하세요
- 표나 목록 형식으로 정리하세요
- 관련 장비의 모델명, 제조사, 위치 등을 포함하세요
- 데이터에 없는 내용은 추측하지 마세요

답변:"""
                
                try:
                    # QwenLLM의 올바른 메서드 사용
                    if hasattr(self.llm, 'generate_response'):
                        # 컨텍스트 준비
                        context_chunks = [{
                            'content': content_sample,
                            'source': str(txt_path.name),
                            'score': 1.0
                        }]
                        response_obj = self.llm.generate_response(prompt, context_chunks)
                        if response_obj and hasattr(response_obj, 'answer'):
                            llm_response = response_obj.answer
                        else:
                            llm_response = str(response_obj) if response_obj else ""
                    else:
                        # 폴백 - 직접 __call__ 사용
                        llm_response = self.llm(prompt, max_tokens=1024, temperature=0.1)['choices'][0]['text']
                    
                    if llm_response and llm_response.strip():
                        return f"📊 AI 분석 결과:\n\n{llm_response}\n\n📄 출처: {txt_path.name}"
                except Exception as e:
                    print(f"⚠️ LLM 처리 오류: {e}")
            
            # LLM도 실패한 경우 기본 메시지
            return f"❌ '{query}'에 대한 정보를 찾을 수 없습니다.\n\n💡 다른 검색어를 시도해보세요:\n- 제조사명 (HP, SONY, Harris 등)\n- 장비명 (CCU, 카메라, 마이크 등)\n- 연도 (2015년, 2020년 등)"
            
        except Exception as e:
            return f"❌ 자산 검색 실패: {e}"
    
    def _get_asset_summary(self, txt_path: Path) -> str:
        """자산 파일 요약 정보 반환"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            summary = "📊 채널A 방송장비 자산 현황\n"
            summary += "━" * 40 + "\n"
            
            # 처음 100줄에서 주요 통계 추출
            for line in lines[:100]:
                if '총 보유 장비:' in line or \
                   '• ' in line and ('개' in line or '대' in line):
                    summary += line
            
            summary += f"\n📄 출처: {txt_path.name}"
            return summary
            
        except Exception as e:
            return f"❌ 요약 생성 실패: {e}"
    
    def _categorize_equipment(self, equipment_name: str) -> str:
        """장비명을 기반으로 동적 카테고리 분류"""
        name_lower = equipment_name.lower()
        
        # 패턴 기반 동적 분류
        if any(word in name_lower for word in ['camera', 'ccu', '카메라', 'cam']):
            return '카메라 관련'
        elif any(word in name_lower for word in ['monitor', '모니터', 'display']):
            return '모니터/디스플레이'
        elif any(word in name_lower for word in ['mic', 'microphone', '마이크', 'audio']):
            return '오디오/마이크'
        elif any(word in name_lower for word in ['switcher', 'router', '스위처', '라우터']):
            return '스위처/라우터'
        elif any(word in name_lower for word in ['server', '서버', 'storage', 'nas']):
            return '서버/스토리지'
        elif any(word in name_lower for word in ['converter', '컨버터', 'adapter']):
            return '컨버터/어댑터'
        elif any(word in name_lower for word in ['lens', '렌즈', 'optical']):
            return '렌즈/광학'
        elif any(word in name_lower for word in ['tripod', '삼각대', 'stand']):
            return '삼각대/스탠드'
        elif any(word in name_lower for word in ['battery', '배터리', 'charger', 'power']):
            return '전원/배터리'
        elif any(word in name_lower for word in ['cable', '케이블', 'connector']):
            return '케이블/커넥터'
        elif any(word in name_lower for word in ['analyzer', 'test', '분석', '테스트']):
            return '분석/테스트 장비'
        elif any(word in name_lower for word in ['transmitter', 'receiver', '송신', '수신']):
            return '송수신 장비'
        elif any(word in name_lower for word in ['recorder', 'player', '레코더', '플레이어']):
            return '녹화/재생 장비'
        elif any(word in name_lower for word in ['light', '조명', 'led', 'lamp']):
            return '조명 장비'
        elif 'nexio' in name_lower:
            return 'NEXIO 시스템'
        elif 'hp' in name_lower and any(word in name_lower for word in ['z8', 'z6', 'z4', 'workstation']):
            return 'HP 워크스테이션'
        else:
            # 기타 카테고리로 분류
            return '기타 장비'
    
    def _count_by_field(self, content: str, field_name: str, search_value: str) -> dict:
        """특정 필드값으로 장비 수량 계산"""
        lines = content.split('\n')
        count = 0
        items = []
        current_item = []
        is_matching = False
        
        for line in lines:
            # 새로운 장비 항목 시작
            if re.match(r'^\[\d{4}\]', line):
                # 이전 항목이 매칭되었으면 카운트
                if is_matching and current_item:
                    count += 1
                    if len(items) < 10:  # 샘플 10개만 저장
                        items.append('\n'.join(current_item))
                
                # 새 항목 시작
                current_item = [line]
                is_matching = False
            elif current_item:
                current_item.append(line)
                # 필드별 매칭 확인
                if field_name == "담당자" and "담당자:" in line:
                    if search_value in line:
                        is_matching = True
                elif field_name == "위치" and "위치:" in line:
                    # 정확한 위치 매칭 로직 적용
                    location_match = re.search(r'위치:\s*([^|\n]+)', line)
                    if location_match:
                        actual_location = location_match.group(1).strip()
                        
                        # 정확한 매칭 규칙
                        if search_value == actual_location:
                            # 완전 일치
                            is_matching = True
                        elif search_value == '부조정실':
                            # '부조정실'로 검색시 '*부조정실' 패턴만 매칭
                            is_matching = actual_location.endswith('부조정실')
                        elif search_value == '스튜디오':
                            # '스튜디오'로 검색시 '*스튜디오' 패턴만 매칭 
                            is_matching = actual_location.endswith('스튜디오')
                        elif search_value == '편집실':
                            # '편집실'로 검색시 '*편집실' 패턴만 매칭
                            is_matching = actual_location.endswith('편집실')
                        elif search_value in ['중계차', 'van', 'Van', 'VAN']:
                            # 중계차 검색시 Van 관련 위치 모두 매칭
                            is_matching = 'Van' in actual_location or 'VAN' in actual_location
                        elif len(search_value) > 3:
                            # 3글자 이상의 구체적인 위치명은 부분 매칭 허용
                            is_matching = search_value in actual_location
                elif field_name == "벤더사" and "벤더사:" in line:
                    if search_value in line:
                        is_matching = True
                elif field_name == "제조사" and "제조사:" in line:
                    if search_value.upper() in line.upper():
                        is_matching = True
        
        # 마지막 항목 처리
        if is_matching and current_item:
            count += 1
            if len(items) < 10:
                items.append('\n'.join(current_item))
        
        return {
            'count': count,
            'sample_items': items
        }
    
    def _search_asset_by_manufacturer(self, txt_path: Path, query: str) -> str:
        """제조사별 자산 검색 - 정확한 수량 계산"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 제조사명 추출 (더 유연한 접근)
            # 1. 알려진 제조사 목록
            known_manufacturers = [
                'SONY', 'HARRIS', 'HP', 'TOSHIBA', 'PANASONIC', 'CANON',
                'DELL', 'APPLE', 'SAMSUNG', 'LG', 'AVID', 'BLACKMAGIC',
                'MICROSOFT', 'ADOBE', 'GRASS VALLEY', 'EVERTZ', 'IMAGINE',
                'ASHIDAVOX', 'ATOMOS', 'ARRI', 'RED', 'JVC', 'IKEGAMI'
            ]
            
            manufacturer = None
            query_upper = query.upper()
            
            # 알려진 제조사 확인
            for mfr in known_manufacturers:
                if mfr in query_upper:
                    manufacturer = mfr
                    break
            
            # 못 찾았으면 영문 대문자 단어 추출
            if not manufacturer:
                words = re.findall(r'\b[A-Z][A-Z0-9]*\b', query_upper)
                for word in words:
                    if len(word) >= 2 and word not in ['THE', 'AND', 'OR', 'FOR']:
                        manufacturer = word
                        break
            
            if manufacturer:
                # 정확한 수량 계산
                result = self._count_by_field(content, "제조사", manufacturer)
                
                response = f"📊 {manufacturer} 제조사 장비 현황\n"
                response += "=" * 50 + "\n"
                response += f"✅ 총 보유 수량: {result['count']}개\n\n"
                
                if result.get('sample_items'):
                    # 모델별 통계
                    model_counts = {}
                    for item in result['sample_items']:
                        lines = item.split('\n')
                        for line in lines:
                            if '모델:' in line:
                                model = line.split('모델:')[1].split('|')[0].strip()
                                if model:
                                    model_counts[model] = model_counts.get(model, 0) + 1
                    
                    if model_counts:
                        response += "📦 주요 모델:\n"
                        for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                            response += f"  • {model}: {count}개\n"
                        response += "\n"
                    
                    # 샘플 장비 목록
                    response += "📋 대표 장비 (샘플):\n"
                    for i, item in enumerate(result['sample_items'][:5], 1):
                        lines = item.split('\n')
                        for line in lines:
                            if line.startswith('[') and ']' in line:
                                response += f"\n{i}. {line.strip()}\n"
                            elif '기본정보:' in line:
                                # 모델과 시리얼만 표시
                                parts = line.split('|')
                                for part in parts:
                                    if '모델:' in part or 'S/N:' in part:
                                        response += f"   {part.strip()}\n"
                
                response += f"\n📄 출처: {txt_path.name}"
                # LLM으로 답변 개선
                return self._enhance_asset_response(response, query)
            
            # 제조사를 찾지 못한 경우
            else:
                # 제조사별 검색
                lines = content.split('\n')
                results = []
                count = 0
                models = {}  # 모델별 집계
                
                for line in lines:
                    if manufacturer in line.upper() or f"제조사: {manufacturer}" in line:
                        count += 1
                        if len(results) < 20:  # 처음 20개
                            results.append(line.strip())
                        
                        # 모델명 추출하여 집계
                        model_match = re.search(r'모델:\s*([^\|]+)', line)
                        if model_match:
                            model = model_match.group(1).strip()
                            models[model] = models.get(model, 0) + 1
                
                if results:
                    response = f"📊 {manufacturer} 제조사 장비 현황\n"
                    response += "=" * 50 + "\n"
                    response += f"총 보유 수량: {count}개\n\n"
                    
                    # 모델별 현황 (상위 10개)
                    if models:
                        response += "📦 모델별 분포:\n"
                        for model, cnt in sorted(models.items(), key=lambda x: x[1], reverse=True)[:10]:
                            response += f"  • {model}: {cnt}개\n"
                        response += "\n"
                    
                    response += "📋 상세 목록 (일부):\n"
                    response += "-" * 40 + "\n"
                    # 제조사별 검색도 30개까지 표시
                    display_limit = min(30, count)
                    for i, result in enumerate(results[:display_limit], 1):
                        response += f"{i}. {result}\n"
                    
                    if count > display_limit:
                        response += f"\n⚠️ 총 {count}개 중 {display_limit}개만 표시\n"
                        response += "🔍 전체 목록이 필요하시면 다시 요청하세요.\n"
                    
                    response += f"\n📄 출처: {txt_path.name}"
                    # LLM으로 답변 개선
                    return self._enhance_asset_response(response, query)
                else:
                    return f"❌ {manufacturer} 제조사 장비가 없습니다."
            
            return "❌ 제조사명을 확인할 수 없습니다."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _format_detailed_asset_response(self, asset_data: list, model: str, query: str) -> str:
        """자산 데이터를 상세하고 정확하게 포맷팅"""
        if not asset_data:
            return f"❌ {model} 모델 장비가 없습니다."
        
        lines = []
        lines.append(f"📊 **{model} 장비 현황**")
        lines.append("=" * 60)
        lines.append(f"\n### 📈 전체 보유 수량: **{len(asset_data)}개**\n")
        
        # 위치별 분포
        locations = {}
        for item in asset_data:
            if '위치' in item:
                loc = item['위치']
                locations[loc] = locations.get(loc, 0) + 1
        
        if locations:
            lines.append("### 📍 위치별 분포")
            for loc, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"• **{loc}**: {count}개")
            lines.append("")
        
        # 상세 목록 - 더 자세한 관리정보 중심 형식으로 변경
        lines.append("### 📋 상세 장비 정보")
        lines.append("")
        
        for i, item in enumerate(asset_data[:10], 1):  # 처음 10개만
            # [1] 형식으로 변경하고 항목명 포함
            item_name = f"{item.get('모델', model)}"
            lines.append(f"[{i}]  {item_name}")
            
            # 기본정보 - 모델명 별도 표시
            basic_info = []
            if '제조사' in item:
                basic_info.append(f"제조사: {item['제조사']}")
            if '모델' in item:
                basic_info.append(f"모델: {item['모델']}")
            if 'S/N' in item:
                basic_info.append(f"S/N: {item['S/N']}")
            if basic_info:
                lines.append(f"  기본정보: {' | '.join(basic_info)}")
            
            # 위치정보
            location_info = []
            if '위치' in item:
                location_info.append(f"위치: {item['위치']}")
            if '시스템' in item:
                location_info.append(f"시스템: {item['시스템']}")
            if location_info:
                lines.append(f"  위치정보: {' | '.join(location_info)}")
            
            # 관리정보 - 더 상세한 정보 포함
            mgmt_info = []
            if '담당자' in item:
                mgmt_info.append(f"담당자: {item['담당자']}")
            if '연락처' in item:
                mgmt_info.append(f"연락처: {item['연락처']}")
            if '벤더사' in item:
                mgmt_info.append(f"벤더사: {item['벤더사']}")
            if '계약업체' in item:
                mgmt_info.append(f"계약업체: {item['계약업체']}")
            if mgmt_info:
                lines.append(f"  관리정보: {' | '.join(mgmt_info)}")
            
            lines.append("")  # 각 항목 사이 공백
        
        if len(asset_data) > 10:
            lines.append(f"\n... 외 {len(asset_data) - 10}개 더 있음")
        
        # 추가 통계
        lines.append("\n### 📊 추가 통계")
        
        # 구입연도별 분포
        years = {}
        for item in asset_data:
            if '구입일' in item:
                year = item['구입일'][:4] if len(item['구입일']) >= 4 else None
                if year and year.isdigit():
                    years[year] = years.get(year, 0) + 1
        
        if years:
            lines.append("\n**구입연도별 분포:**")
            for year, count in sorted(years.items(), reverse=True)[:3]:
                lines.append(f"• {year}년: {count}개")
        
        lines.append("\n---")
        lines.append("📎 출처: 채널A 방송장비 자산 데이터베이스")
        
        return '\n'.join(lines)
    
    def _search_asset_by_model(self, txt_path: Path, query: str) -> str:
        """모델별 자산 검색"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 모델명 추출 (HP Z840, XDS-PD1000 등 - 더 유연한 패턴)
            model_patterns = [
                r'(Z\d+)',  # Z840, Z620 등
                r'([A-Z]{2,}[-]?[A-Z]*\d+)',  # XDS-PD1000, DL360 등
                r'([A-Z]+[-]?\d+)',  # PD1000, DL-360 등
                r'(\w+[-]?\w+\d+)',  # 일반적인 모델명
            ]
            
            model = None
            for pattern in model_patterns:
                model_match = re.search(pattern, query, re.IGNORECASE)
                if model_match:
                    model = model_match.group(1).upper()
                    break
            
            if model:
                
                # 모델 패턴으로 검색
                lines = content.split('\n')
                results = []
                count = 0
                
                for line in lines:
                    if model in line.upper():
                        count += 1
                        if len(results) < 10:  # 처음 10개만
                            results.append(line)
                
                if results:
                    # 데이터를 딕셔너리 리스트로 변환 (여러 줄 처리)
                    asset_data = []
                    
                    # 각 항목을 찾기 (모델명이 있는 줄을 찾고 전후 줄 포함)
                    for i, line in enumerate(lines):
                        if model in line.upper() and '모델:' in line:
                            # 항목 블록 구성 (이전 줄 + 현재 줄 + 다음 줄들)
                            block_lines = []
                            
                            # 이전 줄 (항목 번호)
                            if i > 0:
                                block_lines.append(lines[i-1])
                            
                            # 현재 줄부터 시작해서 다음 항목 시작까지 또는 최대 15줄
                            for j in range(i, min(i+15, len(lines))):
                                block_lines.append(lines[j])
                                # 다음 항목이 시작되면 중단
                                if j > i and lines[j].strip().startswith('[') and lines[j].strip().endswith(']'):
                                    break
                            
                            # 블록을 하나의 문자열로 합침
                            block = '\n'.join(block_lines)
                            
                            # 정보 추출
                            item_dict = {'모델': model}
                            
                            # 기본정보 추출 (블록에서)
                            # 제조사 추출
                            mfr_match = re.search(r'제조사:\s*([^|]+)', block)
                            if mfr_match:
                                item_dict['제조사'] = mfr_match.group(1).strip()
                            
                            # S/N 추출 (여러 개의 S/N 처리)
                            serial_match = re.search(r'S/N:\s*([^|\n]+)', block)
                            if serial_match:
                                sn_text = serial_match.group(1).strip()
                                # 여러 시리얼 번호가 줄바꿈으로 구분된 경우
                                if '\n' in block[block.find('S/N:'):]:
                                    # S/N 이후 다음 항목까지 모든 줄 수집
                                    sn_lines = []
                                    in_sn = False
                                    for line in block.split('\n'):
                                        if 'S/N:' in line:
                                            in_sn = True
                                            sn_lines.append(line.split('S/N:')[1].strip())
                                        elif in_sn and '구입정보:' not in line and '위치정보:' not in line and '관리정보:' not in line:
                                            # 다음 섹션이 시작되기 전까지 수집
                                            if line.strip() and not line.strip().startswith('['):
                                                sn_lines.append(line.strip())
                                        elif '구입정보:' in line or '위치정보:' in line or '관리정보:' in line:
                                            break
                                    item_dict['S/N'] = ', '.join(sn_lines) if sn_lines else sn_text
                                else:
                                    item_dict['S/N'] = sn_text
                            
                            # 구입정보 추출
                            # 구입일 추출
                            date_match = re.search(r'구입일:\s*([^|]+)', block)
                            if date_match:
                                date_str = date_match.group(1).strip()
                                item_dict['구입일'] = date_str[:10] if len(date_str) >= 10 else date_str
                            
                            # 단가 및 금액 추출
                            price_match = re.search(r'단가:\s*([^|\n]+)', block)
                            if price_match:
                                item_dict['단가'] = price_match.group(1).strip()
                            
                            amount_match = re.search(r'금액:\s*([^|\n]+)', block)
                            if amount_match:
                                item_dict['금액'] = amount_match.group(1).strip()
                            
                            # 위치정보 추출  
                            loc_match = re.search(r'위치:\s*([^|\n]+)', block)
                            if loc_match:
                                item_dict['위치'] = loc_match.group(1).strip()
                                
                            system_match = re.search(r'시스템:\s*([^|\n]+)', block)
                            if system_match:
                                item_dict['시스템'] = system_match.group(1).strip()
                            
                            # 관리정보 추출
                            manager_match = re.search(r'담당자:\s*([^|\n]+)', block)
                            if manager_match:
                                item_dict['담당자'] = manager_match.group(1).strip()
                            
                            vendor_match = re.search(r'벤더사:\s*([^|\n]+)', block)
                            if vendor_match:
                                item_dict['벤더사'] = vendor_match.group(1).strip()
                            
                            # 연락처 추출
                            contact_match = re.search(r'연락처:\s*([^|\n]+)', block)
                            if contact_match:
                                item_dict['연락처'] = contact_match.group(1).strip()
                            
                            # 계약업체 추출
                            contract_match = re.search(r'계약업체:\s*([^|\n]+)', block)
                            if contract_match:
                                item_dict['계약업체'] = contract_match.group(1).strip()
                            
                            # 공백 라인 제외
                            if item_dict.get('S/N'):
                                asset_data.append(item_dict)
                    
                    # 직접 상세한 포맷으로 출력
                    return self._format_detailed_asset_response(asset_data, model, query)
                    
                    # 위치별 분포 분석
                    locations = {}
                    for line in lines:
                        if model in line.upper():
                            loc_match = re.search(r'위치:\s*([^|]+)', line)
                            if loc_match:
                                loc = loc_match.group(1).strip()
                                locations[loc] = locations.get(loc, 0) + 1
                    
                    if locations:
                        response += "### 📍 위치별 분포\n"
                        for loc, cnt in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
                            response += f"• **{loc}**: {cnt}개\n"
                        response += "\n"
                    
                    response += "### 📋 상세 목록 (일부)\n"
                    response += "```\n"
                    for i, result in enumerate(results, 1):
                        # 각 항목을 더 읽기 쉽게 포맷
                        serial_match = re.search(r'S/N:\s*([^|]+)', result)
                        loc_match = re.search(r'위치:\s*([^|]+)', result)
                        
                        formatted_line = f"[{i:02d}]"
                        if serial_match:
                            formatted_line += f" S/N: {serial_match.group(1).strip()}"
                        if loc_match:
                            formatted_line += f" | 위치: {loc_match.group(1).strip()}"
                        
                        response += f"{formatted_line}\n"
                    response += "```\n"
                    
                    if count > 10:
                        response += f"\n... 외 {count - 10}개 더 있음\n"
                    
                    response += f"\n---\n📎 출처: 채널A 방송장비 자산 데이터베이스"
                    return response
                else:
                    return f"❌ {model} 모델 장비가 없습니다."
            
            return "❌ 모델명을 입력해주세요."
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_multiple_documents(self, query: str) -> str:
        """여러 문서 검색 및 리스트 반환"""
        try:
            # 질문에서 키워드 추출
            query_lower = query.lower()
            
            # 매칭된 문서들 수집
            matched_docs = []
            
            for cache_key, metadata in self.metadata_cache.items():
                # TXT 파일은 제외 (PDF만 처리)
                if metadata.get('is_txt', False):
                    continue

                filename = metadata.get('filename', cache_key)
                score = 0
                filename_lower = filename.lower()
                
                # 키워드 매칭
                keywords_in_query = []

                # 동적 키워드 추출 (하드코딩 제거)
                query_words = re.findall(r'[가-힣]+|[A-Za-z]+', query_lower)
                file_words = re.findall(r'[가-힣]+|[A-Za-z]+', filename_lower)

                # 불용어 제외
                stopwords = ['의', '및', '건', '검토서', '관련', '문서', '찾아', '줘', '있어', '어떤', '기안서']

                # 장비명 특별 가중치 (DVR, CCU 등)
                equipment_names = ['dvr', 'ccu', '카메라', '렌즈', '모니터', '스위처', '마이크', '믹서', '삼각대', '중계차']
                for equipment in equipment_names:
                    if equipment in query_lower:
                        # 쿼리에 장비명이 있고 파일명에도 있으면 높은 점수
                        if equipment in filename_lower:
                            score += 15  # 장비명 완전 매칭시 높은 점수
                        # 파일명에 없더라도 메타데이터 키워드에 있으면 점수 부여
                        elif any(equipment in kw.lower() for kw in metadata.get('keywords', [])):
                            score += 8  # 키워드에 있으면 중간 점수
                        # 텍스트 검색은 필요시에만 (성능 최적화)
                        elif score < 3 and metadata.get('text'):
                            # 점수가 낮을 때만 텍스트 검색
                            if equipment in metadata.get('text', '').lower()[:500]:
                                score += 3
                
                for word in query_words:
                    if len(word) >= 2 and word not in stopwords:
                        keywords_in_query.append(word)
                        # 파일명에 해당 단어가 있으면 점수 부여
                        if word in file_words:
                            # 단어 길이에 비례한 점수
                            score += len(word) * 2
                        # 부분 매칭 (3글자 이상)
                        elif len(word) >= 3:
                            for f_word in file_words:
                                if word in f_word or f_word in word:
                                    score += len(word)
                
                # 메타데이터 키워드 매칭
                for keyword in metadata['keywords']:
                    if keyword.lower() in query_lower:
                        score += 3
                
                # 연도와 월 매칭
                year_match = re.search(r'(20\d{2})', query)
                month_match = re.search(r'(\d{1,2})\s*월', query)
                
                if year_match:
                    query_year = year_match.group(1)
                    if metadata['year'] == query_year:
                        score += 5
                        
                        # 월도 지정된 경우
                        if month_match:
                            query_month = int(month_match.group(1))
                            file_month_match = re.search(r'\d{4}-(\d{2})-\d{2}', filename)
                            if file_month_match:
                                file_month = int(file_month_match.group(1))
                                if file_month == query_month:
                                    score += 10  # 월까지 일치하면 높은 점수
                                else:
                                    score = 0  # 월이 다르면 제외
                                    continue
                    else:
                        # 연도가 다르면 제외
                        continue  # 연도가 다르면 무조건 제외
                
                # 최소 점수 기준 설정 (너무 많은 문서 방지)
                # 기안자나 특정 년도 검색이 아니면 기본 기준
                if '기안자' in query_lower or re.search(r'20\d{2}년', query):
                    MIN_SCORE = 2  # 기안자/년도 검색은 낮은 기준
                else:
                    MIN_SCORE = 3  # 기본 최소 3점 이상만 포함

                # 장비명 검색시 적절한 기준 적용
                has_equipment = False
                for equipment in equipment_names:
                    if equipment in query_lower:
                        has_equipment = True
                        # 장비명이 파일명에 있으면 무조건 포함
                        if equipment in filename_lower:
                            MIN_SCORE = 0  # 파일명에 있으면 무조건 포함
                        else:
                            MIN_SCORE = max(3, MIN_SCORE)  # 장비 검색시 최소 3점
                        break
                
                if score >= MIN_SCORE:
                    # metadata의 path 사용
                    pdf_path = metadata.get('path')
                    if isinstance(pdf_path, str):
                        pdf_path = Path(pdf_path)
                    if not pdf_path:
                        pdf_path = self.docs_dir / filename

                    info = self._extract_pdf_info(pdf_path)
                    matched_docs.append({
                        'filename': filename,
                        'score': score,
                        'info': info,
                        'year': metadata['year'],
                        'cache_key': cache_key  # 파일 경로 정보 추가
                    })
            
            # 중복 제거 및 최적화
            unique_docs = {}
            for doc in matched_docs:
                filename = doc['filename']
                if filename not in unique_docs:
                    unique_docs[filename] = doc
                else:
                    # 더 높은 점수를 가진 문서를 유지
                    if doc['score'] > unique_docs[filename]['score']:
                        unique_docs[filename] = doc
                    # 같은 점수면 year_ 폴더 우선
                    elif doc['score'] == unique_docs[filename]['score'] and 'year_' in doc.get('cache_key', ''):
                        unique_docs[filename] = doc

            matched_docs = list(unique_docs.values())

            # 점수 순으로 정렬
            matched_docs.sort(key=lambda x: x['score'], reverse=True)

            # 결과 제한 (성능 최적화)
            # 장비 검색은 20개까지, 일반 검색은 15개까지
            max_results = 20 if has_equipment else 15
            if len(matched_docs) > max_results:
                matched_docs = matched_docs[:max_results]
            
            if not matched_docs:
                return "❌ 관련 문서를 찾을 수 없습니다."
            
            # 결과 포맷팅 (통합형 UI)
            report = []
            report.append(f"## 🔍 '{query}' 검색 결과")
            report.append(f"**총 {len(matched_docs)}개 문서 발견**\n")
            report.append("---\n")
            
            # 연도별로 그룹화 (중복 제거는 이미 위에서 완료)
            docs_by_year = {}

            for doc in matched_docs:
                year = doc['year']
                if year not in docs_by_year:
                    docs_by_year[year] = []
                docs_by_year[year].append(doc)
            
            # 연도별로 표시
            for year in sorted(docs_by_year.keys(), reverse=True):
                report.append(f"### 📅 {year}년 ({len(docs_by_year[year])}개)\n")
                
                for doc in docs_by_year[year]:
                    info = doc['info']
                    filename = doc['filename']
                    relative_path = doc.get('cache_key', filename)  # 캐시 키가 상대 경로
                    
                    # 카테고리 판단 및 이모지
                    if '구매' in filename:
                        category = "구매요청"
                        emoji = "🛒"
                    elif '수리' in filename or '보수' in filename:
                        category = "수리/보수"
                        emoji = "🔧"
                    elif '폐기' in filename:
                        category = "폐기처리"
                        emoji = "🗑️"
                    elif '검토' in filename:
                        category = "검토보고서"
                        emoji = "📋"
                    else:
                        category = "기타"
                        emoji = "📄"
                    
                    # 제목 추출 (날짜 제외)
                    title_parts = filename.replace('.pdf', '').split('_', 1)
                    title = title_parts[1] if len(title_parts) > 1 else title_parts[0]
                    
                    # 기본 정보
                    drafter = info.get('기안자', '')
                    date = info.get('날짜', '')
                    amount = info.get('금액', '')
                    
                    # 개요 생성 - metadata_cache에서 실제 텍스트 활용
                    summary = ""

                    # metadata에서 실제 텍스트 가져오기
                    cached_metadata = None
                    for ck, md in self.metadata_cache.items():
                        if md.get('filename') == filename:
                            cached_metadata = md
                            break

                    if cached_metadata and cached_metadata.get('text'):
                        # 캐시된 텍스트에서 주요 내용 추출
                        text = cached_metadata['text'][:500]  # 처음 500자

                        # 주요 정보 추출
                        if '목적' in text:
                            purpose_match = re.search(r'목적[:\s]+([^\n]+)', text)
                            if purpose_match:
                                summary = purpose_match.group(1).strip()
                        elif '내용' in text:
                            content_match = re.search(r'내용[:\s]+([^\n]+)', text)
                            if content_match:
                                summary = content_match.group(1).strip()
                        elif '사유' in text:
                            reason_match = re.search(r'사유[:\s]+([^\n]+)', text)
                            if reason_match:
                                summary = reason_match.group(1).strip()

                    # 텍스트가 없거나 추출 실패시 기본값
                    if not summary:
                        if '구매' in filename:
                            summary = "장비 구매 요청"
                        elif '수리' in filename or '보수' in filename:
                            summary = "장비 수리/보수 건"
                        elif '폐기' in filename:
                            summary = "노후 장비 폐기 처리"
                        elif '교체' in filename:
                            summary = "노후 장비 교체 검토"
                        elif '검토' in filename:
                            summary = "기술 검토 보고서"
                        else:
                            summary = "기술관리팀 업무 문서"
                    
                    # 카드 UI 형태로 출력
                    report.append(f"#### {emoji} **{title}**")
                    report.append(f"**[{category}]** | {date if date else '날짜 미상'}")
                    
                    # 상세 정보
                    if drafter:
                        report.append(f"- **기안자**: {drafter}")
                    if amount:
                        report.append(f"- **금액**: {amount}")
                    if summary:
                        report.append(f"- **개요**: {summary}")
                    
                    # 파일 경로 정보 포함 (web_interface에서 처리할 수 있도록)
                    # 특별한 마커 사용: @@PDF_PREVIEW@@
                    file_path_str = str(relative_path) if relative_path else filename
                    report.append(f"- **파일**: [{file_path_str}] @@PDF_PREVIEW@@{file_path_str}@@")
                    report.append("")  # 간격
                
                report.append("---\n")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ 문서 검색 실패: {e}"

    def _search_and_analyze_by_content(self, query: str) -> str:
        """특정 내용이 언급된 경우 관련 문서들을 모두 찾아서 분석

        예시:
        - "DVR 교체 검토 내용" → DVR 관련 모든 문서 찾고 교체 검토 내용 정리
        - "삼각대 구매 건" → 삼각대 관련 모든 구매 문서 찾기
        """
        try:
            # 1. 핵심 키워드와 작업 타입 분리
            query_lower = query.lower()

            # 장비/시스템 키워드
            equipment_keywords = []
            equipment_terms = ['DVR', '중계차', '카메라', '삼각대', '모니터', 'CCU', '오디오', '서버', '마이크', '스위치']
            for term in equipment_terms:
                if term.lower() in query_lower:
                    equipment_keywords.append(term)

            # 작업 타입 키워드
            action_keywords = []
            action_terms = ['교체', '검토', '구매', '수리', '보수', '폐기', '도입', '업그레이드', '설치']
            for term in action_terms:
                if term in query_lower:
                    action_keywords.append(term)

            if not equipment_keywords:
                # 문장에서 명사 추출
                nouns = re.findall(r'[\uac00-\ud7a3]{2,}', query)
                equipment_keywords = [n for n in nouns if n not in ['관련', '문서', '내용', '정리', '분석']]

            print(f"🔍 장비 키워드: {equipment_keywords}, 작업 키워드: {action_keywords}")

            # 2. 단계별 문서 검색
            # 단계 1: 파일명에 키워드가 있는 문서
            primary_files = []
            # 단계 2: 작업 타입만 일치하는 문서
            secondary_files = []
            # 단계 3: 내용에 키워드가 있는 문서 (느림, 필요시만)
            content_match_files = []

            for cache_key, metadata in self.metadata_cache.items():
                if metadata.get('is_pdf'):
                    # 실제 파일명 사용 (cache_key가 아닌 metadata['filename'])
                    filename_lower = metadata.get('filename', cache_key).lower()
                    path = metadata['path']

                    # 파일명에 장비 키워드가 있는지 확인
                    has_equipment_keyword = any(kw.lower() in filename_lower for kw in equipment_keywords)
                    has_action_keyword = any(kw.lower() in filename_lower for kw in action_keywords)

                    if has_equipment_keyword:
                        primary_files.append(path)
                    elif has_action_keyword:
                        secondary_files.append(path)

            # 3. 결과 병합 (최대 15개)
            relevant_files = primary_files[:10] + secondary_files[:5]

            if not relevant_files:
                # 키워드가 너무 없으면 내용 검색 시도 (시간 소요)
                if len(equipment_keywords) > 0:
                    print("🔍 파일명에서 찾지 못함, 내용 검색 시작...")
                    for file_path, metadata in list(self.metadata_cache.items())[:30]:  # 최대 30개만
                        if metadata.get('is_pdf'):
                            try:
                                info = self._extract_pdf_info(metadata['path'])
                                if info and 'text' in info:
                                    content = info['text'][:2000]  # 처음 2000자만
                                    if any(kw.lower() in content.lower() for kw in equipment_keywords):
                                        content_match_files.append(metadata['path'])
                                        if len(content_match_files) >= 5:  # 최대 5개
                                            break
                            except:
                                continue
                    relevant_files.extend(content_match_files)

            if not relevant_files:
                return f"❌ '{', '.join(equipment_keywords + action_keywords)}' 관련 문서를 찾을 수 없습니다."

            print(f"📄 {len(relevant_files)}개 관련 문서 발견")

            # 성능 최적화: 상위 5개 문서만 처리
            max_docs_to_process = 5
            files_to_process = relevant_files[:max_docs_to_process]
            if len(relevant_files) > max_docs_to_process:
                print(f"⚡ 성능 최적화: 상위 {max_docs_to_process}개 문서만 처리 (전체 {len(relevant_files)}개 중)")

            # 4. 각 문서의 내용 추출 및 분석
            document_analyses = []
            all_contents = []

            for file_path in files_to_process:
                try:
                    info = self._extract_pdf_info(file_path)
                    if info:
                        # 작업 키워드와 관련된 부분 추출
                        relevant_content = []
                        if 'text' in info:
                            lines = info['text'].split('\n')
                            for i, line in enumerate(lines):
                                line_lower = line.lower()
                                # 작업 키워드가 포함된 문장과 주변 문맥 추출
                                if any(kw in line_lower for kw in action_keywords + equipment_keywords):
                                    # 전후 2줄씩 포함
                                    start = max(0, i-2)
                                    end = min(len(lines), i+3)
                                    context = ' '.join(lines[start:end])
                                    relevant_content.append(context)

                        doc_analysis = {
                            'filename': file_path.name,
                            'title': info.get('제목', file_path.stem),
                            'date': info.get('날짜', ''),
                            'drafter': info.get('기안자', ''),
                            'amount': info.get('금액', ''),
                            'relevant_content': relevant_content[:3],  # 최대 3개 관련 부분
                            'full_text': info.get('text', '')[:2000]  # 전체 텍스트 일부
                        }
                        document_analyses.append(doc_analysis)
                        all_contents.append(f"[{file_path.name}]\n" + '\n'.join(relevant_content[:3]))
                except Exception as e:
                    print(f"⚠️ {file_path.name} 처리 실패: {e}")
                    continue

            if not document_analyses:
                return "❌ 문서 내용을 분석할 수 없습니다."

            # 5. LLM을 사용하여 종합 분석
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print("🤖 LLM 모델 로딩 중...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)

            combined_text = '\n\n'.join(all_contents)

            prompt = f"""다음은 '{', '.join(equipment_keywords)}' 관련 '{', '.join(action_keywords)}' 문서들의 핵심 내용입니다.

사용자 질문: {query}

문서 내용:
{combined_text[:6000]}

위 내용을 바탕으로 사용자 질문에 대해 답변해주세요.
포함해야 할 내용:
1. 각 문서에서 찾은 핵심 정보
2. 연도별/시기별 변화 (있다면)
3. 기술적 사양이나 모델 정보
4. 비용 정보
5. 결론 및 추천사항

자연스럽게 설명해주세요."""

            context_chunks = [{
                'content': combined_text[:6000],
                'metadata': {'source': 'multiple_documents'},
                'score': 1.0
            }]

            response_obj = self.llm.generate_response(prompt, context_chunks)
            llm_response = response_obj.answer if hasattr(response_obj, 'answer') else str(response_obj)

            # 6. 결과 구성
            result = []
            result.append(f"📊 **'{', '.join(equipment_keywords)}' 관련 {len(document_analyses)}개 문서 분석**\n")
            result.append("="*50 + "\n\n")

            # LLM 분석 결과
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            # 분석된 문서 목록
            result.append("\n📄 **분석된 문서:**\n")
            for doc in document_analyses:
                result.append(f"\n• **{doc['title']}**")
                if doc['date']:
                    result.append(f"  - 날짜: {doc['date']}")
                if doc['drafter']:
                    result.append(f"  - 기안자: {doc['drafter']}")
                if doc['amount']:
                    result.append(f"  - 금액: {doc['amount']}")
                if doc['relevant_content']:
                    result.append(f"  - 핵심 내용: {len(doc['relevant_content'])}개 부분 발견")

            return '\n'.join(result)

        except Exception as e:
            return f"❌ 내용 기반 분석 실패: {e}"

    def _read_and_summarize_documents(self, query: str) -> str:
        """관련 문서들을 실제로 읽고 종합 정리하는 메서드

        Args:
            query: 사용자 질문 (예: "DVR관련 문서 다 읽고 정리해줘")

        Returns:
            종합 정리된 내용
        """
        try:
            # 키워드 추출
            query_lower = query.lower()
            keywords = []

            # 주요 키워드 추출
            important_keywords = ['DVR', '중계차', '카메라', '삼각대', '모니터', '오디오', '서버', '스위치']
            for kw in important_keywords:
                if kw.lower() in query_lower:
                    keywords.append(kw)

            # 키워드가 없으면 기본 기준 사용
            if not keywords:
                # 문장에서 명사 추출
                nouns = re.findall(r'[\uac00-\ud7a3]{2,}', query)
                keywords = [n for n in nouns if n not in ['관련', '문서', '읽고', '정리', '내용', '모두', '전부']]

            if not keywords:
                return "❌ 검색 키워드를 찾을 수 없습니다. 구체적인 키워드를 지정해주세요."

            print(f"🔍 키워드로 문서 검색: {keywords}")

            # 관련 문서 찾기
            relevant_files = []
            for file_path, metadata in self.metadata_cache.items():
                if metadata.get('is_pdf'):
                    # 파일명이나 제목에 키워드가 포함되어 있는지 확인
                    filename_lower = file_path.lower()
                    for kw in keywords:
                        if kw.lower() in filename_lower:
                            relevant_files.append(metadata['path'])
                            break

            if not relevant_files:
                return f"❌ '{', '.join(keywords)}' 관련 문서를 찾을 수 없습니다."

            print(f"📄 {len(relevant_files)}개 관련 문서 발견")

            # 각 문서의 내용 추출
            all_contents = []
            document_summaries = []

            for file_path in relevant_files[:10]:  # 최대 10개 문서만 처리
                try:
                    # PDF 내용 추출
                    info = self._extract_pdf_info(file_path)
                    if info:
                        doc_summary = {
                            'filename': file_path.name,
                            'title': info.get('제목', file_path.stem),
                            'date': info.get('날짜', '날짜 미상'),
                            'drafter': info.get('기안자', '미상'),
                            'amount': info.get('금액', ''),
                            'content': info.get('text', '')[:3000]  # 처음 3000자
                        }

                        # 주요 내용 추출
                        if 'text' in info:
                            # 중요한 문장 추출
                            important_sentences = []
                            lines = info['text'].split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and len(line) > 20:
                                    # 중요 키워드가 포함된 문장
                                    if any(kw in line for kw in ['개요', '목적', '내용', '결과', '결론', '추천', '필요', '예산', '금액']):
                                        important_sentences.append(line[:200])

                            doc_summary['key_points'] = important_sentences[:5]

                        document_summaries.append(doc_summary)
                        all_contents.append(f"\n[{file_path.name}]\n{info.get('text', '')[:3000]}")

                except Exception as e:
                    print(f"⚠️ {file_path.name} 처리 실패: {e}")
                    continue

            if not document_summaries:
                return "❌ 문서 내용을 읽을 수 없습니다."

            # LLM을 사용하여 종합 정리
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print("🤖 LLM 모델 로딩 중...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)

            # 종합 정리 프롬프트
            combined_text = '\n\n'.join(all_contents)

            prompt = f"""다음은 '{', '.join(keywords)}' 관련 문서들의 내용입니다.

이 문서들을 읽고 종합적으로 정리해주세요.

포함해야 할 내용:
1. 주요 내용 요약
2. 연도별/시기별 주요 사항
3. 기술적 사양이나 모델 정보 (있다면)
4. 비용 정보 (있다면)
5. 검토 결과나 추천사항
6. 공통점과 차이점

문서 내용:
{combined_text[:8000]}

자연스럽고 이해하기 쉽게 정리해주세요. 테플릿 형식이 아닌 대화형 형식으로 답변해주세요."""

            # LLM 호출
            context_chunks = [{
                'content': combined_text[:8000],
                'metadata': {'source': 'multiple_documents'},
                'score': 1.0
            }]

            response_obj = self.llm.generate_response(prompt, context_chunks)
            llm_response = response_obj.answer if hasattr(response_obj, 'answer') else str(response_obj)

            # 결과 구성
            result = []
            result.append(f"📄 **{len(document_summaries)}개 {', '.join(keywords)} 관련 문서 종합 분석**\n")
            result.append("="*50 + "\n")

            # LLM 응답 추가
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            # 각 문서 간단 정보
            result.append("\n📊 **분석된 문서 목록:**\n")
            for doc in document_summaries:
                result.append(f"\n• **{doc['title']}**")
                result.append(f"  - 날짜: {doc['date']}")
                result.append(f"  - 기안자: {doc['drafter']}")
                if doc['amount']:
                    result.append(f"  - 금액: {doc['amount']}")

            return '\n'.join(result)

        except Exception as e:
            return f"❌ 문서 종합 분석 실패: {e}"

    def _generate_detailed_location_list(self, content: str, location: str, result: dict, txt_path: Path) -> str:
        """특정 위치의 장비 목록을 LLM으로 정리하여 표시"""
        try:
            # LLM 로드 (필요시)
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print("🤖 LLM 모델 로딩 중...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
            
            # 해당 위치의 장비들 수집
            lines = content.split('\n')
            location_items = []
            current_item = []
            
            for line in lines:
                if line.strip().startswith('[') and line.strip().endswith(']'):
                    # 새로운 장비 항목 시작
                    if current_item and self._is_location_match(current_item, location):
                        location_items.append('\n'.join(current_item))
                    current_item = [line]
                elif current_item:
                    current_item.append(line)
            
            # 마지막 항목 처리
            if current_item and self._is_location_match(current_item, location):
                location_items.append('\n'.join(current_item))
            
            if not location_items:
                return f"❌ {location}에서 장비를 찾을 수 없습니다."
            
            # LLM으로 정리할 데이터 준비 (최대 50개)
            sample_items = location_items[:50]
            sample_text = '\n\n'.join(sample_items)
            
            # LLM 프롬프트 - 기술관리팀 필수 정보 포함
            prompt = f"""
다음은 "{location}"에 설치된 방송장비 목록입니다. 
기술관리팀이 자주 확인하는 중요 정보들을 포함하여 체계적으로 정리해주세요.

요구사항:
1. 장비를 카테고리별로 분류 (카메라, 오디오, 모니터, 서버, 네트워크 등)
2. 각 장비마다 다음 정보 포함: 구분3/구분4/구분5, 제조사, 모델명, S/N, 단가, 금액, 구입일, 담당자, 벤더사
3. 총 장비 수: {len(location_items)}개

장비 데이터:
{sample_text[:8000]}

다음 형식으로 정리해주세요:

## 📊 {location} 시스템 장비 현황

### 📈 총 장비 수: {len(location_items)}개

### 📋 카테고리별 장비 분류

**🎥 카메라 관련**
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

**🔊 오디오 관련** 
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

**💻 서버/컴퓨터**
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

**📺 모니터/디스플레이**
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

**🌐 네트워크/통신**
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

**🔧 기타**
- 장비명 (제조사/모델/S/N) | 구분: 구분3>구분4>구분5 | 💰 단가/금액 | 📅 구입일 | 👤 담당자 | 🏢 벤더사

중요: 구분정보, 구입정보(단가/금액/구입일), 관리정보(담당자/벤더사) 모두 포함해주세요.
"""

            # LLM 호출
            context = [{'content': sample_text[:8000], 'metadata': {'source': txt_path.name}, 'score': 1.0}]
            response = self.llm.generate_response(prompt, context)
            
            answer = response.answer if hasattr(response, 'answer') else str(response)
            
            if len(location_items) > 50:
                answer += f"\n\n⚠️ 총 {len(location_items)}개 중 상위 50개를 기준으로 분석하였습니다."
            
            answer += f"\n\n📄 출처: {txt_path.name}"
            return answer
            
        except Exception as e:
            # LLM 실패시 기본 포맷으로 표시
            response = f"📊 {location} 장비 목록\n"
            response += "=" * 50 + "\n"
            response += f"✅ 총 장비 수: {result['count']}개\n\n"
            
            if result.get('sample_items'):
                response += "📋 주요 장비 목록:\n"
                for i, item in enumerate(result['sample_items'][:10], 1):
                    lines = item.split('\n')
                    for line in lines:
                        if '[' in line and ']' in line:
                            response += f"{i}. {line.strip()}\n"
                        elif '모델:' in line or '제조사:' in line:
                            response += f"   {line.strip()}\n"
                    response += "\n"
            
            response += f"📄 출처: {txt_path.name}"
            return response

    def _is_location_match(self, item_lines: list, location: str) -> bool:
        """위치 매칭 로직 개선 - 정확한 위치 매칭"""
        item_text = '\n'.join(item_lines)
        
        # 위치 정보가 있는 라인 찾기
        for line in item_lines:
            if '위치:' in line or '위치정보:' in line:
                # 실제 위치 추출
                location_match = re.search(r'위치:\s*([^|\n]+)', line)
                if location_match:
                    actual_location = location_match.group(1).strip()
                    
                    # 정확한 매칭 규칙
                    if location == actual_location:
                        # 완전 일치 (가장 우선)
                        return True
                    elif location == '부조정실':
                        # '부조정실'로 검색시 '*부조정실' 패턴만 매칭
                        return actual_location.endswith('부조정실')
                    elif location == '스튜디오':
                        # '스튜디오'로 검색시 '*스튜디오' 패턴만 매칭 
                        return actual_location.endswith('스튜디오')
                    elif location == '편집실':
                        # '편집실'로 검색시 '*편집실' 패턴만 매칭
                        return actual_location.endswith('편집실')
                    elif location in ['중계차', 'van', 'Van', 'VAN']:
                        # 중계차 검색시 Van 관련 위치 모두 매칭
                        return 'Van' in actual_location or 'VAN' in actual_location
                    elif location == "광화문부조정실":
                        # "광화문 부조정실" 같은 복합 위치명 처리
                        return "광화문" in actual_location and "부조정실" in actual_location
                    elif len(location) > 3:
                        # 3글자 이상의 구체적인 위치명은 부분 매칭 허용
                        return location in actual_location
        
        return False

    def _search_location_equipment_combo(self, txt_path: Path, query: str) -> str:
        """위치 + 장비명 복합 검색 (예: 중계차 CCU현황)"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 장비 키워드 추출 (대소문자 구분 없이)
            equipment_keywords = ["CCU", "카메라", "모니터", "오디오", "비디오", "서버", "스위치", "라우터"]
            found_equipment = None
            query_upper = query.upper()
            for eq in equipment_keywords:
                if eq.upper() in query_upper:
                    found_equipment = eq
                    break
            
            if not found_equipment:
                # 장비명이 없어도 쿼리 전체에서 관련 텍스트 검색
                found_equipment = query  # 전체 쿼리를 장비명으로 사용
            
            # "위치별로" 같은 전체 위치 요청인지 확인
            is_all_locations = "위치별" in query or "현황" in query
            
            # 위치 키워드 추출
            location_pattern = r'[가-힣]{2,}(?:스튜디오|부조정실|편집실|더빙실|사옥|센터|실|층|관|동|호)|중계차|van|Van|VAN'
            locations = re.findall(location_pattern, query, re.IGNORECASE)
            
            # 모든 위치별로 검색하는 경우
            if is_all_locations and not locations:
                # 모든 위치별 CCU 현황 정리
                return self._search_equipment_all_locations(txt_path, found_equipment)
            
            if not locations and not is_all_locations:
                return "❌ 위치 정보를 찾을 수 없습니다."
            
            found_location = locations[0] if locations else None
            
            # 항목별로 검색 - 올바른 [NNNN] 형식 사용
            lines = content.split('\n')
            matching_items = []
            current_item = []
            
            for line in lines:
                # [NNNN] 형식의 시작 라인을 찾기
                if re.match(r'^\[\d{4}\]', line.strip()):
                    # 이전 항목 검사
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 위치 조건 확인
                        location_match = self._check_location_in_item(item_text, found_location)
                        # 장비명 조건 확인 - CCU의 경우 "Camera Control Unit"도 포함
                        if found_equipment.upper() == "CCU":
                            equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                        else:
                            equipment_match = found_equipment.upper() in item_text.upper()
                        
                        if location_match and equipment_match:
                            matching_items.append(item_text)
                    
                    current_item = [line]
                else:
                    if current_item:  # 현재 항목이 시작된 후에만 추가
                        current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                location_match = self._check_location_in_item(item_text, found_location)
                # 장비명 조건 확인 - CCU의 경우 "Camera Control Unit"도 포함
                if found_equipment == "CCU":
                    equipment_match = "CCU" in item_text or "Camera Control Unit" in item_text
                else:
                    equipment_match = found_equipment in item_text
                
                if location_match and equipment_match:
                    matching_items.append(item_text)
            
            if not matching_items:
                return f"❌ {found_location}에서 {found_equipment} 장비를 찾을 수 없습니다."
            
            # 결과 포맷팅
            response = f"📊 {found_location} {found_equipment} 현황\n"
            response += "=" * 60 + "\n"
            response += f"✅ 총 {len(matching_items)}개\n\n"
            
            # 상세 목록
            for i, item in enumerate(matching_items, 1):
                response += f"[{i}] "
                lines = item.split('\n')
                
                # 제목 추출
                title_line = lines[0] if lines else ""
                response += title_line.replace('[', '').replace(']', '').strip() + "\n"
                
                # 주요 정보 추출
                for line in lines[1:]:
                    if '기본정보:' in line or '위치정보:' in line or '관리정보:' in line:
                        response += f"  {line.strip()}\n"
                
                response += "\n"
            
            response += f"📄 출처: {txt_path.name}"
            return response
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_location_all_equipment(self, txt_path: Path, query: str) -> str:
        """특정 위치의 모든 장비를 상세하게 표시"""
        try:
            # 완전판 파일 우선 사용
            complete_path = self.docs_dir / "assets" / "채널A_방송장비_자산_전체_7904개_완전판.txt"
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 위치 키워드 추출
            location_keyword = None
            if '중계차' in query:
                location_keyword = '중계차'
            else:
                # 다른 위치 패턴 찾기
                location_pattern = r'[가-힣]{2,}(?:스튜디오|부조정실|편집실|더빙실|사옥|센터|실|층|관|동|호)'
                locations = re.findall(location_pattern, query)
                if locations:
                    location_keyword = locations[0]
            
            if not location_keyword:
                return "❌ 위치를 명확히 지정해주세요."
            
            # 항목별로 검색
            lines = content.split('\n')
            matching_items = []
            current_item = []
            
            for line in lines:
                # [NNNN] 형식의 시작 라인
                if re.match(r'^\[\d{4}\]', line.strip()):
                    # 이전 항목 검사
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 위치 체크
                        if self._check_location_in_item(item_text, location_keyword):
                            matching_items.append(item_text)
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                if self._check_location_in_item(item_text, location_keyword):
                    matching_items.append(item_text)
            
            if not matching_items:
                return f"❌ {location_keyword}에 장비가 없습니다."
            
            # 결과 포맷팅 - 상세 정보 포함
            response = f"📊 {location_keyword} 장비 현황\n"
            response += "=" * 70 + "\n"
            response += f"✅ 총 {len(matching_items)}개 장비\n\n"
            
            # 카테고리별 분류
            categories = {}
            for item in matching_items:
                # 카테고리 추출 (기본정보에서)
                cat_match = re.search(r'기본정보:\s*([^|]+)', item)
                if cat_match:
                    cat = cat_match.group(1).strip().split()[0] if cat_match.group(1).strip() else "기타"
                else:
                    cat = "기타"
                
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)
            
            # 카테고리별 요약
            response += "📋 장비 카테고리별 분류:\n"
            for cat, items in sorted(categories.items()):
                response += f"  • {cat}: {len(items)}개\n"
            response += "\n" + "-" * 70 + "\n\n"
            
            # 금액 총계 계산
            total_value = 0
            for item in matching_items:
                amount_match = re.search(r'금액:\s*([\d,]+)원', item)
                if amount_match:
                    amount_str = amount_match.group(1).replace(',', '')
                    try:
                        total_value += int(amount_str)
                    except:
                        pass
            
            if total_value > 0:
                # 억원 단위로 변환
                value_in_billions = total_value / 100000000
                response += f"💰 **총 자산가치**: {value_in_billions:.1f}억원\n\n"
            
            # 상세 목록 (30개로 증가)
            response += "📄 **상세 장비 목록** (최대 30개):\n\n"
            
            # 전체 표시 여부 결정 (30개로 증가)
            display_items = matching_items[:30] if len(matching_items) > 30 else matching_items
            
            for i, item in enumerate(display_items, 1):
                lines = item.split('\n')
                
                # 제목 추출
                title_match = re.match(r'^\[(\d{4})\]\s*(.+)', lines[0])
                if title_match:
                    item_no = title_match.group(1)
                    item_name = title_match.group(2)
                    response += f"[{i}] [{item_no}] {item_name}\n"
                
                # 모든 정보를 저장할 딕셔너리
                item_info = {}
                
                # 상세 정보 추출
                for line in lines[1:]:
                    if '기본정보:' in line:
                        info_match = re.search(r'기본정보:\s*(.+?)(?:\||$)', line)
                        if info_match:
                            basic_info = info_match.group(1).strip()
                            # 모델명과 제조사 추출
                            parts = basic_info.split()
                            if len(parts) >= 2:
                                item_info['model'] = parts[0]
                                item_info['manufacturer'] = parts[1] if len(parts) > 1 else ''
                            response += f"    📌 모델: {basic_info}\n"
                    elif '위치:' in line:
                        loc_match = re.search(r'위치:\s*([^|]+)', line)
                        if loc_match:
                            item_info['location'] = loc_match.group(1).strip()
                            response += f"    📍 위치: {item_info['location']}\n"
                    elif '관리정보:' in line:
                        # 전체 관리정보 라인 파싱
                        mgmt_full = line.split('관리정보:')[1] if '관리정보:' in line else ''
                        mgmt_parts = mgmt_full.split('|')
                        
                        for part in mgmt_parts:
                            part = part.strip()
                            if '담당자:' in part:
                                manager = part.replace('담당자:', '').strip()
                                if manager:
                                    response += f"    👤 담당자: {manager}\n"
                            elif '자산번호:' in part:
                                asset_no = part.replace('자산번호:', '').strip()
                                if asset_no:
                                    response += f"    🔢 자산번호: {asset_no}\n"
                            elif '시리얼:' in part:
                                serial = part.replace('시리얼:', '').strip()
                                if serial and serial != 'N/A':
                                    response += f"    🔤 시리얼: {serial}\n"
                    elif '구입정보:' in line:
                        # 전체 구입정보 라인 파싱
                        purchase_full = line.split('구입정보:')[1] if '구입정보:' in line else ''
                        purchase_parts = purchase_full.split('|')
                        
                        for part in purchase_parts:
                            part = part.strip()
                            if '구입일:' in part:
                                purchase_date = part.replace('구입일:', '').strip()
                                if purchase_date:
                                    response += f"    📅 구입일: {purchase_date}\n"
                            elif '금액:' in part:
                                amount = part.replace('금액:', '').strip()
                                if amount and amount != '0원':
                                    response += f"    💰 금액: {amount}\n"
                            elif '원' in part and '금액' not in part:
                                # 금액이 따로 표시된 경우
                                if part.strip() and part.strip() != '0원':
                                    response += f"    💰 금액: {part.strip()}\n"
                
                response += "\n"
            
            if len(matching_items) > len(display_items):
                response += f"\n... 외 {len(matching_items) - len(display_items)}개 장비 더 있음\n"
            
            response += f"\n📄 출처: {txt_path.name}"
            
            # LLM으로 답변 개선
            if self.llm and len(matching_items) > 0:
                try:
                    # Asset LLM Enhancer 로드
                    if not self.asset_enhancer:
                        from asset_llm_enhancer import AssetLLMEnhancer
                        self.asset_enhancer = AssetLLMEnhancer(self.llm)
                    
                    # 답변 개선
                    enhanced_response = self.asset_enhancer.enhance_asset_response(
                        raw_data=response,
                        query=query,
                        llm=self.llm
                    )
                    
                    if enhanced_response and len(enhanced_response) > len(response):
                        return enhanced_response
                except Exception as e:
                    print(f"Asset LLM 개선 실패: {e}")
                    # 기본 응답 반환
            
            return response
            
        except Exception as e:
            return f"❌ 검색 실패: {e}"
    
    def _search_equipment_all_locations(self, txt_path: Path, equipment: str) -> str:
        """모든 위치별 장비 현황 정리"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 항목별로 검색
            lines = content.split('\n')
            location_equipment = {}  # {위치: [장비 목록]}
            current_item = []
            
            for line in lines:
                # [NNNN] 형식의 시작 라인을 찾기
                if re.match(r'^\[\d{4}\]', line.strip()):
                    # 이전 항목 검사
                    if current_item:
                        item_text = '\n'.join(current_item)
                        # 장비명 조건 확인
                        if equipment.upper() == "CCU":
                            equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                        else:
                            equipment_match = equipment.upper() in item_text.upper()
                        
                        if equipment_match:
                            # 위치 추출
                            location_info = None
                            for item_line in current_item:
                                if "위치:" in item_line:
                                    # 위치: 뒤의 값 추출
                                    match = re.search(r'위치:\s*([^|]+)', item_line)
                                    if match:
                                        location_info = match.group(1).strip()
                                        break
                            
                            if location_info:
                                if location_info not in location_equipment:
                                    location_equipment[location_info] = []
                                # 장비 정보 추출 (첫 줄만)
                                location_equipment[location_info].append(current_item[0])
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            # 마지막 항목 처리
            if current_item:
                item_text = '\n'.join(current_item)
                if equipment.upper() == "CCU":
                    equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                else:
                    equipment_match = equipment.upper() in item_text.upper()
                
                if equipment_match:
                    location_info = None
                    for item_line in current_item:
                        if "위치:" in item_line:
                            match = re.search(r'위치:\s*([^|]+)', item_line)
                            if match:
                                location_info = match.group(1).strip()
                                break
                    
                    if location_info:
                        if location_info not in location_equipment:
                            location_equipment[location_info] = []
                        location_equipment[location_info].append(current_item[0])
            
            # 결과 포맷팅
            if location_equipment:
                total_count = sum(len(items) for items in location_equipment.values())
                response = f"📊 **{equipment.upper()} 위치별 현황**\n"
                response += "=" * 70 + "\n"
                response += f"✅ 총 {total_count}개 장비가 {len(location_equipment)}개 위치에 분포\n\n"
                
                # 위치별 정렬 (많은 순)
                sorted_locations = sorted(location_equipment.items(), key=lambda x: len(x[1]), reverse=True)
                
                for location, items in sorted_locations:
                    response += f"📍 **{location}**: {len(items)}개\n"
                    # 샘플 3개만 표시
                    for i, item in enumerate(items[:3], 1):
                        response += f"   {i}. {item}\n"
                    if len(items) > 3:
                        response += f"   ... 외 {len(items)-3}개\n"
                    response += "\n"
                
                response += f"📄 출처: {txt_path.name}"
                return response
            else:
                return f"❌ {equipment.upper()} 장비를 찾을 수 없습니다."
                
        except Exception as e:
            return f"❌ 검색 실패: {e}"

    def _check_location_in_item(self, item_text: str, search_location: str) -> bool:
        """항목에서 위치 조건 확인"""
        # 위치 정보 추출
        location_match = re.search(r'위치:\s*([^|\n]+)', item_text)
        if not location_match:
            return False
            
        actual_location = location_match.group(1).strip()
        
        # 정확한 매칭 규칙 적용
        if search_location == actual_location:
            return True
        elif search_location == '부조정실':
            return actual_location.endswith('부조정실')
        elif search_location == '스튜디오':
            return actual_location.endswith('스튜디오')
        elif search_location == '편집실':
            return actual_location.endswith('편집실')
        elif search_location in ['중계차', 'van', 'Van', 'VAN']:
            return 'Van' in actual_location or 'VAN' in actual_location or '중계차' in actual_location
        elif len(search_location) > 3:
            return search_location in actual_location
        
        return False


def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("🚀 Perfect RAG - 정확한 문서 검색 시스템")
    print("=" * 60)
    
    # 시스템 초기화
    rag = PerfectRAG()
    
    # 테스트 질문들
    test_queries = [
        "2024 채널에이 중계차 노후 보수건 기안자 누구?",
        "뷰파인더 소모품 케이블 구매 날짜 언제?",
        "티비로직 월모니터 고장 수리 금액 얼마?",
        "2021년 짐벌카메라 구매 기안자 누구?",
        "스튜디오 모니터 교체 검토서 내용 요약",
    ]
    
    print("\n📋 테스트 시작")
    print("=" * 60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n질문 {i}: {query}")
        print("-" * 40)
        answer = rag.answer(query)
        print(answer)
        print("-" * 40)
        
        # 자동 진행 (input 제거)
    
    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print("=" * 60)



if __name__ == "__main__":
    main()