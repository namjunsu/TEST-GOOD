"""
AI-CHAT-V3 Configuration File
모든 경로와 설정을 중앙 관리
"""

import os
from pathlib import Path

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.absolute()

# 경로 설정
MODELS_DIR = os.getenv('MODELS_DIR', PROJECT_ROOT / 'models')
DOCS_DIR = os.getenv('DOCS_DIR', PROJECT_ROOT / 'docs')
CACHE_DIR = os.getenv('CACHE_DIR', PROJECT_ROOT / 'rag_system' / 'cache')
DB_DIR = os.getenv('DB_DIR', PROJECT_ROOT / 'rag_system' / 'db')

# 모델 경로
QWEN_MODEL_PATH = os.getenv('QWEN_MODEL_PATH', 
    MODELS_DIR / 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf')
SENTENCE_TRANSFORMERS_CACHE = os.getenv('SENTENCE_TRANSFORMERS_CACHE',
    MODELS_DIR / 'sentence_transformers')

# 임베딩 모델
KOREAN_EMBEDDING_MODEL = os.getenv('KOREAN_EMBEDDING_MODEL', 
    'jhgan/ko-sroberta-multitask')

# 검색 설정
VECTOR_WEIGHT = float(os.getenv('VECTOR_WEIGHT', '0.2'))
BM25_WEIGHT = float(os.getenv('BM25_WEIGHT', '0.8'))
RRF_K = int(os.getenv('RRF_K', '20'))

# 품질 임계값
QUALITY_THRESHOLD = float(os.getenv('QUALITY_THRESHOLD', '0.7'))
RELEVANCE_THRESHOLD = float(os.getenv('RELEVANCE_THRESHOLD', '0.6'))
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.7'))
COMPLETENESS_THRESHOLD = float(os.getenv('COMPLETENESS_THRESHOLD', '0.6'))

# LLM 생성 설정 (성능 최적화)
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.3'))  # 0.7 -> 0.3 (더 결정적, 빠른 응답)
MAX_TOKENS = int(os.getenv('MAX_TOKENS', '800'))  # 1200 -> 800 (토큰 수 최적화)
TOP_P = float(os.getenv('TOP_P', '0.85'))  # 0.9 -> 0.85 (더 집중된 선택)
TOP_K = int(os.getenv('TOP_K', '30'))  # 40 -> 30 (더 빠른 샘플링)
REPEAT_PENALTY = float(os.getenv('REPEAT_PENALTY', '1.15'))  # 1.1 -> 1.15 (반복 강력 방지)

# GPU 최적화 설정 (NVIDIA RTX PRO 4000 - 16GB VRAM)
N_THREADS = int(os.getenv('N_THREADS', '8'))   # GPU 사용시 CPU 스레드 줄이기
N_CTX = int(os.getenv('N_CTX', '16384'))       # 컨텍스트 윈도우 (2배 확장 - 16K)
N_BATCH = int(os.getenv('N_BATCH', '512'))    # 배치 크기
USE_MLOCK = bool(os.getenv('USE_MLOCK', 'False'))  # GPU 사용시 메모리 락 비활성화
USE_MMAP = bool(os.getenv('USE_MMAP', 'True'))     # 메모리 매핑

# GPU 설정 (활성화됨!)
N_GPU_LAYERS = int(os.getenv('N_GPU_LAYERS', '-1'))  # -1 = 모든 레이어 GPU 사용
MAIN_GPU = int(os.getenv('MAIN_GPU', '0'))           # 기본 GPU ID
F16_KV = bool(os.getenv('F16_KV', 'True'))           # GPU 메모리 최적화

# 성능 최적화 설정 (2025-01-18 추가)
# 문서 검색 최적화
MAX_DOCUMENTS_TO_PROCESS = int(os.getenv('MAX_DOCUMENTS_TO_PROCESS', '5'))  # 15 → 5
MAX_PAGES_PER_PDF = int(os.getenv('MAX_PAGES_PER_PDF', '10'))  # 50 → 10
PDF_TIMEOUT_SECONDS = int(os.getenv('PDF_TIMEOUT_SECONDS', '5'))  # PDF당 타임아웃
SEARCH_TIMEOUT_SECONDS = int(os.getenv('SEARCH_TIMEOUT_SECONDS', '20'))  # 전체 검색 타임아웃

# 병렬 처리 설정
PARALLEL_WORKERS = int(os.getenv('PARALLEL_WORKERS', '4'))  # 병렬 워커 수
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '5'))  # 배치 크기

# 캐싱 설정 강화
PDF_TEXT_CACHE_SIZE = int(os.getenv('PDF_TEXT_CACHE_SIZE', '100'))  # PDF 텍스트 캐시 크기
RESPONSE_CACHE_TTL = int(os.getenv('RESPONSE_CACHE_TTL', '7200'))  # 응답 캐시 TTL (2시간)
CACHE_MAX_SIZE = int(os.getenv('CACHE_MAX_SIZE', '500'))  # 캐시 최대 크기

# 디버그 설정
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# 모든 경로를 문자열로 변환
MODELS_DIR = str(MODELS_DIR)
DOCS_DIR = str(DOCS_DIR)
CACHE_DIR = str(CACHE_DIR)
DB_DIR = str(DB_DIR)
QWEN_MODEL_PATH = str(QWEN_MODEL_PATH)
SENTENCE_TRANSFORMERS_CACHE = str(SENTENCE_TRANSFORMERS_CACHE)