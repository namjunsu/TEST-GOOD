"""애플리케이션 상수 정의

Magic Number 중앙화로 유지보수성 향상.
환경변수가 설정되면 환경변수 값을 우선 사용.

사용법:
    from config.constants import SearchConfig, LLMConfig

    top_k = SearchConfig.DEFAULT_TOP_K
    max_tokens = LLMConfig.MAX_TOKENS_QA
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    """검색 관련 상수"""

    # top_k 기본값
    DEFAULT_TOP_K: int = 5
    DETAILED_TOP_K: int = 8
    SEARCH_TOP_K: int = 10
    ALL_DOCS_TOP_K: int = 200  # "전부", "모두" 쿼리용

    # 점수 임계값
    RAG_MIN_SCORE: float = 0.35
    BM25_MIN_ABS: float = 5.0
    VEC_MIN_ABS: float = 0.25

    # 키워드 검색
    MIN_KEYWORD_COVERAGE: int = 2
    MIN_TOKEN_COUNT: int = 4

    # 문서 스니펫
    MIN_SNIPPET_LEN: int = 1200
    MAX_SNIPPET_LEN: int = 5000
    MIN_CONTENT_LEN: int = 50

    # UI 표시 제한
    CARD_DISPLAY_LIMIT: int = 10
    SNIPPET_MAX_LENGTH: int = 400
    TITLE_MAX_LENGTH: int = 160


@dataclass(frozen=True)
class ScoringConfig:
    """스코어링 관련 상수 (hybrid.py용)"""

    # 파일명 보너스 (토큰당)
    FILENAME_TOKEN_BONUS: float = 0.2
    FILENAME_PHRASE_BONUS: float = 0.8
    FILENAME_BONUS_CAP: float = 2.0

    # match_ratio 스케일링
    MATCH_RATIO_SCALE: float = 8.0
    MAX_FINAL_SCORE: float = 10.0

    # 텍스트 길이 페널티 임계값
    SHORT_TEXT_THRESHOLD: int = 200
    VERY_SHORT_TEXT_THRESHOLD: int = 100
    SHORT_TEXT_PENALTY: float = 0.5
    VERY_SHORT_TEXT_PENALTY: float = 0.2

    # 유사도 보너스 (파일명 유사도 기반)
    HIGH_SIM_THRESHOLD: float = 0.8
    MED_SIM_THRESHOLD: float = 0.6
    LOW_SIM_THRESHOLD: float = 0.4
    HIGH_SIM_BONUS: float = 30.0
    MED_SIM_BONUS: float = 20.0
    LOW_SIM_BONUS: float = 10.0


@dataclass(frozen=True)
class LLMConfig:
    """LLM 생성 관련 상수"""

    # 모드별 max_tokens
    MAX_TOKENS_DETAILED: int = 1500
    MAX_TOKENS_SECTION: int = 900
    MAX_TOKENS_SUMMARY: int = 600
    MAX_TOKENS_QA: int = 800

    # 기본값
    DEFAULT_TEMPERATURE: float = 0.1
    DEFAULT_COMPRESSION_RATIO: float = 0.7

    # 컨텍스트 제한
    MAX_CONTEXT_TOKENS: int = 3200
    MAX_CONTEXT_CHARS: int = 10000


@dataclass(frozen=True)
class OCRConfig:
    """OCR 처리 관련 상수"""

    # DPI 설정
    DEFAULT_DPI: int = 300
    HIGH_QUALITY_DPI: int = 400

    # 텍스트 품질 임계값
    POOR_TEXT_THRESHOLD: int = 100  # 100자 미만 = POOR
    LOW_TEXT_THRESHOLD: int = 500   # 500자 미만 = LOW
    GOOD_AVG_PER_PAGE: int = 300    # 페이지당 평균 300자 이상 = GOOD


@dataclass(frozen=True)
class RouterConfig:
    """쿼리 라우터 관련 상수 (query_router.py용)"""

    # 파일명 유사도 스코어링
    PARTIAL_MATCH_BASE: float = 0.8     # 부분 포함 시 기본 점수
    LENGTH_BONUS_MAX: float = 0.4       # 길이 보너스 최대값
    LENGTH_PENALTY_FACTOR: float = 0.01  # 길이 차이 페널티 계수

    # 후보 선택 임계값
    SINGLE_CANDIDATE_THRESHOLD: float = 0.66  # 단일 후보 확정 점수

    # 라우팅 신뢰도 (높음 → 낮음)
    CONF_VERY_HIGH: float = 0.98   # SEARCH_CONTENT_ONLY (정밀 내용 검색)
    CONF_HIGH: float = 0.95        # COST, DOCUMENT (존재 확인/상세)
    CONF_MEDIUM_HIGH: float = 0.9  # DOCUMENT, SEARCH (list_intent), QA (존재 확인)
    CONF_MEDIUM: float = 0.85      # QA (info_question), SEARCH (search_intent)
    CONF_QA_KEYWORD: float = 0.8   # QA (키워드 감지)
    CONF_DOC_REF_ONLY: float = 0.7  # SEARCH (문서 참조만)
    CONF_LOW_CONF_MAX: float = 0.65  # low-conf 하향 조정 최대값
    CONF_FALLBACK: float = 0.6     # DOCUMENT (doc_reference_only)
    CONF_DEFAULT: float = 0.5      # QA (기본)


@dataclass(frozen=True)
class HandlerConfig:
    """핸들러 관련 상수 (handlers/search.py용)"""

    # 검색 문서 수
    BULK_SEARCH_TOP_K: int = 200   # 전체/목록 검색 시 top_k
    NORMAL_SEARCH_TOP_K: int = 10  # 일반 검색 시 top_k


@dataclass(frozen=True)
class CacheConfig:
    """캐시 관련 상수"""

    # TTL (초 단위)
    QUERY_CACHE_TTL: int = 3600      # 1시간
    METADATA_CACHE_TTL: int = 86400  # 24시간

    # 크기 제한
    MAX_CACHE_SIZE_MB: int = 500
    MAX_CACHE_ENTRIES: int = 10000


@dataclass(frozen=True)
class HybridSearchConfig:
    """하이브리드 검색 Stage 관련 상수"""

    # FTS 검색 설정
    FTS_SUFFICIENT_RATIO: float = 0.5      # FTS 결과가 목표의 50% 이상이면 충분
    FTS_OVERSAMPLE_FACTOR: int = 2         # FTS 검색 시 top_k * 2 로 오버샘플링

    # DOC_ANCHORED 모드 설정
    DOC_ANCHORED_SEARCH_K: int = 50        # DOC_ANCHORED 모드 검색 후보 수
    DOC_ANCHORED_FALLBACK_MULTIPLIER: int = 3  # 필터링 결과 없을 때 원본 배수

    # BM25 보충 설정
    BM25_SUPPLEMENT_THRESHOLD: float = 0.5  # FTS 결과가 이 비율 미만이면 BM25 보충

    # 선택 문서 스코어
    SELECTED_DOC_SCORE: float = 99.9       # 선택된 문서 강제 스코어


@dataclass(frozen=True)
class DBConfig:
    """데이터베이스 관련 상수"""

    # 타임아웃 (초)
    LOCK_TIMEOUT: int = 30
    BUSY_TIMEOUT: int = 5000  # milliseconds

    # 경로 (기본값)
    DEFAULT_METADATA_DB: str = "metadata.db"
    DEFAULT_EXTRACTED_DIR: str = "data/extracted"


@dataclass(frozen=True)
class PipelineConfig:
    """RAG 파이프라인 관련 상수"""

    # 컨텍스트 설정
    CONTEXT_MAX_LENGTH: int = 10000          # hydrate_context max_len
    SNIPPET_PREVIEW_LENGTH: int = 400        # 스니펫 미리보기 길이
    FALLBACK_SNIPPET_LENGTH: int = 800       # 폴백 스니펫 길이

    # 성능 가드 임계값 (초)
    SLOW_QUERY_CRITICAL: float = 10.0        # 심각한 슬로 쿼리
    SLOW_QUERY_WARNING: float = 3.0          # 경고 슬로 쿼리

    # 출처 표시 제한
    DEFAULT_MAX_SOURCES: int = 3             # 기본 출처 표시 수
    BULK_MAX_SOURCES: int = 200              # 전체/모든 쿼리 출처 표시 수

    # 토큰 임계값
    MIN_TOKEN_COUNT_FOR_RAG: int = 4         # RAG 모드 최소 토큰 수

    # Evidence 폴백
    EVIDENCE_FALLBACK_COUNT: int = 3         # raw_results 폴백 시 사용할 개수


# 환경변수 오버라이드 지원 함수
def get_search_config() -> dict:
    """SearchConfig를 환경변수로 오버라이드"""
    return {
        "default_top_k": int(os.getenv("SEARCH_TOP_K", SearchConfig.DEFAULT_TOP_K)),
        "rag_min_score": float(os.getenv("RAG_MIN_SCORE", SearchConfig.RAG_MIN_SCORE)),
        "bm25_min_abs": float(os.getenv("BM25_MIN_ABS", SearchConfig.BM25_MIN_ABS)),
        "vec_min_abs": float(os.getenv("VEC_MIN_ABS", SearchConfig.VEC_MIN_ABS)),
        "min_keyword_coverage": int(os.getenv("MIN_KEYWORD_COVERAGE", SearchConfig.MIN_KEYWORD_COVERAGE)),
    }


def get_llm_config() -> dict:
    """LLMConfig를 환경변수로 오버라이드"""
    return {
        "max_tokens_detailed": int(os.getenv("LLM_MAX_TOKENS_DETAILED", LLMConfig.MAX_TOKENS_DETAILED)),
        "max_tokens_section": int(os.getenv("LLM_MAX_TOKENS_SECTION", LLMConfig.MAX_TOKENS_SECTION)),
        "max_tokens_summary": int(os.getenv("LLM_MAX_TOKENS_SUMMARY", LLMConfig.MAX_TOKENS_SUMMARY)),
        "max_tokens_qa": int(os.getenv("LLM_MAX_TOKENS_QA", LLMConfig.MAX_TOKENS_QA)),
        "default_temperature": float(os.getenv("LLM_TEMPERATURE", LLMConfig.DEFAULT_TEMPERATURE)),
    }


__all__ = [
    "CacheConfig",
    "DBConfig",
    "HandlerConfig",
    "HybridSearchConfig",
    "LLMConfig",
    "OCRConfig",
    "PipelineConfig",
    "RouterConfig",
    "ScoringConfig",
    "SearchConfig",
    "get_llm_config",
    "get_search_config",
]
