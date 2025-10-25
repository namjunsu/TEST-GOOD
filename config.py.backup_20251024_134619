"""
AI-CHAT-V3 Configuration File
모든 경로와 설정을 중앙 관리 - 개선된 버전
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import json
import warnings
import multiprocessing

# 프로젝트 루트 디렉터리
PROJECT_ROOT = Path(__file__).parent.absolute()

# 환경별 설정
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')  # development, staging, production

# 헬퍼 함수들
def get_env_int(key: str, default: int) -> int:
    """환경 변수를 안전하게 정수로 변환"""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        warnings.warn(f"Invalid integer value for {key}, using default: {default}")
        return default

def get_env_float(key: str, default: float) -> float:
    """환경 변수를 안전하게 실수로 변환"""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        warnings.warn(f"Invalid float value for {key}, using default: {default}")
        return default

def get_env_bool(key: str, default: bool) -> bool:
    """환경 변수를 안전하게 불린으로 변환"""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

def get_env_path(key: str, default: Path) -> Path:
    """환경 변수를 안전하게 Path로 변환"""
    value = os.getenv(key, str(default))
    return Path(value) if value else default

def validate_threshold(value: float, name: str) -> float:
    """임계값 범위 검증 (0.0 ~ 1.0)"""
    if not 0.0 <= value <= 1.0:
        warnings.warn(f"{name} = {value} is out of range [0.0, 1.0], clamping...")
        return max(0.0, min(1.0, value))
    return value

# 경로 설정 (검증 및 생성)
MODELS_DIR = get_env_path('MODELS_DIR', PROJECT_ROOT / 'models')
DOCS_DIR = get_env_path('DOCS_DIR', PROJECT_ROOT / 'docs')
CACHE_DIR = get_env_path('CACHE_DIR', PROJECT_ROOT / 'rag_system' / 'cache')
DB_DIR = get_env_path('DB_DIR', PROJECT_ROOT / 'rag_system' / 'db')

# 디렉터리 자동 생성
for dir_path in [MODELS_DIR, DOCS_DIR, CACHE_DIR, DB_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 모델 경로
QWEN_MODEL_PATH = get_env_path('QWEN_MODEL_PATH',
    MODELS_DIR / 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf')
SENTENCE_TRANSFORMERS_CACHE = get_env_path('SENTENCE_TRANSFORMERS_CACHE',
    MODELS_DIR / 'sentence_transformers')

# 임베딩 모델
KOREAN_EMBEDDING_MODEL = os.getenv('KOREAN_EMBEDDING_MODEL',
    'jhgan/ko-sroberta-multitask')

# 검색 설정
VECTOR_WEIGHT = get_env_float('VECTOR_WEIGHT', 0.2)
BM25_WEIGHT = get_env_float('BM25_WEIGHT', 0.8)
RRF_K = get_env_int('RRF_K', 20)

# 가중치 합이 1이 되도록 정규화
weight_sum = VECTOR_WEIGHT + BM25_WEIGHT
if abs(weight_sum - 1.0) > 0.01:
    warnings.warn(f"VECTOR_WEIGHT + BM25_WEIGHT = {weight_sum} != 1.0, normalizing...")
    VECTOR_WEIGHT = VECTOR_WEIGHT / weight_sum
    BM25_WEIGHT = BM25_WEIGHT / weight_sum

# 품질 임계값
QUALITY_THRESHOLD = validate_threshold(get_env_float('QUALITY_THRESHOLD', 0.7), 'QUALITY_THRESHOLD')
RELEVANCE_THRESHOLD = validate_threshold(get_env_float('RELEVANCE_THRESHOLD', 0.6), 'RELEVANCE_THRESHOLD')
CONFIDENCE_THRESHOLD = validate_threshold(get_env_float('CONFIDENCE_THRESHOLD', 0.7), 'CONFIDENCE_THRESHOLD')
COMPLETENESS_THRESHOLD = validate_threshold(get_env_float('COMPLETENESS_THRESHOLD', 0.6), 'COMPLETENESS_THRESHOLD')

# LLM 생성 설정 (성능 최적화)
# 환경별 기본값
LLM_DEFAULTS = {
    'development': {'temperature': 0.7, 'max_tokens': 800, 'top_p': 0.9},
    'staging': {'temperature': 0.5, 'max_tokens': 600, 'top_p': 0.87},
    'production': {'temperature': 0.3, 'max_tokens': 512, 'top_p': 0.85}  # 800→512 (-36%)
}

defaults = LLM_DEFAULTS.get(ENVIRONMENT, LLM_DEFAULTS['production'])

TEMPERATURE = validate_threshold(get_env_float('TEMPERATURE', defaults['temperature']), 'TEMPERATURE')
MAX_TOKENS = max(1, min(4096, get_env_int('MAX_TOKENS', defaults['max_tokens'])))  # 1-4096 범위
TOP_P = validate_threshold(get_env_float('TOP_P', defaults['top_p']), 'TOP_P')
TOP_K = max(1, min(100, get_env_int('TOP_K', 30)))  # 1-100 범위
REPEAT_PENALTY = max(1.0, min(2.0, get_env_float('REPEAT_PENALTY', 1.15)))  # 1.0-2.0 범위

# GPU 최적화 설정 (NVIDIA RTX PRO 4000 - 16GB VRAM)
# 🔥 메모리 최적화 설정 (14GB → 8GB 목표)
N_THREADS = max(1, min(32, get_env_int('N_THREADS', 4)))  # GPU 사용 시 CPU 스레드 최소화 (20→4로 변경)
N_CTX = max(512, min(32768, get_env_int('N_CTX', 16384)))  # 컨텍스트 확장으로 더 많은 문서 처리
N_BATCH = max(1, min(2048, get_env_int('N_BATCH', 1024)))  # 배치 크기 증가로 처리 속도 향상
USE_MLOCK = get_env_bool('USE_MLOCK', False)
USE_MMAP = get_env_bool('USE_MMAP', True)
LOW_VRAM = get_env_bool('LOW_VRAM', False)  # RTX 4000 16GB VRAM 충분

# GPU 설정 (활성화됨!)
N_GPU_LAYERS = get_env_int('N_GPU_LAYERS', -1)  # -1 = 모든 레이어 GPU 사용
MAIN_GPU = max(0, get_env_int('MAIN_GPU', 0))  # GPU ID (음수 방지)
F16_KV = get_env_bool('F16_KV', True)  # GPU 메모리 최적화

# 성능 최적화 설정 (2025-01-18 추가)
# 문서 검색 최적화
MAX_DOCUMENTS_TO_PROCESS = max(1, min(50, get_env_int('MAX_DOCUMENTS_TO_PROCESS', 20)))  # 더 많은 문서 동시 처리
MAX_PAGES_PER_PDF = max(1, min(100, get_env_int('MAX_PAGES_PER_PDF', 50)))  # PDF 페이지 처리 증가
PDF_TIMEOUT_SECONDS = max(1, min(60, get_env_int('PDF_TIMEOUT_SECONDS', 5)))
SEARCH_TIMEOUT_SECONDS = max(5, min(300, get_env_int('SEARCH_TIMEOUT_SECONDS', 20)))

# 병렬 처리 설정
max_workers = multiprocessing.cpu_count()
PARALLEL_WORKERS = max(1, min(max_workers, get_env_int('PARALLEL_WORKERS', min(12, max_workers))))  # 병렬 워커 증가
BATCH_SIZE = max(1, min(20, get_env_int('BATCH_SIZE', 10)))  # 배치 크기 증가

# 캐싱 설정 강화
PDF_TEXT_CACHE_SIZE = max(10, min(1000, get_env_int('PDF_TEXT_CACHE_SIZE', 100)))
RESPONSE_CACHE_TTL = max(60, min(86400, get_env_int('RESPONSE_CACHE_TTL', 7200)))  # 1분-24시간
CACHE_MAX_SIZE = max(50, min(5000, get_env_int('CACHE_MAX_SIZE', 500)))

# 디버그 설정
DEBUG_MODE = get_env_bool('DEBUG_MODE', False)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# 로그 레벨 검증
VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
if LOG_LEVEL not in VALID_LOG_LEVELS:
    warnings.warn(f"Invalid LOG_LEVEL: {LOG_LEVEL}, using INFO")
    LOG_LEVEL = 'INFO'

# 모든 경로를 문자열로 변환 (하위 호환성)
MODELS_DIR = str(MODELS_DIR)
DOCS_DIR = str(DOCS_DIR)
CACHE_DIR = str(CACHE_DIR)
DB_DIR = str(DB_DIR)
QWEN_MODEL_PATH = str(QWEN_MODEL_PATH)
SENTENCE_TRANSFORMERS_CACHE = str(SENTENCE_TRANSFORMERS_CACHE)

# 설정 요약 표시
def get_config_summary() -> Dict[str, Any]:
    """현재 설정 요약 반환"""
    return {
        'environment': ENVIRONMENT,
        'gpu': {
            'enabled': N_GPU_LAYERS != 0,
            'layers': N_GPU_LAYERS,
            'main_gpu': MAIN_GPU
        },
        'llm': {
            'temperature': TEMPERATURE,
            'max_tokens': MAX_TOKENS,
            'context_size': N_CTX
        },
        'search': {
            'vector_weight': VECTOR_WEIGHT,
            'bm25_weight': BM25_WEIGHT,
            'max_docs': MAX_DOCUMENTS_TO_PROCESS
        },
        'performance': {
            'parallel_workers': PARALLEL_WORKERS,
            'cache_size': CACHE_MAX_SIZE,
            'cache_ttl': RESPONSE_CACHE_TTL
        },
        'debug': DEBUG_MODE
    }

# 설정 파일 저장/로드
CONFIG_FILE = PROJECT_ROOT / 'config.json'

def save_config(config: Optional[Dict[str, Any]] = None):
    """현재 설정을 파일로 저장"""
    if config is None:
        config = get_config_summary()

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    return config

def load_config_from_file():
    """설정 파일에서 로드"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            warnings.warn(f"Failed to load config file: {e}")
    return None

def reload_config():
    """환경 변수에서 설정 다시 로드"""
    global VECTOR_WEIGHT, BM25_WEIGHT, TEMPERATURE, MAX_TOKENS
    # 주요 설정들을 다시 로드
    VECTOR_WEIGHT = get_env_float('VECTOR_WEIGHT', 0.2)
    BM25_WEIGHT = get_env_float('BM25_WEIGHT', 0.8)
    TEMPERATURE = get_env_float('TEMPERATURE', defaults['temperature'])
    MAX_TOKENS = get_env_int('MAX_TOKENS', defaults['max_tokens'])
    return get_config_summary()

def validate_config() -> Dict[str, bool]:
    """설정 유효성 검사"""
    validations = {}

    # 모델 파일 존재 확인
    validations['model_exists'] = Path(QWEN_MODEL_PATH).exists()

    # 디렉터리 쓰기 권한 확인
    validations['cache_writable'] = os.access(CACHE_DIR, os.W_OK)
    validations['db_writable'] = os.access(DB_DIR, os.W_OK)

    # GPU 설정 확인
    validations['gpu_configured'] = N_GPU_LAYERS != 0

    # 가중치 합 확인
    validations['weights_normalized'] = abs((VECTOR_WEIGHT + BM25_WEIGHT) - 1.0) < 0.01

    return validations

# 초기화 시 설정 검증
if ENVIRONMENT == 'development' and DEBUG_MODE:
    print("\n=== Configuration Summary ===")
    for key, value in get_config_summary().items():
        print(f"{key}: {value}")
    print("\n=== Configuration Validation ===")
    for check, passed in validate_config().items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}: {passed}")
    print("============================\n")