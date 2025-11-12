"""
쿼리 모드 라우터
2025-11-07 (단순화 버전)

질의 의도를 분석하여 적절한 쿼리 모드를 결정합니다.

규칙:
- 비용 질의 → COST 모드
- 문서 참조 + 내용/요약 의도 → DOCUMENT 모드
- 목록/검색 의도 → SEARCH 모드
- 기본값 또는 Q&A 의도 → QA 모드

변경 이력 (2025-11-07):
- DOC_ANCHORED 모드 제거 (과도한 필드 추출 문제)
- PREVIEW + SUMMARY → DOCUMENT 통합
- LIST + SEARCH + LIST_FIRST → SEARCH 통합
- 8개 모드 → 4개 모드 단순화
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.core.logging import get_logger
from app.rag.routing_monitor import get_monitor

logger = get_logger(__name__)


@dataclass
class ScoreStats:
    """검색 결과 점수 통계"""
    top1: float
    top2: float
    top3: float
    delta12: float
    delta13: float
    ratio12: float  # top1 / max(top2, 1e-9)
    hits: int


@dataclass
class RouteDecision:
    """쿼리 라우팅 결정 (모드 + 의도 플래그)

    2025-11-10: 모드와 의도를 분리하여 파이프라인 동작을 명확화
    - mode: 4개 모드 (COST, DOCUMENT, SEARCH, QA) 유지
    - intent flags: 각 모드 내에서 세부 동작 결정
    - 예: SEARCH + list_intent=True → LLM 건너뛰고 목록 스키마 반환
    """
    mode: "QueryMode"
    reason: str
    confidence: float

    # 의도 플래그
    list_intent: bool = False        # 목록 반환 의도 (리스트, 목록, 전부, 모든)
    content_intent: bool = False     # 내용 반환 의도 (요약, 미리보기, 내용)
    cost_intent: bool = False        # 비용 조회 의도 (총액, 금액, 얼마)

    # 추출된 파라미터 (필터링용)
    drafter: Optional[str] = None    # 기안자 이름
    year: Optional[int] = None       # 연도 (YYYY)
    date_range: Optional[Tuple[str, str]] = None  # 날짜 범위 (시작, 끝)

    # 정렬 기준 (최신순, 오래된순 등)
    sort_by: Optional[List[str]] = None  # ["date_desc"], ["date_asc"] 등


# 헬퍼 함수: 파일명 정규화 (공백/특수문자 제거)
def _norm(s: str) -> str:
    """문자열 정규화: 소문자 + 공백/특수문자 제거"""
    s = s.lower()
    s = s.replace("&", "and")
    s = re.sub(r"[\s_·,:()\\[\\\]-]+", "", s)
    return s


# 헬퍼 함수: 파일명 유사도 스코어
def _score(qn: str, tn: str) -> float:
    """부분 포함 + 길이 근접 혼합 스코어 (0~1)"""
    if qn in tn or tn in qn:
        base = 0.8
    else:
        base = 0.0
    diff = abs(len(qn) - len(tn))
    length_bonus = max(0.0, 0.4 - diff * 0.01)
    return min(1.0, base + length_bonus)


class QueryMode(Enum):
    """쿼리 모드 (단순화: 8개 → 4개)

    2025-11-07: 모드 구조 재설계
    - DOC_ANCHORED 제거 (과도한 필드 추출 문제)
    - PREVIEW + SUMMARY → DOCUMENT 통합
    - LIST + SEARCH + LIST_FIRST → SEARCH 통합
    """

    COST = "cost"  # 비용 조회 (renamed from COST_SUM)
    DOCUMENT = "document"  # 문서 내용/요약 (통합: PREVIEW + SUMMARY)
    SEARCH = "search"  # 문서 검색 (통합: LIST + SEARCH + LIST_FIRST)
    QA = "qa"  # 질답 모드 (RAG 파이프라인, 기본)


class QueryRouter:
    """쿼리 모드 라우터"""

    # 비용 질의 패턴 (합계/총액/금액 얼마 질의)
    COST_INTENT_PATTERN = re.compile(
        r"("
        # Pattern 1: Original - cost keyword + interrogative (backward compatibility)
        r"(합계|총액|총계|금액|비용).*(얼마|알려줘|확인|인지)"
        r"|"
        # Pattern 2: Original - short interrogative forms
        r"얼마였지|얼마였나요|얼마야"
        r"|"
        # Pattern 3: NEW - cost keyword + optional particle + question mark (e.g., "총액은?")
        r"(총액|금액|비용|합계|총계)(은|는)?\s*\?"
        r"|"
        # Pattern 4: NEW - context + cost keyword (e.g., "기안한 문서 총액", "소모품 구매 총액")
        r"(기안|작성|문서|구매|소모품|발주|납품|년|월).*(총액|금액|비용|합계|총계)"
        r"|"
        # Pattern 5: NEW - year/period + cost keyword (e.g., "2024년 총액")
        r"\d{4}년?\s*(총액|금액|비용|합계|총계)"
        r"|"
        # Pattern 6: NEW - compound cost phrases (e.g., "비용 합계", "합계 금액")
        r"(비용|구매)\s*(합계|총액)"
        r"|"
        r"(합계|총액)\s*(금액|비용)"
        r")",
        re.IGNORECASE,
    )

    # 목록 검색 패턴 (연도/작성자 + 찾기)
    LIST_INTENT_PATTERN = re.compile(
        r"(\d{4}년?|[가-힣]{2,4}(가|이)?|모든|전체|all).*(찾아|검색|리스트|목록|보여|알려|문서)",
        re.IGNORECASE,
    )

    # 요약 패턴 (요약/정리/개요 + 다양한 변형)
    SUMMARY_INTENT_PATTERN = re.compile(
        r"(요약|정리|개요|내용.*요약|요약해|요약헤줘|정리해|개요.*알려)",
        re.IGNORECASE,
    )

    # 검색 패턴 (문서 찾기 요청)
    SEARCH_INTENT_PATTERN = re.compile(
        r"(관련\s*(문서|파일|기안서)|"  # "XX 관련 문서"
        r"문서\s*(찾|검색)|"            # "문서 찾아줘", "문서 검색"
        r"파일\s*(찾|검색|있)|"          # "파일 찾아", "파일 있어?"
        r"기안서\s*(찾|검색|있)|"        # "기안서 찾아"
        r"(있어\??|있나요|있는지)|"     # "있어?", "있나요"
        r"(몇\s*개|개수|총|count|number))",  # "몇개", "개수", "총" (NEW)
        re.IGNORECASE,
    )

    # 문서 지시어 패턴 (이문서, 이 문서, 해당 문서 등)
    DOC_REFERENCE_PATTERN = re.compile(
        r"(이\s?문서|해당\s?문서|이\s?파일|그\s?문서)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        config_path: str = "config/document_processing.yaml",
        query_parser: Optional[Any] = None
    ):
        """초기화

        Args:
            config_path: 설정 파일 경로
            query_parser: QueryParser 인스턴스 (옵션, Phase 2 연동용)
        """
        self.config = self._load_config(config_path)
        self.qa_keywords = self.config.get("mode_routing", {}).get(
            "qa_intent_keywords", []
        )
        self.preview_keywords = self.config.get("mode_routing", {}).get(
            "preview_only_keywords", []
        )
        filename_pattern_str = self.config.get("mode_routing", {}).get(
            "filename_pattern", r"\S+\.pdf"
        )

        # 정규식 사전 컴파일 (Phase 1: 성능 개선)
        self.filename_re = re.compile(filename_pattern_str, re.IGNORECASE)

        # QueryParser 연동 (Phase 2)
        self.query_parser = query_parser

        # Low-confidence 가드레일 설정 (환경 변수)
        self.low_conf_delta = float(os.getenv("LOW_CONF_DELTA", "0.05"))
        self.low_conf_min_hits = int(os.getenv("LOW_CONF_MIN_HITS", "1"))

        # 라우팅 모니터 초기화
        self.monitor = get_monitor()

        logger.info(
            f"📋 모드 라우터 초기화: QA 키워드 {len(self.qa_keywords)}개, 미리보기 키워드 {len(self.preview_keywords)}개, "
            f"Low-conf delta={self.low_conf_delta}, min_hits={self.low_conf_min_hits}, "
            f"QueryParser={'enabled' if query_parser else 'disabled'}"
        )

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드

        Args:
            config_path: 설정 파일 경로

        Returns:
            설정 딕셔너리
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"⚠️ 설정 파일 없음: {config_path}, 기본값 사용")
                return {}

            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # 하위 호환: v0 스키마를 v1로 정규화
            from app.config.compat import normalize_config
            config = normalize_config(config)

            logger.info(f"✓ 설정 로드: {config_path} (schema v{config.get('schema_version', 0)})")
            return config

        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            return {}

    def _is_low_confidence(self, retrieval_results: Any) -> bool:
        """검색 결과가 낮은 신뢰도인지 판단

        Args:
            retrieval_results: HybridRetriever.search() 결과 (score_stats 속성 포함 가능)

        Returns:
            True if low confidence, False otherwise
        """
        # score_stats 추출 (duck typing)
        score_stats = getattr(retrieval_results, "score_stats", {}) or {}

        hits = score_stats.get("hits", 0)
        delta12 = score_stats.get("delta12", 0.0)

        # 조건: hits가 충분하고, delta12가 임계값보다 작으면 low-confidence
        if hits >= self.low_conf_min_hits and delta12 < self.low_conf_delta:
            logger.warning(
                f"⚠️ Low-confidence 감지: delta12={delta12:.3f} < {self.low_conf_delta}, "
                f"hits={hits} → LIST_FIRST 모드 활성화"
            )
            return True

        return False

    def _log_routing_decision(self, query: str, mode: QueryMode, confidence: float, reason: str) -> None:
        """라우팅 결정 기록

        Args:
            query: 사용자 질의
            mode: 결정된 모드
            confidence: 신뢰도 (0.0~1.0)
            reason: 라우팅 이유
        """
        try:
            self.monitor.log_decision(
                query=query,
                mode=mode.value,
                reason=reason,
                confidence=confidence
            )
        except Exception as e:
            # 모니터링 실패가 라우팅을 막으면 안 됨
            logger.error(f"라우팅 모니터링 실패: {e}")

    def _detect_intents(self, query: str) -> Dict[str, bool]:
        """의도 신호 감지 (Phase 1: 중복 제거 및 단일화)

        Args:
            query: 사용자 질의

        Returns:
            의도 플래그 딕셔너리 {"cost": bool, "list": bool, "content": bool}
        """
        ql = query.lower()

        return {
            "cost": self.COST_INTENT_PATTERN.search(query) is not None,
            "list": (
                self.LIST_INTENT_PATTERN.search(query) is not None
                or self.SEARCH_INTENT_PATTERN.search(query) is not None
            ),
            "content": (
                "내용" in ql
                or "미리보기" in ql
                or "자세히" in ql
                or "상세히" in ql
                or "자세하게" in ql
                or "구체적으로" in ql
                or self.SUMMARY_INTENT_PATTERN.search(query) is not None
                or any(k in ql for k in self.preview_keywords)
            ),
        }

    def _extract_query_params(self, query: str) -> Dict[str, Any]:
        """쿼리에서 파라미터 추출 (기안자, 연도 등)

        Args:
            query: 사용자 질의

        Returns:
            추출된 파라미터 딕셔너리 {drafter: str, year: int, ...}

        Note:
            Phase 2에서 QueryParser로 대체 예정
        """
        # QueryParser가 있으면 우선 사용
        if self.query_parser:
            try:
                parsed = self.query_parser.parse_filters(query)
                params = {}
                if parsed.get("drafter"):
                    params["drafter"] = parsed["drafter"]
                if parsed.get("year"):
                    # year는 문자열일 수 있으므로 처리
                    year_str = parsed["year"]
                    if "-" in str(year_str):  # 범위 (예: "2024-2025")
                        params["year"] = int(year_str.split("-")[0])  # 시작 연도 사용
                    else:
                        params["year"] = int(year_str)
                return params
            except Exception as e:
                logger.warning(f"QueryParser 사용 실패, 기본 추출 사용: {e}")

        # 기본 추출 로직 (레거시)
        params = {}

        # 연도 추출 (YYYY년 형식)
        year_match = re.search(r"(\d{4})\s*년?", query)
        if year_match:
            params["year"] = int(year_match.group(1))

        # 기안자 추출 (한글 이름 2-4자)
        drafter_match = re.search(r"([가-힣]{2,4})\s*(문서|기안서|작성|기안|의)", query)
        if drafter_match:
            params["drafter"] = drafter_match.group(1)

        return params

    def classify_mode(self, query: str) -> RouteDecision:
        """쿼리 모드 자동 분류 및 라우팅 (단순화 버전)

        사용자 질의를 분석하여 가장 적절한 QueryMode로 자동 라우팅합니다.
        패턴 매칭과 키워드 감지를 통해 우선순위에 따라 모드를 결정합니다.

        우선순위 (높음 → 낮음):
            1. COST: 비용 조회 질의 (예: "합계", "총액")
            2. DOCUMENT: 문서 내용/요약 요청 (파일명 or 문서지시어 + 내용/요약 의도)
            3. SEARCH: 문서 검색 (찾기, 검색, 목록 등)
            4. QA: 질답 모드 (기본)

        모드 판단 기준:
            COST: COST_INTENT_PATTERN 매칭
            DOCUMENT: (파일명 or 문서지시어 or 문서타입) & (미리보기 or 요약 or 내용 의도)
            SEARCH: LIST_INTENT_PATTERN or SEARCH_INTENT_PATTERN 매칭
                    (예: "찾아줘", "검색", "관련 문서", "2024년 문서")
            QA: qa_keywords 매칭 또는 모든 조건 불만족 시 기본값

        Args:
            query (str): 사용자 질의.
                예: "2024년 남준수 문서 전부" → SEARCH
                    "중계차 렌즈 문서 찾아줘" → SEARCH
                    "이 문서 요약해줘" → DOCUMENT
                    "미러클랩 카메라 삼각대 기술검토서 내용 알려줘" → DOCUMENT
                    "비용 합계는?" → COST

        Returns:
            RouteDecision: 모드 + 의도 플래그 + 추출된 파라미터를 포함하는 결정 객체

        Example:
            >>> router = QueryRouter()
            >>> router.classify_mode("중계차 카메라 문서 찾아줘")
            QueryMode.SEARCH
            >>> router.classify_mode("2024년 남준수 문서 전부")
            QueryMode.SEARCH
            >>> router.classify_mode("이 문서 요약해줘")
            QueryMode.DOCUMENT
            >>> router.classify_mode("미러클랩 삼각대 기술검토서 내용 알려줘")
            QueryMode.DOCUMENT

        Note:
            - 로깅을 통해 결정 과정 추적 가능
            - 모든 조건 불만족 시 QueryMode.QA 반환 (fallback)
        """
        query_lower = query.lower()

        # 파라미터 추출 (기안자, 연도 등)
        params = self._extract_query_params(query)

        # 의도 플래그 감지 (Phase 1: 단일화된 메서드 사용)
        intents = self._detect_intents(query)

        # 1. 비용 질의 체크 (최우선)
        if intents["cost"]:
            logger.info("🎯 모드 결정: COST (비용 질의 감지)")
            reason = self.get_routing_reason(query)
            self._log_routing_decision(query, QueryMode.COST, confidence=0.95, reason=reason)
            return RouteDecision(
                mode=QueryMode.COST,
                reason=reason,
                confidence=0.95,
                cost_intent=True,
                year=params.get("year"),
                drafter=params.get("drafter")
            )

        # 2. 파일명 패턴 체크 (Phase 1: 사전 컴파일된 정규식 사용)
        has_filename = self.filename_re.search(query) is not None

        # 3. 문서 지시어 체크 (이문서, 해당 문서 등)
        has_doc_reference = self.DOC_REFERENCE_PATTERN.search(query) is not None

        # 4. 문서 타입 키워드 체크 (검토서, 기안서, 견적서 등)
        has_doc_type_keyword = bool(
            re.search(
                r"(검토서|기안서|견적서|제안서|보고서|계획서|공문|발주서|납품서|영수증)",
                query,
                re.IGNORECASE,
            )
        )

        # 5. Q&A 의도 키워드 체크
        has_qa_intent = any(keyword in query_lower for keyword in self.qa_keywords)

        # 6. DOCUMENT 모드 우선: 문서 참조 + 내용 요청
        # "이 문서 요약해줘", "XXX 기술검토서 내용 알려줘", "파일명.pdf 미리보기"
        if (has_filename or has_doc_reference or has_doc_type_keyword) and intents[
            "content"
        ]:
            logger.info("🎯 모드 결정: DOCUMENT (문서 내용/요약)")
            reason = self.get_routing_reason(query)
            self._log_routing_decision(
                query, QueryMode.DOCUMENT, confidence=0.9, reason=reason
            )
            return RouteDecision(
                mode=QueryMode.DOCUMENT,
                reason=reason,
                confidence=0.9,
                content_intent=True,
                year=params.get("year"),
                drafter=params.get("drafter"),
            )

        # 7. SEARCH 모드: 목록/검색 의도
        # "2024년 남준수 문서 전부", "중계차 카메라 문서 찾아줘"
        if intents["list"]:
            logger.info("🎯 모드 결정: SEARCH (문서 검색)")
            reason = self.get_routing_reason(query)
            self._log_routing_decision(
                query, QueryMode.SEARCH, confidence=0.9, reason=reason
            )
            return RouteDecision(
                mode=QueryMode.SEARCH,
                reason=reason,
                confidence=0.9,
                list_intent=True,
                year=params.get("year"),
                drafter=params.get("drafter"),
            )

        # 10. Q&A 의도 키워드 체크 (일반 QA 키워드)
        if has_qa_intent:
            logger.info("🎯 모드 결정: QA (의도 키워드 감지)")
            reason = self.get_routing_reason(query)
            self._log_routing_decision(query, QueryMode.QA, confidence=0.8, reason=reason)
            return RouteDecision(
                mode=QueryMode.QA,
                reason=reason,
                confidence=0.8,
                year=params.get("year"),
                drafter=params.get("drafter")
            )

        # 8. 문서 참조만 있고 의도 불명확 → SEARCH (Phase 1: 개선, list_intent=True)
        # 레거시: DOCUMENT(0.6) → 개선: SEARCH(0.7) + list_intent
        if has_filename or has_doc_reference:
            logger.info("🎯 모드 결정: SEARCH (문서 참조 감지, 목록 우선)")
            reason = self.get_routing_reason(query)
            self._log_routing_decision(
                query, QueryMode.SEARCH, confidence=0.7, reason=reason
            )
            return RouteDecision(
                mode=QueryMode.SEARCH,
                reason=reason,
                confidence=0.7,
                list_intent=True,
                year=params.get("year"),
                drafter=params.get("drafter"),
            )

        # 12. 기본: Q&A 모드
        logger.info("🎯 모드 결정: QA (기본)")
        reason = "default_qa"
        self._log_routing_decision(query, QueryMode.QA, confidence=0.5, reason=reason)
        return RouteDecision(
            mode=QueryMode.QA,
            reason=reason,
            confidence=0.5,
            year=params.get("year"),
            drafter=params.get("drafter")
        )

    def get_routing_reason(self, query: str) -> str:
        """모드 라우팅 이유 반환 (로깅용)

        Args:
            query: 사용자 질의

        Returns:
            라우팅 이유 문자열
        """
        query_lower = query.lower()

        has_cost_intent = self.COST_INTENT_PATTERN.search(query) is not None
        has_list_intent = self.LIST_INTENT_PATTERN.search(query) is not None
        has_summary_intent = self.SUMMARY_INTENT_PATTERN.search(query) is not None
        has_doc_reference = self.DOC_REFERENCE_PATTERN.search(query) is not None
        has_qa_intent = any(keyword in query_lower for keyword in self.qa_keywords)
        has_filename = self.filename_re.search(query) is not None
        has_preview_intent = any(
            keyword in query_lower for keyword in self.preview_keywords
        )

        detected_qa_keywords = [kw for kw in self.qa_keywords if kw in query_lower]
        detected_preview_keywords = [
            kw for kw in self.preview_keywords if kw in query_lower
        ]

        reason_parts = []

        if has_cost_intent:
            reason_parts.append("cost_intent")

        if has_list_intent:
            reason_parts.append("list_intent")

        if has_summary_intent:
            reason_parts.append("summary_intent")

        if has_doc_reference:
            reason_parts.append("doc_reference")

        if has_filename:
            reason_parts.append("filename_detected")

        if has_qa_intent:
            reason_parts.append(f"qa_keywords({','.join(detected_qa_keywords)})")

        if has_preview_intent:
            reason_parts.append(
                f"preview_keywords({','.join(detected_preview_keywords)})"
            )

        if not reason_parts:
            reason_parts.append("default_qa")

        return "|".join(reason_parts)

    def suggest_alternative_modes(self, query: str) -> List[Tuple[QueryMode, float, str]]:
        """낮은 신뢰도일 때 대체 모드 제안

        Args:
            query: 사용자 질의

        Returns:
            (QueryMode, confidence, reason) 튜플 리스트 (신뢰도 높은 순)
        """
        query_lower = query.lower()
        suggestions = []

        # 각 모드별 신뢰도 계산
        # 1. COST 모드 체크
        if self.COST_INTENT_PATTERN.search(query):
            suggestions.append((QueryMode.COST, 0.95, "cost_intent"))

        # 2. SEARCH 모드 체크
        has_list = self.LIST_INTENT_PATTERN.search(query) is not None
        has_search = self.SEARCH_INTENT_PATTERN.search(query) is not None

        if has_list or has_search:
            conf = 0.9 if has_list else 0.85
            reason = "list_intent" if has_list else "search_intent"
            suggestions.append((QueryMode.SEARCH, conf, reason))

        # 3. DOCUMENT 모드 체크
        has_filename = self.filename_re.search(query) is not None
        has_doc_ref = self.DOC_REFERENCE_PATTERN.search(query) is not None
        has_summary = self.SUMMARY_INTENT_PATTERN.search(query) is not None
        has_content = "내용" in query_lower or "미리보기" in query_lower

        if (has_filename or has_doc_ref) and (has_summary or has_content):
            suggestions.append((QueryMode.DOCUMENT, 0.9, "doc_reference+content"))
        elif has_filename or has_doc_ref:
            suggestions.append((QueryMode.DOCUMENT, 0.6, "doc_reference_only"))

        # 4. QA 모드 체크
        has_qa = any(keyword in query_lower for keyword in self.qa_keywords)
        if has_qa:
            suggestions.append((QueryMode.QA, 0.8, "qa_keywords"))

        # 5. 제안이 없으면 QA를 기본으로
        if not suggestions:
            suggestions.append((QueryMode.QA, 0.5, "default"))

        # 신뢰도 높은 순으로 정렬
        suggestions.sort(key=lambda x: x[1], reverse=True)

        return suggestions

    def classify_mode_with_confidence(self, query: str) -> RouteDecision:
        """모드 분류 + 신뢰도 + 의도 플래그 반환 (2025-11-10: RouteDecision 반환)

        Args:
            query: 사용자 질의

        Returns:
            RouteDecision 객체 (모드 + 의도 플래그 + 추출된 파라미터 포함)
        """
        # 기본 분류 수행 (모니터링 포함) - 이제 RouteDecision 반환
        decision = self.classify_mode(query)
        return decision

    def classify_mode_with_retrieval(
        self, query: str, retrieval_results: Any = None
    ) -> RouteDecision:
        """검색 결과를 고려한 모드 분류 (Phase 1: 검색 신뢰도 연동)

        Args:
            query: 사용자 질의
            retrieval_results: HybridRetriever.search() 결과 (score_stats 속성 포함 가능)

        Returns:
            RouteDecision 객체

        Note:
            Phase 1 개선: 검색 신뢰도가 낮으면 SEARCH(list_intent=True)로 하향 조정
        """
        # 기본 모드 분류
        decision = self.classify_mode(query)

        # 검색 결과가 있고 낮은 신뢰도인 경우
        if retrieval_results and self._is_low_confidence(retrieval_results):
            # DOCUMENT 또는 QA → SEARCH로 하향 조정 (안전한 목록 반환)
            if decision.mode in (QueryMode.DOCUMENT, QueryMode.QA):
                logger.warning(
                    f"⚠️ 낮은 검색 신뢰도 감지 → {decision.mode.value} → SEARCH(list_intent=True) 하향 조정"
                )
                return RouteDecision(
                    mode=QueryMode.SEARCH,
                    reason=f"low_conf_from_{decision.mode.value}",
                    confidence=min(decision.confidence, 0.65),
                    list_intent=True,
                    year=decision.year,
                    drafter=decision.drafter,
                )

        return decision

    def classify_mode_with_hits(
        self,
        query: str,
        hits: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[RouteDecision, Optional[List[Dict[str, Any]]]]:
        """검색 결과(hits)를 고려한 모드 분류 + 단일 후보 확정 (2025-11-10: RouteDecision 반환)

        Args:
            query: 사용자 질의
            hits: 검색 결과 리스트 (filename, title 등 포함)

        Returns:
            (RouteDecision, filtered_hits or None)
        """
        q = query.strip()

        # 요약/내용 의도 감지
        wants_content = self.SUMMARY_INTENT_PATTERN.search(q) is not None or "내용" in q.lower()

        if wants_content and hits:
            # 쿼리 정규화
            qn = _norm(q)

            # 검색 결과를 스코어로 정렬
            ranked = sorted(
                hits,
                key=lambda h: _score(qn, _norm(h.get("title") or h.get("filename", ""))),
                reverse=True
            )[:2]  # 상위 2개만

            if ranked:
                top = ranked[0]
                top_score = _score(qn, _norm(top.get("title") or top.get("filename", "")))

                # 단일 후보 확정 조건: 1개만 있거나, 상위 스코어가 0.66 이상
                if len(ranked) == 1 or top_score >= 0.66:
                    logger.info(f"✅ 요약/내용 의도 감지 + 단일 후보 확정 (score={top_score:.2f}) → DOCUMENT 모드")
                    # RouteDecision 생성
                    decision = RouteDecision(
                        mode=QueryMode.DOCUMENT,
                        reason="content_intent_single_candidate",
                        confidence=top_score,
                        content_intent=True
                    )
                    return decision, [top]

        # 기본 분류 (검색 결과 무관)
        decision = self.classify_mode(query)
        return decision, hits
