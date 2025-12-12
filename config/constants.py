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
class MetricsConfig:
    """메트릭 수집 관련 상수 (metrics_collector.py용)"""

    # 지연시간 샘플 윈도 크기
    LATENCY_WINDOW_SIZE: int = 2000

    # EWMA 반감기 (초)
    EWMA_HALFLIFE_SECONDS: float = 60.0


@dataclass(frozen=True)
class RoutingMonitorConfig:
    """라우팅 모니터 관련 상수 (routing_monitor.py용)"""

    # 쿼리 길이 제한
    QUERY_MAX_LENGTH: int = 200
    QUERY_LOG_PREVIEW_LENGTH: int = 50

    # 신뢰도 임계값
    LOW_CONFIDENCE_WARN: float = 0.5
    LOW_CONFIDENCE_FILTER: float = 0.7

    # 결과 제한
    LOW_CONF_RESULT_LIMIT: int = 10
    MOST_COMMON_LIMIT: int = 20

    # 분석 기간 및 기본값
    ANALYSIS_DAYS: int = 7
    MIN_OCCURRENCES_DEFAULT: int = 5


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
    COST_SEARCH_TOP_K: int = 15    # 비용 조회 시 top_k

    # 텍스트 품질 검사 임계값
    MIN_TEXT_LENGTH: int = 10               # 최소 텍스트 길이
    MAX_SPECIAL_CHAR_RATIO: float = 0.2     # 특수문자 비율 상한
    MIN_KOREAN_CHAR_RATIO: float = 0.3      # 한글 비율 하한

    # 응답 제한
    MAX_COST_DOCS_DISPLAY: int = 10         # 비용 응답 시 최대 표시 문서 수


@dataclass(frozen=True)
class DocumentHandlerConfig:
    """문서 핸들러 관련 상수 (handlers/document.py용)"""

    # 텍스트 길이 임계값
    SHORT_TEXT_THRESHOLD: int = 500         # 짧은 문서 임계값 (원문 반환)
    MIN_TEXT_LENGTH: int = 10               # 최소 텍스트 길이

    # 컨텍스트 윈도우
    CONTEXT_WINDOW: int = 8000              # LLM 컨텍스트 최대 길이
    CHUNK_CONTEXT_MAX: int = 12000          # 청크 결합 최대 길이
    CHUNK_SNIPPET_MAX: int = 3000           # 개별 청크 최대 길이

    # 미리보기 길이
    DETAILED_PREVIEW_LEN: int = 3000        # 자세히 모드 미리보기
    NORMAL_PREVIEW_LEN: int = 1500          # 일반 모드 미리보기
    EVIDENCE_SNIPPET_LEN: int = 1000        # Evidence 스니펫 길이

    # 토큰 설정
    DEFAULT_MAX_TOKENS: int = 800           # 기본 max_tokens
    SUMMARY_MIN_TOKENS: int = 1000          # 요약 모드 최소 토큰

    # 청크 로드
    DEFAULT_CHUNK_TOP_K: int = 20           # 기본 청크 로드 수
    FALLBACK_CHUNK_TOP_K: int = 10          # 폴백 청크 로드 수


@dataclass(frozen=True)
class CacheConfig:
    """캐시 관련 상수"""

    # TTL (초 단위)
    QUERY_CACHE_TTL: int = 3600      # 1시간
    METADATA_CACHE_TTL: int = 86400  # 24시간

    # 크기 제한
    MAX_CACHE_SIZE_MB: int = 500
    MAX_CACHE_ENTRIES: int = 10000

    # QueryCache 설정 (cache_manager.py)
    QUERY_CACHE_MAX_SIZE: int = 100  # 최대 캐시 항목 수
    QUERY_CACHE_DEFAULT_TTL: int = 3600  # 기본 TTL (1시간)
    QUERY_CACHE_GLOBAL_TTL: int = 7200  # 글로벌 인스턴스 TTL (2시간)
    INFLIGHT_WAIT_TIMEOUT: float = 10.0  # 스탬피드 대기 타임아웃


@dataclass(frozen=True)
class APIConfig:
    """API 서버 관련 상수 (api/main.py용)"""

    # GZip 압축 설정
    GZIP_MINIMUM_SIZE: int = 1024           # 1KB 이상 응답에 압축 적용

    # 로그 로테이션 설정
    LOG_ROTATION_SIZE_BYTES: int = 10485760  # 10MB (10 * 1024 * 1024)

    # 인덱스 위생 임계값
    INDEX_SANITY_THRESHOLD_GAP: int = 5     # fs/index 카운트 차이 허용치

    # 서버 설정
    DEFAULT_PORT: int = 7860                # 기본 포트


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

    # strict_content 모드 설정
    STRICT_CONTENT_OVERSAMPLE: int = 5     # strict_content 모드 오버샘플링 배수

    # 메타데이터 라우팅 설정
    METADATA_MATCH_SCORE: float = 3.0      # 메타데이터 일치 기본 스코어

    # 짧은 텍스트 페널티 (relevance score 계산용)
    RELEVANCE_SHORT_TEXT_THRESHOLD: int = 100  # 짧은 텍스트 임계값
    RELEVANCE_SHORT_TEXT_PENALTY: float = 0.7  # 짧은 텍스트 페널티 배수


@dataclass(frozen=True)
class HybridRetrieverConfig:
    """HybridRetriever 환경변수 기본값 (retrievers/hybrid.py용)"""

    # 검색 설정
    SNIPPET_MAX_LENGTH: int = 3600          # 스니펫 최대 길이
    RETRIEVE_TOPK: int = 200                # 검색 top_k 기본값
    DISPLAY_LIMIT: int = 20                 # 표시 제한

    # 병렬 처리
    PARALLEL_MAX_WORKERS: int = 3           # 병렬 워커 수

    # 인덱스 경로
    DEFAULT_BM25_INDEX_PATH: str = "var/index/bm25_index.pkl"
    DEFAULT_ROUTER_KEYWORDS_PATH: str = "config/router_keywords.yaml"


@dataclass(frozen=True)
class ExactMatchConfig:
    """정확일치 검색기 관련 상수 (retrievers/exact_match.py용)"""

    # 스코어 가중치
    EXACT_CODE_WEIGHT: float = 3.0          # model_codes 테이블에서 정확일치
    FILENAME_EXACT_WEIGHT: float = 1.5      # 파일명 정확일치 (토큰 전체)
    FILENAME_PARTIAL_WEIGHT: float = 1.0    # 파일명 부분일치
    RECENCY_WEIGHT: float = 0.1             # 최신성 가중 (연도당)

    # 스니펫 설정
    SNIPPET_MAX_LENGTH: int = 800           # 스니펫 최대 길이

    # 스코어 범위
    SCORE_MIN: float = 0.0                  # 최소 스코어
    SCORE_MAX: float = 10.0                 # 최대 스코어


@dataclass(frozen=True)
class DBConfig:
    """데이터베이스 관련 상수"""

    # 타임아웃 (초)
    LOCK_TIMEOUT: int = 30
    BUSY_TIMEOUT: int = 5000  # milliseconds

    # 경로 (기본값)
    DEFAULT_METADATA_DB: str = "metadata.db"
    DEFAULT_EXTRACTED_DIR: str = "data/extracted"

    # SQLite PRAGMA 설정 (metadata_db.py용)
    MMAP_SIZE: int = 1073741824       # 1GB mmap
    CACHE_SIZE: int = -524288         # ~512MB cache (음수: KB 단위)
    PAGE_SIZE: int = 4096             # 페이지 크기
    ANALYSIS_LIMIT: int = 400         # 분석 제한

    # 텍스트 제한
    TEXT_PREVIEW_MAX_LENGTH: int = 1000  # text_preview 최대 길이


@dataclass(frozen=True)
class ResponseBuilderConfig:
    """응답 빌더 관련 상수 (handlers/response.py용)"""

    # 쿼리 분류
    SHORT_QUERY_TOKEN_THRESHOLD: int = 3    # 짧은 질의 판별 토큰 임계값

    # 키워드 분석
    KEYWORD_COVERAGE_MAX_RESULTS: int = 10  # 키워드 커버리지 검사 최대 결과 수

    # Evidence 포맷팅
    EVIDENCE_SNIPPET_MAX_LEN: int = 400     # Evidence 스니펫 최대 길이
    FALLBACK_TITLE_MAX_LEN: int = 160       # 폴백 스니펫용 제목 최대 길이

    # 텍스트 미리보기
    TEXT_PREVIEW_MAX_LEN: int = 100         # clean_text_preview 결과 길이

    # 카드 표시
    COUNT_QUERY_CARD_LIMIT: int = 10        # 카운트 쿼리 시 표시 카드 수

    # 파일 참조 토큰
    FILE_REF_TOKEN_LEN: int = 10            # 파일 ref 토큰 해시 길이


@dataclass(frozen=True)
class FinanceExtractorConfig:
    """금액 추출기 관련 상수 (extractors/finance.py용)"""

    # 금액 검증 허용 오차
    TOTAL_AMOUNT_TOLERANCE: float = 0.015   # 총액-공급가액 불일치 허용 (1.5%)
    QTY_PRICE_TOLERANCE: float = 0.05       # 단가×수량 불일치 허용 (5%)
    VAT_RULE_TOLERANCE: float = 0.02        # VAT 10% 규칙 허용 오차 (2%)

    # VAT 세율
    VAT_RATE: float = 0.1                   # 부가세 기본 세율 (10%)


@dataclass(frozen=True)
class JsonUtilsConfig:
    """JSON 유틸리티 관련 상수 (json_utils.py용)"""

    # 마스킹 출력 길이
    MASK_OUTPUT_MAX_LEN: int = 200          # 마스킹된 출력 최대 길이
    VALUE_PREVIEW_MAX_LEN: int = 50         # 개별 값 미리보기 최대 길이
    LOG_PREVIEW_MAX_LEN: int = 200          # 로그 미리보기 최대 길이


@dataclass(frozen=True)
class MetaParserConfig:
    """메타데이터 파서 관련 상수 (parse_meta.py용)"""

    # 설정 핫리로드
    CONFIG_RELOAD_SECS: int = 10            # 설정 재로드 체크 주기 (초)

    # 카테고리 분류
    CATEGORY_BODY_SAMPLE_LEN: int = 500     # 본문 분류 시 분석할 길이


@dataclass(frozen=True)
class TableParserConfig:
    """표 파서 관련 상수 (parse_tables.py용)"""

    # 헤더 탐색
    HEADER_SCAN_LINES: int = 300             # 헤더 스캔 범위 (앞쪽 N줄)
    HEADER_MIN_CELLS: int = 2                # 헤더 최소 셀 개수
    HEADER_MAX_CELLS: int = 10               # 헤더 최대 셀 개수
    HEADER_SIMILARITY_THRESHOLD: float = 0.7  # 헤더 감지 유사도 임계값

    # 합계 검증
    DEFAULT_REL_TOLERANCE: float = 0.01      # 상대 허용치 기본값 (1%)


@dataclass(frozen=True)
class SummaryTemplateConfig:
    """요약 템플릿 관련 상수 (summary_templates.py용)"""

    # 문서 종류 감지
    DOC_KIND_SAMPLE_LENGTH: int = 2000      # 감지 시 분석할 텍스트 길이
    MINUTES_KEYWORD_THRESHOLD: int = 2      # 회의록 판별 키워드 임계값

    # 금액 파싱 윈도우
    MONEY_SEARCH_WINDOW: int = 60           # 기본 윈도우 크기
    MONEY_RECHECK_WINDOW: int = 80          # 재확인 윈도우 크기

    # 출력 포맷팅 제한
    MAX_COMPARE_ALTERNATIVES: int = 4       # 비교 대안 최대 표시 개수
    MAX_EVIDENCE_DISPLAY: int = 2           # 증거 최대 표시 개수


@dataclass(frozen=True)
class MergeExtractorConfig:
    """필드 병합기 관련 상수 (extractors/merge.py용)"""

    # reason 문장 길이 필터
    REASON_MIN_LENGTH: int = 8               # 사유 최소 길이
    REASON_MAX_LENGTH: int = 240             # 사유 최대 길이

    # duration_years 범위
    DURATION_YEARS_MIN: int = 1              # 사용 기간 최솟값 (년)
    DURATION_YEARS_MAX: int = 30             # 사용 기간 최댓값 (년)


@dataclass(frozen=True)
class QueryExpanderConfig:
    """쿼리 확장기 관련 상수 (query_expander.py용)"""

    # 프롬프트 인젝션 방지
    MAX_QUERY_LENGTH: int = 500              # 질의 길이 제한

    # 캐시 설정
    CACHE_TTL_SEC: int = 900                 # 캐시 TTL (15분)
    CACHE_KEY_MAX_LENGTH: int = 200          # 캐시 키 최대 길이

    # FTS 쿼리 생성
    MAX_FTS_TERMS: int = 24                  # FTS 쿼리 용어 제한


@dataclass(frozen=True)
class PersistentCacheConfig:
    """영구 캐시 관련 상수 (persistent_cache.py용)"""

    # TTL 설정
    DEFAULT_TTL_SEC: int = 7200              # 기본 TTL (2시간)

    # DB 크기 제한
    MAX_DB_SIZE_MB: int = 256                # DB 최대 크기 (MB)
    MMAP_SIZE_BYTES: int = 268435456         # mmap 크기 (256MB)

    # 정리 설정
    CLEANUP_PROBABILITY: float = 0.01        # 정리 확률 (1%)
    LRU_EVICT_BATCH_SIZE: int = 1000         # LRU 축출 배치 크기

    # SQLite 타임아웃
    CONNECT_TIMEOUT_SEC: float = 5.0         # 연결 타임아웃 (초)
    BUSY_TIMEOUT_MS: int = 5000              # busy 타임아웃 (ms)


@dataclass(frozen=True)
class ContextHydratorConfig:
    """컨텍스트 수화기 관련 상수 (context_hydrator.py용)"""

    # 텍스트 길이
    DEDUP_HASH_LENGTH: int = 200             # 중복 제거용 텍스트 해시 길이
    MIN_TEXT_FOR_PDF: int = 500              # PDF 보강 트리거 임계값
    PDF_NEEDED_LENGTH: int = 5000            # PDF 추출 필요 길이

    # 파일 크기 제한
    MAX_PDF_SIZE_MB: int = 64                # PDF 최대 크기 (MB)

    # 문장 추출
    MIN_SENTENCE_LENGTH: int = 10            # 최소 문장 길이


@dataclass(frozen=True)
class DoctypeConfig:
    """문서 유형 분류기 관련 상수 (doctype.py용)"""

    # 핫리로드 설정
    HOT_RELOAD_INTERVAL_SEC: int = 10        # 설정 파일 재로드 체크 간격 (초)

    # Confidence 임계값
    LOW_CONFIDENCE_THRESHOLD: float = 0.5    # low confidence 판정 기준

    # 기본 우선순위
    DEFAULT_PRIORITY: int = 999              # 우선순위 미지정 시 기본값


@dataclass(frozen=True)
class QueryRoutingConfig:
    """쿼리 라우팅 관련 상수 (query_routing.py용)"""

    # 리트리버 파라미터 (모드별)
    DETAILED_TOP_K: int = 10                 # detailed 모드 top_k
    DETAILED_MAX_CONTEXT: int = 4000         # detailed 모드 max_context_tokens
    SUMMARY_TOP_K: int = 8                   # summary 모드 top_k
    SUMMARY_MAX_CONTEXT: int = 3500          # summary 모드 max_context_tokens
    NUMERIC_TOP_K: int = 6                   # numeric 모드 top_k
    NUMERIC_MAX_CONTEXT: int = 2500          # numeric 모드 max_context_tokens
    DEFAULT_TOP_K: int = 5                   # 기본 QA 모드 top_k
    DEFAULT_MAX_CONTEXT: int = 2000          # 기본 QA 모드 max_context_tokens

    # 쿼리 판단 임계값
    SHORT_QUERY_TOKEN_THRESHOLD: int = 3     # 짧은 쿼리 토큰 임계값
    KEYWORD_COVERAGE_LIMIT: int = 10         # 키워드 커버리지 상위 결과 수

    # 해시 토큰 설정
    FILE_REF_HASH_LENGTH: int = 10           # 파일 참조 해시 토큰 길이


@dataclass(frozen=True)
class QueryParserConfig:
    """쿼리 파서 관련 상수 (query_parser.py용)"""

    # 연도 파싱
    YEAR_MIN: int = 1900                     # 연도 유효 범위 하한
    YEAR_MAX: int = 2100                     # 연도 유효 범위 상한
    TWO_DIGIT_YEAR_WINDOW: int = 20          # 2자리 연도 해석 윈도우

    # 한국 이름 길이
    NAME_MIN_LENGTH: int = 2                 # 한국 이름 최소 길이
    NAME_MAX_LENGTH: int = 4                 # 한국 이름 최대 길이

    # 퍼지 매칭
    FUZZY_MAX_CHECKS: int = 50               # 퍼지 매칭 최대 체크 수
    FUZZY_LENGTH_DIFF_MAX: int = 1           # 허용 길이 차이
    JAMO_SIMILARITY_THRESHOLD: float = 0.80  # 자모 유사도 1차 컷 임계값
    FUZZY_MATCH_THRESHOLD: float = 0.87      # 퍼지 매칭 최종 임계값


@dataclass(frozen=True)
class ParallelExecutorConfig:
    """병렬 실행기 관련 상수 (parallel_executor.py용)"""

    DEFAULT_MAX_WORKERS: int = 6             # 기본 병렬 워커 수
    FALLBACK_TIMEOUT_SEC: float = 5.0        # 경쟁 실행 기본 타임아웃 (초)


@dataclass(frozen=True)
class DocumentUtilsConfig:
    """문서 유틸리티 관련 상수 (document_utils.py용)"""

    # 텍스트 길이 제한
    FULL_TEXT_MAX_LENGTH: int = 5000         # 전체 텍스트 최대 길이
    CHUNK_TEXT_MAX_LENGTH: int = 5000        # 청크 텍스트 최대 길이
    CONTEXT_MAX_LENGTH: int = 6000           # 최종 컨텍스트 최대 길이

    # OCR 설정
    OCR_MIN_VALID_LENGTH: int = 50           # OCR 최소 유효 텍스트 길이

    # 검색 설정
    FALLBACK_SEARCH_TOP_K: int = 20          # 폴백 검색 상위 결과 수
    SUMMARY_SEARCH_TOP_K: int = 10           # 요약용 검색 상위 결과 수
    MAX_CHUNKS_COUNT: int = 10               # 최대 청크 수


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
    "APIConfig",
    "CacheConfig",
    "ContextHydratorConfig",
    "DBConfig",
    "DoctypeConfig",
    "DocumentUtilsConfig",
    "DocumentHandlerConfig",
    "ExactMatchConfig",
    "FinanceExtractorConfig",
    "HandlerConfig",
    "HybridRetrieverConfig",
    "HybridSearchConfig",
    "JsonUtilsConfig",
    "LLMConfig",
    "MergeExtractorConfig",
    "MetaParserConfig",
    "MetricsConfig",
    "OCRConfig",
    "ParallelExecutorConfig",
    "PersistentCacheConfig",
    "PipelineConfig",
    "QueryExpanderConfig",
    "QueryParserConfig",
    "QueryRoutingConfig",
    "ResponseBuilderConfig",
    "RouterConfig",
    "RoutingMonitorConfig",
    "ScoringConfig",
    "SearchConfig",
    "SummaryTemplateConfig",
    "TableParserConfig",
    "get_llm_config",
    "get_search_config",
]
