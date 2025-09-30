#!/usr/bin/env python3
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import threading
from queue import Queue
from functools import partial

"""
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
from contextlib import nullcontext

try:
    from log_system import get_logger, TimerContext
    chat_logger = get_logger()
    logger = chat_logger
except ImportError:
    chat_logger = None
    logger = None
    TimerContext = None
    
try:
    from response_formatter import ResponseFormatter
except ImportError:
    ResponseFormatter = None

warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfplumber")

logging.getLogger("pdfplumber").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

try:
    from config_manager import config_manager as cfg
    USE_YAML_CONFIG = True
except ImportError:
    import config as cfg
    USE_YAML_CONFIG = False

from rag_system.qwen_llm import QwenLLM
from rag_system.llm_singleton import LLMSingleton
from metadata_db import MetadataDB

try:
    from everything_like_search import EverythingLikeSearch
    EVERYTHING_SEARCH_AVAILABLE = True
except ImportError:
    EVERYTHING_SEARCH_AVAILABLE = False
    if logger:
        logger.warning("EverythingLikeSearch not available, using legacy search")

try:
    from metadata_extractor import MetadataExtractor
    METADATA_EXTRACTOR_AVAILABLE = True
except ImportError:
    METADATA_EXTRACTOR_AVAILABLE = False
    if logger:
        logger.warning("MetadataExtractor not available, metadata extraction disabled")

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

try:
    from statistics_module import StatisticsModule
    STATISTICS_MODULE_AVAILABLE = True
except ImportError:
    STATISTICS_MODULE_AVAILABLE = False
    if logger:
        logger.warning("StatisticsModule not available - using embedded statistics")

try:
    from intent_module import IntentModule
    INTENT_MODULE_AVAILABLE = True
except ImportError:
    INTENT_MODULE_AVAILABLE = False
    if logger:
        logger.warning("IntentModule not available - using embedded intent analysis")

import traceback

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

class DocumentNotFoundException(RAGException):
    """문서를 찾을 수 없을 때"""

class PDFExtractionException(RAGException):
    """PDF 추출 실패"""

class LLMException(RAGException):
    """LLM 관련 오류"""

class CacheException(RAGException):
    """캐시 관련 오류"""

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
        self._load_performance_config()

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

        self.max_pdf_cache = 50

        self.config_dir = Path(__file__).parent / 'config'
        self.config_dir.mkdir(exist_ok=True)
        self.cache_dir = self.config_dir / 'cache'
        self.cache_dir.mkdir(exist_ok=True)

        self.llm = None
        from collections import OrderedDict
        self.MAX_CACHE_SIZE = 100
        self.MAX_METADATA_CACHE = 500
        self.MAX_PDF_CACHE = 50
        self.CACHE_TTL = 3600

        self.documents_cache = OrderedDict()
        self.metadata_cache = OrderedDict()
        self.search_mode = 'document'
        self.answer_cache = OrderedDict()
        self.pdf_text_cache = OrderedDict()

        self.pdf_processor = None
        self.error_handler = None
        self.error_recovery = None

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

        self.document_module = None
        if DOCUMENT_MODULE_AVAILABLE:
            try:
                doc_config = {
                    'max_pdf_cache': self.max_pdf_cache,
                    'max_text_length': self.max_text_length,
                    'max_pdf_pages': self.max_pdf_pages,
                    'enable_ocr': False
                }
                self.document_module = DocumentModule(doc_config)
                if logger:
                    logger.info("✅ DocumentModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ DocumentModule 초기화 실패: {e}")
                self.document_module = None

        self.llm_module = None
        if LLM_MODULE_AVAILABLE:
            try:
                llm_config = {
                    'model_path': self.model_path,
                    'preload_llm': preload_llm
                }
                self.llm_module = LLMModule(llm_config)
                if logger:
                    logger.info("✅ LLMModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ LLMModule 초기화 실패: {e}")
                self.llm_module = None

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

        self.statistics_module = None
        if STATISTICS_MODULE_AVAILABLE:
            try:
                stats_config = {
                    'docs_dir': str(self.docs_dir)
                }
                self.statistics_module = StatisticsModule(stats_config)
                if logger:
                    logger.info("✅ StatisticsModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ StatisticsModule 초기화 실패: {e}")
                self.statistics_module = None

        self.intent_module = None
        if INTENT_MODULE_AVAILABLE:
            try:
                self.intent_module = IntentModule(llm_module=self.llm_module)
                if logger:
                    logger.info("✅ IntentModule 초기화 성공")
            except Exception as e:
                if logger:
                    logger.error(f"❌ IntentModule 초기화 실패: {e}")
                self.intent_module = None

        self.everything_search = None
        if not self.search_module and EVERYTHING_SEARCH_AVAILABLE:
            try:
                self.everything_search = EverythingLikeSearch()
                if not hasattr(self, '_index_initialized'):
                    self.everything_search.index_all_files()
                    self.__class__._index_initialized = True
                if logger:
                    logger.info("Everything-like search initialized successfully")
            except Exception as e:
                if logger:
                    logger.error(f"Failed to initialize Everything-like search: {e}")
                self.everything_search = None

        self.formatter = ResponseFormatter() if ResponseFormatter else None

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

        try:
            self.metadata_db = MetadataDB(db_path=str(self.config_dir / "metadata.db"))
            logger.info("✅ MetadataDB 초기화 성공")
        except Exception as e:
            logger.error(f"️ MetadataDB 초기화 실패: {e}")
            self.metadata_db = None

        self.pdf_files = []
        self.txt_files = []

        self.pdf_files.extend(list(self.docs_dir.glob('*.pdf')))
        self.txt_files.extend(list(self.docs_dir.glob('*.txt')))

        for year in range(2014, 2026):
            year_folder = self.docs_dir / f"year_{year}"
            if year_folder.exists():
                self.pdf_files.extend(list(year_folder.glob('*.pdf')))
                self.txt_files.extend(list(year_folder.glob('*.txt')))

        special_folders = ['recent', 'archive']
        for folder in special_folders:
            special_folder = self.docs_dir / folder
            if special_folder.exists():
                self.pdf_files.extend(list(special_folder.glob('*.pdf')))
                self.txt_files.extend(list(special_folder.glob('*.txt')))

        self.pdf_files = list(set(self.pdf_files))
        self.txt_files = list(set(self.txt_files))
        self.all_files = self.pdf_files + self.txt_files

        if logger:
            logger.info(f"{len(self.pdf_files)}개 PDF, {len(self.txt_files)}개 TXT 문서 발견")

        self._build_metadata_cache()

        self._build_metadata_index()

        if preload_llm:
            self._preload_llm()

    def _manage_cache_size(self, cache_dict, max_size, cache_name="cache"):
        """캐시 크기 관리 - LRU 방식으로 오래된 항목 제거"""

    def _add_to_cache(self, cache_dict, key, value, max_size):
        """캐시에 항목 추가 with 크기 제한"""
        if key in cache_dict:
            del cache_dict[key]

        cache_dict[key] = {
            'data': value,
            'timestamp': time.time()
        }

        self._manage_cache_size(cache_dict, max_size, str(type(cache_dict)))

    def _preload_llm(self):
        """LLM을 미리 로드"""

        # LLMModule이 없으면 기존 방식 사용
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                if logger:
                    logger.info("LLM 모델 로딩 중...")
            elif logger:
                logger.info("LLM 모델 재사용")

            try:
                start = time.time()
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                elapsed = time.time() - start
                if elapsed > 1.0:  # 1초 이상 걸린 경우만 표시
                    if logger:
                        logger.info(f"LLM 로드 완료 ({elapsed:.1f}초)")
            except LLMException as e:
                if logger:
                    logger.error(f"LLM 로드 실패: {e}")
    
    def _build_metadata_index(self):
        """모든 PDF의 메타데이터를 추출하여 DB에 저장"""
        if not self.metadata_db:
            return

        logger.info("📚 메타데이터 인덱스 구축 시작...")
        indexed = 0

        for pdf_path in self.pdf_files[:30]:
            try:
                existing = self.metadata_db.get_document(pdf_path.name)
                if existing and existing.get('title'):
                    continue

                metadata = self._extract_pdf_metadata(pdf_path)
                if metadata:
                    self.metadata_db.add_document(metadata)
                    indexed += 1

            except Exception as e:
                logger.error(f"메타데이터 추출 실패 {pdf_path.name}: {e}")

        if indexed > 0:
            logger.info(f"✅ {indexed}개 문서 메타데이터 인덱싱 완료")

    def _extract_pdf_metadata(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """PDF에서 메타데이터 추출"""
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf = PyPDF2.PdfReader(file)

                # 첫 페이지에서 텍스트 추출
                first_page = pdf.pages[0].extract_text() if pdf.pages else ""

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

        all_results = {}

        # 동적 배치 크기 계산
        if batch_size is None:
            batch_size = min(20, max(10, len(pdf_paths) // 30))
            logger.info(f"동적 배치 크기 설정: {batch_size}")

        # pdf_processor가 없으면 순차 처리로 폴백
        if self.pdf_processor is None:
            if logger:
                logger.info("병렬 처리기 미활성화 - 순차 처리 모드")

            # ThreadPoolExecutor로 간단한 병렬 처리 (CPU 코어 수 기반 최적화)
            optimal_workers = min(os.cpu_count() or 4, 12, max(4, batch_size))
            with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                for i in range(0, len(pdf_paths), batch_size):
                    batch = pdf_paths[i:i + batch_size]
                    if logger:
                        logger.info(f"배치 {i//batch_size + 1}/{(len(pdf_paths)-1)//batch_size + 1} 처리 중 ({len(batch)}개 파일)")

                    # 각 PDF를 병렬로 처리
                    futures = {executor.submit(self._extract_pdf_info, pdf): pdf for pdf in batch}

                    for future in as_completed(futures):
                        pdf_path = futures[future]
                        try:
                            result = future.result(timeout=30)  # 30초 타임아웃
                            all_results[str(pdf_path)] = result
                        except PDFExtractionException as e:
                            if logger:
                                logger.warning(f"{pdf_path.name} 처리 실패: {str(e)[:50]}")
                            all_results[str(pdf_path)] = {'error': str(e)}

                    # 메모리 최적화
                    if i % (batch_size * 5) == 0:
                        gc.collect()
            for i in range(0, len(pdf_paths), batch_size):
                batch = pdf_paths[i:i + batch_size]

                batch_results = self.pdf_processor.process_multiple_pdfs(batch)
                all_results.update(batch_results)

                # 메모리 관리
                if len(self.pdf_processor.extraction_cache) > 50:
                    self.pdf_processor.clear_cache()

        return all_results

    def _find_metadata_by_filename(self, filename: str) -> Optional[Dict]:
        """파일명으로 메타데이터 찾기 (새로운 캐시 구조 지원)"""
        if filename in self.metadata_cache:
            return self.metadata_cache[filename]

        for cache_key, metadata in self.metadata_cache.items():
            if metadata.get('filename') == filename:
                return metadata

    def _build_metadata_cache(self):
        """모든 문서의 메타데이터를 미리 추출 (캐싱 지원)"""
        cache_file = self.cache_dir / "metadata_cache.pkl"

        # 기존 캐시 파일이 있으면 로드
        if cache_file.exists():
            try:
                import pickle
                with open(cache_file, 'rb') as f:
                    self.metadata_cache = pickle.load(f)
                if logger:
                    logger.info(f"캐시 로드 완료: {len(self.metadata_cache)}개 문서")
                return  # 캐시가 있으면 재구축 불필요
            except Exception as e:
                if logger:
                    logger.warning(f"캐시 로드 실패, 재구축: {e}")

        logger.info("메타데이터 캐시 구축 시작")
        if logger:
            logger.info("문서 메타데이터 구축 중...")

        # 병렬 처리 설정 확인
        use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

        # 병렬 처리 활성화 여부와 관계없이 process_pdfs_in_batch 사용 (내부에서 처리)
        if self.pdf_files and len(self.pdf_files) > 10:  # 10개 이상일 때만 병렬 처리
            if logger:
                logger.info(f"{len(self.pdf_files)}개 PDF 처리 시작 (병렬 모드)")
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

        if logger:
            logger.info(f"{len(self.metadata_cache)}개 문서 메타데이터 구축 완료")

        # 캐시 저장
        try:
            import pickle
            with open(cache_file, 'wb') as f:
                pickle.dump(self.metadata_cache, f)
            if logger:
                logger.info(f"캐시 저장 완료: {cache_file}")
        except Exception as e:
            if logger:
                logger.warning(f"캐시 저장 실패: {e}")

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
        """PDF 정보 추출 (StatisticsModule 위임 또는 폴백용) - 캐싱 적용"""

        cache_key = str(pdf_path)

        if cache_key in self.pdf_text_cache:
            cached_result = self.pdf_text_cache.pop(cache_key)
            self.pdf_text_cache[cache_key] = cached_result
            return cached_result

        text = ""

        def extract_with_pdfplumber():
            nonlocal text
            with pdfplumber.open(pdf_path) as pdf:
                pages_to_read = min(len(pdf.pages), self.max_pdf_pages)
                for page in pdf.pages[:pages_to_read]:
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    if page_text:
                        text += page_text + "\n"
                        if len(text) > self.max_text_length:
                            break
            return text

        text = extract_with_pdfplumber()
        if not text and hasattr(self, '_try_ocr_extraction'):
            text = self._try_ocr_extraction(pdf_path)

        if not text:
            try:
                from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
                ocr = EnhancedOCRProcessor()
                text, _ = ocr.extract_text_with_ocr(str(pdf_path))
            except Exception:
                pass

        if not text:
            return {}

        info = {}

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
            
        date_patterns = [
            r'기안일[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'시행일자[\s:：]*(\d{4}[-년]\s*\d{1,2}[-월]\s*\d{1,2})',
            r'(\d{4}-\d{2}-\d{2})\s*\d{2}:\d{2}',
            r'일자[\s:：]*(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2})',
            r'날짜[\s:：]*(\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2})',
            r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})'
        ]

        date_found = False
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                info['날짜'] = match.group(1).strip()
                date_found = True
                break

        if not date_found:
            filename = pdf_path.name
            filename_date_patterns = [
                r'(20\d{2}[-_.]0?[1-9]|1[0-2][-_.][0-2]?\d|3[01])',
                r'(20\d{2})[-_.]?(\d{1,2})[-_.]?(\d{1,2})',
            ]

            for pattern in filename_date_patterns:
                match = re.search(pattern, filename)
                if match:
                    if len(match.groups()) == 1:
                        date_str = match.group(1)
                        date_str = date_str.replace('_', '-').replace('.', '-')
                        info['날짜'] = date_str
                        date_found = True
                        break
                    if len(match.groups()) == 3:
                        year, month, day = match.groups()
                        try:
                            normalized_date = f"{year}-{int(month):02d}-{int(day):02d}"
                            info['날짜'] = normalized_date
                            date_found = True
                            break
                        except ValueError:
                            continue
            
            dept_match = re.search(r'기안부서[\s:：]*([^\n시행]+)', text)
            if dept_match:
                dept = dept_match.group(1).strip()
                dept = dept.split('시행')[0].strip()
                info['부서'] = dept
            
            if '부서' not in info:
                team_match = re.search(r'([가-힣]+팀[\-가-힣]+파트)', text)
                if team_match:
                    info['부서'] = team_match.group(1)
            
            amounts = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', text)
            if amounts:
                numeric_amounts = []
                for amt in amounts:
                    try:
                        num = int(amt.replace(',', ''))
                        numeric_amounts.append((num, amt))
                    except (ValueError, AttributeError):
                        pass
                if numeric_amounts:
                    numeric_amounts.sort(reverse=True)
                    info['금액'] = f"{numeric_amounts[0][1]}원"
            
            title_match = re.search(r'제목[\s:：]*([^\n]+)', text)
            if title_match:
                info['제목'] = title_match.group(1).strip()
            
            info['text'] = text[:3000]

        MAX_PDF_CACHE_SIZE = 50
        if len(self.pdf_text_cache) >= MAX_PDF_CACHE_SIZE:
            self.pdf_text_cache.popitem(last=False)

        self.pdf_text_cache[cache_key] = info

        return info

    def _search_by_content(self, query: str) -> List[Dict[str, Any]]:
        """검색 모듈로 위임된 검색 함수"""
        if self.search_module:
            try:
                results = self.search_module.search_by_content(query, top_k=20)
                if logger:
                    logger.info(f"SearchModule found {len(results)} documents for query: {query}")
                return results
            except Exception: return None

        # SearchModule이 없으면 빈 결과 반환
        if logger:
            logger.warning("SearchModule not available")
        return []

    def _extract_context(self, text: str, keyword: str, window: int = 200) -> str:
        """키워드 주변 컨텍스트 추출"""

        pos = text_lower.find(keyword_lower)
        if pos == -1:
            return ""

        start = max(0, pos - window)
        end = min(len(text), pos + len(keyword) + window)

        context = text[start:end]
        context = context.replace(keyword, f"**{keyword}**")

        return f"...{context}..."

    def find_best_document(self, query: str) -> Optional[Path]:
        """질문에 가장 적합한 문서 찾기 - SearchModule로 위임 또는 간단한 폴백"""

        # SearchModule이 있으면 위임
        if self.search_module:
            try:
                result = self.search_module.find_best_document(query)
                if result:
                    return Path(result)
            except Exception as e:
                if logger:
                    logger.error(f"SearchModule 문서 검색 실패: {e}, 폴백 사용")

        # 폴백: 간단한 검색 로직
        content_based_results = self._search_by_content(query)
        if content_based_results and content_based_results[0]['score'] > 20:
            best_result = content_based_results[0]
            return best_result['path']

        # 기본 파일명 매칭 폴백
        for cache_key, metadata in self.metadata_cache.items():
            filename_lower = metadata.get('filename', cache_key).lower()
            if any(word in filename_lower for word in query.lower().split() if len(word) > 1):
                return Path(metadata.get('path', self.docs_dir / cache_key))
        
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """두 문자열의 유사도 계산 (0~1)
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
        
        cache_key = f"{file_path.name}_{info_type}"
        if cache_key in self.documents_cache:
            return self.documents_cache[cache_key]
        
        info = self._extract_txt_info(file_path) if file_path.suffix == '.txt' else self._extract_pdf_info(file_path)
        
        if not info:
            return " 문서를 읽을 수 없습니다"
        
        result = ""
        
        if info_type == "all":
            result = f" {file_path.stem}\n"
            result += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for key, value in info.items():
                if key != 'text':
                    result += f"• {key}: {value}\n"
        if info_type in ["기안자", "날짜", "부서", "금액"]:
            result = f" {info_type}: {info.get(info_type, '정보 없음')}"
        else:
            result = ""
            if '기안자' in info:
                result += f"• 기안자: {info['기안자']}\n"
            if '부서' in info:
                result += f"• 부서: {info['부서']}\n"
            if '제목' in info:
                result += f"• 제목: {info['제목']}\n"
        if info_type == "요약":
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
            else:
                result = f" {file_path.stem}\n\n"
            result += f" **기본 정보**\n"
            if '기안자' in info:
                result += f"• 기안자: {info['기안자']}\n"
            if '날짜' in info:
                result += f"• 날짜: {info['날짜']}\n"
            if '부서' in info:
                result += f"• 부서: {info['부서']}\n"
            
            result += f"\n **주요 내용**\n"
            
            if 'text' in info:
                if self.llm_module:
                    summary = self.llm_module.generate_smart_summary(info['text'], str(file_path.name))
                else:
                    summary = self._generate_smart_summary(info['text'], file_path)
                result += summary
            
            if '금액' in info and info['금액'] != '정보 없음':
                result += f"\n **비용 정보**\n"
                result += f"• 금액: {info['금액']}\n"
            
            result += f"\n 출처: {file_path.name}"
        
        self.documents_cache[cache_key] = result
        
        return result

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

        unique_results = self._remove_duplicate_documents(results)

        response = f" **검색 결과** ({len(unique_results)}개 문서)\n\n"

        for i, doc in enumerate(unique_results[:5], 1):
            title = doc.get('title', '제목 없음')
            date = doc.get('date', '날짜 미상')
            category = doc.get('category', '기타')
            drafter = doc.get('drafter', '미상')

            if 'extracted_date' in doc:
                date = doc['extracted_date']
            if 'extracted_type' in doc:
                category = doc['extracted_type']
            if 'extracted_dept' in doc:
                drafter = doc['extracted_dept']

            if date and date != '날짜 미상' and len(date) >= 10:
                display_date = date[:10]
            display_date = date[:4] if date and len(date) >= 4 else "날짜미상"

            response += f"**{i}. [{category}] {title}**\n"
            response += f"    {display_date} |  {drafter}"

            if 'extracted_amount' in doc:
                amount = doc['extracted_amount']
                response += f" | 💰 {amount:,}원"

            response += "\n"

            if 'path' in doc:
                try:
                    file_path = Path(doc['path'])
                    if file_path.exists():
                        if self.llm_module:
                            summary = self.llm_module.generate_smart_summary("", str(file_path.name))
                        else:
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

    def answer_from_specific_document(self, query: str, filename: str) -> str:
        """특정 문서에 대해서만 답변 생성 (문서 전용 모드) - 초상세 버전
        
        Args:
            query: 사용자 질문
            filename: 특정 문서 파일명
        """
        
        doc_metadata = self._find_metadata_by_filename(filename)
        if not doc_metadata:
            return f" 문서를 찾을 수 없습니다: {filename}"
        doc_path = doc_metadata['path']
        
        if filename.endswith('.pdf'):
            info = self._extract_pdf_info_with_retry(doc_path)
            if not info.get('text'):
                return f" PDF 내용을 읽을 수 없습니다: {filename}"
            
            if self.llm is None:
                print(" LLM 모델 로드 중...")
                self._preload_llm()
            
            full_text = info['text'][:15000]
            
            if any(word in query for word in ['요약', '정리', '개요', '내용']):
                prompt = self._create_detailed_summary_prompt(query, full_text, filename)
            if any(word in query for word in ['상세', '자세히', '구체적', '세세히', '세부']):
                prompt = self._create_ultra_detailed_prompt(query, full_text, filename)
            if any(word in query for word in ['품목', '목록', '리스트', '항목']):
                prompt = self._create_itemized_list_prompt(query, full_text, filename)
            else:
                prompt = self._create_document_specific_prompt(query, full_text, filename)
            
            try:
                context_chunks = [
                    {
                        'content': full_text,
                        'source': filename,
                        'metadata': {
                            'filename': filename,
                            'date': doc_metadata.get('date', ''),
                            'title': doc_metadata.get('title', ''),
                            'is_document_only_mode': True
                        }
                    }
                ]
                
                response = self.llm.generate_response(query, context_chunks)
                answer = response.answer if hasattr(response, 'answer') else str(response)
                
                if len(answer) < 200 and '자세히' in query:
                    answer = self._enhance_short_answer(answer, full_text, query)
                    
            except Exception as e:
                print(f"LLM 오류: {e}")
                answer = self._detailed_text_search(info['text'], query, filename)
            
            answer += f"\n\n **출처**: {filename}"
            return answer

        return None if filename.endswith('.txt') else f" 지원하지 않는 파일 형식입니다: {filename}"
    
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
        
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\d+', query)
        
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in keywords if len(keyword) > 1):
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
    
    def _safe_pdf_extract(self, pdf_path, max_retries=3):
        """안전한 PDF 추출 with 재시도"""

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

    def _create_prompt(self, query: str, context: str, filename: str, prompt_type: str = 'default') -> str:
        """통합 프롬프트 생성 함수"""
        if prompt_type == 'detailed':
            return f"""

문서 내용을 분석하여 상세히 답변하세요:
{context}

중요 정보는 **굵게** 표시하고, 관련 내용을 모두 포함하세요.
"""
        else:  # default
            return f"""

문서 내용:
{context}

위 문서를 분석하여 질문에 답변하세요.
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

        return hash_key

    def answer(self, query: str, mode: str = 'auto') -> str:
        """답변 생성 메서드"""

        if cache_key in self.answer_cache:
            cached_response, cached_time = self.answer_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                self.answer_cache.move_to_end(cache_key)
                return cached_response
            else:
                del self.answer_cache[cache_key]

        response = self._answer_internal(query, mode)

        self.answer_cache[cache_key] = (response, time.time())
        if len(self.answer_cache) > self.max_cache_size:
            self.answer_cache.popitem(last=False)

        return response
    
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
    
    def get_cache_stats(self) -> Dict:
        """캐시 상태 정보 반환"""

        response_cache_size = len(self.response_cache) if hasattr(self, 'response_cache') else 0
        total_size = len(self.answer_cache) + len(self.documents_cache) + len(self.metadata_cache) + response_cache_size
        return {
            'size': response_cache_size,
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
        
        start_time = time.time()
        error_msg = None
        success = True
        response = ""
        metadata = {}
        
        try:
            
            if mode == 'auto':
                with TimerContext(chat_logger, "classify_intent") if chat_logger else nullcontext():
                    if self.intent_module:
                        mode = self.intent_module.classify_search_intent(query)
                    else:
                        mode = self._classify_search_intent(query)
            
            self.search_mode = mode
            metadata['search_mode'] = mode
            
            query_lower = query.lower()

            if self.search_mode == 'document':
                if any(keyword in query_lower for keyword in ["문서", "찾아", "검색", "어떤", "무엇", "뭐"]):
                    search_results = self._search_by_content(query)

                    if not search_results:
                        response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                    else:
                        response = f"**{query}** 검색 결과\n\n"

                        seen = set()
                        unique_results = []
                        for r in sorted(search_results, key=lambda x: x.get('score', 0), reverse=True):
                            if r['filename'] not in seen:
                                seen.add(r['filename'])
                                unique_results.append(r)

                        response += f"총 {len(unique_results)}개 문서 발견\n\n"

                        for i, result in enumerate(unique_results[:10], 1):
                            response += f"**{i}. {result['filename']}**\n"

                            if result.get('source') == 'everything_search':
                                if result.get('date'):
                                    response += f"   📅 날짜: {result['date']}\n"
                                if result.get('category') and result['category'] != '기타':
                                    response += f"   📁 카테고리: {result['category']}\n"
                                if result.get('keywords'):
                                    keywords_list = result['keywords'].split()[:5]
                                    if keywords_list:
                                        response += f"   🔑 키워드: {', '.join(keywords_list)}\n"
                            elif result.get('context'):
                                context = result['context']
                                if '[OCR' in context or '페이지' in context:
                                    response += f"   📄 스캔 문서 (OCR 필요)\n"
                                else:
                                    clean_text = context.replace('\n', ' ').strip()[:150]
                                    response += f"   📝 {clean_text}...\n"
                            response += "\n"

                        if len(unique_results) > 5:
                            response += f"\n... 외 {len(unique_results) - 5}개 문서\n"
                else:
                    if self.everything_search:
                        search_results = self.everything_search.search(query, limit=1)
                        if search_results:
                            top_result = search_results[0]
                            doc_path = Path(top_result['path'])

                            if doc_path.exists():
                                if self.llm_module:
                                    try:
                                        if self.document_module:
                                            doc_info = self.document_module.extract_pdf_text(doc_path)
                                            content = doc_info.get('text', '')
                                        else:
                                            content = self._extract_full_pdf_content(doc_path).get('text', '')

                                        response = self.llm_module.generate_smart_summary(content, str(doc_path.name))
                                    except Exception as e:
                                        logger.error(f"LLMModule 요약 생성 오류: {e}")
                                        response = self._generate_llm_summary(doc_path, query)
                                else:
                                    response = self._generate_llm_summary(doc_path, query)
                            else:
                                response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                        else:
                            response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                    else:
                        doc_path = self.find_best_document(query)

                        if not doc_path:
                            response = "❌ 관련 문서를 찾을 수 없습니다. 더 구체적으로 질문해주세요."
                        elif self.llm_module:
                            try:
                                if self.document_module:
                                    doc_info = self.document_module.extract_pdf_text(doc_path)
                                    content = doc_info.get('text', '')
                                else:
                                    content = self._extract_full_pdf_content(doc_path).get('text', '')

                                response = self.llm_module.generate_smart_summary(content, str(doc_path.name))
                            except Exception as e:
                                logger.error(f"LLMModule 요약 생성 오류: {e}")
                                response = self._generate_llm_summary(doc_path, query)
                        else:
                            response = self._generate_llm_summary(doc_path, query)
            else:
                response = "❌ 문서 검색 중 오류가 발생했습니다."

            processing_time = time.time() - start_time
            if chat_logger:
                chat_logger.log_query(
                    query=query,
                    response=response,
                    search_mode=self.search_mode,
                    processing_time=processing_time,
                    metadata=metadata
                )

            return response

        except Exception as e:
            error_msg = str(e)
            success = False
            response = f" 처리 중 오류 발생: {error_msg}"
            
            processing_time = time.time() - start_time
            
            if chat_logger:
                chat_logger.log_error(
                    error_type=type(e).__name__,
                    error_msg=error_msg,
                    query=query
                )
            
            return response
    
    def _get_detail_only_prompt(self, query: str, context: str, filename: str) -> str:
        return self._create_prompt(query, context, filename, 'detailed')

    def _placeholder1(self):
        """기본 정보 제외한 상세 내용만 생성하는 프롬프트"""
        return f"""

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

    def _is_gian_document(self, text: str) -> bool:
        """기안서 문서인지 확인"""
    
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
        except Exception: return None
    
    def _extract_full_pdf_content(self, pdf_path: Path) -> dict:
        """PDF 전체 내용 추출 및 구조화 - DocumentModule 활용으로 단순화"""
        try:
            return self._extract_pdf_info(pdf_path)
        except Exception:
            return None
    
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
    
    def _extract_key_sentences(self, content, num_sentences=5):
        """핵심 문장 추출 헬퍼"""

        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_sentences:
            return sentences

        important_keywords = ['결정', '승인', '구매', '계약', '예산', '진행', '완료']
        scored_sentences = []

        for sentence in sentences:
            score = sum(1 for keyword in important_keywords if keyword in sentence)
            scored_sentences.append((sentence, score))

        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        return [s[0] for s in scored_sentences[:num_sentences]]

    def _generate_llm_summary(self, pdf_path: Path, query: str) -> str:
        """LLM을 사용한 상세 요약 - LLMModule로 위임 (2025-09-29 리팩토링)"""
        if logger:
            logger.info("LLM 요약 생성 시작")

        # LLMModule이 있으면 위임
        if self.llm_module:
            try:
                # PDF 내용 추출
                pdf_info = self._extract_full_pdf_content(pdf_path)
                content = pdf_info.get('text', '') if pdf_info and 'error' not in pdf_info else ''

                # LLMModule을 사용하여 스마트 요약 생성
                return self.llm_module.generate_smart_summary(content, str(pdf_path.name), query)
            except Exception as e:
                if logger:
                    logger.error(f"LLMModule 요약 생성 실패: {e}, 폴백 사용")

        # 간단한 폴백 구현
        pdf_info = self._extract_full_pdf_content(pdf_path)
        if pdf_info and 'error' not in pdf_info:
            # 기본 정보 추출
            info_parts = []
            if '제목' in pdf_info:
                info_parts.append(f"제목: {pdf_info['제목']}")
            if '기안자' in pdf_info:
                info_parts.append(f"기안자: {pdf_info['기안자']}")
            if '금액' in pdf_info:
                info_parts.append(f"금액: {pdf_info['금액']}")

            return "\n".join(info_parts) if info_parts else "문서 정보를 추출할 수 없습니다."
        else:
            return "문서를 읽을 수 없습니다."

    def _collect_statistics_data(self, query: str) -> Dict:
        """통계 데이터 수집 및 구조화 - StatisticsModule로 위임 (2025-09-29 리팩토링)"""

        return {
            'title': '통계 분석',
            'headers': ['항목', '값'],
            'table_data': [['총 문서 수', str(len(self.metadata_cache))]],
            '총계': f'총 {len(self.metadata_cache)}개 문서',
            '분석': {'note': 'StatisticsModule 필요'},
            '추천': ['StatisticsModule을 로드하여 상세 통계를 확인하세요.']
        }
    
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
    
    def _determine_equipment_category(self, equipment_name: str, item_text: str) -> str:
        """장비명과 텍스트로 카테고리 결정"""
        
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

        try:
            filename = file_path.stem if hasattr(file_path, 'stem') else str(file_path)

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

        filename = file_path.stem if hasattr(file_path, 'stem') else str(file_path)
        result.append(f"📄 {filename}")
        result.append("-" * 50)

        if metadata.get('date'):
            result.append(f"📅 날짜: {metadata['date']}")
        if metadata.get('author'):
            result.append(f"✍️ 기안자: {metadata['author']}")

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

    def _is_location_match(self, item_lines: list, location: str) -> bool:
        """위치 매칭 로직 개선 - 정확한 위치 매칭"""
        
        for line in item_lines:
            if '위치:' in line or '위치정보:' in line:
                location_match = re.search(r'위치:\s*([^|\n]+)', line)
                if location_match:
                    actual_location = location_match.group(1).strip()
                    
                    if location == actual_location:
                        return True
                    if location == '부조정실':
                        return actual_location.endswith('부조정실')
                    if location == '스튜디오':
                        return actual_location.endswith('스튜디오')
                    if location == '편집실':
                        return actual_location.endswith('편집실')
                    if location in ['중계차', 'van', 'Van', 'VAN']:
                        return 'Van' in actual_location or 'VAN' in actual_location
                    if location == "광화문부조정실":
                        return "광화문" in actual_location and "부조정실" in actual_location
                    if len(location) > 3:
                        return location in actual_location
        
        return False

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
