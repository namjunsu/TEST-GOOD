"""
쿼리 모드 라우터
2025-11-01

질의 의도를 분석하여 Q&A 모드 vs 문서 미리보기 모드를 결정합니다.

규칙:
- Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모드 우선
- 파일명만 있고 Q&A 의도가 없으면 미리보기 모드
- 고신뢰 + 장비 용어 → DOC_ANCHORED 모드 (단일 문서 앵커)
"""

import os
import re
from enum import Enum
from pathlib import Path
import yaml
from typing import Dict, Any
from dataclasses import dataclass

from app.core.logging import get_logger
from typing import List, Tuple, Optional

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


# 장비/사양 도메인 용어 (DVR, 카메라 등)
DEVICE_TERMS = (
    "dvr", "hrd-", "hrd442", "hrd-442", "hanwha", "한화", "nvr",
    "녹화", "모니터", "교체", "ip ", "카메라", "eng", "마이크"
)

# 환경변수로 조정 가능한 임계값
FORCE_TOP1_MIN = float(os.getenv("ROUTER_FORCE_DOC_TOP1_MIN", "15.0"))
FORCE_DELTA12_MIN = float(os.getenv("ROUTER_FORCE_DOC_DELTA12_MIN", "3.0"))
FORCE_RATIO12_MIN = float(os.getenv("ROUTER_FORCE_DOC_RATIO12_MIN", "1.35"))


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


def _has_device_terms(query: str) -> bool:
    """장비/사양 도메인 용어 포함 여부 체크"""
    ql = query.lower()
    return any(term in ql for term in DEVICE_TERMS)


def _should_force_doc_anchor(query: str, score_stats: dict) -> bool:
    """DOC_ANCHORED 모드 강제 조건 체크

    Args:
        query: 사용자 질의
        score_stats: 검색 결과 점수 통계 dict

    Returns:
        True if should force DOC_ANCHORED mode
    """
    # 장비 용어 포함 시 무조건 DOC_ANCHORED
    if _has_device_terms(query):
        logger.info(f"🎯 DOC_ANCHORED 강제: 장비 용어 감지")
        return True

    # 고신뢰 점수 조건 (Top-1 우세)
    top1 = score_stats.get("top1", 0.0)
    delta12 = score_stats.get("delta12", 0.0)
    top2 = score_stats.get("top2", 0.0)
    ratio12 = top1 / max(top2, 1e-9)

    if top1 >= FORCE_TOP1_MIN and (delta12 >= FORCE_DELTA12_MIN or ratio12 >= FORCE_RATIO12_MIN):
        logger.info(
            f"🎯 DOC_ANCHORED 강제: 고신뢰 점수 "
            f"(top1={top1:.2f}, delta12={delta12:.2f}, ratio12={ratio12:.2f})"
        )
        return True

    return False


class QueryMode(Enum):
    """쿼리 모드"""

    COST_SUM = "cost_sum"  # 비용 합계 직접 조회 모드 (최우선)
    PREVIEW = "preview"  # 문서 미리보기 모드 (파일 전문)
    LIST = "list"  # 목록 검색 모드 (다건 카드 표시)
    LIST_FIRST = "list_first"  # 낮은 신뢰도 → 목록 우선 표시 모드
    DOC_ANCHORED = "doc_anchored"  # 단일 문서 앵커 모드 (Top-1 고정)
    SUMMARY = "summary"  # 내용 요약 모드 (5줄 섹션)
    SEARCH = "search"  # 문서 검색 모드 (문서 리스트 반환)
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
        r"(기안|작성|문서|구매|소모품|발주|납품).*(총액|금액|비용|합계|총계)"
        r"|"
        # Pattern 5: NEW - compound cost phrases (e.g., "비용 합계", "합계 금액")
        r"(비용|구매)\s*(합계|총액)"
        r"|"
        r"(합계|총액)\s*(금액|비용)"
        r")",
        re.IGNORECASE,
    )

    # 목록 검색 패턴 (연도/작성자 + 찾기)
    LIST_INTENT_PATTERN = re.compile(
        r"(\d{4}년?|[가-힣]{2,4}(가|이)?).*(찾아|검색|리스트|목록|보여|알려)",
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
        r"(있어\??|있나요|있는지))",     # "있어?", "있나요"
        re.IGNORECASE,
    )

    # 문서 지시어 패턴 (이문서, 이 문서, 해당 문서 등)
    DOC_REFERENCE_PATTERN = re.compile(
        r"(이\s?문서|해당\s?문서|이\s?파일|그\s?문서)",
        re.IGNORECASE,
    )

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.qa_keywords = self.config.get("mode_routing", {}).get(
            "qa_intent_keywords", []
        )
        self.preview_keywords = self.config.get("mode_routing", {}).get(
            "preview_only_keywords", []
        )
        self.filename_pattern = self.config.get("mode_routing", {}).get(
            "filename_pattern", r"\S+\.pdf"
        )

        # Low-confidence 가드레일 설정 (환경 변수)
        self.low_conf_delta = float(os.getenv("LOW_CONF_DELTA", "0.05"))
        self.low_conf_min_hits = int(os.getenv("LOW_CONF_MIN_HITS", "1"))

        logger.info(
            f"📋 모드 라우터 초기화: QA 키워드 {len(self.qa_keywords)}개, 미리보기 키워드 {len(self.preview_keywords)}개, "
            f"Low-conf delta={self.low_conf_delta}, min_hits={self.low_conf_min_hits}"
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
                logger.info(f"✓ 설정 로드: {config_path}")
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

    def classify_mode(self, query: str) -> QueryMode:
        """쿼리 모드 자동 분류 및 라우팅

        사용자 질의를 분석하여 가장 적절한 QueryMode로 자동 라우팅합니다.
        패턴 매칭과 키워드 감지를 통해 우선순위에 따라 모드를 결정합니다.

        우선순위 (높음 → 낮음):
            1. COST_SUM: 비용 합계 질의 (예: "합계", "총 비용")
            2. PREVIEW: 파일명 + 미리보기 의도
            3. LIST: 연도/작성자 기반 목록 검색
            4. SEARCH: 키워드 기반 문서 검색 (NEW)
            5. SUMMARY: 문서 지시어 + 요약 의도
            6. QA: Q&A 의도 키워드 또는 기본값

        모드 판단 기준:
            COST_SUM: COST_INTENT_PATTERN 매칭
            PREVIEW: 파일명 패턴 + (미리보기 키워드 or "미리보기" 단어)
            LIST: LIST_INTENT_PATTERN 매칭 & 요약 의도 없음
            SEARCH: SEARCH_INTENT_PATTERN 매칭
                    (예: "찾아줘", "검색", "관련 문서", "있어?")
            SUMMARY: (파일명 or 문서 지시어 or 문서 타입) & 요약 의도
            QA: qa_keywords 매칭 또는 모든 조건 불만족 시 기본값

        Args:
            query (str): 사용자 질의.
                예: "2024년 남준수 문서 전부" → LIST
                    "중계차 렌즈 문서 찾아줘" → SEARCH
                    "이 문서 요약해줘" → SUMMARY
                    "비용 합계는?" → COST_SUM

        Returns:
            QueryMode: 분류된 쿼리 모드 (COST_SUM, PREVIEW, LIST,
                      SEARCH, SUMMARY, QA 중 하나)

        Example:
            >>> router = QueryRouter()
            >>> router.classify_mode("중계차 카메라 문서 찾아줘")
            QueryMode.SEARCH
            >>> router.classify_mode("2024년 남준수 문서 전부")
            QueryMode.LIST
            >>> router.classify_mode("이 문서 요약해줘")
            QueryMode.SUMMARY

        Note:
            - 로깅을 통해 결정 과정 추적 가능
            - 모든 조건 불만족 시 QueryMode.QA 반환 (fallback)
        """
        query_lower = query.lower()

        # 0. 비용 질의 체크 (최우선)
        if self.COST_INTENT_PATTERN.search(query):
            logger.info("🎯 모드 결정: COST_SUM (비용 질의 감지)")
            return QueryMode.COST_SUM

        # 1. 파일명 패턴 체크
        has_filename = (
            re.search(self.filename_pattern, query, re.IGNORECASE) is not None
        )

        # 2. 문서 지시어 체크 (이문서, 해당 문서 등)
        has_doc_reference = self.DOC_REFERENCE_PATTERN.search(query) is not None

        # 2.1. 문서 타입 키워드 체크 (검토서, 기안서, 견적서 등)
        has_doc_type_keyword = bool(re.search(
            r"(검토서|기안서|견적서|제안서|보고서|계획서|공문|발주서|납품서|영수증)",
            query, re.IGNORECASE
        ))

        # 3. 미리보기 전용 키워드 체크
        has_preview_intent = any(
            keyword in query_lower for keyword in self.preview_keywords
        )

        # 4. PREVIEW 모드 (파일명 + 미리보기 의도)
        if has_filename and (has_preview_intent or "미리보기" in query_lower):
            logger.info("🎯 모드 결정: PREVIEW (파일명 + 미리보기)")
            return QueryMode.PREVIEW

        # 5. LIST 모드 (연도/작성자 + 찾기) - 요약 의도가 없을 때만
        if self.LIST_INTENT_PATTERN.search(query) and not self.SUMMARY_INTENT_PATTERN.search(query):
            logger.info("🎯 모드 결정: LIST (목록 검색)")
            return QueryMode.LIST

        # 6. SUMMARY 모드 (파일명/문서지시어/문서타입 + 요약 의도)
        # 수정: 문서 타입 키워드도 문서 참조로 인정
        if (has_filename or has_doc_reference or has_doc_type_keyword) and self.SUMMARY_INTENT_PATTERN.search(query):
            logger.info("🎯 모드 결정: SUMMARY (내용 요약)")
            return QueryMode.SUMMARY

        # 7. SEARCH 모드 (문서 검색 의도)
        # "중계차 카메라 렌즈관련 문서 찾아줘", "유인혁 기안서 문서 찾아줘" 등
        if self.SEARCH_INTENT_PATTERN.search(query):
            logger.info("🎯 모드 결정: SEARCH (문서 검색)")
            return QueryMode.SEARCH

        # 8. Q&A 의도 키워드 체크 (레거시 호환)
        has_qa_intent = any(keyword in query_lower for keyword in self.qa_keywords)

        if has_qa_intent:
            logger.info("🎯 모드 결정: QA (의도 키워드 감지)")
            return QueryMode.QA

        # 9. 파일명만 있으면 PREVIEW (레거시 호환)
        if has_filename:
            logger.info("🎯 모드 결정: PREVIEW (파일명만 존재)")
            return QueryMode.PREVIEW

        # 10. 기본: Q&A 모드
        logger.info("🎯 모드 결정: QA (기본)")
        return QueryMode.QA

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
        has_filename = (
            re.search(self.filename_pattern, query, re.IGNORECASE) is not None
        )
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

    def classify_mode_with_retrieval(
        self,
        query: str,
        retrieval_results: Any = None
    ) -> QueryMode:
        """검색 결과를 고려한 모드 분류 (DOC_ANCHORED + low-confidence 가드레일 포함)

        Args:
            query: 사용자 질의
            retrieval_results: HybridRetriever.search() 결과 (score_stats 속성 포함 가능)

        Returns:
            QueryMode (COST_SUM, PREVIEW, LIST, LIST_FIRST, DOC_ANCHORED, SUMMARY, QA 중 하나)
        """
        # score_stats 추출
        score_stats = getattr(retrieval_results, "score_stats", {}) or {}

        # 1. DOC_ANCHORED 강제 체크 (최우선)
        if retrieval_results is not None and _should_force_doc_anchor(query, score_stats):
            return QueryMode.DOC_ANCHORED

        # 2. Low-confidence 체크
        if retrieval_results is not None and self._is_low_confidence(retrieval_results):
            return QueryMode.LIST_FIRST

        # 3. 기본 모드 분류
        return self.classify_mode(query)

    def classify_mode_with_hits(
        self,
        query: str,
        hits: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[QueryMode, Optional[List[Dict[str, Any]]]]:
        """검색 결과(hits)를 고려한 모드 분류 + 단일 후보 확정

        Args:
            query: 사용자 질의
            hits: 검색 결과 리스트 (filename, title 등 포함)

        Returns:
            (QueryMode, filtered_hits or None)
        """
        q = query.strip()

        # 요약 의도 감지
        wants_summary = self.SUMMARY_INTENT_PATTERN.search(q) is not None

        if wants_summary and hits:
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
                    logger.info(f"✅ 요약 의도 감지 + 단일 후보 확정 (score={top_score:.2f}) → SUMMARY 모드")
                    return QueryMode.SUMMARY, [top]

        # 기본 분류 (검색 결과 무관)
        mode = self.classify_mode(query)
        return mode, hits
