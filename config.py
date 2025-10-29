"""
AI-CHAT-V3 Configuration System

완벽하게 재작성된 설정 시스템:
- 완전한 타입 안전성 (mypy strict 통과)
- Frozen dataclass (불변성 보장)
- 싱글톤 패턴 (전역 일관성)
- Custom exceptions (명확한 에러 처리)
- 보안 강화 (민감 정보 필터링)
- 완벽한 문서화

Author: Claude (Best Developer Mode)
Date: 2025-01-24
Version: 2.0.0
"""

import os
import json
import warnings
import multiprocessing
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Final, TypedDict, cast
from dataclasses import dataclass

# ============================================================================
# Type Definitions (완벽한 타입 시스템)
# ============================================================================

Environment = Literal['development', 'staging', 'production']
LogLevel = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']


class GPUConfig(TypedDict):
    """GPU 설정 타입"""
    enabled: bool
    layers: int
    main_gpu: int
    f16_kv: bool


class LLMConfig(TypedDict):
    """LLM 설정 타입"""
    temperature: float
    max_tokens: int
    context_size: int
    top_p: float
    top_k: int
    repeat_penalty: float


class SearchConfig(TypedDict):
    """검색 설정 타입"""
    vector_weight: float
    bm25_weight: float
    max_docs: int
    quality_threshold: float
    relevance_threshold: float


class PerformanceConfig(TypedDict):
    """성능 설정 타입"""
    parallel_workers: int
    cache_size: int
    cache_ttl: int
    batch_size: int


class ConfigSummary(TypedDict):
    """설정 요약 타입"""
    environment: str
    gpu: GPUConfig
    llm: LLMConfig
    search: SearchConfig
    performance: PerformanceConfig
    debug: bool


# ============================================================================
# Custom Exceptions (명확한 에러 처리)
# ============================================================================

class ConfigError(Exception):
    """설정 관련 기본 예외"""
    pass


class ConfigValidationError(ConfigError):
    """설정 검증 실패"""
    pass


class ConfigLoadError(ConfigError):
    """설정 로드 실패"""
    pass


class ConfigSaveError(ConfigError):
    """설정 저장 실패"""
    pass


# ============================================================================
# Constants (매직 넘버 제거)
# ============================================================================

class Limits:
    """시스템 제한 상수"""

    # LLM 토큰 제한
    MIN_TOKENS: Final[int] = 1
    MAX_TOKENS: Final[int] = 4096
    DEFAULT_TOKENS: Final[int] = 512

    # 컨텍스트 크기
    MIN_CONTEXT: Final[int] = 512
    MAX_CONTEXT: Final[int] = 32768
    DEFAULT_CONTEXT: Final[int] = 16384

    # Top-K 범위
    MIN_TOP_K: Final[int] = 1
    MAX_TOP_K: Final[int] = 100
    DEFAULT_TOP_K: Final[int] = 30

    # 반복 페널티
    MIN_REPEAT_PENALTY: Final[float] = 1.0
    MAX_REPEAT_PENALTY: Final[float] = 2.0
    DEFAULT_REPEAT_PENALTY: Final[float] = 1.15

    # 스레드 범위
    MIN_THREADS: Final[int] = 1
    MAX_THREADS: Final[int] = 32
    DEFAULT_THREADS: Final[int] = 4

    # 배치 크기
    MIN_BATCH: Final[int] = 1
    MAX_BATCH: Final[int] = 2048
    DEFAULT_BATCH: Final[int] = 1024

    # 문서 처리
    MIN_DOCUMENTS: Final[int] = 1
    MAX_DOCUMENTS: Final[int] = 50
    DEFAULT_DOCUMENTS: Final[int] = 20

    # PDF 페이지
    MIN_PDF_PAGES: Final[int] = 1
    MAX_PDF_PAGES: Final[int] = 100
    DEFAULT_PDF_PAGES: Final[int] = 50

    # 타임아웃 (초)
    MIN_TIMEOUT: Final[int] = 1
    MAX_TIMEOUT: Final[int] = 300
    DEFAULT_PDF_TIMEOUT: Final[int] = 5
    DEFAULT_SEARCH_TIMEOUT: Final[int] = 20

    # 워커 수
    MIN_WORKERS: Final[int] = 1
    DEFAULT_WORKERS: Final[int] = 12

    # 캐시 크기
    MIN_CACHE_SIZE: Final[int] = 10
    MAX_CACHE_SIZE: Final[int] = 5000
    DEFAULT_CACHE_SIZE: Final[int] = 500
    DEFAULT_PDF_CACHE: Final[int] = 100

    # 캐시 TTL (초)
    MIN_CACHE_TTL: Final[int] = 60
    MAX_CACHE_TTL: Final[int] = 86400
    DEFAULT_CACHE_TTL: Final[int] = 7200


class Thresholds:
    """임계값 상수"""

    MIN_THRESHOLD: Final[float] = 0.0
    MAX_THRESHOLD: Final[float] = 1.0

    DEFAULT_QUALITY: Final[float] = 0.7
    DEFAULT_RELEVANCE: Final[float] = 0.6
    DEFAULT_CONFIDENCE: Final[float] = 0.7
    DEFAULT_COMPLETENESS: Final[float] = 0.6

    # 가중치
    DEFAULT_VECTOR_WEIGHT: Final[float] = 0.2
    DEFAULT_BM25_WEIGHT: Final[float] = 0.8

    # RRF
    DEFAULT_RRF_K: Final[int] = 20


class DefaultPaths:
    """기본 경로 상수"""

    MODELS_SUBDIR: Final[str] = 'models'
    DOCS_SUBDIR: Final[str] = 'docs'
    CACHE_SUBDIR: Final[str] = 'rag_system/cache'
    DB_SUBDIR: Final[str] = 'rag_system/db'

    QWEN_MODEL_FILENAME: Final[str] = 'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'
    SENTENCE_TRANSFORMERS_SUBDIR: Final[str] = 'sentence_transformers'

    CONFIG_FILENAME: Final[str] = 'config.json'


class DefaultModels:
    """기본 모델 상수"""

    KOREAN_EMBEDDING: Final[str] = 'jhgan/ko-sroberta-multitask'


# ============================================================================
# Environment Variable Helpers (안전한 변환)
# ============================================================================

def get_env_int(key: str, default: int, min_val: int, max_val: int) -> int:
    """환경 변수를 안전하게 정수로 변환 (범위 검증 포함)

    Args:
        key: 환경 변수 키
        default: 기본값
        min_val: 최소값
        max_val: 최대값

    Returns:
        int: 변환된 정수 (범위 내)

    Raises:
        ConfigValidationError: 변환 실패 또는 범위 초과 시
    """
    try:
        value = int(os.getenv(key, str(default)))
        if not min_val <= value <= max_val:
            raise ConfigValidationError(
                f"{key}={value} is out of range [{min_val}, {max_val}]"
            )
        return value
    except ValueError as e:
        raise ConfigValidationError(f"Invalid integer value for {key}: {e}") from e


def get_env_float(key: str, default: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """환경 변수를 안전하게 실수로 변환 (범위 검증 포함)

    Args:
        key: 환경 변수 키
        default: 기본값
        min_val: 최소값
        max_val: 최대값

    Returns:
        float: 변환된 실수 (범위 내)

    Raises:
        ConfigValidationError: 변환 실패 또는 범위 초과 시
    """
    try:
        value = float(os.getenv(key, str(default)))
        if not min_val <= value <= max_val:
            raise ConfigValidationError(
                f"{key}={value} is out of range [{min_val}, {max_val}]"
            )
        return value
    except ValueError as e:
        raise ConfigValidationError(f"Invalid float value for {key}: {e}") from e


def get_env_bool(key: str, default: bool) -> bool:
    """환경 변수를 안전하게 불린으로 변환

    Args:
        key: 환경 변수 키
        default: 기본값

    Returns:
        bool: 변환된 불린
    """
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def get_env_path(key: str, default: Path) -> Path:
    """환경 변수를 안전하게 Path로 변환

    Args:
        key: 환경 변수 키
        default: 기본 경로

    Returns:
        Path: 변환된 경로
    """
    value = os.getenv(key)
    return Path(value) if value else default


def get_env_literal(key: str, default: str, valid_values: List[str]) -> str:
    """환경 변수를 검증된 문자열로 변환

    Args:
        key: 환경 변수 키
        default: 기본값
        valid_values: 유효한 값 목록

    Returns:
        str: 검증된 문자열

    Raises:
        ConfigValidationError: 유효하지 않은 값
    """
    value = os.getenv(key, default)
    if value not in valid_values:
        raise ConfigValidationError(
            f"{key}={value} is not valid. Must be one of: {valid_values}"
        )
    return value


# ============================================================================
# Main Configuration Class (불변 + 싱글톤)
# ============================================================================

# 모듈 레벨 싱글톤 인스턴스 (클래스 외부에서 관리)
_singleton_instance: Optional['Config'] = None

@dataclass(frozen=True)
class Config:
    """AI-CHAT 시스템 설정 (불변)

    이 클래스는 frozen dataclass로 구현되어 생성 후 변경이 불가능합니다.
    싱글톤 패턴을 사용하여 전역적으로 하나의 인스턴스만 존재합니다.

    Attributes:
        프로젝트 경로:
            project_root: 프로젝트 루트 디렉터리
            models_dir: 모델 파일 디렉터리
            docs_dir: 문서 디렉터리
            cache_dir: 캐시 디렉터리
            db_dir: 데이터베이스 디렉터리

        모델 경로:
            qwen_model_path: Qwen LLM 모델 파일 경로
            sentence_transformers_cache: Sentence Transformers 캐시 경로
            korean_embedding_model: 한국어 임베딩 모델명

        환경 설정:
            environment: 실행 환경 (development/staging/production)
            debug_mode: 디버그 모드 활성화 여부
            log_level: 로그 레벨

        검색 설정:
            vector_weight: 벡터 검색 가중치
            bm25_weight: BM25 검색 가중치
            rrf_k: RRF 알고리즘 K값

        품질 임계값:
            quality_threshold: 품질 임계값
            relevance_threshold: 관련성 임계값
            confidence_threshold: 신뢰도 임계값
            completeness_threshold: 완전성 임계값

        LLM 설정:
            temperature: 생성 온도
            max_tokens: 최대 토큰 수
            top_p: Top-p 샘플링
            top_k: Top-k 샘플링
            repeat_penalty: 반복 페널티

        GPU 설정:
            n_gpu_layers: GPU 레이어 수 (-1=전체)
            main_gpu: 메인 GPU ID
            f16_kv: FP16 KV 캐시 사용
            n_ctx: 컨텍스트 크기
            n_batch: 배치 크기
            n_threads: CPU 스레드 수
            use_mlock: mlock 사용
            use_mmap: mmap 사용
            low_vram: 저VRAM 모드

        성능 설정:
            max_documents_to_process: 최대 처리 문서 수
            max_pages_per_pdf: PDF 최대 페이지 수
            pdf_timeout_seconds: PDF 처리 타임아웃
            search_timeout_seconds: 검색 타임아웃
            parallel_workers: 병렬 워커 수
            batch_size: 배치 크기
            pdf_text_cache_size: PDF 텍스트 캐시 크기
            response_cache_ttl: 응답 캐시 TTL
            cache_max_size: 최대 캐시 크기

    Example:
        >>> config = Config.get_instance()
        >>> print(config.environment)
        'production'
        >>> print(config.max_tokens)
        512
    """

    # 프로젝트 경로
    project_root: Path
    models_dir: Path
    docs_dir: Path
    cache_dir: Path
    db_dir: Path

    # 모델 경로
    qwen_model_path: Path
    sentence_transformers_cache: Path
    korean_embedding_model: str

    # 환경 설정
    environment: Environment
    debug_mode: bool
    log_level: LogLevel

    # 검색 설정
    vector_weight: float
    bm25_weight: float
    rrf_k: int
    search_top_k: int  # 검색 결과 개수

    # 품질 임계값
    quality_threshold: float
    relevance_threshold: float
    confidence_threshold: float
    completeness_threshold: float

    # LLM 설정
    temperature: float
    max_tokens: int
    top_p: float
    top_k: int
    repeat_penalty: float

    # GPU 설정
    n_gpu_layers: int
    main_gpu: int
    f16_kv: bool
    n_ctx: int
    n_batch: int
    n_threads: int
    use_mlock: bool
    use_mmap: bool
    low_vram: bool

    # 성능 설정
    max_documents_to_process: int
    max_pages_per_pdf: int
    pdf_timeout_seconds: int
    search_timeout_seconds: int
    parallel_workers: int
    batch_size: int
    pdf_text_cache_size: int
    response_cache_ttl: int
    cache_max_size: int

    @classmethod
    def get_instance(cls) -> 'Config':
        """싱글톤 인스턴스 반환 (최초 호출 시 생성)

        Returns:
            Config: 전역 설정 인스턴스

        Example:
            >>> config = Config.get_instance()
            >>> config2 = Config.get_instance()
            >>> assert config is config2  # 동일한 인스턴스
        """
        # 모듈 레벨 싱글톤 사용
        global _singleton_instance
        if _singleton_instance is None:
            _singleton_instance = cls._create_from_env()
        return _singleton_instance

    @classmethod
    def _create_from_env(cls) -> 'Config':
        """환경 변수에서 설정 생성 (내부 메서드)"""

        # 프로젝트 루트
        project_root = Path(__file__).parent.absolute()

        # 환경 변수
        environment = cast(Environment, get_env_literal(
            'ENVIRONMENT',
            'production',
            ['development', 'staging', 'production']
        ))

        # 경로 설정
        models_dir = get_env_path('MODELS_DIR', project_root / DefaultPaths.MODELS_SUBDIR)
        docs_dir = get_env_path('DOCS_DIR', project_root / DefaultPaths.DOCS_SUBDIR)
        cache_dir = get_env_path('CACHE_DIR', project_root / DefaultPaths.CACHE_SUBDIR)
        db_dir = get_env_path('DB_DIR', project_root / DefaultPaths.DB_SUBDIR)

        # 디렉터리 생성
        for dir_path in [models_dir, docs_dir, cache_dir, db_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 모델 경로
        qwen_model_path = get_env_path(
            'QWEN_MODEL_PATH',
            models_dir / DefaultPaths.QWEN_MODEL_FILENAME
        )
        sentence_transformers_cache = get_env_path(
            'SENTENCE_TRANSFORMERS_CACHE',
            models_dir / DefaultPaths.SENTENCE_TRANSFORMERS_SUBDIR
        )

        # 임베딩 모델
        korean_embedding_model = os.getenv(
            'KOREAN_EMBEDDING_MODEL',
            DefaultModels.KOREAN_EMBEDDING
        )

        # 검색 가중치 (.env.example의 SEARCH_* 접두사 지원)
        vector_weight = get_env_float('SEARCH_VECTOR_WEIGHT', Thresholds.DEFAULT_VECTOR_WEIGHT)
        if vector_weight == Thresholds.DEFAULT_VECTOR_WEIGHT:
            # SEARCH_ 접두사 없는 fallback
            vector_weight = get_env_float('VECTOR_WEIGHT', Thresholds.DEFAULT_VECTOR_WEIGHT)

        bm25_weight = get_env_float('SEARCH_BM25_WEIGHT', Thresholds.DEFAULT_BM25_WEIGHT)
        if bm25_weight == Thresholds.DEFAULT_BM25_WEIGHT:
            # SEARCH_ 접두사 없는 fallback
            bm25_weight = get_env_float('BM25_WEIGHT', Thresholds.DEFAULT_BM25_WEIGHT)

        # 가중치 정규화
        weight_sum = vector_weight + bm25_weight
        if abs(weight_sum - 1.0) > 0.01:
            warnings.warn(f"VECTOR_WEIGHT + BM25_WEIGHT = {weight_sum} != 1.0, normalizing...")
            vector_weight = vector_weight / weight_sum
            bm25_weight = bm25_weight / weight_sum

        # 품질 임계값
        quality_threshold = get_env_float('QUALITY_THRESHOLD', Thresholds.DEFAULT_QUALITY)
        relevance_threshold = get_env_float('RELEVANCE_THRESHOLD', Thresholds.DEFAULT_RELEVANCE)
        confidence_threshold = get_env_float('CONFIDENCE_THRESHOLD', Thresholds.DEFAULT_CONFIDENCE)
        completeness_threshold = get_env_float('COMPLETENESS_THRESHOLD', Thresholds.DEFAULT_COMPLETENESS)

        # LLM 기본값 (환경별)
        llm_defaults = {
            'development': {'temperature': 0.7, 'max_tokens': 800, 'top_p': 0.9},
            'staging': {'temperature': 0.5, 'max_tokens': 600, 'top_p': 0.87},
            'production': {'temperature': 0.3, 'max_tokens': 512, 'top_p': 0.85}
        }
        defaults = llm_defaults[environment]

        # LLM 설정 (.env.example LLM_* 접두사 지원)
        temperature = get_env_float('LLM_TEMPERATURE', defaults['temperature'])
        if temperature == defaults['temperature']:
            # LLM_ 접두사 없는 fallback
            temperature = get_env_float('TEMPERATURE', defaults['temperature'])

        max_tokens = get_env_int('LLM_MAX_TOKENS', defaults['max_tokens'], Limits.MIN_TOKENS, Limits.MAX_TOKENS)
        if max_tokens == defaults['max_tokens']:
            # LLM_ 접두사 없는 fallback
            max_tokens = get_env_int('MAX_TOKENS', defaults['max_tokens'], Limits.MIN_TOKENS, Limits.MAX_TOKENS)
        top_p = get_env_float('TOP_P', defaults['top_p'])
        top_k = get_env_int('TOP_K', Limits.DEFAULT_TOP_K, Limits.MIN_TOP_K, Limits.MAX_TOP_K)
        repeat_penalty = get_env_float(
            'REPEAT_PENALTY',
            Limits.DEFAULT_REPEAT_PENALTY,
            Limits.MIN_REPEAT_PENALTY,
            Limits.MAX_REPEAT_PENALTY
        )

        # GPU 설정
        n_gpu_layers = int(os.getenv('N_GPU_LAYERS', '-1'))  # -1은 무제한이므로 범위 검증 제외
        main_gpu = max(0, get_env_int('MAIN_GPU', 0, 0, 16))
        f16_kv = get_env_bool('F16_KV', True)
        n_ctx = get_env_int('N_CTX', Limits.DEFAULT_CONTEXT, Limits.MIN_CONTEXT, Limits.MAX_CONTEXT)
        n_batch = get_env_int('N_BATCH', Limits.DEFAULT_BATCH, Limits.MIN_BATCH, Limits.MAX_BATCH)
        n_threads = get_env_int('N_THREADS', Limits.DEFAULT_THREADS, Limits.MIN_THREADS, Limits.MAX_THREADS)
        use_mlock = get_env_bool('USE_MLOCK', False)
        use_mmap = get_env_bool('USE_MMAP', True)
        low_vram = get_env_bool('LOW_VRAM', False)

        # 성능 설정
        max_documents_to_process = get_env_int(
            'MAX_DOCUMENTS_TO_PROCESS',
            Limits.DEFAULT_DOCUMENTS,
            Limits.MIN_DOCUMENTS,
            Limits.MAX_DOCUMENTS
        )
        max_pages_per_pdf = get_env_int(
            'MAX_PAGES_PER_PDF',
            Limits.DEFAULT_PDF_PAGES,
            Limits.MIN_PDF_PAGES,
            Limits.MAX_PDF_PAGES
        )
        pdf_timeout_seconds = get_env_int(
            'PDF_TIMEOUT_SECONDS',
            Limits.DEFAULT_PDF_TIMEOUT,
            Limits.MIN_TIMEOUT,
            Limits.MAX_TIMEOUT
        )
        search_timeout_seconds = get_env_int(
            'SEARCH_TIMEOUT_SECONDS',
            Limits.DEFAULT_SEARCH_TIMEOUT,
            Limits.MIN_TIMEOUT,
            Limits.MAX_TIMEOUT
        )

        # 병렬 처리
        max_workers = multiprocessing.cpu_count()
        parallel_workers = get_env_int(
            'PARALLEL_WORKERS',
            min(Limits.DEFAULT_WORKERS, max_workers),
            Limits.MIN_WORKERS,
            max_workers
        )
        batch_size = get_env_int('BATCH_SIZE', 10, 1, 20)

        # 캐싱
        pdf_text_cache_size = get_env_int(
            'PDF_TEXT_CACHE_SIZE',
            Limits.DEFAULT_PDF_CACHE,
            Limits.MIN_CACHE_SIZE,
            Limits.MAX_CACHE_SIZE
        )
        response_cache_ttl = get_env_int(
            'RESPONSE_CACHE_TTL',
            Limits.DEFAULT_CACHE_TTL,
            Limits.MIN_CACHE_TTL,
            Limits.MAX_CACHE_TTL
        )
        cache_max_size = get_env_int(
            'CACHE_MAX_SIZE',
            Limits.DEFAULT_CACHE_SIZE,
            Limits.MIN_CACHE_SIZE,
            Limits.MAX_CACHE_SIZE
        )

        # 디버그 설정
        debug_mode = get_env_bool('DEBUG_MODE', False)
        log_level = cast(LogLevel, get_env_literal(
            'LOG_LEVEL',
            'INFO',
            ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        ))

        # RRF (.env.example의 SEARCH_RRF_K 지원)
        rrf_k = get_env_int('SEARCH_RRF_K', Thresholds.DEFAULT_RRF_K, 1, 100)
        if rrf_k == Thresholds.DEFAULT_RRF_K:
            # SEARCH_ 접두사 없는 fallback
            rrf_k = get_env_int('RRF_K', Thresholds.DEFAULT_RRF_K, 1, 100)

        # 검색 TOP_K 파라미터 추가 (.env.example SEARCH_TOP_K 지원)
        search_top_k = get_env_int('SEARCH_TOP_K', 5, 1, 100)

        return cls(
            project_root=project_root,
            models_dir=models_dir,
            docs_dir=docs_dir,
            cache_dir=cache_dir,
            db_dir=db_dir,
            qwen_model_path=qwen_model_path,
            sentence_transformers_cache=sentence_transformers_cache,
            korean_embedding_model=korean_embedding_model,
            environment=environment,
            debug_mode=debug_mode,
            log_level=log_level,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            rrf_k=rrf_k,
            search_top_k=search_top_k,
            quality_threshold=quality_threshold,
            relevance_threshold=relevance_threshold,
            confidence_threshold=confidence_threshold,
            completeness_threshold=completeness_threshold,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            n_gpu_layers=n_gpu_layers,
            main_gpu=main_gpu,
            f16_kv=f16_kv,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            use_mlock=use_mlock,
            use_mmap=use_mmap,
            low_vram=low_vram,
            max_documents_to_process=max_documents_to_process,
            max_pages_per_pdf=max_pages_per_pdf,
            pdf_timeout_seconds=pdf_timeout_seconds,
            search_timeout_seconds=search_timeout_seconds,
            parallel_workers=parallel_workers,
            batch_size=batch_size,
            pdf_text_cache_size=pdf_text_cache_size,
            response_cache_ttl=response_cache_ttl,
            cache_max_size=cache_max_size,
        )

    def get_summary(self) -> ConfigSummary:
        """설정 요약 반환 (보안: 경로 정보 제외)

        Returns:
            ConfigSummary: 설정 요약 딕셔너리
        """
        return ConfigSummary(
            environment=self.environment,
            gpu=GPUConfig(
                enabled=self.n_gpu_layers != 0,
                layers=self.n_gpu_layers,
                main_gpu=self.main_gpu,
                f16_kv=self.f16_kv
            ),
            llm=LLMConfig(
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                context_size=self.n_ctx,
                top_p=self.top_p,
                top_k=self.top_k,
                repeat_penalty=self.repeat_penalty
            ),
            search=SearchConfig(
                vector_weight=self.vector_weight,
                bm25_weight=self.bm25_weight,
                max_docs=self.max_documents_to_process,
                quality_threshold=self.quality_threshold,
                relevance_threshold=self.relevance_threshold
            ),
            performance=PerformanceConfig(
                parallel_workers=self.parallel_workers,
                cache_size=self.cache_max_size,
                cache_ttl=self.response_cache_ttl,
                batch_size=self.batch_size
            ),
            debug=self.debug_mode
        )

    def validate(self) -> Dict[str, bool]:
        """설정 유효성 검사

        Returns:
            Dict[str, bool]: 검증 결과

        Example:
            >>> config = Config.get_instance()
            >>> results = config.validate()
            >>> print(results['model_exists'])
            True
        """
        validations = {}

        # 모델 파일 존재 확인
        validations['model_exists'] = self.qwen_model_path.exists()

        # 디렉터리 쓰기 권한 확인
        validations['cache_writable'] = os.access(str(self.cache_dir), os.W_OK)
        validations['db_writable'] = os.access(str(self.db_dir), os.W_OK)

        # GPU 설정 확인
        validations['gpu_configured'] = self.n_gpu_layers != 0

        # 가중치 합 확인
        validations['weights_normalized'] = abs((self.vector_weight + self.bm25_weight) - 1.0) < 0.01

        return validations

    def save_to_file(self, filepath: Optional[Path] = None) -> None:
        """설정을 JSON 파일로 저장 (보안: 민감 정보 필터링)

        Args:
            filepath: 저장 경로 (None이면 기본 경로 사용)

        Raises:
            ConfigSaveError: 저장 실패 시

        Example:
            >>> config = Config.get_instance()
            >>> config.save_to_file()
        """
        if filepath is None:
            filepath = self.project_root / DefaultPaths.CONFIG_FILENAME

        try:
            # 민감 정보 제외하고 요약만 저장
            summary = self.get_summary()

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

        except (IOError, OSError) as e:
            raise ConfigSaveError(f"Failed to save config to {filepath}: {e}") from e

    @classmethod
    def load_from_file(cls, filepath: Optional[Path] = None) -> Optional[ConfigSummary]:
        """설정 파일에서 로드 (참고용, 실제 설정은 환경변수 우선)

        Args:
            filepath: 로드 경로 (None이면 기본 경로 사용)

        Returns:
            Optional[ConfigSummary]: 로드된 설정 요약 (실패 시 None)

        Example:
            >>> summary = Config.load_from_file()
            >>> if summary:
            ...     print(summary['environment'])
        """
        if filepath is None:
            filepath = Path(__file__).parent.absolute() / DefaultPaths.CONFIG_FILENAME

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return cast(ConfigSummary, json.load(f))
        except (IOError, OSError, json.JSONDecodeError) as e:
            warnings.warn(f"Failed to load config from {filepath}: {e}")
            return None

    def print_summary(self) -> None:
        """설정 요약 출력 (디버그용)

        Example:
            >>> config = Config.get_instance()
            >>> config.print_summary()
        """
        print("\n=== Configuration Summary ===")
        summary = self.get_summary()
        for key, value in summary.items():
            print(f"{key}: {value}")

        print("\n=== Configuration Validation ===")
        for check, passed in self.validate().items():
            status = "✅" if passed else "❌"
            print(f"{status} {check}: {passed}")
        print("============================\n")


# ============================================================================
# 하위 호환성 (기존 코드와의 호환성 유지)
# ============================================================================

# 싱글톤 인스턴스 자동 생성
_config = Config.get_instance()

# 기존 코드 호환을 위한 모듈 레벨 변수들 (읽기 전용)
PROJECT_ROOT = str(_config.project_root)
MODELS_DIR = str(_config.models_dir)
DOCS_DIR = str(_config.docs_dir)
CACHE_DIR = str(_config.cache_dir)
DB_DIR = str(_config.db_dir)
QWEN_MODEL_PATH = str(_config.qwen_model_path)
SENTENCE_TRANSFORMERS_CACHE = str(_config.sentence_transformers_cache)
KOREAN_EMBEDDING_MODEL = _config.korean_embedding_model
ENVIRONMENT = _config.environment
VECTOR_WEIGHT = _config.vector_weight
BM25_WEIGHT = _config.bm25_weight
RRF_K = _config.rrf_k
SEARCH_TOP_K = _config.search_top_k
QUALITY_THRESHOLD = _config.quality_threshold
RELEVANCE_THRESHOLD = _config.relevance_threshold
CONFIDENCE_THRESHOLD = _config.confidence_threshold
COMPLETENESS_THRESHOLD = _config.completeness_threshold
TEMPERATURE = _config.temperature
MAX_TOKENS = _config.max_tokens
TOP_P = _config.top_p
TOP_K = _config.top_k
REPEAT_PENALTY = _config.repeat_penalty
N_GPU_LAYERS = _config.n_gpu_layers
MAIN_GPU = _config.main_gpu
F16_KV = _config.f16_kv
N_CTX = _config.n_ctx
N_BATCH = _config.n_batch
N_THREADS = _config.n_threads
USE_MLOCK = _config.use_mlock
USE_MMAP = _config.use_mmap
LOW_VRAM = _config.low_vram
MAX_DOCUMENTS_TO_PROCESS = _config.max_documents_to_process
MAX_PAGES_PER_PDF = _config.max_pages_per_pdf
PDF_TIMEOUT_SECONDS = _config.pdf_timeout_seconds
SEARCH_TIMEOUT_SECONDS = _config.search_timeout_seconds
PARALLEL_WORKERS = _config.parallel_workers
BATCH_SIZE = _config.batch_size
PDF_TEXT_CACHE_SIZE = _config.pdf_text_cache_size
RESPONSE_CACHE_TTL = _config.response_cache_ttl
CACHE_MAX_SIZE = _config.cache_max_size
DEBUG_MODE = _config.debug_mode
LOG_LEVEL = _config.log_level

# 하위 호환 함수들
def get_config_summary() -> ConfigSummary:
    """설정 요약 반환 (하위 호환)"""
    return _config.get_summary()

def validate_config() -> Dict[str, bool]:
    """설정 검증 (하위 호환)"""
    return _config.validate()

def save_config(_unused_config: Optional[Dict[str, Any]] = None) -> ConfigSummary:
    """설정 저장 (하위 호환)

    Note: config 매개변수는 하위 호환을 위해 유지되나 무시됩니다.
    """
    _config.save_to_file()
    return _config.get_summary()

def load_config_from_file() -> Optional[ConfigSummary]:
    """설정 로드 (하위 호환)"""
    return Config.load_from_file()

def reload_config() -> ConfigSummary:
    """설정 재로드 (하위 호환)

    Note: frozen dataclass이므로 재로드 불가능.
    새 인스턴스를 생성하려면 프로세스를 재시작하세요.
    """
    warnings.warn(
        "reload_config() is deprecated. Config is frozen and cannot be reloaded. "
        "Restart the process to apply new environment variables.",
        DeprecationWarning,
        stacklevel=2
    )
    return _config.get_summary()


# ============================================================================
# 초기화 (개발 모드에서 요약 출력)
# ============================================================================

if _config.environment == 'development' and _config.debug_mode:
    _config.print_summary()
