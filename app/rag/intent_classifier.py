"""
LLM 기반 쿼리 의도 분류기
2025-12-23

정규식 패턴 매칭 대신 LLM을 사용하여 쿼리 의도를 분류합니다.
표현 변형에 강하고, 새 패턴 추가 없이 다양한 질의를 처리할 수 있습니다.

사용 예:
    classifier = IntentClassifier(llm)
    result = classifier.classify("남준수가 쓴 문서 다 보여줘")
    # result: {"mode": "YEAR_SUMMARY", "drafter": "남준수", ...}
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.logging import get_logger
from app.rag.router_models import QueryMode, RouteDecision
from config.constants import RouterConfig

logger = get_logger(__name__)

# 의도 분류 프롬프트 (한국어)
INTENT_CLASSIFICATION_PROMPT = """다음 질문의 의도를 분석하여 JSON으로 분류해주세요.

## 가능한 mode 값:
- COST: 비용/금액/총액/합계를 묻는 질문 (예: "얼마야?", "총액은?", "비용 합계")
- SEARCH: 문서를 찾거나 목록을 보여달라는 질문 (예: "문서 찾아줘", "목록 보여줘", "검색해줘")
- DOCUMENT: 특정 문서의 내용/요약을 보여달라는 질문 (예: "이 문서 요약해줘", "내용 알려줘")
- YEAR_SUMMARY: 특정 연도/기간의 문서들을 종합 정리해달라는 질문 (예: "2024년 문서 정리해줘", "올해 문서들 요약")
- QA: 일반 질문/답변 (위에 해당 안 되는 경우)

## 추출할 필드:
- year: 연도 (숫자, 예: 2024). "올해"는 2025, "작년"은 2024
- drafter: 기안자/작성자 이름 (한글 2-3자)
- filename: 파일명 (있는 경우)

## 주의:
- JSON만 출력하세요. 설명 없이 JSON만.
- 확실하지 않은 필드는 null로 설정

## 질문:
{query}

## JSON 출력:"""


@dataclass
class IntentResult:
    """의도 분류 결과"""
    mode: QueryMode
    confidence: float
    year: Optional[int] = None
    drafter: Optional[str] = None
    filename: Optional[str] = None
    raw_response: Optional[str] = None


class IntentClassifier:
    """LLM 기반 쿼리 의도 분류기"""

    def __init__(self, llm: Any):
        """
        Args:
            llm: LLM 인스턴스 (QwenLLM 또는 VllmLLM)
        """
        self.llm = llm
        self._mode_map = {
            "cost": QueryMode.COST,
            "search": QueryMode.SEARCH,
            "document": QueryMode.DOCUMENT,
            "year_summary": QueryMode.YEAR_SUMMARY,
            "qa": QueryMode.QA,
        }

    def classify(self, query: str) -> IntentResult:
        """쿼리 의도 분류

        Args:
            query: 사용자 질문

        Returns:
            IntentResult: 분류 결과
        """
        if not query or not query.strip():
            return IntentResult(mode=QueryMode.QA, confidence=0.5)

        try:
            prompt = INTENT_CLASSIFICATION_PROMPT.format(query=query)
            response = self._generate(prompt)
            result = self._parse_response(response)
            logger.info(f"🧠 LLM 의도 분류: query='{query[:50]}...' → mode={result.mode.value}")
            return result
        except Exception as e:
            logger.warning(f"⚠️ LLM 의도 분류 실패: {e}, fallback to QA")
            return IntentResult(mode=QueryMode.QA, confidence=0.3, raw_response=str(e))

    def _generate(self, prompt: str) -> str:
        """LLM 호출 (짧은 응답용)"""
        # vLLM vs llama_cpp 분기
        is_vllm = hasattr(self.llm, "__class__") and "Vllm" in self.llm.__class__.__name__

        if is_vllm:
            # vLLM: generate_response 사용
            response = self.llm.generate_response(prompt, [], max_tokens=150)
            if hasattr(response, "answer"):
                return response.answer
            return str(response)
        else:
            # llama_cpp: create_chat_completion 직접 호출
            llm_instance = getattr(self.llm, "llm", None)
            if llm_instance and hasattr(llm_instance, "create_chat_completion"):
                result = llm_instance.create_chat_completion(
                    messages=[
                        {"role": "system", "content": "당신은 질문 의도 분류 전문가입니다. JSON만 출력하세요."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=150,
                    temperature=0.1,
                )
                return result["choices"][0]["message"]["content"]
            else:
                # fallback: generate_response
                response = self.llm.generate_response(prompt, [])
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

    def _parse_response(self, response: str) -> IntentResult:
        """LLM 응답 파싱"""
        # JSON 추출 (응답에 다른 텍스트가 섞여 있을 수 있음)
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if not json_match:
            logger.warning(f"⚠️ JSON 파싱 실패: {response[:100]}")
            return IntentResult(mode=QueryMode.QA, confidence=0.3, raw_response=response)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 디코드 실패: {e}")
            return IntentResult(mode=QueryMode.QA, confidence=0.3, raw_response=response)

        # mode 파싱
        mode_str = data.get("mode", "qa").lower().strip()
        mode = self._mode_map.get(mode_str, QueryMode.QA)

        # 연도 파싱
        year = data.get("year")
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        # drafter 파싱
        drafter = data.get("drafter")
        if drafter:
            drafter = str(drafter).strip()
            if len(drafter) < 2 or len(drafter) > 4:
                drafter = None

        # filename 파싱
        filename = data.get("filename")
        if filename:
            filename = str(filename).strip()

        return IntentResult(
            mode=mode,
            confidence=0.9,  # LLM 분류는 높은 신뢰도
            year=year,
            drafter=drafter,
            filename=filename,
            raw_response=response,
        )

    def to_route_decision(self, result: IntentResult, query: str) -> RouteDecision:
        """IntentResult를 RouteDecision으로 변환"""
        return RouteDecision(
            mode=result.mode,
            reason="llm_intent_classifier",
            confidence=result.confidence,
            year=result.year,
            drafter=result.drafter,
            content_intent=result.mode in (QueryMode.DOCUMENT, QueryMode.YEAR_SUMMARY),
            list_intent=result.mode in (QueryMode.SEARCH, QueryMode.YEAR_SUMMARY),
            cost_intent=result.mode == QueryMode.COST,
        )


# 싱글톤 인스턴스 (lazy initialization)
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier(llm: Any = None) -> Optional[IntentClassifier]:
    """IntentClassifier 싱글톤 인스턴스 반환

    Args:
        llm: LLM 인스턴스 (최초 호출 시 필수)

    Returns:
        IntentClassifier 또는 None (LLM 없으면)
    """
    global _classifier_instance
    if _classifier_instance is None and llm is not None:
        _classifier_instance = IntentClassifier(llm)
    return _classifier_instance
