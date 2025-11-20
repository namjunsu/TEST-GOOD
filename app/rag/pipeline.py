"""RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

import base64
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from app.core.errors import ERROR_MESSAGES, ErrorCode, ModelError, SearchError
from app.core.logging import get_logger
from app.prompts.document_prompts import (
    build_detailed_prompt,
    build_qa_prompt,
    build_section_prompt,
    build_summary_prompt,
)
from app.rag.cache_manager import cache_query_result, get_cache_stats, get_cached_result
from app.rag.domain_synonyms import expand_for_strict_content
from app.rag.persistent_cache import cache_query_result_persistent, get_cached_result_persistent
from app.rag.query_router import QueryMode, QueryRouter
from app.utils.sqlite_helpers import connect_metadata
from app.utils.text_normalizer import detect_section, is_detailed_mode, normalize_query

logger = get_logger(__name__)


# ============================================================================
# 라우팅 헬퍼 함수들 (스몰토크/산술/도메인 키워드 감지)
# ============================================================================

import re

# 스몰토크 패턴 (전체 일치 또는 문장 단독 위주)
SMALLTALK_PATTERNS = {
    'hi', 'hello', 'hey',
    '안녕', '안녕하세요', '안녕하십니까',
    '감사', '고마워', '감사합니다', '고마워요',
    'thanks', 'thank you',
    'bye', 'goodbye', '잘가', '안녕히',
}

# 도메인 키워드 (장비/프로젝트/기술 용어)
DOMAIN_KEYWORDS = {
    # 장비
    'nvr', 'sync', 'eco8000', 'lvm-180a', 'odin', 'vmix', 'faiss',
    'tri-level', 'sdi', 'lut', 'intercom', 'di box', 'dibox',
    '무선마이크', '마이크', '카메라', '렌즈', '삼각대', '케이블',
    '건전지', '배터리', '소모품', '장비', '중계차',
    # 프로젝트/프로그램
    '돌직구쇼', '뉴스', '스튜디오', '광화문', '오픈스튜디오',
    '중계', '방송', '채널에이',
    # 기술/문서
    '기안서', '구매', '수리', '교체', '검토', '기술검토',
    '오버홀', '도입', '노후화', '단종',
    '작성', '작성된', '문서', '리스트', '목록',
    # 작성자 (실제 기안자 이름)
    '최새름', '유인혁', '남준수', '박준서', '이원구',
    '최정은', '한건희', '김경현', '김수연', '김창수', '송경원',
}


def clean_ui_metadata(query: str) -> str:
    """UI에서 복사한 메타데이터 태그 제거 (🏷, 📅, ✍ 등)

    예시:
        입력: "2024 중계차 🏷 pdf · 📅 2024-10-24 · ✍ 문서 내용 요약해 줘"
        출력: "2024 중계차 문서 내용 요약해 줘"
    """
    import re

    # 원본 보존 (디버깅용)
    original = query

    # 패턴 1: 🏷 [텍스트] · 형태 제거
    query = re.sub(r'🏷[^·]+·\s*', '', query)

    # 패턴 2: 📅 [날짜] · 형태 제거
    query = re.sub(r'📅[^·]+·\s*', '', query)

    # 패턴 3: ✍ [텍스트] (마지막 항목, · 없음)
    query = re.sub(r'✍[^·]+', '', query)

    # 패턴 4: "pdf", "해 줘" 같은 불필요한 확장자 언급 제거
    query = re.sub(r'\s+pdf\s+', ' ', query)

    # 연속 공백 정리
    query = re.sub(r'\s+', ' ', query).strip()

    # 변경사항이 있으면 로그 출력
    if query != original:
        logger.info(f"🧹 UI 메타데이터 제거: '{original[:60]}...' → '{query[:60]}...'")

    return query


def route_query(query: str) -> Dict[str, Any]:
    """쿼리 라우팅: 모드/섹션/프롬프트/리트리버 파라미터 결정

    우선순위:
        1. 상세 모드 (detailed_mode) - 최우선
        2. 섹션 고정 (detected_section)
        3. 요약 모드 (needs_summary)
        4. 기본 Q&A 모드

    Args:
        query: 사용자 질의

    Returns:
        dict: {
            "mode": "DETAILED|SECTION|SUMMARY|QA",
            "prompt_type": 프롬프트 타입,
            "max_tokens": LLM 생성 토큰 수,
            "retriever_params": {
                "top_k": int,
                "chunk_merge": bool,
                "max_context_tokens": int
            },
            "detailed_mode": bool,
            "detected_section": str | None,
            "needs_summary": bool
        }
    """
    # 1) 정규화
    nq = normalize_query(query)

    # 2) 모드/섹션 판단 (상세 모드 우선권)
    detailed = is_detailed_mode(nq)
    section = detect_section(nq)

    # 3) 요약 트리거 (섹션 미지정 & 상세 모드 아님일 때만)
    needs_summary = False
    if not section and not detailed:
        # "내용" 단독은 제외, "요약", "summary" 등 명시적 키워드만
        if any(k in nq for k in ["요약", "summary", "한줄", "한 문장"]):
            needs_summary = True

    # 4) 리트리버 파라미터 (상세 모드 시 상향)
    retriever_params = {
        "top_k": 8 if detailed else 5,
        "chunk_merge": True if detailed else False,
        "max_context_tokens": 3200 if detailed else 2000,
    }

    # 5) 프롬프트/토큰
    if detailed:
        mode = "DETAILED"
        prompt_type = "detailed"
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_DETAILED", "1500"))
    elif section:
        mode = "SECTION"
        prompt_type = "section"
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SECTION", "900"))
    elif needs_summary:
        mode = "SUMMARY"
        prompt_type = "summary"
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SUMMARY", "600"))
    else:
        mode = "QA"
        prompt_type = "qa"
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_QA", "800"))

    logger.info(
        f"🎯 라우팅 결정: mode={mode}, detailed={detailed}, section={section}, "
        f"summary={needs_summary}, top_k={retriever_params['top_k']}, "
        f"max_tokens={max_tokens}"
    )

    return {
        "mode": mode,
        "prompt_type": prompt_type,
        "max_tokens": max_tokens,
        "retriever_params": retriever_params,
        "detailed_mode": detailed,
        "detected_section": section,
        "needs_summary": needs_summary,
    }


def is_smalltalk(query: str) -> bool:
    """스몰토크/인사/감탄사 감지 (전체 일치 또는 정규식)"""
    s = query.strip().lower()

    # 1. 직접 패턴 일치 (전체 문장이 스몰토크)
    if s in SMALLTALK_PATTERNS:
        return True

    # 2. 정규식 패턴 (스몰토크만 포함, 구두점 허용)
    smalltalk_regex = r'^(안녕|안녕하세요|안녕하십니까|감사합니다?|고마워요?|thanks|thank you|hi|hello|hey|bye|goodbye|잘가|안녕히)[.!?\s]*$'
    if re.fullmatch(smalltalk_regex, s):
        return True

    return False


def is_simple_math(query: str) -> bool:
    """단순 산술 질의 감지 (예: 1+1은?, 2*3=?)"""
    q_stripped = query.strip()
    # 정규식: 숫자 연산자 숫자 (옵션: = 결과)
    math_pattern = r'^\s*\d+\s*[\+\-\*/]\s*\d+\s*(=\s*\d+)?\s*[은?]*\s*$'
    return bool(re.match(math_pattern, q_stripped))


def has_domain_keyword(query: str) -> bool:
    """도메인 키워드 포함 여부 확인"""
    q_lower = query.lower()
    for keyword in DOMAIN_KEYWORDS:
        if keyword in q_lower:
            return True
    return False


def get_query_token_count(query: str) -> int:
    """간이 토큰 카운트 (한글/영문/숫자/기호 분리)"""
    # 정규식: [한글 블록]+, [영문숫자하이픈]+를 각각 1토큰으로 계산
    tokens = re.findall(r'[A-Za-z0-9\-_/]+|[가-힣]+', query)
    return len(tokens)


def _norm_chunk_text(r: Dict[str, Any]) -> str:
    """청크 텍스트 정규화 (snippet/content/text 통일)"""
    return (r.get("snippet") or r.get("content") or r.get("text") or "").lower()


def get_keyword_coverage(query: str, results: list) -> int:
    """쿼리와 검색 결과 간 도메인 키워드 교집합 개수 계산

    Args:
        query: 사용자 질문
        results: 검색 결과 리스트

    Returns:
        교집합된 키워드 개수
    """
    q_lower = query.lower()
    # 쿼리에서 매칭된 키워드
    query_keywords = {kw for kw in DOMAIN_KEYWORDS if kw in q_lower}

    if not query_keywords:
        return 0

    # 검색 결과 청크에서 발견된 키워드 (상위 10개)
    found_keywords = set()
    for result in results[:10]:
        chunk_text = _norm_chunk_text(result)
        for kw in query_keywords:
            if kw in chunk_text:
                found_keywords.add(kw)

    return len(found_keywords)


def force_chat_mode(query: str) -> tuple[bool, str]:
    """강제 CHAT 모드 적용 여부 판단

    Returns:
        (should_force, reason)
    """
    # 1. 스몰토크
    if is_smalltalk(query):
        return True, "smalltalk"

    # 2. 단순 산술
    if is_simple_math(query):
        return True, "simple_math"

    # 3. 짧은 질의 (토큰 < 3) - 단, 도메인 키워드가 있으면 제외
    tokens = get_query_token_count(query)
    if tokens < 3 and not has_domain_keyword(query):
        return True, "short_query"

    return False, ""


def _encode_file_ref(filename: str) -> Optional[str]:
    """파일명을 토큰(해시)으로 변환 (보안 강화, 경로 노출 방지)

    Args:
        filename: 파일명

    Returns:
        doc:{hash} 형식 토큰 또는 None

    Note:
        - 경로를 base64로 노출하지 않고 해시 토큰 사용
        - 백엔드에서 /preview?ref=doc:xxx 로 검증 후 제공
    """
    import hashlib

    try:
        # 1. metadata.db에서 파일 존재 확인
        with connect_metadata() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT path FROM documents WHERE filename = ? LIMIT 1",
                (filename,)
            )
            result = cursor.fetchone()

        if result and result[0]:
            # 해시 토큰 생성 (filename 기준, 10자 단축)
            token = hashlib.sha1(filename.encode()).hexdigest()[:10]
            return f"doc:{token}"

        # 2. Fallback: docs 폴더 검색
        year_match = re.search(r'(\d{4})-', filename)
        if year_match:
            year = year_match.group(1)
            file_path = Path(f"docs/year_{year}") / filename
            if file_path.exists():
                token = hashlib.sha1(filename.encode()).hexdigest()[:10]
                return f"doc:{token}"

        # 3. Fallback2: docs 폴더 전체 검색
        docs_dir = Path("docs")
        if docs_dir.exists():
            for file_path in docs_dir.rglob(filename):
                if file_path.is_file():
                    token = hashlib.sha1(filename.encode()).hexdigest()[:10]
                    return f"doc:{token}"

    except Exception as e:
        logger.warning(f"ref 토큰 생성 실패: {filename} - {e}")

    return None

# 진단 모드 설정
DIAG_RAG = os.getenv("DIAG_RAG", "false").lower() == "true"
DIAG_LOG_LEVEL = os.getenv("DIAG_LOG_LEVEL", "INFO").upper()


# ============================================================================
# Request / Response 데이터 클래스
# ============================================================================


@dataclass
class RAGRequest:
    """RAG 요청 파라미터

    Attributes:
        query: 사용자 질문
        top_k: 검색 결과 개수
        compression_ratio: 컨텍스트 압축 비율 (0.0~1.0)
        use_hyde: HyDE 사용 여부
        temperature: LLM 생성 온도
    """

    query: str
    top_k: int = 5
    compression_ratio: float = 0.7
    use_hyde: bool = False
    temperature: float = 0.1


@dataclass
class RAGResponse:
    """RAG 응답 결과

    Attributes:
        answer: 생성된 답변
        source_docs: 참고 문서 목록 (하위 호환)
        evidence_chunks: Evidence용 정규화 청크 (권장)
        raw_results: 원본 검색 결과 (Evidence 최소 보장용)
        latency: 전체 실행 시간 (초)
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        metrics: 내부 지표 (검색/압축/생성 시간 등)
        diagnostics: 진단 정보 (DIAG_RAG=true일 때만 채워짐)
    """

    answer: str
    source_docs: List[str] = field(default_factory=list)
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)
    raw_results: List[Dict[str, Any]] = field(default_factory=list)
    latency: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)  # 진단 정보


# ============================================================================
# 프로토콜 정의 (의존성 역전)
# ============================================================================


class Retriever(Protocol):
    """검색 엔진 인터페이스"""

    def search(
        self,
        query: str,
        top_k: int,
        *,
        mode: str = "chat",
        selected_filename: Optional[str] = None,
        strict_content: bool = False,
    ) -> List[Dict[str, Any]]:
        """검색 수행 (정규화 스키마 반환)

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            mode: 검색 모드 ("chat", "doc_anchored" 등)
            selected_filename: 우선 검색할 문서명
            strict_content: 정밀 내용 검색 모드 (본문 일치만, 2025-11-19 추가)

        Returns:
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict
                }, ...
            ]
        """
        ...


class Compressor(Protocol):
    """컨텍스트 압축기 인터페이스"""

    def compress(
        self, chunks: List[Dict[str, Any]], ratio: float
    ) -> List[Dict[str, Any]]:
        """문서 압축

        Args:
            chunks: 원본 청크 목록 (정규화된 dict)
            ratio: 압축 비율

        Returns:
            압축된 청크 목록 (동일 스키마)
        """
        ...


class Generator(Protocol):
    """LLM 생성기 인터페이스"""

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        """답변 생성

        Args:
            query: 사용자 질문
            context: 참고 문서
            temperature: 생성 온도
            mode: 생성 모드 ("chat", "rag", "summarize") - 토큰 예산 제어

        Returns:
            생성된 답변
        """
        ...


# ============================================================================
# RAG 파이프라인 (파사드)
# ============================================================================


class RAGPipeline:
    """RAG 파이프라인 파사드

    검색 → 압축 → 생성을 단일 인터페이스로 제공.
    내부 구현은 Retriever/Compressor/Generator에 위임.

    Example:
        >>> pipeline = RAGPipeline()
        >>> response = pipeline.query("질문", top_k=5)
        >>> if response.success:
        ...     print(response.answer)
        ...     print(f"참고: {response.source_docs}")
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        compressor: Optional[Compressor] = None,
        generator: Optional[Generator] = None,
    ):
        """RAG 파이프라인 초기화

        Args:
            retriever: 검색 엔진 (None이면 기본 HybridRetriever 사용)
            compressor: 압축기 (None이면 기본 ContextCompressor 사용)
            generator: LLM 생성기 (None이면 기본 LlamaCppGenerator 사용)
        """
        self.retriever = retriever or self._create_default_retriever()
        self.compressor = compressor or self._create_default_compressor()
        self.generator = generator or self._create_default_generator()
        self.query_router = QueryRouter()  # 🎯 모드 라우터 초기화

        # 🔒 Closed-World Validation: 고유 기안자 캐싱
        self.known_drafters = self._load_known_drafters()

        logger.info(f"RAG Pipeline initialized (known_drafters: {len(self.known_drafters)}명)")

    def _load_full_text_if_short(self, filename: str, snippet: str) -> str:
        """스니펫이 짧으면 data/extracted에서 전체 텍스트 로드"""
        EXTRACTED_DIR = Path(os.getenv("EXTRACTED_DIR", "data/extracted"))
        MIN_SNIPPET_LEN = int(os.getenv("DOC_ANCHOR_MIN_SNIPPET", "1200"))

        if len(snippet) >= MIN_SNIPPET_LEN:
            return snippet

        # 파일명에서 확장자 제거 후 .txt 찾기
        stem = os.path.splitext(filename)[0]
        txt_path = EXTRACTED_DIR / f"{stem}.txt"

        if txt_path.exists():
            try:
                full_text = txt_path.read_text(encoding="utf-8", errors="ignore")
                logger.info(f"📄 DOC_ANCHORED: {filename} 전체 텍스트 로드 ({len(full_text)}자)")
                return full_text[:5000]  # 최대 5000자
            except Exception as e:
                logger.warning(f"⚠️ 전체 텍스트 로드 실패: {e}")

        return snippet

    def query(
        self,
        query: str,
        top_k: int = 5,
        compression_ratio: float = 0.7,
        use_hyde: bool = False,
        temperature: float = 0.1,
        selected_filename: Optional[str] = None,
    ) -> RAGResponse:
        """RAG 질의 (단일 진입점)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수
            compression_ratio: 압축 비율
            use_hyde: HyDE 사용 여부
            temperature: LLM 생성 온도
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

        Returns:
            RAGResponse: 답변 + 메타데이터
        """

        # 입력 검증
        if not query or not query.strip():
            return RAGResponse(
                answer="",
                success=False,
                error="빈 질문입니다",
            )

        start_time = time.perf_counter()
        metrics = {}
        diagnostics = {}  # 진단 정보 수집

        try:
            # 0. 검색 전 pre-routing: 장비 질의 감지 (DOC_ANCHORED 필터링용)
            # QueryRouter의 device term 감지 로직 활용 (공개 API 우선, fallback to 비공개)
            preliminary_mode = "chat"
            if hasattr(self, 'query_router'):
                has_device = (
                    getattr(self.query_router, "has_device_terms", None) or
                    getattr(self.query_router, "_has_device_terms", None)
                )
                if callable(has_device) and has_device(query):
                    preliminary_mode = "doc_anchored"
                    logger.info("🎯 검색 전 DOC_ANCHORED 모드 감지 (장비 용어)")

            # 1. 검색: 정규화된 청크(dict) 리스트 기대
            search_start = time.perf_counter()
            results = self.retriever.search(query, top_k, mode=preliminary_mode, selected_filename=selected_filename)
            metrics["search_time"] = time.perf_counter() - search_start

            # [검색 결과 Top-N 진단 로그]
            logger.info(f"RETRIEVE_TOPN mode={preliminary_mode}")
            for i, doc in enumerate(results[:10], 1):
                score = doc.get('score', 0.0)
                doc_id = doc.get('doc_id', 'unknown')
                snippet_preview = doc.get('snippet', '')[:60].replace('\n', ' ')
                logger.info(f"  #{i} score={score:.4f} doc={doc_id} preview={snippet_preview}...")

            # [DIAG] 검색 결과 진단
            if DIAG_RAG:
                diagnostics["retrieved_k"] = len(results)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

            if not results:
                logger.warning(f"No results found for query: {query[:50]}")
                if DIAG_RAG:
                    diagnostics["mode"] = "no_results"
                    diagnostics["generate_path"] = "fallback_no_context"

                # 검색 결과 없음 → CHAT 모드로 폴백
                metrics["mode"] = "chat"
                metrics["top_score"] = 0.0

                return RAGResponse(
                    answer="관련 문서가 검색되지 않았다.",
                    success=True,
                    latency=time.perf_counter() - start_time,
                    metrics=metrics,
                    diagnostics=diagnostics,
                )

            # 2. 압축: 청크 단위 유지(페이지/스니펫/메타 보존)
            compress_start = time.perf_counter()
            compressed = self.compressor.compress(results, compression_ratio)
            metrics["compress_time"] = time.perf_counter() - compress_start

            # [DIAG] 압축 후 진단
            if DIAG_RAG:
                diagnostics["after_compress_k"] = len(compressed)
                diagnostics["compression_ratio"] = compression_ratio
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 압축 완료: {len(results)} → {len(compressed)}개 문서"
                    )

            # 3. 생성: 모드 결정 → 컨텍스트 최적화 → 생성
            gen_start = time.perf_counter()

            # CRITICAL: Inject compressed chunks into generator for proper LLM context
            if hasattr(self.generator, "compressed_chunks"):
                self.generator.compressed_chunks = compressed
                logger.debug(
                    f"Injected {len(compressed)} compressed chunks into generator"
                )

            # [DIAG] 생성 전 컨텍스트 스냅샷
            if DIAG_RAG and DIAG_LOG_LEVEL == "DEBUG":
                for i, c in enumerate(compressed[:3], 1):  # 상위 3개만 로그
                    logger.debug(
                        f"[DIAG] Context[{i}]: doc_id={c.get('doc_id')}, "
                        f"filename={c.get('filename', 'N/A')}, "
                        f"page={c.get('page', 0)}, "
                        f"snippet={c.get('snippet', '')[:120]}..."
                    )

            # 🎯 STEP 1: QueryRouter 모드 분류 (DOC_ANCHORED 최우선 체크)
            # CRITICAL: 검색 결과를 고려한 지능형 라우팅
            route_decision = self.query_router.classify_mode_with_retrieval(query, results)
            router_reason = route_decision.reason
            query_mode = route_decision.mode  # Extract QueryMode enum
            logger.info(f"🔀 QueryRouter 분류: mode={query_mode.value}, reason={router_reason}")

            # 🎯 STEP 2: 모드 결정 로직
            # CRITICAL: Determine mode BEFORE context hydration to apply mode-aware context limits
            mode_env = os.getenv('MODE', 'AUTO').upper()
            top_score = results[0].get('score', 0.0) if results else 0.0
            metrics["top_score"] = top_score

            if mode_env == 'AUTO':
                # ━━━ 1. 강제 CHAT 모드 체크 (스몰토크/산술/짧은 질의) ━━━
                should_force, force_reason = force_chat_mode(query)
                if should_force:
                    metrics["mode"] = "chat"
                    metrics["force_chat_reason"] = force_reason
                    logger.info(f"🎯 AUTO 모드: CHAT 강제 적용 (이유: {force_reason})")
                else:
                    # ━━━ 2. 도메인 키워드 + 절대값 임계값 기반 판단 ━━━
                    has_keyword = has_domain_keyword(query)
                    token_count = get_query_token_count(query)

                    # 환경변수에서 절대값 임계값 읽기
                    use_absolute = os.getenv('RAG_MIN_SCORE_POLICY', 'normalized') == 'absolute'
                    bm25_min = float(os.getenv('BM25_MIN_ABS', '5.0'))
                    vec_min = float(os.getenv('VEC_MIN_ABS', '0.25'))

                    # 절대값 정책 사용 시 (권장)
                    if use_absolute:
                        # 실제 BM25/벡터 스코어를 results에서 추출 시도
                        # (현재는 fused score만 있으므로 간소화)
                        # 일단 top_score를 벡터 스코어로 간주
                        pass_abs_threshold = top_score >= vec_min
                        pass_domain = has_keyword
                        pass_length = token_count >= 4

                        # 🔒 Coverage Gate: 검색 결과에서 실제로 키워드가 발견되는지 확인
                        keyword_coverage = get_keyword_coverage(query, results)
                        min_coverage = int(os.getenv('MIN_KEYWORD_COVERAGE', '2'))
                        pass_coverage = keyword_coverage >= min_coverage

                        should_use_rag = pass_abs_threshold and pass_domain and pass_length and pass_coverage
                        metrics["mode"] = "rag" if should_use_rag else "chat"
                        metrics["keyword_coverage"] = keyword_coverage

                        logger.info(
                            f"🎯 AUTO 모드 (절대값): top_score={top_score:.3f}, "
                            f"has_keyword={has_keyword}, token_count={token_count}, "
                            f"coverage={keyword_coverage}/{min_coverage}, "
                            f"threshold={vec_min}, selected_mode={metrics['mode']}"
                        )
                    else:
                        # 기존 정규화 정책 (fallback)
                        rag_min_score = float(os.getenv('RAG_MIN_SCORE', '0.35'))
                        metrics["mode"] = "rag" if top_score >= rag_min_score else "chat"
                        logger.info(
                            f"🎯 AUTO 모드 (정규화): top_score={top_score:.3f}, "
                            f"threshold={rag_min_score}, selected_mode={metrics['mode']}"
                        )

            elif mode_env == 'CHAT':
                metrics["mode"] = "chat"
                metrics["top_score"] = 0.0
            else:  # RAG, SUMMARIZE
                metrics["mode"] = "rag"
                metrics["top_score"] = results[0].get('score', 0.0) if results else 0.0

            # 🎯 STEP 2: 모드 기반 컨텍스트 최적화
            determined_mode = metrics.get("mode", "rag")
            logger.info(f"🎯 모드={determined_mode} → 컨텍스트 최적화 시작")

            # Context Hydrator with mode-aware optimization (폴백 보장)
            try:
                from app.rag.utils.context_hydrator import hydrate_context
            except Exception as e:
                logger.warning(f"⚠️ hydrate_context import 실패, 폴백 사용: {e}")
                def hydrate_context(chunks, max_len=10000, mode="rag"):
                    """안전 폴백: 청크 스니펫 결합"""
                    parts = []
                    for c in chunks:
                        t = (c.get("snippet") or c.get("content") or c.get("text") or "")
                        if t:
                            parts.append(t[:800])
                    ctx = "\n\n".join(parts)[:max_len]
                    return ctx, {"fallback": True, "joined": len(parts)}

            hydrate_start = time.perf_counter()
            context, hydrator_metrics = hydrate_context(compressed, max_len=10000, mode=determined_mode)
            metrics["hydrate_time"] = time.perf_counter() - hydrate_start
            # Merge hydrator metrics into main metrics
            metrics.update({f"ctx_{k}": v for k, v in hydrator_metrics.items()})

            # 🎯 STEP 3: 생성 (모드별 토큰 예산 적용)
            logger.info(f"🎯 모드={determined_mode} → 생성 시작")
            llm_gen_start = time.perf_counter()
            answer = self.generator.generate(query, context, temperature, mode=determined_mode)
            metrics["generate_time"] = time.perf_counter() - llm_gen_start

            # [DIAG] 생성 완료 진단
            if DIAG_RAG:
                diagnostics["mode"] = "normal"
                diagnostics["generate_path"] = "from_context"
                diagnostics["used_k"] = len(compressed)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용"
                    )

            total_latency = time.perf_counter() - start_time
            metrics["total_time"] = total_latency

            # 🚨 성능 가드: 슬로 쿼리 임계값 체크
            if total_latency > 10.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>10s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...' | "
                    f"search={metrics['search_time']:.2f}s, "
                    f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                    f"generate={metrics['generate_time']:.2f}s"
                )
            elif total_latency > 3.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>3s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...'"
                )

            logger.info(
                f"RAG query completed in {total_latency:.2f}s "
                f"(search={metrics['search_time']:.2f}s, "
                f"compress={metrics['compress_time']:.2f}s, "
                f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                f"generate={metrics['generate_time']:.2f}s)"
            )

            # CHAT 모드일 경우 출처 제거 (일반 대화는 문서 인용 불필요)
            # "전부" 또는 "개수" 질의 감지 시 출처도 더 많이 표시
            max_sources = 200 if any(kw in query.lower() for kw in ["전부", "모두", "모든", "전체", "all", "몇", "개수", "총"]) else 3
            final_source_docs = [] if determined_mode == "chat" else [c.get("doc_id") for c in results[:max_sources]]
            final_evidence_chunks = [] if determined_mode == "chat" else compressed

            return RAGResponse(
                answer=answer,
                source_docs=final_source_docs,
                evidence_chunks=final_evidence_chunks,  # UI용 근거
                raw_results=results,  # Evidence 최소 보장용
                latency=total_latency,
                success=True,
                metrics=metrics,
                diagnostics=diagnostics,
            )

        except SearchError as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_RETRIEVE] 검색 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except ModelError as e:
            logger.error(f"Model inference failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_GENERATE] 생성 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_UNKNOWN] {str(e)}",
                latency=time.perf_counter() - start_time,
            )

    def _make_response(
        self, text: str, selected: List[Dict[str, Any]], retrieved: List[Dict[str, Any]]
    ) -> dict:
        """표준 응답 구조 생성 (citations 포함)

        Args:
            text: 생성된 답변 텍스트
            selected: 실제 사용된 청크 리스트 (압축 후)
            retrieved: 검색된 원본 결과 리스트

        Returns:
            표준화된 응답 dict (citations 필수)
        """
        citations = []
        for c in selected:
            filename = c.get("filename") or c.get("doc_id") or c.get("title", "")
            ref = _encode_file_ref(filename) if filename else None

            citations.append({
                "doc_id": c.get("doc_id"),
                "filename": filename,
                "title": c.get("title") or filename or c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": (
                    c.get("text") or c.get("snippet") or c.get("content") or ""
                )[:400],
                "ref": ref,  # 🔴 base64 인코딩된 파일 경로
                "preview_url": c.get("preview_url"),
                "download_url": c.get("download_url"),
            })

        return {
            "text": text,
            "citations": citations,  # 🔴 표준 키 (필수)
            "evidence": citations,  # 하위 호환성 (동일 데이터)
            "status": {
                "retrieved_count": len(retrieved),
                "selected_count": len(selected),
                "found": len(selected) > 0,  # 🔴 유일한 판정 기준
            },
        }

    def answer(self, query: str, top_k: Optional[int] = None, selected_filename: Optional[str] = None) -> dict:
        """답변 생성 (Evidence 포함 구조화된 응답)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수 (None이면 기본값 5)
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

        Returns:
            dict: {
                "text": 답변 텍스트,
                "citations": 참고 문서 목록 (표준 키),
                "evidence": 참고 문서 목록 (하위 호환),
                "status": {
                    "retrieved_count": int,
                    "selected_count": int,
                    "found": bool
                }
            }
        """
        # ✨ 2-tier Cache check - 메모리 캐시 → 영구 캐시
        cache_key = f"{query}:{selected_filename}" if selected_filename else query

        # Tier 1: 메모리 캐시 확인 (가장 빠름)
        cached_result = get_cached_result(cache_key)
        if cached_result:
            logger.info(f"🎯 Memory Cache HIT! Returning cached result for query: {query[:50]}...")
            if "status" in cached_result:
                cached_result["status"]["from_cache"] = "memory"
            return cached_result

        # Tier 2: 영구 캐시 확인 (서버 재시작 후에도 유지)
        cached_result = get_cached_result_persistent(cache_key)
        if cached_result:
            logger.info(f"💾 Persistent Cache HIT! Returning cached result for query: {query[:50]}...")
            # 영구 캐시에서 가져온 결과를 메모리 캐시에도 저장 (다음 접근을 위해)
            cache_query_result(cache_key, cached_result)
            if "status" in cached_result:
                cached_result["status"]["from_cache"] = "persistent"
            return cached_result

        # 🚀 조기 단락: 선택된 문서가 있으면 즉시 DOCUMENT 모드로 처리
        # 검색·라우팅·압축 단계 완전 생략 → 성능 향상 (20~60% 지연시간 감소)
        if selected_filename:
            logger.info(f"⚡ 선택된 문서({selected_filename}) 감지 → 즉시 DOCUMENT 모드 실행 (검색 스킵)")
            # 파일명 정규화 (NFKC, 공백 정규화, 대소문자 통일)
            import unicodedata
            normalized_filename = unicodedata.normalize("NFKC", selected_filename).strip()
            normalized_filename = re.sub(r'\s+', ' ', normalized_filename)

            # UI 메타데이터 제거
            actual_query = clean_ui_metadata(query)

            # 확장 쿼리에서 실제 질문 추출
            if "현재 질문:" in actual_query:
                parts = actual_query.split("현재 질문:")
                if len(parts) > 1:
                    actual_query = parts[-1].strip()

            result = self._answer_document(actual_query, selected_filename=normalized_filename)

            # 결과 캐싱
            cache_query_result(cache_key, result)
            cache_query_result_persistent(cache_key, result)

            return result

        # 🔥 CRITICAL: 기안자/날짜 검색은 QuickFixRAG에 위임 (전문 로직 보유)
        if hasattr(self.generator, "rag"):
            import sqlite3

            # ✅ 확장된 쿼리에서 실제 질문 추출 (chat_interface.py 대응)
            actual_query = query
            if "현재 질문:" in query:
                parts = query.split("현재 질문:")
                if len(parts) > 1:
                    actual_query = parts[-1].strip()
                    logger.info(f"📝 확장 쿼리에서 추출: '{actual_query[:50]}'")

            # 🧹 UI 메타데이터 제거 (🏷 pdf · 📅 2024-10-24 · ✍ 등)
            actual_query = clean_ui_metadata(actual_query)

            # 🔍 쿼리에서 문서명 추출 (사용자가 직접 타이핑한 경우)
            # 패턴: "문서제목 이 문서/해당 문서 ..."
            if not selected_filename:
                doc_ref_pattern = r'^(.+?)\s+(이\s?문서|해당\s?문서|이문서)'
                match = re.match(doc_ref_pattern, actual_query, re.IGNORECASE)
                if match:
                    candidate_title = match.group(1).strip()
                    # 날짜 패턴 제거 (예: "2025-01-09_광화문_스튜디오..." → "광화문_스튜디오...")
                    candidate_title = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[-_]', '', candidate_title)

                    # metadata_db에서 제목으로 문서 검색
                    from app.data.metadata_db import MetadataDB
                    db = MetadataDB()
                    try:
                        # 제목 정규화 (특수문자, 공백 처리)
                        normalized_title = candidate_title.replace('_', ' ').replace('&', '').strip()

                        # DB에서 제목 유사도 검색 (LIKE 패턴)
                        conn = db.conn
                        cursor = conn.cursor()
                        query_sql = """
                            SELECT filename, title FROM documents
                            WHERE title LIKE ? OR filename LIKE ?
                            ORDER BY
                                CASE
                                    WHEN title = ? THEN 1
                                    WHEN title LIKE ? THEN 2
                                    ELSE 3
                                END
                            LIMIT 1
                        """
                        like_pattern = f"%{normalized_title}%"
                        cursor.execute(query_sql, (like_pattern, like_pattern, candidate_title, f"{candidate_title}%"))
                        result = cursor.fetchone()

                        if result:
                            selected_filename = result[0]
                            logger.info(f"📌 쿼리에서 문서명 추출: '{candidate_title}' → '{selected_filename}'")
                    except Exception as e:
                        logger.warning(f"문서명 추출 중 오류 (무시): {e}")

            # 🎯 모드 라우팅: Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모드 우선
            route_decision = self.query_router.classify_mode(actual_query)

            # 🔧 selected_filename이 있으면 무조건 DOCUMENT 모드로 전환 (우선순위 최상위)
            # 문서가 선택된 상태에서는 모든 질문에 대해 LLM이 해당 문서 기반으로 답변
            if selected_filename:
                logger.info(f"🎯 선택된 문서({selected_filename}) 감지 → DOCUMENT 모드로 강제")
                route_decision.mode = QueryMode.DOCUMENT
                route_decision.reason = "selected_doc"

            # 🔧 요약 의도 + 쿼리에 날짜/문서명 패턴이 있으면 DOCUMENT 모드로 강제
            has_summary_intent = self.query_router.SUMMARY_INTENT_PATTERN.search(actual_query) or "내용" in actual_query.lower()
            has_date_pattern = re.search(r'\d{4}[-_]\d{2}[-_]\d{2}', actual_query)  # 2025-06-10 형식

            if has_summary_intent and has_date_pattern and not selected_filename:
                logger.info(f"🎯 요약 의도 + 날짜 패턴 감지 → DOCUMENT 모드로 강제")
                route_decision.mode = QueryMode.DOCUMENT
                route_decision.reason = "summary_with_date_pattern"

            logger.info(
                f"🔀 라우팅 결과: mode={route_decision.mode.value}, reason={route_decision.reason}"
            )

            # 💰 COST 모드: 비용 합계 직접 조회
            if route_decision.mode == QueryMode.COST:
                return self._answer_cost_sum(actual_query)

            # 📄 DOCUMENT 모드: 문서 내용/요약 (통합: PREVIEW + SUMMARY)
            if route_decision.mode == QueryMode.DOCUMENT:
                return self._answer_document(actual_query, selected_filename=selected_filename)

            # 🔍 SEARCH 모드: 문서 검색 (통합: LIST + SEARCH + LIST_FIRST)
            if route_decision.mode == QueryMode.SEARCH:
                return self._answer_search(actual_query)

            # 🎯 SEARCH_CONTENT_ONLY 모드: 정밀 내용 검색 (2025-11-19 추가)
            if route_decision.mode == QueryMode.SEARCH_CONTENT_ONLY:
                return self._answer_search_content_only(actual_query)

            # 🔍 디버깅: 실제 pattern matching 대상 로깅
            logger.info(f"🔍 Pattern matching 대상 쿼리: '{actual_query[:100]}'")

            # ✅ P0: 파일명 직접 언급 패턴 감지 (레거시 호환, PREVIEW 모드 외)
        # 일반 쿼리는 기존 로직 사용
        response = self.query(query, top_k=top_k or 5, selected_filename=selected_filename)

        if response.success:
            # 검색/압축에서 넘어온 정규화 청크 사용 (실제 page/snippet/meta 노출)
            evidence = [
                {
                    "doc_id": c.get("doc_id"),
                    "page": c.get("page", 1),
                    "snippet": c.get("snippet", ""),
                    "meta": c.get(
                        "meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}
                    ),
                }
                for c in (response.evidence_chunks or [])
            ]

            # CRITICAL: Evidence 최소 보장 (sources_cited가 비어도 검색 결과는 표시)
            evidence_injected = False
            if not evidence and response.raw_results:
                logger.info("Evidence empty, using raw_results[:3] as fallback")
                evidence = [
                    {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "page": 0,  # 검색 결과는 페이지 정보 없음
                        "snippet": r.get("snippet") or r.get("text_preview", "")[:400],  # 500 → 400 (스니펫 일관성)
                        "meta": {
                            "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                            "filename": r.get("filename", ""),
                            "page": 0,
                        },
                    }
                    for r in response.raw_results[:3]
                ]
                evidence_injected = True

            # [DIAG] Evidence 진단 정보 추가
            if DIAG_RAG and response.diagnostics:
                response.diagnostics["evidence_count"] = len(evidence)
                response.diagnostics["evidence_injected"] = evidence_injected

            # 🔥 CRITICAL: status.found 플래그 - UI 판정 단일 소스
            # retrieved_count: 검색된 원본 결과 수
            # selected_count: 실제 사용된 증거 수 (evidence)
            # found: 검색 성공 여부 (evidence가 1개 이상이면 True)
            status = {
                "retrieved_count": len(response.raw_results or []),
                "selected_count": len(evidence),
                "found": len(evidence) > 0,  # 🔴 유일한 판정 기준
            }

            # 운영 표준 1행 요약 로그 (필수)
            author_mode = bool(re.search(r"(작성자|기안자|제안자)", query))
            search_ms = int(response.metrics.get("search_time", 0) * 1000)
            generate_ms = int(response.metrics.get("generate_time", 0) * 1000)
            total_ms = int(response.latency * 1000)

            logger.info(
                f'[RAG] query="{query[:50]}..." | '
                f"retrieved={status['retrieved_count']} | "
                f"selected={status['selected_count']} | "
                f"found={status['found']} | "
                f"author_mode={author_mode} | "
                f"backfill={evidence_injected} | "
                f"search_ms={search_ms} | "
                f"generate_ms={generate_ms} | "
                f"total_ms={total_ms}"
            )

            result = {
                "text": response.answer,
                "citations": evidence,  # 🔴 표준 키 (필수)
                "evidence": evidence,  # 하위 호환성 (동일 데이터)
                "status": status,  # UI에서 이것만 확인
                "diagnostics": response.diagnostics if DIAG_RAG else {},
            }

            # ✨ Cache the successful result to both tiers
            cache_key = f"{query}:{selected_filename}" if selected_filename else query
            cache_query_result(cache_key, result)  # Memory cache
            cache_query_result_persistent(cache_key, result)  # Persistent cache
            logger.info(f"📝 Cached result to memory + persistent storage for query: {query[:50]}...")

            return result
        else:
            # 에러 발생 시 (중립 톤, 사과 표현 금지)
            error_msg = ERROR_MESSAGES.get(
                ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다."
            )
            if response.error:
                error_msg = f"{error_msg}\n\n상세: {response.error}"

            # 운영 표준 로그 (에러 케이스)
            logger.error(
                f'[RAG] query="{query[:50]}..." | '
                f'status=ERROR | error="{response.error}"'
            )

            return {
                "text": error_msg,
                "citations": [],  # 🔴 표준 키 (필수)
                "evidence": [],  # 하위 호환성
                "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
            }

    def answer_text(self, query: str) -> str:
        """답변 텍스트만 반환 (하위 호환성)

        Args:
            query: 사용자 질문

        Returns:
            str: 생성된 답변 텍스트
        """
        result = self.answer(query)
        return result["text"]

    def _answer_search(self, query: str) -> dict:
        """문서 검색 (키워드 기반 BM25 검색, 상세 정보 포함)

        SEARCH 모드 핸들러로, 사용자의 키워드를 기반으로 관련 문서를 검색하고
        메타데이터(기안자, 날짜, 비용)와 함께 카드 형식으로 반환합니다.

        처리 흐름:
            1. 불용어 제거하여 검색 키워드 추출
            2. BM25 retriever로 상위 10개 문서 검색
            3. 각 문서의 메타데이터를 DB에서 조회
            4. 카드 형식으로 포맷팅 (제목, 기안자, 날짜, 비용, 미리보기)

        Args:
            query (str): 사용자 질의.
                예: "중계차 카메라 렌즈관련 문서 찾아줘"
                    "유인혁 기안서 문서 찾아줘"
                    "렌즈 오버홀 문서 있어?"

        Returns:
            dict: 표준 응답 구조
                {
                    "mode": "SEARCH",
                    "text": str,  # 포맷팅된 카드 목록
                    "files": list[str],  # 파일명 목록
                    "count": int,  # 검색된 문서 수
                    "citations": list[dict],  # Evidence 정보
                    "evidence": list[dict],  # 하위 호환용 (citations와 동일)
                    "status": {
                        "retrieved_count": int,
                        "selected_count": int,
                        "found": bool
                    }
                }

        Example:
            >>> pipeline._answer_search("중계차 카메라 문서 찾아줘")
            {
                "mode": "SEARCH",
                "text": "📄 **'중계차 카메라' 관련 문서 (3건)**\\n\\n1. **중계차 카메라 렌즈 오버홀**\\n   📋 기안서 | 📅 2024-03-15 | ✍ 유인혁\\n   💰 2,500,000원\\n   📝 Canon HJ40x10B 렌즈 오버홀...",
                "files": ["2024-03-15_중계차_카메라_렌즈_오버홀.pdf", ...],
                "count": 3,
                ...
            }

        Note:
            - 최대 10개 문서까지 반환
            - 불용어: "문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘"
            - 검색 실패 시 count=0, found=False 반환
        """
        import re

        from app.data.metadata_db import MetadataDB

        try:
            # 검색 키워드 추출 (불용어 제거)
            stop_words = ["문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘"]
            keywords = query
            for word in stop_words:
                keywords = keywords.replace(word, " ")
            keywords = keywords.strip()

            # 기안자명 추출 (쿼리에서 한글 이름 패턴 검색)
            drafter_filter = None
            # DB에서 자주 등장하는 기안자 목록 (추후 DB 조회로 개선 가능)
            common_drafters = ["남준수", "최새름", "유인혁", "이의주", "강병규", "박연수", "이호영", "이승헌"]
            for name in common_drafters:
                if name in query:
                    drafter_filter = name
                    logger.info(f"🔍 기안자 필터 적용: {drafter_filter}")
                    break

            logger.info(f"🔍 문서 검색: 키워드='{keywords}'{f' | 기안자={drafter_filter}' if drafter_filter else ''}")

            # "전부" 또는 "개수" 또는 "리스트" 질의 감지 - 검색 개수 조정
            # "몇개", "개수" 질의는 정확한 카운트를 위해 많은 문서를 검색해야 함
            # 타이핑 오류 대응: "몆" (U+BA86) 추가
            # 🔧 "리스트 보여줘" 의도나 기안자 필터가 있으면 검색 개수를 늘림
            needs_all = any(kw in query.lower() for kw in ["전부", "모두", "모든", "전체", "all", "몇", "몆", "개수", "총"])
            wants_list = any(kw in query.lower() for kw in ["리스트", "목록", "보여", "알려"])
            search_top_k = 200 if (needs_all or wants_list or drafter_filter) else 10  # 131개 문서도 커버하도록 200으로 증가
            logger.info(f"🔍 검색 top_k: {search_top_k} (needs_all={needs_all}, wants_list={wants_list}, has_drafter={bool(drafter_filter)})")

            # BM25 검색 실행
            if not hasattr(self.retriever, 'search'):
                logger.error("❌ Retriever에 search 메서드가 없습니다")
                return {
                    "mode": "SEARCH",
                    "text": "검색 기능을 사용할 수 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 하이브리드 검색 실행
            search_results = self.retriever.search(keywords, top_k=search_top_k)

            # 결과에서 파일명 추출 (중복 제거)
            filenames = []
            seen = set()
            for result in search_results:
                filename = result.get("filename") or result.get("doc_id")
                if filename and filename not in seen:
                    filenames.append(filename)
                    seen.add(filename)

            if not filenames:
                return {
                    "mode": "SEARCH",
                    "text": f"'{keywords}' 관련 문서를 찾지 못했습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 🔢 "총 몇개" 질문 감지 - 개수만 답하고 리스트 생략
            # 타이핑 오류 대응: "몆개" (잘못된 자모 조합) → "몇개"
            count_only_query = any(kw in query.lower() for kw in ["몇개", "몆개", "몇 개", "몆 개", "개수", "총", "몇", "몆"])

            # 각 문서의 메타데이터 조회
            db = MetadataDB()

            # 날짜 필터링 (연도 추출)
            year_filter = None
            year_match = re.search(r'(20\d{2})년?', query)
            if year_match:
                year_filter = year_match.group(1)
                logger.info(f"📅 연도 필터 적용: {year_filter}")

            # 기안자 + 날짜 필터로 정확한 개수 계산
            if count_only_query:
                conn = db._get_conn()
                sql = "SELECT COUNT(*) as cnt FROM documents WHERE 1=1"
                params = []

                if drafter_filter:
                    sql += " AND drafter = ?"
                    params.append(drafter_filter)

                if year_filter:
                    sql += " AND (date LIKE ? OR display_date LIKE ?)"
                    params.extend([f"{year_filter}%", f"{year_filter}%"])

                cursor = conn.execute(sql, params)
                total_count = cursor.fetchone()['cnt']

                # 개수만 답변
                drafter_text = f"{drafter_filter} " if drafter_filter else ""
                year_text = f"{year_filter}년 " if year_filter else ""

                return {
                    "mode": "SEARCH",
                    "text": f"{year_text}{drafter_text}문서는 총 **{total_count}개**입니다.",
                    "files": [],
                    "count": total_count,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": total_count,
                        "selected_count": 0,
                        "found": total_count > 0
                    }
                }

            doc_details = []

            # "전부" 또는 "개수" 또는 "리스트/목록" 질의 감지 - 최대 개수 조정
            # 🔧 기안자 필터가 있으면 더 많은 문서를 검색해야 함 (필터링으로 줄어들기 때문)
            wants_list = any(kw in query.lower() for kw in ["리스트", "목록", "보여", "알려", "전부", "모두", "모든", "전체", "all"])
            max_docs = 200 if wants_list or drafter_filter else 10

            for filename in filenames[:max_docs]:  # 최대 개수까지
                # DB에서 메타데이터 조회 (filename + 기안자 필터 + 날짜 필터)
                conn = db._get_conn()

                # SQL 쿼리 동적 생성 (필터 조건 추가)
                sql = "SELECT * FROM documents WHERE filename = ?"
                params = [filename]

                if drafter_filter:
                    sql += " AND drafter = ?"
                    params.append(drafter_filter)

                if year_filter:
                    sql += " AND (date LIKE ? OR display_date LIKE ?)"
                    params.extend([f"{year_filter}%", f"{year_filter}%"])

                sql += " LIMIT 1"
                cursor = conn.execute(sql, params)
                row = cursor.fetchone()

                if row:
                    doc = dict(row)
                    doc_details.append({
                        "filename": filename,
                        "drafter": doc.get("drafter", "작성자 미상"),
                        "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                        "doctype": doc.get("doctype", "문서"),
                        "claimed_total": doc.get("claimed_total"),
                        "text_preview": doc.get("text_preview", "")[:400]  # 100 → 400 (evidence snippet 확장)
                    })
                else:
                    # 기안자 필터가 적용된 경우, 매칭되지 않은 문서는 스킵
                    if drafter_filter:
                        logger.debug(f"🔍 기안자 필터로 제외: {filename}")
                        continue
                    # 메타데이터가 없는 경우 파일명만 표시 (필터 없을 때만)
                    doc_details.append({
                        "filename": filename,
                        "drafter": "작성자 미상",
                        "date": "날짜 없음",
                        "doctype": "문서",
                        "claimed_total": None,
                        "text_preview": ""
                    })

            # 응답 텍스트 포맷팅 (리팩토링 계획서의 형식 참고)
            cards = []
            for i, doc in enumerate(doc_details, 1):
                filename = doc["filename"]

                # 파일명에서 제목 추출
                title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
                title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
                title = title.replace('_', ' ')

                # 카드 생성
                card_lines = [f"{i}. **{title}**"]
                card_lines.append(f"   📋 {doc['doctype']} | 📅 {doc['date']} | ✍ {doc['drafter']}")

                # 비용 정보 추가 (있는 경우)
                if doc['claimed_total']:
                    card_lines.append(f"   💰 {doc['claimed_total']:,}원")

                # 미리보기 추가 (있는 경우)
                if doc['text_preview']:
                    # 마커 제거: [페이지 X], [OCR ...], 불필요한 공백
                    clean_text = re.sub(r'\[페이지\s*\d+\]', '', doc['text_preview'])
                    clean_text = re.sub(r'\[OCR[^\]]*\]', '', clean_text)
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

                    if clean_text:  # 정리 후 내용이 있으면 표시
                        preview = clean_text[:80]
                        card_lines.append(f"   📝 {preview}...")

                cards.append("\n".join(card_lines))

            # "몇개", "개수" 질의인지 확인
            is_count_query = any(kw in query.lower() for kw in ["몇개", "몇 개", "개수", "총", "count", "number"])

            if is_count_query:
                # 개수만 간단히 답변
                answer_text = f"**'{keywords}' 관련 문서는 총 {len(doc_details)}개**입니다.\n\n" + "\n\n".join(cards[:10])
                if len(cards) > 10:
                    answer_text += f"\n\n... 외 {len(cards) - 10}개 문서 (\"전부 보여줘\"를 입력하면 모든 문서를 볼 수 있습니다)"
            else:
                # 일반 검색 결과
                answer_text = f"📄 **'{keywords}' 관련 문서 ({len(doc_details)}건)**\n\n" + "\n\n".join(cards)

            # Evidence 구성
            evidence = []
            for doc in doc_details:
                filename = doc["filename"]

                # 실제 파일 경로 생성
                year_match = re.search(r'(\d{4})-', filename)
                if year_match:
                    year = year_match.group(1)
                    file_path_str = f"docs/year_{year}/{filename}"
                else:
                    file_path_str = f"docs/{filename}"

                # 제목 생성 (폴백용)
                title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
                title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
                title = title.replace('_', ' ')

                # Snippet 폴백 체인: text_preview → BM25 청크 → 제목
                snippet = doc.get("text_preview", "").strip()

                if not snippet:
                    # text_preview 없으면 BM25 인덱스에서 청크 가져오기
                    try:
                        chunks = self.retriever.search(filename, top_k=1)
                        if chunks:
                            chunk_text = _norm_chunk_text(chunks[0])
                            snippet = chunk_text[:400] if chunk_text else ""
                    except Exception as e:
                        logger.debug(f"⚠️ BM25 청크 폴백 실패 ({filename}): {e}")

                # 여전히 없으면 제목 사용
                if not snippet:
                    snippet = title[:160]

                evidence.append({
                    "doc_id": filename,
                    "filename": filename,
                    "file_path": file_path_str,
                    "page": 1,
                    "snippet": snippet[:400],  # 최대 400자
                    "ref": None,
                    "meta": {
                        "filename": filename,
                        "drafter": doc.get("drafter"),
                        "date": doc.get("date"),
                        "doctype": doc.get("doctype")
                    }
                })

            return {
                "mode": "SEARCH",
                "text": answer_text,
                "files": filenames,
                "count": len(doc_details),
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": len(doc_details),
                    "selected_count": len(doc_details),
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ 문서 검색 실패: {e}", exc_info=True)
            return {
                "mode": "SEARCH",
                "text": f"문서 검색 중 오류가 발생했습니다: {str(e)}",
                "files": [],
                "count": 0,
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _answer_search_content_only(self, query: str) -> dict:
        """정밀 내용 검색 (2025-11-19 추가)

        사용자가 "문서내용에 X 들어간 문서만" 같은 정밀 검색을 요청했을 때,
        QueryExpander/파일명 보너스/메타데이터 라우팅을 비활성화하고
        BM25 기반으로 본문에 실제로 키워드가 포함된 문서만 반환합니다.

        Args:
            query (str): 사용자 질의.
                예: "문서내용에 티비로직이 들어간 문서만"
                    "내용에 SPG9000 포함된 문서"
                    "본문에 ECO8000 있는 문서"

        Returns:
            dict: 표준 응답 구조
                {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": str,  # 포맷팅된 카드 목록
                    "files": list[str],  # 파일명 목록
                    "count": int,  # 검색된 문서 수
                    "citations": list[dict],  # Evidence 정보
                    "evidence": list[dict],  # 하위 호환용 (citations와 동일)
                    "status": {
                        "retrieved_count": int,
                        "selected_count": int,
                        "found": bool
                    }
                }
        """
        import re

        from app.data.metadata_db import MetadataDB

        try:
            # 검색 키워드 추출 (불용어 제거)
            # 2025-11-19: 단어 경계 고려 (젠하이저 → 젠하 저 방지)
            stop_words = ["문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘",
                          "내용", "본문", "들어간", "포함", "포함된", "있는", "만"]
            # 조사는 단어 경계에서만 제거 (앞뒤 공백/시작/끝 확인)
            postpositions = [" 에 ", " 에서 ", " 이 ", " 가 ", " 을 ", " 를 "]

            keywords = " " + query + " "  # 앞뒤 공백 추가
            for word in stop_words:
                keywords = keywords.replace(word, " ")
            for postposition in postpositions:
                keywords = keywords.replace(postposition, " ")
            keywords = keywords.strip()

            # 빈 키워드 검증 (2025-11-19: 안전장치)
            if not keywords:
                logger.warning("⚠️ 정밀 내용 검색: 불용어 제거 후 키워드가 비어있음")
                return {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": (
                        "⚠️ **정밀 내용 검색을 위해서는 검색할 키워드가 필요합니다.**\n\n"
                        "예시:\n"
                        "- 문서내용에 **티비로직** 들어간 문서만\n"
                        "- 내용에 **SPG9000** 포함된 문서\n"
                        "- 본문에 **ECO8000** 있는 문서만"
                    ),
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False,
                    },
                }

            # 🔧 도메인 동의어 확장 (2025-11-19 추가)
            # QueryExpander 없이도 브랜드/모델명의 한영/대소문자 변형 처리
            expanded_query = expand_for_strict_content(keywords)

            logger.info(f"🎯 정밀 내용 검색: raw='{keywords}', expanded='{expanded_query}'")

            # 🔥 CRITICAL: strict_content=True로 검색 (QueryExpander/파일명보너스 비활성화)
            if not hasattr(self.retriever, 'search'):
                logger.error("❌ Retriever에 search 메서드가 없습니다")
                return {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": "검색 기능을 사용할 수 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # strict_content=True로 정밀 검색 실행 (동의어 확장된 쿼리 사용)
            search_results = self.retriever.search(expanded_query, top_k=50, strict_content=True)

            if not search_results:
                logger.info("⚠️ 정밀 내용 검색 결과 없음")
                return {
                    "mode": "SEARCH_CONTENT_ONLY",
                    "text": f"📄 **'{keywords}' 관련 문서 (0건)**\n\n검색 결과가 없습니다.",
                    "files": [],
                    "count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # DB에서 메타데이터 조회 (중복 제거 포함)
            db = MetadataDB()
            doc_details = []

            # 파일명 중복 제거 (2025-11-19: 안전장치)
            filenames = []
            seen_filenames = set()
            for r in search_results:
                fname = r.get("filename")
                if not fname:
                    continue
                if fname in seen_filenames:
                    continue
                seen_filenames.add(fname)
                filenames.append(fname)

            for filename in filenames[:10]:  # 최대 10개
                conn = db._get_conn()
                cursor = conn.execute("SELECT * FROM documents WHERE filename = ? LIMIT 1", [filename])
                row = cursor.fetchone()

                if row:
                    doc = dict(row)
                    doc_details.append({
                        "filename": filename,
                        "title": doc.get("title", filename),
                        "category": doc.get("category", "기안서"),
                        "date": doc.get("display_date") or doc.get("date", "날짜 없음"),
                        "drafter": doc.get("drafter", "작성자 미상"),
                        "claimed_total": doc.get("claimed_total", 0),
                        "text_preview": doc.get("text_preview", "")[:100],
                        "path": doc.get("path", "")
                    })

            # 응답 포맷팅 (카드 형식)
            response_text = f"📄 **'{keywords}' 내용 포함 문서 ({len(doc_details)}건)**\n\n"

            for i, doc in enumerate(doc_details, 1):
                title = doc["title"] or doc["filename"]
                category_emoji = "📋" if "기안서" in doc["category"] else "📄"
                drafter_str = f"✍ {doc['drafter']}" if doc["drafter"] else ""
                date_str = f"📅 {doc['date']}" if doc["date"] else ""

                meta_parts = [p for p in [category_emoji + " " + doc["category"], date_str, drafter_str] if p]
                meta_line = " | ".join(meta_parts)

                response_text += f"**{i}.** {title}\n"
                if meta_line:
                    response_text += f"   {meta_line}\n"

                # 금액 표시
                if doc["claimed_total"]:
                    response_text += f"   💰 {doc['claimed_total']:,}원\n"

                # 미리보기
                if doc["text_preview"]:
                    response_text += f"   📝 {doc['text_preview']}...\n"

                response_text += "\n"

            # Evidence 구성
            citations = []
            for doc in doc_details:
                citations.append({
                    "doc_id": doc["filename"],
                    "filename": doc["filename"],
                    "page": 1,
                    "snippet": doc["text_preview"],
                    "file_path": doc["path"],
                    "meta": {
                        "filename": doc["filename"],
                        "date": doc["date"],
                        "drafter": doc["drafter"],
                        "category": doc["category"]
                    }
                })

            logger.info(f"✅ 정밀 내용 검색 완료: {len(doc_details)}건")

            return {
                "mode": "SEARCH_CONTENT_ONLY",
                "text": response_text,
                "files": filenames[:10],
                "count": len(doc_details),
                "citations": citations,
                "evidence": citations,
                "status": {
                    "retrieved_count": len(search_results),
                    "selected_count": len(citations),
                    "found": len(citations) > 0
                }
            }

        except Exception as e:
            logger.error(f"❌ 정밀 내용 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())

            return {
                "mode": "SEARCH_CONTENT_ONLY",
                "text": f"검색 중 오류가 발생했습니다: {str(e)}",
                "files": [],
                "count": 0,
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _answer_cost_sum(self, query: str) -> dict:
        """비용 합계 직접 조회 (DB claimed_total 활용, top-N 스캔 + 우선순위 정렬)

        Args:
            query: 사용자 질의 (예: "채널에이 중계차 보수 합계 얼마였지?")

        Returns:
            dict: 표준 응답 구조 (text, citations, evidence, status)
        """
        try:
            # 1. 검색으로 후보 문서 찾기 (3 → 15 확장)
            search_results = self.retriever.search(query, top_k=15)

            if not search_results:
                logger.warning(f"비용 질의 검색 실패: {query}")
                return {
                    "text": "관련 문서를 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 2. DB에서 claimed_total 수집 및 우선순위 정렬
            from app.data.metadata_db import MetadataDB
            db = MetadataDB()

            cost_docs = []  # (claimed_total, doc, filename) 튜플 리스트
            for result in search_results:
                filename = result.get("meta", {}).get("filename") or result.get("doc_id", "")
                if not filename:
                    continue

                doc = db.get_by_filename(filename)
                if doc and doc.get("claimed_total"):
                    cost_docs.append((doc["claimed_total"], doc, filename))

            if not cost_docs:
                # claimed_total 없는 경우
                logger.warning(f"검색된 문서에 비용 정보 없음: {[r.get('doc_id') for r in search_results]}")
                return {
                    "text": "검색된 문서에 비용 합계 정보가 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": len(search_results),
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 우선순위 정렬: 금액 큰 순 (내림차순)
            cost_docs.sort(key=lambda x: x[0], reverse=True)

            # 3. 답변 포맷팅 (복수 문서 지원)
            total_sum = sum(doc[0] for doc in cost_docs)
            evidence = []

            if len(cost_docs) == 1:
                # 단일 문서
                claimed_total, doc, filename = cost_docs[0]
                text_preview = doc.get("text_preview", "")
                vat_status = "VAT 별도" if "VAT" in text_preview or "부가세" in text_preview else "VAT 포함 추정"

                sum_match = doc.get("sum_match")
                if sum_match is None:
                    verification = "sum_match=없음"
                elif sum_match:
                    verification = "sum_match=일치 ✅"
                else:
                    verification = "sum_match=불일치 ⚠️"

                answer_text = f"💰 합계: **₩{claimed_total:,}** ({vat_status})\n"
                answer_text += f"출처: {filename} | 날짜: {doc.get('display_date') or doc.get('date') or '정보 없음'} | 기안자: {doc.get('drafter') or '정보 없음'}\n"
                answer_text += f"검증: {verification}"

                ref = _encode_file_ref(filename)
                evidence = [{
                    "doc_id": filename,
                    "filename": filename,
                    "page": 1,
                    "snippet": f"비용 합계: ₩{claimed_total:,}",
                    "ref": ref,
                    "meta": {
                        "filename": filename,
                        "drafter": doc.get("drafter"),
                        "date": doc.get("display_date") or doc.get("date"),
                        "claimed_total": claimed_total
                    }
                }]

                logger.info(f"💰 비용 질의 성공 (단일): {filename} → ₩{claimed_total:,}")

            else:
                # 복수 문서
                answer_text = f"💰 **총 {len(cost_docs)}건 문서 비용 합계: ₩{total_sum:,}**\n\n"
                answer_text += "**상세 내역:**\n"

                for i, (claimed_total, doc, filename) in enumerate(cost_docs[:10], 1):  # 최대 10건 표시
                    title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
                    title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
                    title = title.replace('_', ' ')

                    answer_text += f"{i}. {title}: ₩{claimed_total:,}\n"
                    answer_text += f"   📅 {doc.get('display_date') or doc.get('date') or '날짜 없음'} | ✍ {doc.get('drafter') or '정보 없음'}\n"

                    ref = _encode_file_ref(filename)
                    evidence.append({
                        "doc_id": filename,
                        "filename": filename,
                        "page": 1,
                        "snippet": f"비용 합계: ₩{claimed_total:,}",
                        "ref": ref,
                        "meta": {
                            "filename": filename,
                            "drafter": doc.get("drafter"),
                            "date": doc.get("display_date") or doc.get("date"),
                            "claimed_total": claimed_total
                        }
                    })

                if len(cost_docs) > 10:
                    answer_text += f"\n... 외 {len(cost_docs) - 10}건 (합계에 포함)"

                logger.info(f"💰 비용 질의 성공 (복수): {len(cost_docs)}건 → 총 ₩{total_sum:,}")

            return {
                "text": answer_text,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": len(search_results),
                    "selected_count": len(cost_docs),
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ 비용 질의 처리 실패: {e}", exc_info=True)
            return {
                "text": f"비용 정보 조회 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _answer_document(self, query: str, selected_filename: Optional[str] = None) -> dict:
        """문서 내용 조회 (DOCUMENT 모드: PREVIEW + SUMMARY 통합)

        DOC_ANCHORED 모드를 대체하여, 문서 전체 내용을 반환합니다.
        5개 필드만 추출하던 구조적 제한을 제거하고, 사용자가 요청한 문서의
        전체 텍스트를 제공합니다.

        Args:
            query: 사용자 질의 (예: "미러클랩 카메라 삼각대 기술검토서 이문서 내용 알려줘")
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

        Returns:
            dict: 표준 응답 구조 (전체 문서 텍스트 포함)

        Note:
            - 과거 DOC_ANCHORED의 5-field 추출 문제를 해결하기 위해 생성됨
            - 전체 문서 텍스트를 data/extracted/ 에서 직접 로드
            - LLM을 사용하지 않고 원문 그대로 반환
        """
        import re
        from pathlib import Path

        try:
            # 1. 문서 식별 (selected_filename 우선, 없으면 쿼리에서 추출)
            target_filename = None

            if selected_filename:
                logger.info(f"🎯 선택된 문서 우선 처리: {selected_filename}")
                target_filename = selected_filename
            else:
                # 쿼리에서 파일명 추출 시도
                # 예: "미러클랩 카메라 삼각대 기술검토서" → 검색으로 문서 찾기
                # 불용어 제거
                stopwords = ["이문서", "이 문서", "해당 문서", "내용", "알려줘", "알려",
                             "보여줘", "보여", "자세하게", "자세히", "요약", "정리"]
                keywords = query
                for word in stopwords:
                    keywords = keywords.replace(word, " ")
                keywords = " ".join(keywords.split())  # 공백 정리

                # .pdf 확장자가 있으면 직접 사용
                filename_match = re.search(r"(\S+\.pdf)", query, re.IGNORECASE)
                if filename_match:
                    target_filename = filename_match.group(1)
                    logger.info(f"📄 쿼리에서 파일명 추출: {target_filename}")
                else:
                    # 키워드로 검색
                    logger.info(f"🔍 키워드로 문서 검색: {keywords}")
                    search_results = self.retriever.search(keywords, top_k=1)

                    if search_results:
                        target_filename = search_results[0].get("meta", {}).get("filename") or search_results[0].get("doc_id", "")
                        logger.info(f"✅ 검색으로 문서 발견: {target_filename}")

            if not target_filename:
                return {
                    "text": "문서를 찾을 수 없습니다. 문서명을 명확히 입력해주세요.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 2. DB에서 메타데이터 조회
            with connect_metadata() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT filename, drafter, date, display_date, category, doctype
                    FROM documents
                    WHERE filename = ? OR filename LIKE ?
                    LIMIT 1
                    """,
                    (target_filename, f"%{target_filename}%"),
                )
                result = cursor.fetchone()

            if not result:
                return {
                    "text": f"'{target_filename}' 문서의 메타데이터를 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            filename, drafter, date, display_date, category, doctype = result

            # 3. data/extracted/ 에서 전체 텍스트 로드 (폴백 보장)
            extracted_dir = Path("data/extracted")
            txt_filename = filename.replace('.pdf', '.txt')
            txt_path = extracted_dir / txt_filename
            full_text = ""

            if txt_path.exists():
                # 전체 텍스트 읽기
                with open(txt_path, 'r', encoding='utf-8') as f:
                    full_text = f.read()
            else:
                # txt 파일 없음 → 인덱스 청크 기반 폴백
                logger.warning(f"⚠️ {txt_path} 없음, 인덱스 청크 폴백 시도")
                try:
                    chunks = self._make_chunks_for_doc(filename)
                    if chunks:
                        joined = "\n\n".join(
                            [(ch.get("text") or ch.get("snippet") or ch.get("content") or "")[:2000]
                             for ch in chunks]
                        )[:8000]
                        full_text = joined if joined else ""
                        logger.info(f"✅ 청크 {len(chunks)}개 결합 → {len(full_text)}자 확보")
                    else:
                        logger.warning(f"⚠️ {filename} 청크도 없음")
                except Exception as e:
                    logger.warning(f"⚠️ 청크 폴백 실패: {e}")

            if not full_text or len(full_text.strip()) < 10:
                return {
                    "text": f"'{filename}' 문서의 텍스트를 확보하지 못했습니다. (extracted txt, 인덱스 청크 모두 실패)",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 1,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 4. 섹션별 키워드 감지 (2025-11-10: 우선순위 최상위로 이동)
            # "개요 부분만", "검토 세부 내용" 등 특정 섹션 요청을 먼저 감지
            section_keywords = {
                '검토': ['검토', '검토내용', '검토 내용', '검토 세부', '리뷰', '검토의견', '검토 의견'],
                '배경': ['배경', '목적', '배경/목적', '추진배경', '추진 배경', '사유'],
                '개요': ['개요 부분', '개요만', '개요 세부'],  # "개요 부분만" 같은 명시적 요청만
                '비교': ['비교', '대안', '비교대안', '비교 대안', '방안', '옵션'],
                '선정': ['선정', '권고', '추천', '제안', '선정사유'],
                '내역': ['내역', '세부내역', '세부 내역', '상세내역', '상세'],
                '예산': ['예산', '비용', '금액', '합계', '총액']
            }

            detected_section = None
            detected_keywords = []
            for section, keywords in section_keywords.items():
                for kw in keywords:
                    if kw in query.lower():
                        detected_section = section
                        detected_keywords = keywords
                        break
                if detected_section:
                    break

            # 5. 라우팅 결정 (정규화 + 통합 로직)
            routing = route_query(query)
            detailed_mode = routing["detailed_mode"]
            detected_section = routing["detected_section"]  # 재할당 (기존 감지 로직 덮어쓰기)
            needs_summary = routing["needs_summary"]
            max_tokens = routing["max_tokens"]

            # 7. 답변 포맷팅
            answer_text = ""

            # LLM 답변 또는 원문
            # 문서가 선택된 상태에서는 항상 LLM을 사용하여 사용자 질문에 답변
            if len(full_text) > 500:
                logger.info(f"💬 문서 기반 LLM 답변 수행 (원문 {len(full_text)}자, 섹션={detected_section}, 요약모드={needs_summary}, 상세모드={detailed_mode})")
                try:
                    # 문서를 청크 형태로 구성
                    chunks = [{
                        "text": full_text[:4000],  # 최대 4000자
                        "snippet": full_text[:4000],
                        "content": full_text[:4000],
                        "filename": filename,
                        "score": 1.0,
                        "meta": {
                            "drafter": drafter,
                            "date": display_date or date,
                            "category": category
                        }
                    }]

                    # 직접 LLM 호출 (인용 검증 우회)
                    # QuickFixGenerator의 내부 LLM 접근
                    if hasattr(self.generator, 'rag') and hasattr(self.generator.rag, 'llm'):
                        llm = self.generator.rag.llm

                        # 섹션이 감지되면 요약 모드보다 우선 (Q&A 모드로 처리)
                        if detected_section:
                            # 섹션별 프롬프트 (템플릿 사용)
                            llm_prompt = build_section_prompt(
                                context=full_text[:4000],
                                section=detected_section,
                                filename=filename,
                                drafter=drafter,
                                date=display_date or date
                            )
                        elif detailed_mode:
                            # 상세 답변 프롬프트 (템플릿 사용)
                            llm_prompt = build_detailed_prompt(
                                context=full_text[:4000],
                                filename=filename,
                                drafter=drafter,
                                date=display_date or date
                            )
                        elif needs_summary:
                            # 요약 모드: 구조화된 요약 시스템 사용 (summary_templates.py)
                            from app.rag.summary_templates import (
                                build_prompt,
                                detect_doc_kind,
                                format_summary_output,
                                parse_summary_json,
                            )

                            # 1. 문서 종류 감지
                            kind = detect_doc_kind(filename, full_text)
                            logger.info(f"📄 문서 종류 감지: {kind}")

                            # 2. 구조화된 프롬프트 생성
                            summary_prompt = build_prompt(
                                kind=kind,
                                filename=filename,
                                drafter=drafter,
                                display_date=display_date,
                                context_text=full_text[:4000],
                                claimed_total=None  # 금액은 메타데이터에서 추출 예정
                            )
                            llm_prompt = summary_prompt
                        else:
                            # 일반 Q&A 프롬프트 (템플릿 사용)
                            llm_prompt = build_qa_prompt(
                                context=full_text[:4000],
                                query=query,
                                filename=filename,
                                drafter=drafter,
                                date=display_date or date
                            )

                        # 3. LLM 호출 (max_tokens는 route_query에서 결정)
                        from llama_cpp import Llama
                        if isinstance(llm.llm, Llama):
                            # System 메시지는 모드별로 설정
                            if detailed_mode:
                                system_msg = "당신은 문서 분석 전문가입니다. 사용자가 요청한 모든 세부사항을 빠짐없이 포함하여 상세하게 답변하세요."
                            elif needs_summary:
                                system_msg = "당신은 문서 요약 전문가입니다. JSON 형식으로만 응답하세요."
                            elif detected_section:
                                system_msg = f"당신은 문서 분석 전문가입니다. 사용자가 요청한 '{detected_section}' 섹션만 정확하게 추출하여 답변하세요."
                            else:
                                system_msg = "당신은 문서 분석 전문가입니다. 문서 내용을 기반으로 정확하게 답변하세요."

                            # 동적 토큰 제한: 문서 길이에 따라 조정하여 hallucination 방지
                            # 문서가 짧을 때 과도한 토큰으로 인한 반복 생성 방지
                            content_length = len(full_text)
                            if detailed_mode:
                                # 상세 모드: 문서 길이의 50% 정도로 제한 (최대 1500)
                                adjusted_tokens = min(max_tokens, max(300, content_length // 3))
                            else:
                                # 일반 모드: 문서 길이의 30% 정도로 제한 (최대 800)
                                adjusted_tokens = min(max_tokens, max(200, content_length // 4))

                            logger.debug(f"토큰 조정: 원본 {max_tokens} → {adjusted_tokens} (문서 {content_length}자)")

                            output = llm.llm.create_chat_completion(
                                messages=[
                                    {"role": "system", "content": system_msg},
                                    {"role": "user", "content": llm_prompt}
                                ],
                                max_tokens=adjusted_tokens,
                                temperature=0.3
                            )
                            llm_raw = output['choices'][0]['message']['content']

                            if needs_summary:
                                # 요약 모드: JSON 파싱 및 포맷팅
                                parsed_json = parse_summary_json(llm_raw)
                                llm_result = format_summary_output(
                                    parsed_json=parsed_json,
                                    kind=kind,
                                    filename=filename,
                                    drafter=drafter,
                                    display_date=display_date,
                                    claimed_total=None
                                )
                            else:
                                # Q&A 모드: 답변 그대로 사용
                                llm_result = llm_raw.strip()
                        else:
                            # Fallback
                            llm_result = f"LLM 타입 불일치: {type(llm.llm)}"
                    else:
                        llm_result = "LLM 접근 실패"

                    # 구조화된 요약 제공
                    answer_text += f"{llm_result}"
                    use_llm = True
                except Exception as e:
                    logger.warning(f"⚠️ LLM 요약 실패, 원문 사용: {e}")
                    logger.exception(e)
                    answer_text += full_text
                    use_llm = False
            else:
                # 전체 텍스트 포함 (길이 제한 없음)
                answer_text += full_text
                use_llm = False

            # 5. Evidence 구성
            ref = _encode_file_ref(filename)
            evidence = [{
                "doc_id": filename,
                "filename": filename,
                "page": 1,
                "snippet": full_text[:1000],  # 스니펫은 1000자로 제한
                "ref": ref,
                "meta": {
                    "filename": filename,
                    "drafter": drafter,
                    "date": display_date or date,
                    "category": category,
                    "doctype": doctype
                }
            }]

            logger.info({
                "mode": "DOCUMENT",
                "filename": filename,
                "text_length": len(full_text),
                "llm": use_llm,  # LLM 요약 사용 여부
                "summary_requested": needs_summary
            })

            return {
                "text": answer_text,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": 1,
                    "selected_count": 1,
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ DOCUMENT 모드 처리 실패: {e}", exc_info=True)
            return {
                "text": f"문서 내용 조회 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _safe_fname(self, meta: dict = None, doc_path: str = None) -> str:
        """파일명 안전 추출 (다양한 소스에서 시도)

        Args:
            meta: 메타데이터 딕셔너리
            doc_path: 문서 경로

        Returns:
            안전하게 추출된 파일명 (기본값: '미상 문서')
        """
        import os

        meta = meta or {}

        # 다양한 필드에서 파일명 시도
        fname = (
            meta.get("fname")
            or meta.get("filename")
            or meta.get("doc_id")
            or (os.path.basename(doc_path) if doc_path else None)
            or "미상 문서"
        )

        return fname

    def _make_chunks_for_doc(self, filename: str) -> list:
        """특정 문서의 청크만 로드 (문서 고정 모드용)

        Args:
            filename: 문서 파일명

        Returns:
            해당 문서의 청크 리스트
        """
        try:
            # BM25 인덱스에서 직접 해당 문서 찾기 (검색 대신 직접 접근)
            if hasattr(self.retriever, 'bm25') and self.retriever.bm25:
                bm25_store = self.retriever.bm25

                # metadata에서 filename이 일치하는 문서의 인덱스 찾기
                target_indices = []
                for i, meta in enumerate(bm25_store.metadata):
                    if meta.get('filename') == filename:
                        target_indices.append(i)
                        logger.info(f"✅ BM25 인덱스에서 발견: {filename} (index={i})")

                # 찾은 문서들의 content를 청크로 변환
                chunks = []
                for idx in target_indices:
                    content = bm25_store.documents[idx]
                    if content and len(content.strip()) > 0:
                        # 전체 문서를 하나의 큰 청크로 사용
                        chunks.append({
                            'doc_id': filename,
                            'page': 1,
                            'text': content,  # 전체 텍스트
                            'score': 1.0,  # 직접 매칭이므로 최고 스코어
                            'filename': filename
                        })
                        logger.info(f"✓ 문서 content 로드: {len(content)}자")

                if chunks:
                    logger.info(f"✓ 문서 청크 {len(chunks)}개 로드 완료")
                    return chunks

            # BM25 사용 불가 시 폴백: 키워드 검색
            logger.warning("⚠️ BM25 직접 접근 불가, 검색으로 폴백")
            search_query = filename.replace('.pdf', '').replace('_', ' ')
            results = self.retriever.search(search_query, top_k=20)

            # 검색 결과를 해당 문서로 필터링
            chunks = []
            for result in results:
                # doc_id 또는 meta.filename이 일치하는 경우만 포함
                doc_id = result.get('doc_id', '')
                meta_filename = result.get('meta', {}).get('filename', '')

                if filename in doc_id or filename in meta_filename:
                    chunks.append({
                        'doc_id': result.get('doc_id', filename),
                        'page': result.get('page', 1),
                        'text': result.get('snippet', result.get('text', '')),
                        'score': result.get('score', 0.0),
                        'filename': filename
                    })

            if not chunks:
                logger.warning(f"⚠️ 문서 청크 없음: {filename}")

            return chunks

        except Exception as e:
            logger.error(f"❌ 문서 청크 로드 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_with_ocr(self, pdf_path: str, start_page: int, total_pages: int) -> str:
        """OCR을 사용하여 PDF에서 텍스트 추출 (pytesseract 우선, paddleocr 폴백)

        Args:
            pdf_path: PDF 파일 경로
            start_page: 시작 페이지 (0-based)
            total_pages: 전체 페이지 수

        Returns:
            추출된 텍스트
        """
        try:
            import pytesseract
            from pdf2image import convert_from_path
            from PIL import Image

            # PDF를 이미지로 변환 (끝 3페이지만)
            images = convert_from_path(
                pdf_path,
                first_page=start_page + 1,  # 1-based
                last_page=total_pages
            )

            text = ""
            for i, img in enumerate(images):
                try:
                    # pytesseract 사용
                    page_text = pytesseract.image_to_string(img, lang='kor+eng')
                    text += page_text + "\n"
                    logger.info(f"✓ OCR (pytesseract) 페이지 {start_page + i + 1}: {len(page_text)}자")
                except Exception as e:
                    logger.warning(f"⚠️ pytesseract 실패 (페이지 {start_page + i + 1}): {e}")

            if len(text.strip()) > 50:
                return text

            # pytesseract 실패 시 paddleocr 시도
            logger.info("🔄 paddleocr 폴백 시도...")
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang='korean')

                text = ""
                for i, img in enumerate(images):
                    # PaddleOCR는 파일 경로 또는 numpy array를 받음
                    import numpy as np
                    img_array = np.array(img)
                    result = ocr.ocr(img_array, cls=True)

                    if result and result[0]:
                        page_text = "\n".join([line[1][0] for line in result[0]])
                        text += page_text + "\n"
                        logger.info(f"✓ OCR (paddleocr) 페이지 {start_page + i + 1}: {len(page_text)}자")

                return text

            except Exception as e:
                logger.warning(f"⚠️ paddleocr 실패: {e}")
                return ""

        except Exception as e:
            logger.error(f"❌ OCR 추출 실패: {e}")
            return ""

    def _gather_summary_context(self, filename: str, pdf_path: str, doc_locked: bool = False) -> str:
        """요약용 컨텍스트 수집 (인덱스 청크 기반, PDF tail 비활성)

        Args:
            filename: 파일명
            pdf_path: PDF 파일 경로
            doc_locked: True면 해당 문서 청크만 사용 (다른 문서 검색 금지)

        Returns:
            수집된 컨텍스트 텍스트 (최대 ~3600자, 약 1.8k 토큰)
        """
        import re

        import pdfplumber
        parts = []

        # 1) PDF 끝 2~3페이지 추출 → 비활성화 (인덱스 청크 우선 전략)
        # 사유: 개요/배경/검토사유/대안/견적 등 핵심 정보가 끝부분이 아닌 중간에 위치하는 경우 다수
        # 인덱스된 청크로 전체 문서를 커버하도록 변경
        logger.info("📋 요약 컨텍스트: PDF tail 추출 비활성 (인덱스 청크 기반 전략)")
        # try:
        #     with pdfplumber.open(pdf_path) as pdf:
        #         total_pages = len(pdf.pages)
        #         start_page = max(0, total_pages - 3)  # 끝 3페이지
        #         tail = ""
        #         for page in pdf.pages[start_page:]:
        #             tail += (page.extract_text() or "")
        #
        #         # OCR 폴백 (텍스트가 너무 짧을 경우)
        #         if len(tail.strip()) < 50:
        #             logger.warning(f"⚠️ PDF 텍스트 부족 ({len(tail)}자), OCR 시도...")
        #             tail = self._extract_with_ocr(pdf_path, start_page, total_pages)
        #
        #         if tail.strip():
        #             parts.append("=== [문서 결론/말미] ===\n" + tail)
        #             logger.info(f"✓ PDF 끝 {total_pages - start_page}페이지 추출: {len(tail)}자")
        # except Exception as e:
        #     logger.warning(f"⚠️ PDF 끝부분 추출 실패: {e}")

        # 2) 인덱스 청크 기반 컨텍스트 수집 (섹션 가중치 적용)
        # 우선순위 키워드: 개요, 배경, 검토사유, 대안, 견적, 결론, 비용, 도입사유
        priority_keywords = r'(개요|배경|검토사유|검토\s*사유|대안|견적|결론|비용|도입사유|도입\s*사유|구매목적|구매\s*목적|선정|권고|총액|합계)'

        try:
            if doc_locked:
                # 문서 고정 모드: 해당 문서의 청크만 로드
                logger.info(f"🔒 문서 고정 모드: {filename}의 청크만 사용")
                chunks = self._make_chunks_for_doc(filename)

                # 섹션 가중치 적용: 우선순위 키워드 포함 청크를 앞으로
                priority_chunks = []
                normal_chunks = []
                for chunk in chunks:
                    chunk_text = chunk.get('text') or chunk.get('snippet') or chunk.get('content') or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_chunks.append(chunk)
                    else:
                        normal_chunks.append(chunk)

                # 우선순위 청크 + 일반 청크 순서로 재조합, 최대 10개 (검토서 상세 정보 포함)
                sorted_chunks = (priority_chunks + normal_chunks)[:10]

                for i, chunk in enumerate(sorted_chunks, 1):
                    chunk_text = chunk.get('text') or chunk.get('snippet') or chunk.get('content') or ""
                    if chunk_text:
                        parts.append(f"=== [문서 청크 {i}] ===\n" + chunk_text[:5000])

                if sorted_chunks:
                    logger.info(f"✓ 문서 고정 청크 {len(sorted_chunks)}개 추출 (우선순위: {len(priority_chunks)}개)")
            else:
                # 일반 모드: 키워드 검색 후 같은 파일 필터링
                search_keywords = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)  # 날짜 제거
                search_keywords = re.sub(r'\.pdf$', '', search_keywords, flags=re.IGNORECASE)
                search_keywords = search_keywords.replace('_', ' ')

                hits = self.retriever.search(search_keywords, top_k=10)
                same_file_hits = [h for h in hits if h.get("filename") == filename]

                # 섹션 가중치 적용
                priority_hits = []
                normal_hits = []
                for h in same_file_hits:
                    chunk_text = h.get('text') or h.get('snippet') or h.get('content') or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_hits.append(h)
                    else:
                        normal_hits.append(h)

                sorted_hits = (priority_hits + normal_hits)[:10]

                for i, h in enumerate(sorted_hits, 1):
                    chunk_text = h.get('text') or h.get('snippet') or h.get('content') or ""
                    if chunk_text:
                        parts.append(f"=== [관련 청크 {i}] ===\n" + chunk_text[:5000])

                if sorted_hits:
                    logger.info(f"✓ RAG 청크 {len(sorted_hits)}개 추출 (우선순위: {len(priority_hits)}개)")
        except Exception as e:
            logger.warning(f"⚠️ RAG 청크 추출 실패: {e}")

        # 3) OCR/원문 스냅샷 (있으면 - 현재는 DB text_preview 활용)
        # 향후 확장: full_text 필드가 있으면 활용
        # if hasattr(self, 'get_fulltext'):
        #     full = self.get_fulltext(filename)
        #     if full and len(full) > 1000:
        #         parts.append("=== [원문 스냅샷] ===\n" + full[:3000])

        # 결합 및 길이 제한 (약 3k 토큰 ~ 6000자, 검토서 상세 정보 포함)
        context = "\n\n".join(parts)[:6000]
        logger.info(f"📋 최종 컨텍스트 길이: {len(context)}자 (청크 수: {len(parts)})")
        return context

    def warmup(self) -> None:
        """워밍업: LLM + 인덱스 사전 로딩

        첫 쿼리 지연 제거를 위해 시작 시 호출.
        """
        logger.info("Warming up RAG pipeline...")
        try:
            # 더미 쿼리 실행
            response = self.query("test warmup query", top_k=1)
            if response.success:
                logger.info(f"Warmup completed in {response.latency:.2f}s")
            else:
                logger.warning(f"Warmup failed: {response.error}")
        except Exception as e:
            logger.error(f"Warmup error: {e}", exc_info=True)

    # ========================================================================
    # 내부 헬퍼: 기본 구현 생성
    # ========================================================================

    def _create_default_retriever(self) -> Retriever:
        """기본 검색 엔진 생성 (v2 또는 v1)

        환경 변수 USE_V2_RETRIEVER로 제어:
        - true: HybridRetrieverV2 사용 (신규 2-layer 아키텍처)
        - false/없음: HybridRetriever 사용 (기존 레거시)
        """
        import os

        use_v2 = os.getenv("USE_V2_RETRIEVER", "false").lower() == "true"

        if use_v2:
            # V2 Retriever는 archive로 이동되었습니다 (20251026)
            # 레거시 코드를 제거하고 v1으로 폴백합니다
            logger.warning(
                "⚠️ USE_V2_RETRIEVER는 더 이상 지원되지 않습니다. v1 Retriever를 사용합니다."
            )
            use_v2 = False
            # try:
            #     from app.rag.retriever_v2 import HybridRetrieverV2
            #     v2_retriever = HybridRetrieverV2()
            #     logger.info("✅ HybridRetrieverV2 (v2 신규 시스템) 생성 완료")
            #
            #     # V2 adapter: fused_results → list 변환
            #     return _V2RetrieverAdapter(v2_retriever)
            # except Exception as e:
            #     logger.error(f"V2 Retriever 생성 실패, v1으로 폴백: {e}")
            #     # 폴백: v1 사용
            #     use_v2 = False

        if not use_v2:
            try:
                from app.rag.retrievers.hybrid import HybridRetriever

                retriever = HybridRetriever()
                logger.info("Default HybridRetriever (v1 레거시) 생성 완료")
                return retriever
            except Exception as e:
                logger.error(f"HybridRetriever 생성 실패: {e}")
                # 폴백: 더미 구현
                return _DummyRetriever()

    def _create_default_compressor(self) -> Compressor:
        """기본 압축기 생성 (현재는 no-op)"""
        logger.info("Default compressor 생성 (no-op)")
        return _NoOpCompressor()

    def _create_default_generator(self) -> Generator:
        """기본 LLM 생성기 생성 (레거시 어댑터 사용)"""
        try:
            # 레거시 구현 어댑터 사용 (점진적 이관 준비)
            legacy_rag = self._create_legacy_adapter()
            logger.info("Default generator 생성 (Legacy Adapter 래핑)")
            return _QuickFixGenerator(legacy_rag)
        except Exception as e:
            logger.error(f"Generator 생성 실패: {e}")
            return _DummyGenerator()

    def _create_legacy_adapter(self):
        """레거시 구현 어댑터 생성 (캡슐화)

        QwenLLM을 래핑하여 기존 레거시 시스템과 연결합니다.
        향후 이 메서드만 수정하여 신규 구현으로 점진 전환 가능.

        Returns:
            _LLMAdapter: LLM 어댑터 인스턴스
        """
        try:
            from rag_system.active.llm_singleton import LLMSingleton

            model_path = os.getenv("MODEL_PATH", "./models/ggml-model-Q4_K_M.gguf")
            logger.info(f"🔍 DEBUG: Attempting to load LLM with model_path={model_path}")
            logger.info(f"🔍 DEBUG: Model file exists: {Path(model_path).exists()}")
            llm = LLMSingleton.get_instance(model_path=model_path)
            logger.info(f"✅ LLM adapter 생성 완료 (LLMSingleton 사용, model={model_path})")
            return _LLMAdapter(llm)
        except Exception as e:
            logger.error(f"LLM adapter 생성 실패: {e}", exc_info=True)
            return None

    def _load_known_drafters(self) -> set:
        """메타DB에서 고유 기안자 로드 (Closed-World Validation용)

        Returns:
            set: 고유 기안자 이름 집합
        """
        try:
            from app.data.metadata_db import MetadataDB

            db = MetadataDB()
            drafters = db.list_unique_drafters()
            db.close()

            logger.info(f"✅ 고유 기안자 {len(drafters)}명 캐싱 완료")
            return drafters
        except Exception as e:
            logger.error(f"기안자 로드 실패: {e}")
            return set()


# ============================================================================
# 폴백 구현 (기본 동작 보장)
# ============================================================================


class _DummyRetriever:
    """더미 검색기 (폴백용)"""

    def search(
        self,
        query: str,
        top_k: int,
        *,
        mode: str = "chat",
        selected_filename: Optional[str] = None,
        strict_content: bool = False,
    ) -> List[Dict[str, Any]]:
        logger.warning("Dummy retriever: 빈 결과 반환")
        return []


class _NoOpCompressor:
    """No-op 압축기 (압축하지 않음)"""

    def compress(
        self, chunks: List[Dict[str, Any]], ratio: float
    ) -> List[Dict[str, Any]]:
        logger.debug("No-op compressor: 압축 스킵")
        return chunks


class _LLMAdapter:
    """QwenLLM 어댑터 (LegacyAdapter 대체)

    QwenLLM을 _QuickFixGenerator가 기대하는 인터페이스로 변환합니다.
    """

    def __init__(self, llm):
        self.llm = llm

    def generate_from_context(self, query: str, context: str, temperature: float = 0.1, mode: str = "rag") -> str:
        """컨텍스트 기반 답변 생성

        Args:
            query: 사용자 질문
            context: 검색된 문서 컨텍스트 (텍스트 형식)
            temperature: 생성 온도
            mode: 생성 모드 (chat/rag/summarize)

        Returns:
            str: 생성된 답변
        """
        # Context를 청크 형식으로 변환
        chunks = [{"snippet": context, "content": context}]

        try:
            # 🎯 모드별 토큰 예산 적용
            logger.info(f"🎯 generate_from_context: mode={mode}")
            response = self.llm.generate_response(query, chunks, max_retries=1, mode=mode)

            if hasattr(response, "answer"):
                return response.answer
            return str(response)
        except Exception as e:
            logger.error(f"LLM 답변 생성 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {str(e)}"


class _QuickFixGenerator:
    """QuickFixRAG 래퍼 (기존 구현 활용)"""

    def __init__(self, rag):
        self.rag = rag
        self.compressed_chunks = None  # Store chunks for LLM

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        # 재검색 금지. 컨텍스트 기반 생성으로 우선 시도.
        try:
            # 1) QuickFixRAG에 전용 메서드가 있으면 사용
            if hasattr(self.rag, "generate_from_context"):
                return self.rag.generate_from_context(
                    query, context, temperature=temperature, mode=mode
                )

            # 2) 내부 LLM 직접 접근 경로가 있으면 사용
            # 🔥 CRITICAL: LLM lazy loading - ensure LLM is loaded before checking
            if hasattr(self.rag, "_ensure_llm_loaded"):
                self.rag._ensure_llm_loaded()

            if hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response"):
                # CRITICAL: generate_response expects List[Dict], not str
                # Convert context string back to chunks format
                if self.compressed_chunks:
                    # Use stored compressed chunks (preferred)
                    logger.debug(
                        f"Using {len(self.compressed_chunks)} compressed chunks for generation (mode={mode})"
                    )
                    response = self.rag.llm.generate_response(
                        query, self.compressed_chunks, max_retries=1, mode=mode
                    )
                else:
                    # Fallback: convert context string to minimal chunks
                    logger.warning(
                        "No compressed_chunks available, converting context string"
                    )
                    snippets = context.split("\n\n")
                    chunks = [
                        {"snippet": s, "content": s} for s in snippets if s.strip()
                    ]
                    response = self.rag.llm.generate_response(
                        query, chunks, max_retries=1, mode=mode
                    )

                # Extract answer from RAGResponse object
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

            # 3) 폴백: 재검색이 포함된 answer는 최후 수단으로만
            logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")
            if self.rag is None:
                logger.error("LegacyAdapter: QuickFixRAG가 없어 답변 생성 불가")
                return "죄송합니다. 현재 답변 생성 기능이 비활성화되어 있습니다."
            return self.rag.answer(query, use_llm_summary=True)
        except Exception as e:
            logger.error(f"Generation 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {str(e)}"


class _V2RetrieverAdapter:
    """V2 Retriever Adapter

    HybridRetrieverV2의 결과 형식 {"fused_results": [...]}를
    v1 인터페이스 형식 [...] 으로 변환.

    v2 results 구조:
        {
            "fused_results": [
                {"id": "doc_4094", "score": 0.123, "filename": "...", ...},
                ...
            ]
        }

    v1 expected 구조:
        [
            {"doc_id": "doc_4094", "snippet": "...", "page": 1, ...},
            ...
        ]
    """

    def __init__(self, v2_retriever):
        """
        Args:
            v2_retriever: HybridRetrieverV2 instance
        """
        self.v2_retriever = v2_retriever
        self.db = v2_retriever.db  # MetadataDB for content fetching

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search using v2 retriever, convert to v1 format

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of dicts in v1 format with keys:
            - doc_id: Document ID
            - snippet: Text snippet
            - page: Page number (default 1)
            - score: Relevance score
            - meta: Metadata dict
        """
        try:
            # Call v2 retriever
            v2_result = self.v2_retriever.search(query, top_k=top_k)
            fused_results = v2_result.get("fused_results", [])

            # Convert to v1 format
            v1_results = []
            for doc in fused_results:
                doc_id = doc.get("id", "unknown")

                # 🔥 CRITICAL: snippet 우선순위
                # 1) 검색 결과에 직접 포함된 snippet/content
                # 2) DB 조회 (get_content)
                # 3) 제목/파일명 기반 폴백

                snippet = ""

                # Priority 1: fused_results에 이미 포함된 데이터
                if "snippet" in doc:
                    snippet = doc["snippet"]
                elif "content" in doc:
                    snippet = doc["content"][:500]

                # Priority 2: DB 조회 (app/rag/db.MetadataDB.get_content)
                if not snippet or len(snippet) < 50:
                    content = self.db.get_content(doc_id)
                    if content and len(content) >= 50:
                        snippet = content[:500]

                # Priority 3: 메타데이터 폴백
                if not snippet or len(snippet) < 50:
                    fallback_parts = []
                    if doc.get("title"):
                        fallback_parts.append(f"제목: {doc['title']}")
                    if doc.get("filename"):
                        fallback_parts.append(f"파일: {doc['filename']}")
                    if doc.get("date"):
                        fallback_parts.append(f"날짜: {doc['date']}")

                    snippet = (
                        " | ".join(fallback_parts)
                        if fallback_parts
                        else f"문서 ID: {doc_id}"
                    )
                    logger.warning(
                        f"V2 Adapter: doc_id={doc_id} snippet 결손, 메타데이터 폴백 사용"
                    )

                v1_results.append(
                    {
                        "doc_id": doc_id,
                        "snippet": snippet,
                        "page": 1,  # v2에서는 page 정보 없음, 기본 1
                        "score": doc.get("score", 0.0),
                        "meta": {
                            "doc_id": doc_id,
                            "filename": doc.get("filename", ""),
                            "title": doc.get("title", ""),
                            "date": doc.get("date", ""),
                            "page": 1,
                        },
                    }
                )

            logger.info(f"V2 Adapter: {len(v1_results)} results converted")
            return v1_results

        except Exception as e:
            logger.error(f"V2 Adapter search failed: {e}", exc_info=True)
            return []

    def warmup(self):
        """워밍업 (v2는 필요 시 자동 로드)"""
        logger.info("V2 Adapter warmup (no-op)")


class _DummyGenerator:
    """더미 생성기 (폴백용)"""

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        logger.warning("Dummy generator: 기본 응답 반환")
        return "[E_GENERATE] 현재 생성기가 비활성 상태입니다."
