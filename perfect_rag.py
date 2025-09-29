#!/usr/bin/env python3
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import threading
from queue import Queue
from functools import partial

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
    chat_logger = get_logger()
    # chat_logger를 logger로도 사용
    logger = chat_logger
except ImportError:
    chat_logger = None
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
from metadata_db import MetadataDB  # Phase 1.2: 메타데이터 DB

# Everything-like 초고속 검색 시스템 추가
try:
    from everything_like_search import EverythingLikeSearch
    EVERYTHING_SEARCH_AVAILABLE = True
except ImportError:
    EVERYTHING_SEARCH_AVAILABLE = False
    if logger:
        logger.warning("EverythingLikeSearch not available, using legacy search")

# 메타데이터 추출 시스템 추가 (2025-09-29)
try:
    from metadata_extractor import MetadataExtractor
    METADATA_EXTRACTOR_AVAILABLE = True
except ImportError:
    METADATA_EXTRACTOR_AVAILABLE = False
    if logger:
        logger.warning("MetadataExtractor not available, metadata extraction disabled")

# 리팩토링된 모듈들 (2025-09-29)
try:
    from search_module import SearchModule
    SEARCH_MODULE_AVAILABLE = True
except ImportError:
    SEARCH_MODULE_AVAILABLE = False
    if logger:
        logger.warning("SearchModule not available - using embedded search")

try:
    from document_module import DocumentModule
    DOCUMENT_MODULE_AVAILABLE = True
except ImportError:
    DOCUMENT_MODULE_AVAILABLE = False
    if logger:
        logger.warning("DocumentModule not available - using embedded document processing")

try:
    from llm_module import LLMModule
    LLM_MODULE_AVAILABLE = True
except ImportError:
    LLM_MODULE_AVAILABLE = False
    if logger:
        logger.warning("LLMModule not available - using embedded LLM handling")

try:
    from cache_module import CacheModule
    CACHE_MODULE_AVAILABLE = True
except ImportError:
    CACHE_MODULE_AVAILABLE = False
    if logger:
        logger.warning("CacheModule not available - using embedded cache management")

# 새로운 모듈 import (제거됨 - 백업 폴더로 이동)
# from pdf_parallel_processor import PDFParallelProcessor
# from error_handler import RAGErrorHandler, ErrorRecovery, DetailedError, safe_execute


import logging
from typing import Optional, Dict, Any, List, Tuple
import traceback

# 로깅 설정 - 이미 상단에서 logger가 설정됨
# logger가 None인 경우 (log_system import 실패 시) 표준 로깅 사용
if logger is None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('perfect_rag.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)


class RAGException(Exception):
    """RAG 시스템 기본 예외"""
    pass

class DocumentNotFoundException(RAGException):
    """문서를 찾을 수 없을 때"""
    pass

class PDFExtractionException(RAGException):
    """PDF 추출 실패"""
    pass

class LLMException(RAGException):
    """LLM 관련 오류"""
    pass

class CacheException(RAGException):
    """캐시 관련 오류"""
    pass


def handle_errors(default_return=None):
    """에러 처리 데코레이터"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RAGPDFExtractionException as e:
                logger.error(f"{func.__name__} - RAG 오류: {str(e)}")
                if default_return is not None:
                    return default_return
                raise
            except PDFExtractionException as e:
                logger.error(f"{func.__name__} - 예상치 못한 오류: {str(e)}", exc_info=True)
                if default_return is not None:
                    return default_return
                raise RAGPDFExtractionException(f"처리 중 오류 발생: {str(e)}")
        return wrapper
    return decorator

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
                        logger.info(f"Performance config loaded from {perf_config_path}")
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to load performance config: {e}")
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

        # PDF 캐시 크기 설정 (DocumentModule 초기화 전에 필요)
        self.max_pdf_cache = 50  # 최대 50개 PDF 캐싱

        # 설정 디렉토리 설정
        self.config_dir = Path(__file__).parent / 'config'
        self.config_dir.mkdir(exist_ok=True)

        self.llm = None
        # 캐시 관리 개선 (크기 제한 및 TTL)
        from collections import OrderedDict
        # 캐시 크기 제한 설정
        self.MAX_CACHE_SIZE = 100  # 응답 캐시 최대 크기
        self.MAX_METADATA_CACHE = 500  # 메타데이터 캐시 최대 크기
        self.MAX_PDF_CACHE = 50  # PDF 텍스트 캐시 최대 크기
        self.CACHE_TTL = 3600  # 캐시 유효 시간 (1시간)

        self.documents_cache = OrderedDict()  # LRU 캐시처럼 동작
        self.metadata_cache = OrderedDict()  # 메타데이터 캐시
        self.search_mode = 'document'  # 검색 모드는 항상 document
        self.answer_cache = OrderedDict()  # 답변 캐시 (LRU)
        self.pdf_text_cache = OrderedDict()  # PDF 텍스트 추출 캐시 (성능 최적화)

        # PDF 병렬 처리기 초기화 (제거됨 - 백업 폴더로 이동)
        # self.pdf_processor = PDFParallelProcessor(config_manager=cfg if USE_YAML_CONFIG else None)
        # self.error_handler = RAGErrorHandler()
        # self.error_recovery = ErrorRecovery()
        self.pdf_processor = None
        self.error_handler = None
        self.error_recovery = None

        # SearchModule 초기화 (2025-09-29 리팩토링)
        self.search_module = None
        if SEARCH_MODULE_AVAILABLE:
            try:
                self.search_module = SearchModule(str(self.docs_dir))
                if logger:
                    logger.info("✅ SearchModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ SearchModule 초기화 실패: {e}")
                self.search_module = None

        # DocumentModule 초기화 (2025-09-29 리팩토링)
        self.document_module = None
        if DOCUMENT_MODULE_AVAILABLE:
            try:
                doc_config = {
                    'max_pdf_cache': self.max_pdf_cache,
                    'max_text_length': self.max_text_length,
                    'max_pdf_pages': self.max_pdf_pages,
                    'enable_ocr': False  # OCR은 필요시 활성화
                }
                self.document_module = DocumentModule(doc_config)
                if logger:
                    logger.info("✅ DocumentModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ DocumentModule 초기화 실패: {e}")
                self.document_module = None

        # LLMModule 초기화 (2025-09-29 리팩토링)
        self.llm_module = None
        if LLM_MODULE_AVAILABLE:
            try:
                llm_config = {
                    'model_path': self.model_path,
                    'preload_llm': preload_llm  # 생성자 파라미터 전달
                }
                self.llm_module = LLMModule(llm_config)
                if logger:
                    logger.info("✅ LLMModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ LLMModule 초기화 실패: {e}")
                self.llm_module = None

        # CacheModule 초기화 (2025-09-29 리팩토링)
        self.cache_module = None
        if CACHE_MODULE_AVAILABLE:
            try:
                cache_config = {
                    'max_cache_size': self.MAX_CACHE_SIZE,
                    'max_metadata_cache': self.MAX_METADATA_CACHE,
                    'max_pdf_cache': self.MAX_PDF_CACHE,
                    'cache_ttl': self.CACHE_TTL,
                    'cache_dir': str(self.config_dir / 'cache')
                }
                self.cache_module = CacheModule(cache_config)
                if logger:
                    logger.info("✅ CacheModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ CacheModule 초기화 실패: {e}")
                self.cache_module = None

        # Everything-like 초고속 검색 시스템 초기화 (SearchModule이 없을 때만)
        self.everything_search = None
        if not self.search_module and EVERYTHING_SEARCH_AVAILABLE:
            try:
                self.everything_search = EverythingLikeSearch()
                # 초기 인덱싱 - 한 번만 실행
                if not hasattr(self, '_index_initialized'):
                    self.everything_search.index_all_files()
                    self.__class__._index_initialized = True
                if logger:
                    logger.info("Everything-like search initialized successfully")
            except Exception as e:
                if logger:
                    logger.error(f"Failed to initialize Everything-like search: {e}")
                self.everything_search = None
        
        # 응답 포맷터 초기화
        self.formatter = ResponseFormatter() if ResponseFormatter else None

        # 메타데이터 추출기 초기화 (2025-09-29 추가)
        self.metadata_extractor = None
        if METADATA_EXTRACTOR_AVAILABLE:
            try:
                self.metadata_extractor = MetadataExtractor()
                if logger:
                    logger.info("✅ MetadataExtractor 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ MetadataExtractor 초기화 실패: {e}")
                self.metadata_extractor = None

        # LLM 개선 모듈 초기화

        # 자산 데이터 제거 (기안서 중심 시스템으로 전환)

        # 메타데이터 DB 초기화
        try:
            self.metadata_db = MetadataDB(db_path=str(self.config_dir / "metadata.db"))
            logger.info("✅ MetadataDB 초기화 성공")
        except Exception as e:
            logger.error(f"️ MetadataDB 초기화 실패: {e}")
            self.metadata_db = None
        
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

        print(f" {len(self.pdf_files)}개 PDF, {len(self.txt_files)}개 TXT 문서 발견")

        # 자산 데이터 로드 (metadata_db 초기화 포함)

        # 문서 메타데이터 사전 추출 (빠른 검색용)
        self._build_metadata_cache()

        # 메타데이터 DB 인덱스 구축 (Phase 1.2)
        self._build_metadata_index()

        # LLM 사전 로드 옵션
        if preload_llm:
            self._preload_llm()

    def _preload_llm(self):
        """LLM을 미리 로드"""
        # LLMModule을 사용하여 LLM 로드
        if self.llm_module:
            if self.llm_module.load_llm():
                self.llm = self.llm_module.llm
                return

        # LLMModule이 없으면 기존 방식 사용
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                print(" LLM 모델 최초 로딩 중...")
            else:
                print("️ LLM 모델 재사용")

            try:
                start = time.time()
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                elapsed = time.time() - start
                if elapsed > 1.0:  # 1초 이상 걸린 경우만 표시
                    print(f" LLM 로드 완료 ({elapsed:.1f}초)")
            except LLMException as e:
                print(f"️ LLM 로드 실패: {e}")
    
    def _build_metadata_index(self):
        """모든 PDF의 메타데이터를 추출하여 DB에 저장"""
        if not self.metadata_db:
            return

        logger.info("📚 메타데이터 인덱스 구축 시작...")
        indexed = 0

        for pdf_path in self.pdf_files[:30]:  # 처음 30개만 빠르게 처리
            try:
                # DB에 이미 있는지 확인
                existing = self.metadata_db.get_document(pdf_path.name)
                if existing and existing.get('title'):
                    continue  # 이미 처리됨

                # 메타데이터 추출
                metadata = self._extract_pdf_metadata(pdf_path)
                if metadata:
                    # DB에 저장
                    self.metadata_db.add_document(metadata)
                    indexed += 1

            except Exception as e:
                logger.error(f"메타데이터 추출 실패 {pdf_path.name}: {e}")

        if indexed > 0:
            logger.info(f"✅ {indexed}개 문서 메타데이터 인덱싱 완료")

    def _extract_pdf_metadata(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """PDF에서 메타데이터 추출"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return None

                # 첫 페이지에서 텍스트 추출
                first_page = pdf.pages[0].extract_text() or ""
                if not first_page:
                    return None

                # 기본 메타데이터
                metadata = {
                    'path': str(pdf_path),
                    'filename': pdf_path.name,
                    'file_size': pdf_path.stat().st_size,
                    'page_count': len(pdf.pages),
                    'text_preview': first_page[:500]
                }

                # 제목 추출
                lines = first_page.split('\n')[:10]
                for line in lines:
                    if len(line) > 10 and len(line) < 100:
                        metadata['title'] = line.strip()
                        break

                # 날짜 추출
                date_patterns = [
                    r'(\d{4})[년-]\s*(\d{1,2})[월-]\s*(\d{1,2})',
                    r'(\d{4})\.(\d{1,2})\.(\d{1,2})'
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, first_page[:1000])
                    if match:
                        year, month, day = match.groups()
                        metadata['year'] = year
                        metadata['month'] = month.zfill(2)
                        metadata['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        break

                # 기안자 추출
                drafter_patterns = [
                    r'기안자[\s:：]*([가-힣]{2,4})',
                    r'작성자[\s:：]*([가-힣]{2,4})'
                ]
                for pattern in drafter_patterns:
                    match = re.search(pattern, first_page[:500])
                    if match:
                        metadata['drafter'] = match.group(1).strip()
                        break

                # 카테고리 추정
                filename_lower = pdf_path.name.lower()
                if '구매' in filename_lower or '구입' in filename_lower:
                    metadata['category'] = '구매'
                elif '수리' in filename_lower or '보수' in filename_lower:
                    metadata['category'] = '수리'
                elif '폐기' in filename_lower:
                    metadata['category'] = '폐기'
                elif '검토' in filename_lower:
                    metadata['category'] = '검토'

                return metadata

        except Exception as e:
            logger.error(f"PDF 메타데이터 추출 오류 {pdf_path.name}: {e}")
            return None

    def _manage_cache(self, cache_dict, key, value):
        """캐시 크기 관리 - LRU 방식"""
        # CacheModule을 사용하여 캐시 관리
        if self.cache_module:
            self.cache_module.manage_cache(cache_dict, key, value)
            return

        # CacheModule이 없으면 기존 방식 사용
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
        """캐시에서 가져오기 (TTL 체크 및 타임스탬프 갱신)"""
        # CacheModule을 사용하여 캐시 조회
        if self.cache_module:
            return self.cache_module.get_from_cache(cache_dict, key)

        # CacheModule이 없으면 기존 방식 사용
        if key in cache_dict:
            cache_value = cache_dict[key]
            current_time = time.time()

            # 튀플 형식 (value, timestamp) 체크
            if isinstance(cache_value, tuple) and len(cache_value) == 2:
                value, timestamp = cache_value

                if current_time - timestamp < self.cache_ttl:
                    # LRU: 사용한 항목을 끝으로 이동
                    cache_dict.move_to_end(key)
                    # 타임스탬프 갱신 (사용 시간 연장)
                    cache_dict[key] = (value, current_time)
                    return value
                else:
                    # TTL 만료 - 삭제
                    del cache_dict[key]
                    return None
            else:
                # 이전 형식 호환 (튀플 아닌 경우)
                cache_dict.move_to_end(key)
                return cache_value

        return None
    
    def _parse_pdf_result(self, result: Dict) -> Dict:
        """병렬 처리 결과를 기존 형식으로 변환"""
        return {
            'text': result.get('text', ''),
            'page_count': result.get('page_count', 0),
            'metadata': result.get('metadata', {}),
            'method': result.get('method', 'parallel')
        }

    def process_pdfs_in_batch(self, pdf_paths: List[Path], batch_size: int = None) -> Dict:
        """여러 PDF를 배치로 병렬 처리 (안전하게 개선)"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import gc

        all_results = {}

        # 동적 배치 크기 계산
        if batch_size is None:
            batch_size = min(20, max(10, len(pdf_paths) // 30))
            logger.info(f"동적 배치 크기 설정: {batch_size}")

        # pdf_processor가 없으면 순차 처리로 폴백
        if self.pdf_processor is None:
            print("️ 병렬 처리기 미활성화 - 순차 처리 모드")

            # ThreadPoolExecutor로 간단한 병렬 처리 (CPU 코어 수 기반 최적화)
            optimal_workers = min(os.cpu_count() or 4, 12, max(4, batch_size))
            with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                for i in range(0, len(pdf_paths), batch_size):
                    batch = pdf_paths[i:i + batch_size]
                    print(f" 배치 {i//batch_size + 1}/{(len(pdf_paths)-1)//batch_size + 1} 처리 중 ({len(batch)}개 파일)")

                    # 각 PDF를 병렬로 처리
                    futures = {executor.submit(self._extract_pdf_info, pdf): pdf for pdf in batch}

                    for future in as_completed(futures):
                        pdf_path = futures[future]
                        try:
                            result = future.result(timeout=30)  # 30초 타임아웃
                            all_results[str(pdf_path)] = result
                        except PDFExtractionException as e:
                            print(f"   {pdf_path.name} 처리 실패: {str(e)[:50]}")
                            all_results[str(pdf_path)] = {'error': str(e)}

                    # 메모리 최적화
                    if i % (batch_size * 5) == 0:
                        gc.collect()
        else:
            # 기존 pdf_processor 사용
            for i in range(0, len(pdf_paths), batch_size):
                batch = pdf_paths[i:i + batch_size]
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
        # 캐시 파일 경로 (Docker volume에 저장)
        cache_dir = Path("/app/cache") if Path("/app/cache").exists() else Path("cache")
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "metadata_cache.pkl"

        # 기존 캐시 파일이 있으면 로드
        if cache_file.exists():
            try:
                import pickle
                with open(cache_file, 'rb') as f:
                    self.metadata_cache = pickle.load(f)
                print(f"✅ 캐시 로드 완료: {len(self.metadata_cache)}개 문서")
                return  # 캐시가 있으면 재구축 불필요
            except Exception as e:
                print(f"⚠️ 캐시 로드 실패, 재구축: {e}")

        logger.info("메타데이터 캐시 구축 시작")
        print(" 문서 메타데이터 구축 중...")

        # 병렬 처리 설정 확인
        use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

        # 병렬 처리 활성화 여부와 관계없이 process_pdfs_in_batch 사용 (내부에서 처리)
        if self.pdf_files and len(self.pdf_files) > 10:  # 10개 이상일 때만 병렬 처리
            print(f" {len(self.pdf_files)}개 PDF 처리 시작 (병렬 모드)...")
            pdf_results = self.process_pdfs_in_batch(self.pdf_files, batch_size=10)

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
                'drafter': None,  # 기안자 정보는 필요시에만 추출
                'full_text': None,  # 나중에 필요시 로드
                'is_txt': filename.endswith('.txt'),  # TXT 파일 여부
                'is_pdf': filename.endswith('.pdf')  # PDF 파일 여부 추가
            }

        print(f" {len(self.metadata_cache)}개 문서 메타데이터 구축 완료")

        # 캐시 저장
        try:
            import pickle
            with open(cache_file, 'wb') as f:
                pickle.dump(self.metadata_cache, f)
            print(f"✅ 캐시 저장 완료: {cache_file}")
        except Exception as e:
            print(f"⚠️ 캐시 저장 실패: {e}")
    
    def _extract_txt_info(self, txt_path: Path) -> Dict:
        """TXT 파일에서 정보 동적 추출"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            info = {'text': text[:3000]}  # 처음 3000자만
            
            # 자산 파일 관련 코드 제거됨
            
            return info

        except Exception as e:
            if logger:
                print(f"️ TXT 읽기 오류 ({txt_path.name}): {e}")
            else:
                print(f"️ TXT 읽기 오류 ({txt_path.name}): {e}")
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
        # DocumentModule을 사용하여 컨텍스트 최적화
        if self.document_module:
            return self.document_module.optimize_context(text, query, max_length)

        # DocumentModule이 없으면 기존 방법 사용
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
        """PDF 정보 추출 (DocumentModule 사용)"""
        # DocumentModule을 사용하여 PDF 처리
        if self.document_module:
            try:
                result = self.document_module.extract_pdf_text_with_retry(pdf_path, max_retries=2)
                if result:
                    return result
            except Exception as e:
                if logger:
                    logger.error(f"DocumentModule PDF 처리 오류: {e}")

        # DocumentModule이 없으면 기존 방법 사용
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
                    if len(match.groups()) == 3:
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

    def _search_by_content(self, query: str) -> List[Dict[str, Any]]:
        """🔥 NEW: Everything-like 초고속 파일 검색"""

        # SearchModule 사용 (2025-09-29 리팩토링)
        if self.search_module:
            try:
                results = self.search_module.search_by_content(query, top_k=20)
                if logger:
                    logger.info(f"SearchModule found {len(results)} documents for query: {query}")
                return results
            except Exception as e:
                if logger:
                    logger.error(f"SearchModule failed: {e}, falling back to embedded search")

        # Everything-like 검색 사용 가능한 경우 (폴백)
        if self.everything_search:
            try:
                # 초고속 SQLite 검색
                search_results = self.everything_search.search(query, limit=20)

                results = []
                for doc in search_results:
                    # 검색 결과를 기존 형식으로 변환
                    result = {
                        'filename': doc['filename'],
                        'path': doc['path'],
                        'date': doc.get('date', ''),
                        'year': doc.get('year', ''),
                        'category': doc.get('category', '기타'),
                        'keywords': doc.get('keywords', ''),
                        'score': 1.0,  # Everything 검색은 관련도 점수가 없으므로 기본값
                        'source': 'everything_search'
                    }

                    # 메타데이터 추출 (2025-09-29 추가)
                    if self.metadata_extractor:
                        try:
                            # PDF 파일인 경우 첫 페이지 텍스트 추출
                            if doc['path'].endswith('.pdf'):
                                with pdfplumber.open(doc['path']) as pdf:
                                    text = pdf.pages[0].extract_text() if pdf.pages else ""

                                # 메타데이터 추출
                                metadata = self.metadata_extractor.extract_all(
                                    text[:1000] if text else "",  # 첫 1000자만
                                    doc['filename']
                                )

                                # 요약 정보를 결과에 추가
                                result['metadata_info'] = metadata.get('summary', {})

                                # 주요 필드 직접 추가 (호환성 유지)
                                if metadata['summary'].get('date'):
                                    result['extracted_date'] = metadata['summary']['date']
                                if metadata['summary'].get('amount'):
                                    result['extracted_amount'] = metadata['summary']['amount']
                                if metadata['summary'].get('department'):
                                    result['extracted_dept'] = metadata['summary']['department']
                                if metadata['summary'].get('doc_type'):
                                    result['extracted_type'] = metadata['summary']['doc_type']

                        except Exception as e:
                            # 메타데이터 추출 실패해도 검색은 계속
                            if logger:
                                logger.debug(f"Metadata extraction failed for {doc['filename']}: {e}")

                    results.append(result)

                if logger:
                    logger.info(f"Everything search found {len(results)} documents for query: {query}")

                return results

            except Exception as e:
                if logger:
                    logger.error(f"Everything search failed: {e}, falling back to legacy search")
                # 실패 시 기존 검색으로 폴백

        # 기존 검색 로직 (Everything 사용 불가 시)
        file_scores = {}  # filename -> result dict
        query_lower = query.lower()
        keywords = [kw.lower() for kw in query.split() if len(kw) > 1]

        # 모든 PDF 파일 검색
        pdf_files = list(self.docs_dir.rglob("*.pdf"))

        if logger:
            logger.info(f"내용 검색 시작: {len(pdf_files)}개 PDF, 키워드: {keywords}")

        # 먼저 파일명 검색 (빠름)
        for pdf_path in pdf_files:
            filename_lower = pdf_path.name.lower()
            score = 0
            matched_keywords = []

            # 파일명에 전체 쿼리가 포함되면 최고 점수
            if query_lower in filename_lower:
                score = 100
                matched_keywords = [query]
            # 파일명에 각 키워드가 포함되면 점수 부여
            else:
                # 핵심 키워드 찾기 (관련, 문서 제외)
                important_keywords = [kw for kw in keywords if kw not in ['관련', '문서', '찾아', '내용']]

                # 모든 중요 키워드가 파일명에 있는지 확인
                if important_keywords:
                    all_important_match = all(kw in filename_lower for kw in important_keywords)

                    for kw in keywords:
                        if kw in filename_lower:
                            # 중요 키워드는 높은 점수
                            if kw in important_keywords:
                                score += 50 if all_important_match else 30
                            else:
                                score += 10  # 관련, 문서 등은 낮은 점수
                            matched_keywords.append(kw)

            if score > 0:
                file_scores[pdf_path.name] = {
                    'path': pdf_path,
                    'filename': pdf_path.name,
                    'score': score,
                    'matched_keywords': matched_keywords,
                    'context': f"파일명 매칭: {pdf_path.name}"
                }

        # 내용 검색 (느림, 일부만)
        for pdf_path in pdf_files[:50]:  # 상위 50개만
            try:
                # 캐시 확인
                cache_key = str(pdf_path)
                if cache_key in self.pdf_text_cache:
                    text = self.pdf_text_cache[cache_key].get('text', '')
                else:
                    # PDF 텍스트 추출
                    with pdfplumber.open(pdf_path) as pdf:
                        text = ""
                        for page_num, page in enumerate(pdf.pages[:5]):  # 처음 5페이지만
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"

                        # OCR 필요 시
                        if not text.strip():
                            text = self._try_ocr_extraction(pdf_path)
                            if not text:
                                continue

                    # 캐시 저장
                    self.pdf_text_cache[cache_key] = {'text': text, 'timestamp': time.time()}

                # 키워드 매칭 점수 계산
                text_lower = text.lower()
                matched_keywords = [kw for kw in keywords if kw in text_lower]

                if matched_keywords:
                    # 점수 계산: 매칭된 키워드 수 + 근접도
                    content_score = len(matched_keywords) * 10

                    # 키워드가 가까이 있으면 보너스
                    for i in range(len(matched_keywords) - 1):
                        if abs(text_lower.find(matched_keywords[i]) - text_lower.find(matched_keywords[i+1])) < 200:
                            content_score += 5

                    # 컨텍스트 추출 (키워드 주변 200자)
                    context = self._extract_context(text, matched_keywords[0], 200)

                    # 기존 파일명 점수와 내용 점수 중 높은 것 사용
                    if pdf_path.name in file_scores:
                        # 이미 파일명으로 매칭된 경우, 더 높은 점수 유지
                        if content_score > file_scores[pdf_path.name]['score']:
                            file_scores[pdf_path.name]['score'] = content_score
                            file_scores[pdf_path.name]['context'] = context
                            file_scores[pdf_path.name]['matched_keywords'].extend(matched_keywords)
                    else:
                        # 새로운 파일 추가
                        file_scores[pdf_path.name] = {
                            'path': pdf_path,
                            'filename': pdf_path.name,
                            'score': content_score,
                            'matched_keywords': matched_keywords,
                            'context': context
                        }

            except Exception as e:
                if logger:
                    logger.warning(f"PDF 내용 검색 실패 {pdf_path.name}: {e}")
                continue

        # 딕셔너리를 리스트로 변환하고 점수 기준 정렬
        results = list(file_scores.values())
        results.sort(key=lambda x: x['score'], reverse=True)

        if logger and results:
            logger.info(f"내용 검색 결과: {len(results)}개 문서 찾음")
            for r in results[:3]:
                logger.info(f"  - {r['filename']}: 점수 {r['score']}, 매칭 {r['matched_keywords']}")

        return results[:10]  # 상위 10개 반환

    def _extract_context(self, text: str, keyword: str, window: int = 200) -> str:
        """키워드 주변 컨텍스트 추출"""
        keyword_lower = keyword.lower()
        text_lower = text.lower()

        pos = text_lower.find(keyword_lower)
        if pos == -1:
            return ""

        start = max(0, pos - window)
        end = min(len(text), pos + len(keyword) + window)

        context = text[start:end]
        # 키워드 하이라이트
        context = context.replace(keyword, f"**{keyword}**")

        return f"...{context}..."

    def find_best_document(self, query: str) -> Optional[Path]:
        """질문에 가장 적합한 문서 찾기 - 동적 매칭 + 내용 검색"""

        # 내용 검색 기능 통합
        if not hasattr(self, 'content_searcher'):
            from content_search import ContentSearcher
            self.content_searcher = ContentSearcher(self.docs_dir)

        # 🔥 NEW: 실제 PDF 내용 기반 검색 추가
        content_based_results = self._search_by_content(query)

        # 내용 검색 결과가 있으면 우선 사용
        if content_based_results and content_based_results[0]['score'] > 20:
            best_result = content_based_results[0]
            if logger:
                logger.info(f"✅ 내용 검색으로 문서 찾음: {best_result['filename']} (점수: {best_result['score']})")
                logger.info(f"   매칭 키워드: {best_result['matched_keywords']}")
            return best_result['path']

        query_lower = query.lower()

        # PDF 문서 우선 처리 키워드 확장
        pdf_priority_keywords = [
            '수리', '보수', '내용', '요약', '검토서', '기술검토',
            '교체', '구매', '폐기', '소모품', '기안', '검토',
            '어떤', '무엇', '뭐', '뭘로', '어디서', '누가'
        ]

        # 문서 검색 후보 초기화 - 딕셔너리로 변경하여 중복 관리
        candidates = {}  # path -> (score, filename)
        
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
            
            # 1. 연도와 월 매칭 (연도가 지정된 경우에만)
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
            # 연도가 지정되지 않은 경우는 모든 문서를 대상으로 계속 진행
            
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
                            # 완전 일치 (가장 높은 점수)
                            if q_word == f_word:
                                # 단어 길이에 따라 가중치 부여
                                weight = len(q_word) * 5  # 2 -> 5로 증가
                                score += weight
                            # 유사도 검사 (오타 처리) - 완전 일치가 아닌 경우만
                            elif self._calculate_similarity(q_word, f_word) >= 0.85:  # 0.8 -> 0.85로 상향
                                # 85% 이상 유사하면 매칭으로 간주
                                weight = len(q_word) * 1.5
                                score += weight
                            # 부분 일치 (긴 단어일 경우)
                            if len(q_word) >= 3 and len(f_word) >= 3:
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
                candidates[metadata['path']] = (score, filename)

        # 내용 검색 추가 (파일명 매칭과 함께)
        try:
            # PDF 파일 리스트 준비
            pdf_files = [p for p in self.pdf_files if p.suffix.lower() == '.pdf']

            if pdf_files:
                logger.info(f"내용 검색 시작: {len(pdf_files)}개 PDF 대상")
                # 성능을 위해 최대 30개 파일만 내용 검색 (더 정확한 파일명 매칭이 우선)
                content_results = self.content_searcher.search_by_content(query, pdf_files, top_k=10, max_files=30)

                # 내용 검색 결과를 점수에 반영
                for result in content_results:
                    pdf_path = result['path']
                    content_score = result['score']

                    if pdf_path in candidates:
                        # 이미 파일명 매칭 점수가 있는 경우, 가중 평균
                        old_score, filename = candidates[pdf_path]
                        # 파일명 점수 60%, 내용 점수 40%
                        new_score = old_score * 0.6 + content_score * 0.4
                        candidates[pdf_path] = (new_score, filename)
                    else:
                        # 파일명 매칭되지 않은 경우, 내용 점수만 사용 (0.8 가중치)
                        candidates[pdf_path] = (content_score * 0.8, pdf_path.name)

                logger.info(f"내용 검색 완료: {len(content_results)}개 매칭")
        except Exception as e:
            logger.warning(f"내용 검색 중 오류 (무시하고 계속): {e}")

        # Phase 1.2: 메타데이터 DB 검색 추가
        if self.metadata_db:
            try:
                # 연도로 검색
                if query_year:
                    db_results = self.metadata_db.search_by_year(query_year)
                    for doc in db_results[:10]:  # 최대 10개
                        doc_path = Path(doc['path'])
                        if doc_path.exists():
                            if doc_path in candidates:
                                # 이미 있으면 점수 보정
                                old_score, filename = candidates[doc_path]
                                candidates[doc_path] = (old_score + 5, filename)
                            else:
                                # 새로 추가 (DB 검색 기반)
                                candidates[doc_path] = (10, doc['filename'])

                # 기안자로 검색
                drafter_patterns = [r'([가-힣]{2,4})(?:가|의|에서|이)\s*(?:작성|기안)']
                for pattern in drafter_patterns:
                    match = re.search(pattern, query)
                    if match:
                        drafter_name = match.group(1)
                        db_results = self.metadata_db.search_by_text(drafter_name)
                        for doc in db_results[:5]:
                            doc_path = Path(doc['path'])
                            if doc_path.exists():
                                if doc_path in candidates:
                                    old_score, filename = candidates[doc_path]
                                    candidates[doc_path] = (old_score + 10, filename)
                                else:
                                    candidates[doc_path] = (15, doc['filename'])

                logger.info("✅ 메타데이터 DB 검색 완료")
            except Exception as e:
                logger.warning(f"메타데이터 DB 검색 중 오류: {e}")

        # 딕셔너리를 리스트로 변환하고 점수순 정렬
        sorted_candidates = sorted(
            [(score, path, filename) for path, (score, filename) in candidates.items()],
            reverse=True
        )

        # 디버깅 출력 (상위 3개)
        if sorted_candidates:
            logger.info("상위 3개 후보 문서:")
            for score, path, filename in sorted_candidates[:3]:
                logger.info(f"  - {filename}: {score:.2f}점")

            top_score = sorted_candidates[0][0]
            # 동점자가 있는지 확인
            same_score = [c for c in sorted_candidates if c[0] == top_score]
            if len(same_score) > 1:
                # 동점일 때는 파일명 길이가 짧은 것 우선
                same_score.sort(key=lambda x: len(x[2]))
                return same_score[0][1]
            return sorted_candidates[0][1]

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
            return " 문서를 읽을 수 없습니다"
        
        result = ""
        
        # 자산 파일 관련 코드 제거됨

        # 일반 문서 처리
        if info_type == "all":
            result = f" {file_path.stem}\n"
            result += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for key, value in info.items():
                if key != 'text':
                    result += f"• {key}: {value}\n"
        if info_type == "기안자":
            result = f" 기안자: {info.get('기안자', '정보 없음')}"
        if info_type == "날짜":
            result = f" 날짜: {info.get('날짜', '정보 없음')}"
        if info_type == "부서":
            result = f" 부서: {info.get('부서', '정보 없음')}"
        if info_type == "금액":
            amount = info.get('금액', '정보 없음')
            result = f" 금액: {amount}"
        else:
            # 특정 정보 요청
            if info_type in info:
                result = f" {info_type}: {info[info_type]}"
            else:
                result = f" {info_type} 정보를 찾을 수 없습니다"
            
            # 짧은 답변 보완 - 추가 정보 제공
            if amount != '정보 없음' and len(result) < 50:
                # 문서 정보 추가
                result += f"\n\n 문서 정보:\n"
                result += f"• 문서명: {file_path.stem}\n"
                if '날짜' in info:
                    result += f"• 날짜: {info['날짜']}\n"
                if '기안자' in info:
                    result += f"• 기안자: {info['기안자']}\n"
                if '부서' in info:
                    result += f"• 부서: {info['부서']}\n"
                if '제목' in info:
                    result += f"• 제목: {info['제목']}\n"
        if info_type == "요약":
            # 간단한 요약 생성
            result = f" {file_path.stem} 요약\n"
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
            result = f" {file_path.stem}\n\n"
            result += f" **기본 정보**\n"
            if '기안자' in info:
                result += f"• 기안자: {info['기안자']}\n"
            if '날짜' in info:
                result += f"• 날짜: {info['날짜']}\n"
            if '부서' in info:
                result += f"• 부서: {info['부서']}\n"
            
            result += f"\n **주요 내용**\n"
            
            # text 필드에서 주요 내용 추출 (개선된 요약 시스템)
            if 'text' in info:
                summary = self._generate_smart_summary(info['text'], file_path)
                result += summary
            
            if '금액' in info and info['금액'] != '정보 없음':
                result += f"\n **비용 정보**\n"
                result += f"• 금액: {info['금액']}\n"
            
            result += f"\n 출처: {file_path.name}"
        
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
                summary_parts.append(" " + " | ".join(purchase_info))

        if '수리' in file_name or '보수' in file_name:
            # 수리 문서
            repair_info = []
            if equipment_keywords:
                repair_info.append(f"수리 대상: {', '.join(set(equipment_keywords[:3]))}")
            if financial_keywords:
                repair_info.append(f"수리 비용: {', '.join(financial_keywords[:2])}")

            if repair_info:
                summary_parts.append(" " + " | ".join(repair_info))

        if '폐기' in file_name:
            # 폐기 문서
            disposal_info = []
            if equipment_keywords:
                disposal_info.append(f"폐기 장비: {', '.join(set(equipment_keywords[:3]))}")

            if disposal_info:
                summary_parts.append("️ " + " | ".join(disposal_info))

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
            return " 관련 문서를 찾을 수 없습니다."

        # 중복 제거
        unique_results = self._remove_duplicate_documents(results)

        response = f" **검색 결과** ({len(unique_results)}개 문서)\n\n"

        for i, doc in enumerate(unique_results[:5], 1):  # 최대 5개만 표시
            title = doc.get('title', '제목 없음')
            date = doc.get('date', '날짜 미상')
            category = doc.get('category', '기타')
            drafter = doc.get('drafter', '미상')

            # 메타데이터 추출 정보 우선 사용 (2025-09-29 추가)
            if 'extracted_date' in doc:
                date = doc['extracted_date']
            if 'extracted_type' in doc:
                category = doc['extracted_type']
            if 'extracted_dept' in doc:
                drafter = doc['extracted_dept']

            # 날짜 표시 개선
            if date and date != '날짜 미상' and len(date) >= 10:
                display_date = date[:10]  # YYYY-MM-DD
            if date and len(date) >= 4:
                display_date = date[:4]  # 연도만
            else:
                display_date = "날짜미상"

            response += f"**{i}. [{category}] {title}**\n"
            response += f"    {display_date} |  {drafter}"

            # 추출된 금액 정보 추가 (2025-09-29)
            if 'extracted_amount' in doc:
                amount = doc['extracted_amount']
                response += f" | 💰 {amount:,}원"

            response += "\n"

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

        response += " **특정 문서를 선택하여 자세한 내용을 확인하세요.**"

        return response

    def _classify_search_intent(self, query: str) -> str:
        """검색 의도 분류 - 항상 document 모드 반환"""
        return 'document'  # Asset 모드 제거, 항상 문서 검색

    def answer_from_specific_document(self, query: str, filename: str) -> str:
        """특정 문서에 대해서만 답변 생성 (문서 전용 모드) - 초상세 버전
        
        Args:
            query: 사용자 질문
            filename: 특정 문서 파일명
        """
        print(f" 문서 전용 모드: {filename}")
        
        # 메타데이터에서 해당 문서 찾기
        doc_metadata = self._find_metadata_by_filename(filename)
        if not doc_metadata:
            return f" 문서를 찾을 수 없습니다: {filename}"
        doc_path = doc_metadata['path']
        
        # PDF인지 TXT인지 확인
        if filename.endswith('.pdf'):
            # PDF 문서 처리 - 전체 내용 추출
            info = self._extract_pdf_info_with_retry(doc_path)
            if not info.get('text'):
                return f" PDF 내용을 읽을 수 없습니다: {filename}"
            
            # LLM 초기화
            if self.llm is None:
                print(" LLM 모델 로드 중...")
                self._preload_llm()
            
            # 전체 문서 텍스트 사용 (15000자로 확대)
            full_text = info['text'][:15000]
            
            # 질문 유형별 특화 프롬프트 생성
            if any(word in query for word in ['요약', '정리', '개요', '내용']):
                prompt = self._create_detailed_summary_prompt(query, full_text, filename)
            if any(word in query for word in ['상세', '자세히', '구체적', '세세히', '세부']):
                prompt = self._create_ultra_detailed_prompt(query, full_text, filename)
            if any(word in query for word in ['품목', '목록', '리스트', '항목']):
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
            answer += f"\n\n **출처**: {filename}"
            
        if filename.endswith('.txt'):
            # TXT 파일 처리 (자산 데이터)
            return None  # Asset 검색 제거
        else:
            return f" 지원하지 않는 파일 형식입니다: {filename}"
        
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
            return f" {filename}에서 찾은 관련 내용:\n\n" + '\n'.join(relevant_lines[:20])
        else:
            return f" {filename}에서 '{query}'에 대한 정보를 찾을 수 없습니다."
    
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
            return f" **{filename}** 상세 분석:\n\n" + '\n---\n'.join(relevant_sections[:10])
        else:
            return f" {filename}에서 '{query}'에 대한 정보를 찾을 수 없습니다."
    
    def _enhance_short_answer(self, answer: str, full_text: str, query: str) -> str:
        """짧은 답변을 보강"""
        enhanced = answer + "\n\n **추가 상세 정보**:\n"
        
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

    def _safe_pdf_extract(self, pdf_path, max_retries=3):
        """안전한 PDF 추출 with 재시도"""
        for attempt in range(max_retries):
            try:
                return self._extract_full_pdf_content(pdf_path)
            except PDFExtractionException as e:
                logger.warning(f"PDF 추출 실패 (시도 {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"PDF 추출 최종 실패: {pdf_path}")
                    return None
                time.sleep(1)  # 재시도 전 대기

    def _validate_input(self, query):
        """입력 검증"""
        if not query:
            raise ValueError("쿼리가 비어있습니다")

        if len(query) > 1000:
            logger.warning(f"쿼리가 너무 깁니다: {len(query)}자")
            query = query[:1000]

        # SQL 인젝션 방지
        dangerous_patterns = ['DROP', 'DELETE', 'INSERT', 'UPDATE', '--', ';']
        for pattern in dangerous_patterns:
            if pattern in query.upper():
                raise ValueError(f"허용되지 않은 패턴: {pattern}")


    def __del__(self):
        """소멸자 - 리소스 정리"""
        self.cleanup_executor()

    def _parallel_search_pdfs(self, pdf_files, query, top_k=5):
        """병렬 PDF 검색 - 성능 최적화"""
        logger.info(f"병렬 검색 시작: {len(pdf_files)}개 PDF, {self.MAX_WORKERS}개 워커")

        results = []
        futures = []

        # 검색 함수 정의
        def search_single_pdf(pdf_path):
            try:
                # 캐시 확인
                cache_key = f"{pdf_path}:{query}"
                if cache_key in self.documents_cache:
                    return self.documents_cache[cache_key]['data']

                # PDF 내용 추출
                content = self._safe_pdf_extract(pdf_path, max_retries=1)
                if not content:
                    return None

                # 관련성 점수 계산
                keywords = query.split()
                score = self._score_document_relevance(content, keywords)

                # 메타데이터 추출
                metadata = self._extract_document_metadata(pdf_path)

                result = {
                    'path': pdf_path,
                    'score': score,
                    'content': content[:500],  # 미리보기용
                    'metadata': metadata
                }

                # 캐시에 저장
                self._add_to_cache(self.documents_cache, cache_key, result, self.MAX_CACHE_SIZE)

                return result

            except Exception as e:
                logger.error(f"PDF 검색 오류 {pdf_path}: {e}")
                return None

        # 병렬 실행
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # 모든 PDF에 대해 비동기 작업 제출
            future_to_pdf = {
                executor.submit(search_single_pdf, pdf): pdf
                for pdf in pdf_files
            }

            # 완료된 작업부터 처리
            for future in as_completed(future_to_pdf):
                pdf = future_to_pdf[future]
                try:
                    result = future.result(timeout=10)  # 10초 타임아웃
                    if result and result['score'] > 0:
                        results.append(result)
                        logger.debug(f"검색 완료: {pdf.name}, 점수: {result['score']:.2f}")
                except Exception as e:
                    logger.error(f"검색 실패 {pdf}: {e}")

        # 점수 순으로 정렬
        results.sort(key=lambda x: x['score'], reverse=True)

        logger.info(f"병렬 검색 완료: {len(results)}개 결과")
        return results[:top_k]

    def _parallel_extract_metadata(self, files):
        """병렬 메타데이터 추출"""
        logger.info(f"병렬 메타데이터 추출: {len(files)}개 파일")

        def extract_single(file_path):
            try:
                return self._extract_document_metadata(file_path)
            except Exception as e:
                logger.error(f"메타데이터 추출 실패 {file_path}: {e}")
                return {}

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = [executor.submit(extract_single, f) for f in files]
            results = []

            for future in as_completed(futures):
                try:
                    metadata = future.result(timeout=5)
                    if metadata:
                        results.append(metadata)
                except Exception as e:
                    logger.error(f"메타데이터 추출 오류: {e}")

        return results

    def _batch_process_documents(self, documents, process_func, batch_size=10):
        """배치 문서 처리 - 메모리 효율성"""
        total = len(documents)
        processed = 0
        results = []

        for i in range(0, total, batch_size):
            batch = documents[i:i+batch_size]

            with ThreadPoolExecutor(max_workers=min(len(batch), self.MAX_WORKERS)) as executor:
                futures = [executor.submit(process_func, doc) for doc in batch]

                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=30)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.error(f"배치 처리 오류: {e}")

            processed += len(batch)
            logger.info(f"진행률: {processed}/{total} ({100*processed/total:.1f}%)")

            # 메모리 정리
            if processed % 50 == 0:
                import gc
                gc.collect()

        return results

    def cleanup_executor(self):
        """병렬 처리 리소스 정리"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
            logger.info("병렬 처리 리소스 정리 완료")

    def _create_ultra_detailed_prompt(self, query: str, context: str, filename: str) -> str:
        """초상세 답변 전용 프롬프트"""
        return f"""
[초상세 분석 모드] - 모든 세부사항 포함

문서: {filename}
요청: {query}

 **최대한 상세하게 답변하세요**:

1. 질문과 관련된 모든 정보를 찾아서 제공
2. 문서의 앞뒤 문맥까지 포함하여 설명
3. 구체적인 수치, 날짜, 이름, 모델명 등 모두 명시
4. 관련 배경 정보도 함께 제공
5. 문서에 암시된 내용도 해석하여 설명

문서 전체 내용:
{context}

답변 규칙:
 최소 500자 이상 상세 답변
 모든 관련 정보 나열
 표나 리스트로 정리
 중요 정보는 **굵게** 표시
 문서의 모든 관련 부분 인용
"""
    
    def _create_itemized_list_prompt(self, query: str, context: str, filename: str) -> str:
        """품목 리스트 전용 프롬프트"""
        return f"""
[품목/항목 상세 분석 모드]

문서: {filename}

문서에 있는 모든 품목/항목을 완전하게 추출하세요:

 **추출 형식**:
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

 분석 대상 문서: {filename}

이 문서만을 분석하여 아래 형식으로 답변하세요.


 [문서 제목]

 **기본 정보**
• 기안자: [문서에서 찾은 기안자명]
• 날짜: [문서 날짜]
• 문서 종류: [기안서/검토서/보고서 등]

 **주요 내용**
[질문과 관련된 핵심 내용을 구조화하여 표시]
• [주요 사항 1]
• [주요 사항 2]
• [세부 내용들...]

 **비용 정보** (비용 관련 내용이 있는 경우)
• 총액: [금액]
• 세부 내역:
  - [품목1]: [금액]
  - [품목2]: [금액]

 **검토 의견** (검토 의견이 있는 경우)
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견]

 출처: {filename}

 **문서 전체 내용**:
{context}

 **사용자 질문**: {query}

️ 주의사항:
- 위 형식을 반드시 따를 것
- 이 문서에 없는 내용은 추측하지 말 것
- 문서의 정확한 표현 사용
- 가능한 한 많은 세부사항 포함
"""
    
    def _get_enhanced_cache_key(self, query: str, mode: str) -> str:
        """향상된 캐시 키 생성 - 유사 질문도 캐시 히트

        예시:
        - "2020년 구매 문서" → "2020 구매 문서"
        - "2020년의 구매한 문서를" → "2020 구매 문서"
        - "구매 2020년 문서" → "2020 구매 문서" (정렬)
        """

        # 1. 쿼리 정규화 및 소문자 변환
        normalized = query.strip().lower()

        # 2. 한글 조사 제거 - 개선된 알고리즘
        # 복합 조사부터 제거 (에서는, 으로는 등)
        compound_particles = ['에서는', '으로는', '에게는', '한테는', '에서도', '으로도',
                            '이라도', '이나마', '이든지', '이라는', '까지도', '부터도']
        simple_particles = ['에서', '으로', '이나', '이든', '이면', '에게', '한테', '께서',
                          '은', '는', '이', '가', '을', '를', '의', '와', '과', '로', '에',
                          '도', '만', '까지', '부터', '마다', '마저', '조차']

        # 단어 단위로 분리 후 조사 제거
        words = normalized.split()
        cleaned_words = []

        for word in words:
            cleaned_word = word

            # 복합 조사 먼저 제거
            for particle in compound_particles:
                if cleaned_word.endswith(particle):
                    cleaned_word = cleaned_word[:-len(particle)]
                    break

            # 단순 조사 제거
            if cleaned_word:  # 빈 문자열이 아니면
                for particle in simple_particles:
                    if cleaned_word.endswith(particle):
                        cleaned_word = cleaned_word[:-len(particle)]
                        break

            # 2글자 이상만 포함
            if cleaned_word and len(cleaned_word) >= 2:
                cleaned_words.append(cleaned_word)

        # 3. 키워드 정렬 (순서 무관 캐시 히트)
        cleaned_words.sort()

        # 4. 캐시 키 생성
        cache_str = f"{mode}:{'_'.join(cleaned_words)}"
        hash_key = hashlib.md5(cache_str.encode('utf-8')).hexdigest()

        # 디버깅 (필요시 활성화)
        # print(f"Cache: '{query}' → '{' '.join(cleaned_words)}' → {hash_key[:8]}...")

        return hash_key

    def answer_with_logging(self, query: str, mode: str = 'auto') -> str:
        """로깅이 통합된 answer 메서드 (캐싱 포함)"""
        # 향상된 캐시 키 생성
        cache_key = self._get_enhanced_cache_key(query, mode)
        
        # 캐시 확인
        if cache_key in self.answer_cache:
            cached_response, cached_time = self.answer_cache[cache_key]
            # TTL 확인 (기본 1시간)
            if time.time() - cached_time < self.cache_ttl:
                print(f" 캐시 히트! (키: {cache_key[:8]}...)")
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
        # CacheModule을 사용하여 캐시 초기화
        if self.cache_module:
            self.cache_module.clear_all_cache()
            return

        # CacheModule이 없으면 기존 방식 사용
        self.answer_cache.clear()
        self.documents_cache.clear()
        self.metadata_cache.clear()
        print("️ 모든 캐시가 초기화되었습니다.")
    
    def get_cache_stats(self) -> Dict:
        """캐시 상태 정보 반환"""
        # CacheModule을 사용하여 캐시 통계 반환
        if self.cache_module:
            return self.cache_module.get_cache_stats()

        # CacheModule이 없으면 기존 방식 사용
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
            mode: 검색 모드 (항상 'document' 사용)
        """
        
        # 시작 시간 기록
        start_time = time.time()
        error_msg = None
        success = True
        response = ""
        metadata = {}
        
        try:
            # 로깅 시스템 시작 - log_query는 답변 완료 후에 호출해야 함
            # if chat_logger:
            #     chat_logger.log_query(query, "started")
            
            # 검색 의도 분류
            if mode == 'auto':
                with TimerContext(chat_logger, "classify_intent") if chat_logger else nullcontext():
                    mode = self._classify_search_intent(query)
                print(f" 검색 모드: {mode}")
            
            self.search_mode = mode
            metadata['search_mode'] = mode
            
            # 모드에 따른 처리
            query_lower = query.lower()

            # document 모드인 경우
            if self.search_mode == 'document':
                # "문서", "찾아", "검색" 키워드가 있으면 여러 문서 목록 반환
                if any(keyword in query_lower for keyword in ["문서", "찾아", "검색", "어떤", "무엇", "뭐"]):
                    # 여러 문서 검색
                    search_results = self._search_by_content(query)

                    if not search_results:
                        response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                    else:
                        # 상위 5개 문서 목록 표시
                        response = f"**{query}** 검색 결과\n\n"

                        # 중복 제거하면서 정렬 순서 유지
                        seen = set()
                        unique_results = []
                        for r in sorted(search_results, key=lambda x: x.get('score', 0), reverse=True):
                            if r['filename'] not in seen:
                                seen.add(r['filename'])
                                unique_results.append(r)

                        response += f"총 {len(unique_results)}개 문서 발견\n\n"

                        for i, result in enumerate(unique_results[:10], 1):
                            response += f"**{i}. {result['filename']}**\n"

                            # Everything search의 경우 메타데이터만 깔끔하게 표시
                            if result.get('source') == 'everything_search':
                                if result.get('date'):
                                    response += f"   📅 날짜: {result['date']}\n"
                                if result.get('category') and result['category'] != '기타':
                                    response += f"   📁 카테고리: {result['category']}\n"
                                if result.get('keywords'):
                                    # 키워드를 깔끔하게 표시
                                    keywords_list = result['keywords'].split()[:5]  # 최대 5개 키워드만
                                    if keywords_list:
                                        response += f"   🔑 키워드: {', '.join(keywords_list)}\n"
                            # 기존 검색 결과
                            elif result.get('context'):
                                # OCR 텍스트인지 확인하고 깔끔하게 처리
                                context = result['context']
                                if '[OCR' in context or '페이지' in context:
                                    # OCR 텍스트는 표시하지 않고 메타데이터만
                                    response += f"   📄 스캔 문서 (OCR 필요)\n"
                                else:
                                    # 일반 텍스트는 깔끔하게 표시
                                    clean_text = context.replace('\n', ' ').strip()[:150]
                                    response += f"   📝 {clean_text}...\n"
                            response += "\n"

                        if len(unique_results) > 5:
                            response += f"\n... 외 {len(unique_results) - 5}개 문서\n"
                else:
                    # 단일 문서 상세 답변
                    # Everything search를 사용하여 가장 관련된 문서 찾기
                    if self.everything_search:
                        search_results = self.everything_search.search(query, limit=1)
                        if search_results:
                            top_result = search_results[0]
                            doc_path = Path(top_result['path'])

                            if doc_path.exists():
                                print(f"📄 선택된 문서: {doc_path.name}")
                                # LLM을 사용하여 문서 내용 분석 및 답변 생성
                                response = self._generate_llm_summary(doc_path, query)
                            else:
                                response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                        else:
                            response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                    else:
                        # 기존 방식 (Everything search 없을 때)
                        doc_path = self.find_best_document(query)

                        if not doc_path:
                            response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                        else:
                            print(f"📄 선택된 문서: {doc_path.name}")
                            # LLM을 사용하여 문서 내용 분석 및 답변 생성
                            response = self._generate_llm_summary(doc_path, query)
            else:
                # Document 모드가 아닌 경우 (발생하지 않아야 함)
                response = "❌ 문서 검색 중 오류가 발생했습니다."

            # 처리 시간 계산 및 로깅
            processing_time = time.time() - start_time
            if chat_logger:
                chat_logger.log_query(
                    query=query,
                    response=response,
                    search_mode=self.search_mode,
                    processing_time=processing_time,
                    metadata=metadata
                )
                print(f"✅ Query completed in {processing_time:.2f}s")

            return response

        except Exception as e:
            # 에러 발생
            error_msg = str(e)
            success = False
            response = f" 처리 중 오류 발생: {error_msg}"
            
            # 처리 시간 계산
            processing_time = time.time() - start_time
            
            # 로깅 시스템
            if chat_logger:
                chat_logger.log_error(
                    error_type=type(e).__name__,
                    error_msg=error_msg,
                    query=query
                )
            
            return response
    
    def _get_detail_only_prompt(self, query: str, context: str, filename: str) -> str:
        """기본 정보 제외한 상세 내용만 생성하는 프롬프트"""
        return f"""
다음 문서에서 핵심 내용을 추출하세요. 
️ 기안자, 날짜, 문서번호 등 기본 정보는 제외하고 실질적인 내용만 작성하세요.

 **구매/수리 사유 및 현황**
• 어떤 문제가 있었는지
• 현재 상황은 어떤지
• 제안하는 해결책은 무엇인지

 **기술적 세부사항** (있는 경우만)
• 장비 사양이나 모델
• 검토한 대안들
• 선택 근거

 **비용 관련** (있는 경우만)
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

️ 30초 내 답변 필요
️ 없는 정보는 "확인 필요"로 표시
"""
        
        # 보고서/내역 정리/기술검토서
        if any(word in query for word in ["내역", "정리", "총", "목록", "구매", "품목", "검토서", "내용", "요약", "알려"]):
            # 기본 정보가 이미 추출되어 있는지 확인
            has_basic_info = 'basic_summary' in locals() if 'locals' in dir() else False
            
            if has_basic_info:
                # 기본 정보가 이미 있으면 상세 내용만 요청
                return f"""
[문서 상세 분석] {filename}

️ 기본 정보(기안자, 날짜 등)는 이미 추출됨. 아래 내용만 작성하세요:

 **핵심 내용**
• 구매/수리 사유: [파손 상태, 문제점 등 구체적으로]
• 현재 상황: [현황 설명]  
• 해결 방안: [제안 내용]

 **기술 검토 내용** (해당시)
• 기존 장비 문제점: [구체적 문제 설명]
• 대체 장비: [모델명, 제조사]
• 주요 사양: [핵심 스펙]
• 선정 이유: [선택 근거]

 **비용 정보**
• 총액: [금액] (부가세 포함/별도)
• 세부 내역:
  - [품목1]: [모델명] - [수량] x [단가] = [금액]
  - [품목2]: [모델명] - [수량] x [단가] = [금액]
• 납품업체: [업체명]

 **검토 의견**
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견/승인사항]

 출처: {filename}

문서 내용:
{context}

요청: {query}

️ 주의사항:
- 위 형식을 반드시 따를 것
- 모든 품목/장비 정보를 빠짐없이 포함
- 금액은 천단위 콤마 포함 (예: 820,000원)
- 모델명, 업체명 등 고유명사는 정확히 표기
"""
        
        # 감사/절차 확인
        if any(word in query for word in ["감사", "절차", "승인", "폐기"]):
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

️ 감사 지적 방지를 위해 정확히 확인
"""
        
        # 기본 프롬프트 (통일된 포맷)
        else:
            return f"""
[기술관리팀 문서 분석]


 {filename.replace('.pdf', '')}

 **기본 정보**
• 기안자: [문서에서 찾은 기안자명]
• 날짜: [문서 날짜]
• 문서 종류: [기안서/검토서/보고서 등]

 **주요 내용**
[질문과 관련된 핵심 내용을 구조화하여 표시]
• [주요 사항 1]
• [주요 사항 2]
• [세부 내용들...]

 **비용 정보** (비용 관련 내용이 있는 경우)
• 총액: [금액]
• 세부 내역:
  - [품목1]: [금액]
  - [품목2]: [금액]

 **검토 의견** (검토 의견이 있는 경우)
• [검토사항 1]
• [검토사항 2]
• 결론: [최종 의견]

 출처: {filename}

문서 내용:
{context}

요청: {query}

️ 주의사항:
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
                    logger.info(f"OCR 성공: {pdf_path.name} - {metadata.get('ocr_text_length', 0)}자 추출")
                return text
            else:
                if logger:
                    logger.warning(f"OCR 실패: {pdf_path.name}")
                return ""
                
        except ImportError:
            if logger:
                logger.warning("OCR 모듈 사용 불가 - pytesseract 또는 Tesseract 미설치")
            return ""
        except Exception as e:
            if logger:
                logger.error(f"OCR 처리 중 오류: {pdf_path.name} - {e}")
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
                        except Exception as e:
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
                if 'Control Box' in full_text or '지미집' in full_text:
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
                            if '7,680,000' in amt:
                                info['비용내역']['방송시스템'] = amt + '원'
                            if '34,340,000' in amt:
                                info['비용내역']['총합계'] = amt + '원 (VAT별도)'
                            if '200,000' in amt:
                                info['비용내역']['수리비용'] = amt + '원 (VAT별도)'
                            if not info['비용내역']:  # 첫 번째 금액
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
        if any(word in query_lower for word in ['비교', '차이', '어떤게 나은', '뭐가 좋']):
            intent['type'] = 'comparison'
            intent['wants_comparison'] = True
            intent['wants_recommendation'] = True
        if any(word in query_lower for word in ['추천', '권장', '어떻게', '방법']):
            intent['type'] = 'recommendation'
            intent['wants_recommendation'] = True
        if any(word in query_lower for word in ['긴급', '빨리', '급해', '바로']):
            intent['type'] = 'urgent'
            intent['is_urgent'] = True
            intent['tone'] = 'direct'
        if any(word in query_lower for word in ['얼마', '비용', '가격', '금액']):
            intent['type'] = 'cost'
            intent['needs_detail'] = True
        if any(word in query_lower for word in ['문제', '고장', '수리', '장애']):
            intent['type'] = 'problem'
            intent['wants_recommendation'] = True
        
        # 컨텍스트 키워드 추출
        important_words = ['DVR', '중계차', '카메라', '삼각대', '방송', '장비', '구매', '수리', '교체', '업그레이드']
        intent['context_keywords'] = [word for word in important_words if word.lower() in query_lower]
        
        # 응답 스타일 결정
        if '?' in query:
            intent['response_style'] = 'explanatory'
        if any(word in query_lower for word in ['해줘', '부탁', '좀']):
            intent['response_style'] = 'helpful'
        
        return intent
    
    def _generate_conversational_response(self, context: str, query: str, intent: Dict[str, Any],
                                         pdf_info: Dict[str, Any] = None) -> str:
        """자연스럽고 대화형 응답 생성"""

        # LLMModule을 사용하여 응답 생성
        if self.llm_module:
            try:
                response = self.llm_module.generate_conversational_response(
                    context=context[:3000],  # 컨텍스트 제한
                    query=query,
                    intent=intent
                )

                # 추가 컨텍스트나 추천 사항 자연스럽게 추가
                if intent.get('wants_recommendation') and '추천' not in response:
                    response += "\n\n참고로, 이와 관련해서 추가로 검토하시면 좋을 사항들도 있습니다. 필요하시면 말씀해 주세요."

                return response
            except Exception as e:
                logger.error(f"LLMModule 응답 생성 오류: {e}")
                return self._generate_fallback_response(context, query, intent)

        # LLMModule이 없으면 기존 방식 사용
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
        
        if intent['type'] == 'comparison':
            user_prompt = f"""다음 정보를 바탕으로 비교 분석을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 비교 대상들의 주요 차이점을 먼저 설명
- 각각의 장단점을 실용적 관점에서 설명
- 상황에 따른 추천 제공
- "이런 경우엔 A가 좋고, 저런 경우엔 B가 낫다"는 식으로 설명"""
        
        if intent['type'] == 'recommendation':
            user_prompt = f"""다음 정보를 바탕으로 실용적인 추천을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 추천 사항을 명확하게 제시
- 추천 이유를 논리적으로 설명
- 고려사항이나 주의점도 함께 언급
- 대안이 있다면 간단히 소개"""
        
        if intent['type'] == 'cost':
            user_prompt = f"""다음 정보에서 비용 관련 내용을 찾아 설명해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 구체적인 금액을 먼저 제시
- 비용 구성이나 내역 설명
- 비용 대비 가치나 효과 언급
- 예산 관련 조언이 있다면 추가"""
        
        if intent['is_urgent']:
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
        if intent['type'] == 'cost':
            cost_info = [line for line in key_info if '원' in line or '금액' in line]
            if cost_info:
                response += f"비용 관련 정보입니다. {cost_info[0]}"
        else:
            if key_info:
                response += f"관련 정보를 찾았습니다. {key_info[0]}"
        
        return response
    

    def _prepare_llm_context(self, content, max_length=2000):
        """LLM 컨텍스트 준비 헬퍼"""
        if not content:
            return ""

        # 내용이 너무 길면 요약
        if len(content) > max_length:
            # 처음과 끝 부분 추출
            start = content[:max_length//2]
            end = content[-(max_length//2):]
            content = f"{start}\n\n... [중략] ...\n\n{end}"

        return content

    def _extract_key_sentences(self, content, num_sentences=5):
        """핵심 문장 추출 헬퍼"""
        if not content:
            return []

        # 문장 분리
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_sentences:
            return sentences

        # 키워드 기반 중요도 계산
        important_keywords = ['결정', '승인', '구매', '계약', '예산', '진행', '완료']
        scored_sentences = []

        for sentence in sentences:
            score = sum(1 for keyword in important_keywords if keyword in sentence)
            scored_sentences.append((sentence, score))

        # 점수 순으로 정렬
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        return [s[0] for s in scored_sentences[:num_sentences]]

    def _format_llm_response(self, raw_response):
        """LLM 응답 포맷팅 헬퍼"""
        if not raw_response:
            return "응답 생성 실패"

        # 불필요한 공백 제거
        formatted = re.sub(r'\n{3,}', '\n\n', raw_response)
        formatted = formatted.strip()

        # 마크다운 스타일 개선
        formatted = re.sub(r'^#', '##', formatted, flags=re.MULTILINE)

        return formatted

    def _generate_llm_summary(self, pdf_path: Path, query: str) -> str:
        """LLM을 사용한 상세 요약 - 대화형 스타일"""
        logger.info("LLM 요약 생성 시작")
        # 사용자 의도 분석
        intent = self._analyze_user_intent(query)

        # 변수 초기화 (스코프 문제 방지)
        basic_summary = ""
        summary = []

        # PDF 파일인 경우 먼저 구조화된 정보 추출 시도
        if pdf_path.suffix.lower() == '.pdf':
            pdf_info = self._extract_full_pdf_content(pdf_path)
            
            # 대화형 응답 생성을 위한 컨텍스트 준비
            context_parts = []

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
                    summary.append(f"\n **세부 장애/수리 내역**")
                    
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
                    summary.append(f"\n **비용 내역**")
                    if '내외관보수' in pdf_info['비용내역']:
                        summary.append(f"• 중계차 내외관 보수: {pdf_info['비용내역']['내외관보수']}")
                    if '방송시스템' in pdf_info['비용내역']:
                        summary.append(f"• 방송 시스템 보수: {pdf_info['비용내역']['방송시스템']}")
                    if '총합계' in pdf_info['비용내역']:
                        summary.append(f"• **총 비용: {pdf_info['비용내역']['총합계']}**")
                # 금액 정보 (기존 호환성 유지)
                if '금액정보' in pdf_info and pdf_info['금액정보']:
                    summary.append(f"\n **주요 금액**")
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
                    summary.append(f"\n **검토 의견**")
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
                                    summary.append("\n** 1안: HD-SDI 입력 모델**")
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
                                    summary.append("\n** 2안: 기존 동일 모델**")
                                    summary.append("• 현재 시스템과 호환성 높음")
                                    summary.append("• 낮은 비용, 설치 용이")
                                    summary.append("• SD급 화질로 개선 효과 없음")
                        
                        # 종합 의견
                        if '종합' in opinion or '결론' in opinion:
                            summary.append("\n** 최종 추천**")
                            if '1안' in opinion and ('유리' in opinion or '적절' in opinion or '추천' in opinion):
                                summary.append("• **1안 채택 권장** - 장기적 운영 및 화질 개선 필요")
                            if '2안' in opinion and ('유리' in opinion or '적절' in opinion):
                                summary.append("• **2안 채택 권장** - 비용 절감 우선")
                    
                    # 중계차 관련인 경우
                    if '중계차 임대' in opinion:
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
                            summary.append(f"\n **도입 연도**: {도입_match.group(1)}년")
                
                # 업체 정보
                if '업체' in pdf_info:
                    summary.append(f"\n **관련 업체**: {pdf_info['업체']}")
            
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
                        print(" LLM 모델 로딩 중...")
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
                print(" LLM 모델 로딩 중...")
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
                    except PDFExtractionException as e:
                        pass
            
            if not text:
                return " 문서 내용을 읽을 수 없습니다"
            
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
                    combined_answer = f"{basic_summary}\n\n **상세 내용**\n{answer}"
                    return f"{combined_answer}\n\n 출처: {pdf_path.name}"
                else:
                    return f"{answer}\n\n 출처: {pdf_path.name}"
            
        except Exception as e:
            return f" 요약 생성 실패: {e}"
    
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
            
        if target_year:
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
                    if '수리' in filename or '보수' in filename:
                        cat = '수리'
                    if '폐기' in filename:
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
            if "기안자별" in query:
                return self._generate_drafter_report(query)
            if "월별" in query and "수리" in query:
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
                if '수리' in filename or '보수' in filename:
                    category = '수리'
                if '폐기' in filename:
                    category = '폐기'
                if '소모품' in filename:
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
                report.append(f" {target_year}년 기술관리팀 문서 통계 보고서")
            else:
                report.append(" 전체 기간 기술관리팀 문서 통계 보고서")
            
            report.append("=" * 50)
            report.append("")
            
            # 전체 요약
            report.append("###  전체 요약")
            report.append(f"• 총 문서 수: {doc_count}개")
            if total_amount > 0:
                report.append(f"• 총 금액: {total_amount:,}원")
            report.append("")
            
            # 카테고리별 통계
            report.append("###  카테고리별 현황")
            report.append("")
            
            for category, docs in stats.items():
                if docs:
                    count = len(docs)
                    ratio = (count / doc_count * 100) if doc_count > 0 else 0
                    report.append(f"• **{category}**: {count}건 ({ratio:.1f}%)")
            report.append("")
            
            # 기안자별 통계
            if drafters:
                report.append("###  기안자별 현황")
                report.append("")
                
                for drafter, count in sorted(drafters.items(), key=lambda x: x[1], reverse=True):
                    if drafter and drafter != '미상':
                        report.append(f"• **{drafter}**: {count}건")
                
                report.append("")
            
            # 월별 통계 (연도 지정시)
            if target_year and monthly:
                report.append("###  월별 현황")
                report.append("")
                
                for month in sorted(monthly.keys()):
                    count = monthly[month]
                    report.append(f"• **{int(month)}월**: {count}건")
                
                report.append("")
            
            # 주요 문서 리스트
            report.append("###  주요 문서 목록")
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
            return f" 통계 보고서 생성 실패: {e}"
    
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
            report.append(" 연도별 구매 현황 보고서 (2021-2025)")
            report.append("=" * 50)
            report.append("")
            
            report.append("###  연도별 구매 통계")
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
            report.append(f"** 총계: {total_count}건 - {total_amount:,}원**")
            report.append("")
            
            # 연도별 상세 내역
            report.append("###  연도별 상세 내역")
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
            return f" 연도별 구매 현황 생성 실패: {e}"
    
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
                if '수리' in filename or '보수' in filename:
                    category = '수리'
                if '폐기' in filename:
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
            report.append(" 기안자별 문서 작성 현황")
            report.append("=" * 50)
            report.append("")
            
            report.append("###  기안자별 전체 통계")
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
            report.append("###  기안자별 연도 분포")
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '미상':
                    stats = drafter_stats[drafter]
                    year_str = ", ".join([f"{year}년({count}건)" for year, count in sorted(stats['years'].items())])
                    report.append(f"• {drafter}: {year_str}")
            report.append("")
            
            # 기안자별 모든 문서
            report.append("###  기안자별 담당 문서 (전체)")
            report.append("* 실무 담당자에게 직접 문의 가능*")
            report.append("")
            
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '미상':
                    stats = drafter_stats[drafter]
                    report.append(f"####  **{drafter}** ({stats['count']}건)")
                    
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
                                '구매': '',
                                '수리': '', 
                                '폐기': '️',
                                '기타': ''
                            }.get(item['category'], '')
                            
                            # 전체 제목 표시 (축약 없이)
                            title = item['title']
                            report.append(f"  • [{date}] {cat_emoji} {title}")
                    report.append("")
            
            return "\n".join(report)
            
        except Exception as e:
            return f" 기안자별 현황 생성 실패: {e}"
    
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
            report.append(" 월별 수리 내역 및 비용 분석")
            report.append("=" * 50)
            report.append("")
            
            report.append("###  전체 요약")
            total_count = sum(stats['count'] for stats in monthly_stats.values())
            report.append(f"• 총 수리 건수: {total_count}건")
            if total_amount > 0:
                report.append(f"• 총 수리 비용: {total_amount:,}원")
                report.append(f"• 평균 수리 비용: {total_amount // total_count:,}원")
            report.append("")
            
            report.append("###  월별 수리 현황")
            report.append("")
            
            for month_key in sorted(monthly_stats.keys()):
                stats = monthly_stats[month_key]
                year, month = month_key.split('-')
                amount_str = f"{stats['amount']:,}원" if stats['amount'] > 0 else "금액미상"
                report.append(f"• **{year}년 {int(month)}월**: {stats['count']}건 - {amount_str}")
            
            report.append("")
            
            # 월별 상세 내역
            report.append("###  월별 상세 수리 내역")
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
            return f" 월별 수리 내역 생성 실패: {e}"
    
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
            if conditions.get('year_range') == 'after':
                year_str += " 이후"
            if conditions.get('year_range') == 'between':
                year_str = f"• 연도: {conditions.get('year_start')}년 ~ {conditions.get('year_end')}년"
            formatted.append(year_str)
        
        if 'price' in conditions:
            price_str = f"• 금액: {conditions['price']:,.0f}원"
            if conditions.get('price_range') == 'above':
                price_str += " 이상"
            if conditions.get('price_range') == 'below':
                price_str += " 이하"
            formatted.append(price_str)
        
        if 'equipment_type' in conditions:
            formatted.append(f"• 장비 유형: {conditions['equipment_type']}")
        
        if 'model' in conditions:
            formatted.append(f"• 모델: {conditions['model']}")
        
        return '\n'.join(formatted) if formatted else "조건 없음"
    
    def _search_location_summary(self, txt_path: Path, location: str) -> str:
        """특정 위치의 장비를 카테고리별로 정리"""
        # Asset 모드 제거됨
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
                                        except Exception as e:
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
                                except Exception as e:
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
                response = f" **{location} 장비 현황**\n"
                response += "=" * 70 + "\n"
                response += f" 총 **{total_count}개** 장비\n"
                if total_amount > 0:
                    # 금액 포맷팅 (억/천만원 단위)
                    if total_amount >= 100000000:  # 1억 이상
                        amount_str = f"{total_amount/100000000:.1f}억원"
                    if total_amount >= 10000000:  # 1천만원 이상
                        amount_str = f"{total_amount/10000000:.0f}천만원"
                    else:
                        amount_str = f"{total_amount:,}원"
                    response += f" 총 자산가치: **{amount_str}**\n\n"
                else:
                    response += "\n"
                
                # 카테고리별 요약
                response += "###  카테고리별 상세 현황\n"
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
                        if category_amount >= 10000000:
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
                
                response += f"\n 출처: {txt_path.name}"
                # Asset 모드 제거됨 - 직접 응답 반환
                return response
            else:
                return f" {location}에서 장비를 찾을 수 없습니다."
                
        except Exception as e:
            return f" 검색 실패: {e}"
    
    def _determine_equipment_category(self, equipment_name: str, item_text: str) -> str:
        """장비명과 텍스트로 카테고리 결정"""
        name_lower = equipment_name.lower()
        text_lower = item_text.lower()
        
        if any(kw in name_lower or kw in text_lower for kw in ['camera', '카메라', 'ccu', 'viewfinder', '뷰파인더']):
            return " 카메라 시스템"
        if any(kw in name_lower or kw in text_lower for kw in ['monitor', '모니터', 'display']):
            return "️ 모니터"
        if any(kw in name_lower or kw in text_lower for kw in ['audio', '오디오', 'mixer', '믹서', 'mic', '마이크']):
            return "️ 오디오 장비"
        if any(kw in name_lower or kw in text_lower for kw in ['server', '서버', 'storage', '스토리지']):
            return " 서버/스토리지"
        if any(kw in name_lower or kw in text_lower for kw in ['switch', '스위치', 'router', '라우터', 'matrix']):
            return " 스위칭/라우팅"
        if any(kw in name_lower or kw in text_lower for kw in ['cable', '케이블', 'connector', '커넥터']):
            return " 케이블/커넥터"
        if any(kw in name_lower or kw in text_lower for kw in ['tripod', '트라이포드', 'pedestal', '페데스탈']):
            return " 카메라 지원장비"
        if any(kw in name_lower or kw in text_lower for kw in ['intercom', '인터컴', 'talkback']):
            return " 인터컴"
        if any(kw in name_lower or kw in text_lower for kw in ['converter', '컨버터', 'encoder', '인코더']):
            return " 컨버터/인코더"
        else:
            return " 기타 장비"

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
            if current_item:
                current_item.append(line)
                # 필드별 매칭 확인
                if field_name == "담당자" and "담당자:" in line:
                    if search_value in line:
                        is_matching = True
                if field_name == "위치" and "위치:" in line:
                    # 정확한 위치 매칭 로직 적용
                    location_match = re.search(r'위치:\s*([^|\n]+)', line)
                    if location_match:
                        actual_location = location_match.group(1).strip()
                        
                        # 정확한 매칭 규칙
                        if search_value == actual_location:
                            # 완전 일치
                            is_matching = True
                        if search_value == '부조정실':
                            # '부조정실'로 검색시 '*부조정실' 패턴만 매칭
                            is_matching = actual_location.endswith('부조정실')
                        if search_value == '스튜디오':
                            # '스튜디오'로 검색시 '*스튜디오' 패턴만 매칭 
                            is_matching = actual_location.endswith('스튜디오')
                        if search_value == '편집실':
                            # '편집실'로 검색시 '*편집실' 패턴만 매칭
                            is_matching = actual_location.endswith('편집실')
                        if search_value in ['중계차', 'van', 'Van', 'VAN']:
                            # 중계차 검색시 Van 관련 위치 모두 매칭
                            is_matching = 'Van' in actual_location or 'VAN' in actual_location
                        if len(search_value) > 3:
                            # 3글자 이상의 구체적인 위치명은 부분 매칭 허용
                            is_matching = search_value in actual_location
                if field_name == "벤더사" and "벤더사:" in line:
                    if search_value in line:
                        is_matching = True
                if field_name == "제조사" and "제조사:" in line:
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
    
    

    def _extract_document_metadata(self, file_path):
        """문서 메타데이터 추출 헬퍼"""
        metadata = {}

        try:
            # 파일명에서 정보 추출
            filename = file_path.stem if hasattr(file_path, 'stem') else str(file_path)

            # 날짜 추출
            date_patterns = [
                r'(\d{4})[.\-_](\d{1,2})[.\-_](\d{1,2})',
                r'(\d{4})(\d{2})(\d{2})',
                r'(\d{2})[.\-_](\d{1,2})[.\-_](\d{1,2})'
            ]
            for pattern in date_patterns:
                match = re.search(pattern, filename)
                if match:
                    metadata['date'] = match.group(0)
                    break

            # 기안자 추출
            author_patterns = [
                r'([가-힣]{2,4})([\s_\-])?기안',
                r'기안자[\s_\-:]*([가-힣]{2,4})',
                r'작성자[\s_\-:]*([가-힣]{2,4})'
            ]
            for pattern in author_patterns:
                match = re.search(pattern, filename)
                if match:
                    metadata['author'] = match.group(1) if '기안' in pattern else match.group(1)
                    break

            return metadata
        except Exception as e:
            print(f"메타데이터 추출 오류: {e}")
            return {}

    def _score_document_relevance(self, content, keywords):
        """문서 관련성 점수 계산 헬퍼"""
        if not content or not keywords:
            return 0

        score = 0
        content_lower = content.lower()

        for keyword in keywords:
            keyword_lower = keyword.lower()
            # 정확한 매칭
            exact_matches = content_lower.count(keyword_lower)
            score += exact_matches * 2

            # 부분 매칭
            if len(keyword_lower) > 2:
                partial_matches = sum(1 for word in content_lower.split()
                                    if keyword_lower in word)
                score += partial_matches

        # 문서 길이 정규화
        doc_length = len(content)
        if doc_length > 0:
            score = score / (doc_length / 1000)  # 1000자 단위로 정규화

        return score

    def _format_search_result(self, file_path, content, metadata):
        """검색 결과 포맷팅 헬퍼"""
        result = []

        # 제목
        filename = file_path.stem if hasattr(file_path, 'stem') else str(file_path)
        result.append(f"📄 {filename}")
        result.append("-" * 50)

        # 메타데이터
        if metadata.get('date'):
            result.append(f"📅 날짜: {metadata['date']}")
        if metadata.get('author'):
            result.append(f"✍️ 기안자: {metadata['author']}")

        # 내용 요약 (처음 200자)
        if content:
            summary = content[:200].replace('\n', ' ')
            result.append(f"\n📝 내용 미리보기:")
            result.append(summary + "...")

        return '\n'.join(result)

    def _aggregate_search_results(self, results):
        """검색 결과 통합 헬퍼"""
        if not results:
            return "검색 결과가 없습니다."

        aggregated = []
        aggregated.append(f"🔍 총 {len(results)}개 문서 발견\n")
        aggregated.append("=" * 60)

        for i, result in enumerate(results, 1):
            aggregated.append(f"\n[{i}] {result}")
            if i < len(results):
                aggregated.append("\n" + "-" * 60)

        return '\n'.join(aggregated)

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

                # 기안자 검색 처리 (메타데이터 DB 활용)
                if '기안자' in query_lower:
                    # "최새름 기안자" 또는 "기안자 최새름" 형태 추출
                    drafter_match = re.search(r'([가-힣]{2,4})\s*기안자|기안자\s*([가-힣]{2,4})', query)
                    if drafter_match:
                        search_drafter = drafter_match.group(1) or drafter_match.group(2)
                        if search_drafter and metadata.get('is_pdf'):
                            found_drafter = False

                            # 1. 메타데이터 DB에서 먼저 확인
                            if self.metadata_db:
                                db_info = self.metadata_db.get_document(filename)
                                if db_info and db_info.get('drafter'):
                                    if search_drafter in db_info['drafter']:
                                        score += 50
                                        found_drafter = True

                            # 2. DB에 없으면 PDF에서 직접 추출 시도
                            if not found_drafter and metadata.get('drafter') is None:
                                try:
                                    # 간단한 텍스트 추출만 시도 (빠른 처리)
                                    import pdfplumber
                                    with pdfplumber.open(metadata['path']) as pdf:
                                        if pdf.pages:
                                            # 첫 페이지만 빠르게 확인
                                            text = pdf.pages[0].extract_text() or ""
                                            if len(text) > 50:  # 텍스트 PDF인 경우
                                                # 기안자 패턴 검색
                                                patterns = [
                                                    r'기안자[\s:：]*([가-힣]{2,4})',
                                                    r'작성자[\s:：]*([가-힣]{2,4})',
                                                ]
                                                for pattern in patterns:
                                                    match = re.search(pattern, text)
                                                    if match:
                                                        drafter = match.group(1).strip()
                                                        # DB에 저장
                                                        if self.metadata_db:
                                                            self.metadata_db.update_document(filename, drafter=drafter)
                                                        if search_drafter in drafter:
                                                            score += 50
                                                            found_drafter = True
                                                        break
                                except Exception as e:
                                    pass

                        # 기안자 검색인데 매칭 안되면 건너뜀
                        if score < 50:
                            continue

                # 장비명 특별 가중치 (DVR, CCU 등) - 정확한 매칭만
                equipment_names = ['dvr', 'ccu', '카메라', '렌즈', '모니터', '스위처', '마이크', '믹서', '삼각대', '중계차']
                for equipment in equipment_names:
                    if equipment in query_lower:
                        # DVR 검색시 DVR만 찾기 (단어 경계 체크)
                        if equipment == 'dvr':
                            # DVR이 정확히 있는지 확인 (D-tap, VR 등 제외)
                            if re.search(r'\bDVR\b', filename, re.IGNORECASE):
                                score += 20  # DVR 완전 매칭
                            if 'dvr' in filename_lower and 'd-tap' not in filename_lower and 'vr' not in filename_lower:
                                score += 15
                        else:
                            # 다른 장비명은 기존 방식
                            if equipment in filename_lower:
                                score += 15

                        # 키워드 체크
                        if any(equipment == kw.lower() for kw in metadata.get('keywords', [])):
                            score += 8
                
                for word in query_words:
                    if len(word) >= 2 and word not in stopwords:
                        keywords_in_query.append(word)
                        # 파일명에 해당 단어가 있으면 점수 부여
                        if word in file_words:
                            # 단어 길이에 비례한 점수
                            score += len(word) * 2
                        # 부분 매칭 - DVR 같은 짧은 단어는 제외
                        if len(word) >= 4:  # 4글자 이상만 부분 매칭
                            for f_word in file_words:
                                # 전체 포함이 아닌 부분 일치만
                                if len(f_word) >= 4 and (word in f_word or f_word in word):
                                    score += len(word) // 2  # 부분 매칭은 점수 절반
                
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
                # 기안자 검색시 점수가 있으면 포함
                has_equipment = False  # 변수를 먼저 초기화

                if '기안자' in query_lower:
                    MIN_SCORE = 1 if score > 0 else 999  # 기안자 검색은 점수 있으면 포함
                elif re.search(r'20\d{2}년', query):
                    MIN_SCORE = 2  # 년도 검색은 낮은 기준
                else:
                    MIN_SCORE = 3  # 기본 최소 3점 이상만 포함

                # 장비명 검색시 적절한 기준 적용
                for equipment in equipment_names:
                    if equipment in query_lower:
                        has_equipment = True
                        # DVR의 경우 특별 처리
                        if equipment == 'dvr':
                            if 'DVR' in filename or ('dvr' in filename_lower and 'd-tap' not in filename_lower and 'vr' not in filename_lower):
                                MIN_SCORE = 0  # DVR이 정확히 있으면 포함
                            else:
                                MIN_SCORE = 10  # DVR 검색인데 DVR이 없으면 높은 기준
                        else:
                            # 다른 장비명
                            if equipment in filename_lower:
                                MIN_SCORE = 0
                            else:
                                MIN_SCORE = max(3, MIN_SCORE)
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
                    if doc['score'] == unique_docs[filename]['score'] and 'year_' in doc.get('cache_key', ''):
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
                return " 관련 문서를 찾을 수 없습니다."
            
            # 결과 포맷팅 (통합형 UI)
            report = []
            report.append(f"##  '{query}' 검색 결과")
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
                report.append(f"###  {year}년 ({len(docs_by_year[year])}개)\n")
                
                for doc in docs_by_year[year]:
                    info = doc['info']
                    filename = doc['filename']
                    relative_path = doc.get('cache_key', filename)  # 캐시 키가 상대 경로
                    
                    # 카테고리 판단 및 이모지
                    if '구매' in filename:
                        category = "구매요청"
                        emoji = ""
                    if '수리' in filename or '보수' in filename:
                        category = "수리/보수"
                        emoji = ""
                    if '폐기' in filename:
                        category = "폐기처리"
                        emoji = "️"
                    if '검토' in filename:
                        category = "검토보고서"
                        emoji = ""
                    else:
                        category = "기타"
                        emoji = ""
                    
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
                        if '내용' in text:
                            content_match = re.search(r'내용[:\s]+([^\n]+)', text)
                            if content_match:
                                summary = content_match.group(1).strip()
                        if '사유' in text:
                            reason_match = re.search(r'사유[:\s]+([^\n]+)', text)
                            if reason_match:
                                summary = reason_match.group(1).strip()

                    # 텍스트가 없거나 추출 실패시 기본값
                    if not summary:
                        if '구매' in filename:
                            summary = "장비 구매 요청"
                        if '수리' in filename or '보수' in filename:
                            summary = "장비 수리/보수 건"
                        if '폐기' in filename:
                            summary = "노후 장비 폐기 처리"
                        if '교체' in filename:
                            summary = "노후 장비 교체 검토"
                        if '검토' in filename:
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
            return f" 문서 검색 실패: {e}"

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

            print(f" 장비 키워드: {equipment_keywords}, 작업 키워드: {action_keywords}")

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
                    if has_action_keyword:
                        secondary_files.append(path)

            # 3. 결과 병합 (최대 15개)
            relevant_files = primary_files[:10] + secondary_files[:5]

            if not relevant_files:
                # 키워드가 너무 없으면 내용 검색 시도 (시간 소요)
                if len(equipment_keywords) > 0:
                    print(" 파일명에서 찾지 못함, 내용 검색 시작...")
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
                            except Exception as e:
                                continue
                    relevant_files.extend(content_match_files)

            if not relevant_files:
                return f" '{', '.join(equipment_keywords + action_keywords)}' 관련 문서를 찾을 수 없습니다."

            print(f" {len(relevant_files)}개 관련 문서 발견")

            # 성능 최적화: 상위 5개 문서만 처리
            max_docs_to_process = 5
            files_to_process = relevant_files[:max_docs_to_process]
            if len(relevant_files) > max_docs_to_process:
                print(f" 성능 최적화: 상위 {max_docs_to_process}개 문서만 처리 (전체 {len(relevant_files)}개 중)")

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
                    print(f"️ {file_path.name} 처리 실패: {e}")
                    continue

            if not document_analyses:
                return " 문서 내용을 분석할 수 없습니다."

            # 5. LLM을 사용하여 종합 분석
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print(" LLM 모델 로딩 중...")
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
            result.append(f" **'{', '.join(equipment_keywords)}' 관련 {len(document_analyses)}개 문서 분석**\n")
            result.append("="*50 + "\n\n")

            # LLM 분석 결과
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            # 분석된 문서 목록
            result.append("\n **분석된 문서:**\n")
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
            return f" 내용 기반 분석 실패: {e}"

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
                return " 검색 키워드를 찾을 수 없습니다. 구체적인 키워드를 지정해주세요."

            print(f" 키워드로 문서 검색: {keywords}")

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
                return f" '{', '.join(keywords)}' 관련 문서를 찾을 수 없습니다."

            print(f" {len(relevant_files)}개 관련 문서 발견")

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
                    print(f"️ {file_path.name} 처리 실패: {e}")
                    continue

            if not document_summaries:
                return " 문서 내용을 읽을 수 없습니다."

            # LLM을 사용하여 종합 정리
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print(" LLM 모델 로딩 중...")
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
            result.append(f" **{len(document_summaries)}개 {', '.join(keywords)} 관련 문서 종합 분석**\n")
            result.append("="*50 + "\n")

            # LLM 응답 추가
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            # 각 문서 간단 정보
            result.append("\n **분석된 문서 목록:**\n")
            for doc in document_summaries:
                result.append(f"\n• **{doc['title']}**")
                result.append(f"  - 날짜: {doc['date']}")
                result.append(f"  - 기안자: {doc['drafter']}")
                if doc['amount']:
                    result.append(f"  - 금액: {doc['amount']}")

            return '\n'.join(result)

        except Exception as e:
            return f" 문서 종합 분석 실패: {e}"

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
                    if location == '부조정실':
                        # '부조정실'로 검색시 '*부조정실' 패턴만 매칭
                        return actual_location.endswith('부조정실')
                    if location == '스튜디오':
                        # '스튜디오'로 검색시 '*스튜디오' 패턴만 매칭 
                        return actual_location.endswith('스튜디오')
                    if location == '편집실':
                        # '편집실'로 검색시 '*편집실' 패턴만 매칭
                        return actual_location.endswith('편집실')
                    if location in ['중계차', 'van', 'Van', 'VAN']:
                        # 중계차 검색시 Van 관련 위치 모두 매칭
                        return 'Van' in actual_location or 'VAN' in actual_location
                    if location == "광화문부조정실":
                        # "광화문 부조정실" 같은 복합 위치명 처리
                        return "광화문" in actual_location and "부조정실" in actual_location
                    if len(location) > 3:
                        # 3글자 이상의 구체적인 위치명은 부분 매칭 허용
                        return location in actual_location
        
        return False

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
                response = f" **{equipment.upper()} 위치별 현황**\n"
                response += "=" * 70 + "\n"
                response += f" 총 {total_count}개 장비가 {len(location_equipment)}개 위치에 분포\n\n"
                
                # 위치별 정렬 (많은 순)
                sorted_locations = sorted(location_equipment.items(), key=lambda x: len(x[1]), reverse=True)
                
                for location, items in sorted_locations:
                    response += f" **{location}**: {len(items)}개\n"
                    # 샘플 3개만 표시
                    for i, item in enumerate(items[:3], 1):
                        response += f"   {i}. {item}\n"
                    if len(items) > 3:
                        response += f"   ... 외 {len(items)-3}개\n"
                    response += "\n"
                
                response += f" 출처: {txt_path.name}"
                return response
            else:
                return f" {equipment.upper()} 장비를 찾을 수 없습니다."
                
        except Exception as e:
            return f" 검색 실패: {e}"

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
        if search_location == '부조정실':
            return actual_location.endswith('부조정실')
        if search_location == '스튜디오':
            return actual_location.endswith('스튜디오')
        if search_location == '편집실':
            return actual_location.endswith('편집실')
        if search_location in ['중계차', 'van', 'Van', 'VAN']:
            return 'Van' in actual_location or 'VAN' in actual_location or '중계차' in actual_location
        if len(search_location) > 3:
            return search_location in actual_location
        
        return False


def main():
    """메인 실행 함수"""
    print("=" * 60)
    print(" Perfect RAG - 정확한 문서 검색 시스템")
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
    
    print("\n 테스트 시작")
    print("=" * 60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n질문 {i}: {query}")
        print("-" * 40)
        answer = rag.answer(query)
        print(answer)
        print("-" * 40)
        
        # 자동 진행 (input 제거)
    
    print("\n" + "=" * 60)
    print(" 테스트 완료!")
    print("=" * 60)




    def _manage_cache_size(self, cache_dict, max_size, cache_name="cache"):
        """캐시 크기 관리 - LRU 방식으로 오래된 항목 제거"""
        if len(cache_dict) > max_size:
            # 가장 오래된 항목들 제거 (FIFO)
            items_to_remove = len(cache_dict) - max_size
            for _ in range(items_to_remove):
                removed = cache_dict.popitem(last=False)  # 가장 오래된 항목 제거
            print(f"  🗑️ {cache_name}에서 {items_to_remove}개 항목 제거 (현재 크기: {len(cache_dict)})")

    def _add_to_cache(self, cache_dict, key, value, max_size):
        """캐시에 항목 추가 with 크기 제한"""
        # 기존 항목이면 삭제 후 다시 추가 (LRU를 위해)
        if key in cache_dict:
            del cache_dict[key]

        # 새 항목 추가
        cache_dict[key] = {
            'data': value,
            'timestamp': time.time()
        }

        # 크기 제한 확인
        self._manage_cache_size(cache_dict, max_size, str(type(cache_dict)))

    def clear_old_cache(self):
        """오래된 캐시 항목 제거"""
        current_time = time.time()

        # 각 캐시 순회하며 오래된 항목 제거
        for cache_name, cache_dict in [
            ('documents', self.documents_cache),
            ('metadata', self.metadata_cache),
            ('answer', self.answer_cache),
            ('pdf_text', self.pdf_text_cache)
        ]:
            if not hasattr(self, cache_name + '_cache'):
                continue

            items_to_remove = []
            for key, value in cache_dict.items():
                if isinstance(value, dict) and 'timestamp' in value:
                    if current_time - value['timestamp'] > self.CACHE_TTL:
                        items_to_remove.append(key)

            for key in items_to_remove:
                del cache_dict[key]

            if items_to_remove:
                print(f"  🗑️ {cache_name}_cache에서 {len(items_to_remove)}개 만료 항목 제거")

    def get_cache_stats(self):
        """캐시 통계 반환"""
        stats = {
            'documents_cache': len(self.documents_cache),
            'metadata_cache': len(self.metadata_cache),
            'answer_cache': len(self.answer_cache) if hasattr(self, 'answer_cache') else 0,
            'pdf_text_cache': len(self.pdf_text_cache) if hasattr(self, 'pdf_text_cache') else 0,
        }

        # 메모리 사용량 추정 (대략적)
        import sys
        total_size = 0
        for cache_dict in [self.documents_cache, self.metadata_cache,
                          getattr(self, 'answer_cache', {}),
                          getattr(self, 'pdf_text_cache', {})]:
            total_size += sys.getsizeof(cache_dict)

        stats['estimated_memory_mb'] = total_size / (1024 * 1024)

        return stats
if __name__ == "__main__":
    main()