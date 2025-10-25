#!/usr/bin/env python3
"""
from app.core.logging import get_logger
Intent Module - 사용자 의도 분석 및 분류 시스템
사용자의 질문 의도를 분석하고 적절한 응답 스타일을 결정합니다.
한국어 처리를 지원하며 다양한 질문 유형을 인식합니다.
"""

import re
from typing import Dict, List, Optional, Any

# 로깅 시스템
try:
    logger = get_logger()
except ImportError:
    logger = get_logger(__name__)

# LLMModule 가져오기 (선택적)
try:
    from llm_module import LLMModule
except ImportError:
    LLMModule = None


class IntentModule:
    """사용자 의도 분석 및 응답 생성을 담당하는 모듈"""

    def __init__(self, llm_module=None):
        """
        IntentModule 초기화

        Args:
            llm_module: LLMModule 인스턴스 (선택적)
        """
        self.llm_module = llm_module
        if logger:
            logger.info("✅ IntentModule 초기화 완료")

    def analyze_user_intent(self, query: str) -> Dict[str, Any]:
        """
        사용자 질문 의도를 자연스럽게 분석

        Args:
            query: 사용자 질문

        Returns:
            Dict: 의도 분석 결과
        """
        query_lower = query.lower()

        intent = {
            'type': 'general',
            'needs_detail': False,
            'wants_comparison': False,
            'wants_recommendation': False,
            'is_urgent': False,
            'tone': 'informative',
            'context_keywords': [],
            'response_style': 'conversational'
        }

        # 의도 파악
        if any(word in query_lower for word in ['요약', '정리', '알려', '설명']):
            intent['type'] = 'summary'
            intent['needs_detail'] = True
        if any(word in query_lower for word in ['비교', '차이', '어떤게 나은', '뭐가 좋']):
            intent['type'] = 'comparison'
            intent['wants_comparison'] = True
            intent['wants_recommendation'] = True
        if any(word in query_lower for word in ['추천', '권장', '어떻게', '방법']):
            intent['type'] = 'recommendation'
            intent['wants_recommendation'] = True
        if any(word in query_lower for word in ['긴급', '빨리', '급해', '바로']):
            intent['type'] = 'urgent'
            intent['is_urgent'] = True
            intent['tone'] = 'direct'
        if any(word in query_lower for word in ['얼마', '비용', '가격', '금액']):
            intent['type'] = 'cost'
            intent['needs_detail'] = True
        if any(word in query_lower for word in ['문제', '고장', '수리', '장애']):
            intent['type'] = 'problem'
            intent['wants_recommendation'] = True

        # 컨텍스트 키워드 추출
        important_words = ['DVR', '중계차', '카메라', '삼각대', '방송', '장비', '구매', '수리', '교체', '업그레이드']
        intent['context_keywords'] = [word for word in important_words if word.lower() in query_lower]

        # 응답 스타일 결정
        if '?' in query:
            intent['response_style'] = 'explanatory'
        if any(word in query_lower for word in ['해줘', '부탁', '좀']):
            intent['response_style'] = 'helpful'

        return intent

    def classify_search_intent(self, query: str) -> str:
        """
        검색 의도 분류 - 항상 document 모드 반환

        Args:
            query: 검색 쿼리

        Returns:
            str: 검색 의도 ('document' 고정)
        """
        return 'document'  # Asset 모드 제거, 항상 문서 검색

    def generate_conversational_response(self, context: str, query: str, intent: Dict[str, Any],
                                       pdf_info: Dict[str, Any] = None) -> str:
        """
        자연스럽고 대화형 응답 생성

        Args:
            context: 문서 컨텍스트
            query: 사용자 질문
            intent: 의도 분석 결과
            pdf_info: PDF 정보 (선택적)

        Returns:
            str: 생성된 응답
        """
        # LLMModule을 사용하여 응답 생성
        if self.llm_module:
            try:
                response = self.llm_module.generate_conversational_response(
                    context=context[:3000],  # 컨텍스트 제한
                    query=query,
                    intent=intent
                )

                # 추가 컨텍스트나 추천 사항 자연스럽게 추가
                if intent.get('wants_recommendation') and '추천' not in response:
                    response += "\n\n참고로, 이와 관련해서 추가로 검토하시면 좋을 사항들도 있습니다. 필요하시면 말씀해 주세요."

                return response
            except Exception as e:
                if logger:
                    logger.error(f"LLMModule 응답 생성 오류: {e}")
                return self.generate_fallback_response(context, query, intent)

        # LLMModule이 없으면 기존 방식 사용
        return self._generate_llm_response(context, query, intent)

    def _generate_llm_response(self, context: str, query: str, intent: Dict[str, Any]) -> str:
        """
        LLM을 사용한 응답 생성 (LLMModule이 없을 때)

        Args:
            context: 문서 컨텍스트
            query: 사용자 질문
            intent: 의도 분석 결과

        Returns:
            str: 생성된 응답
        """
        # LLM에게 자연스러운 대화형 응답을 요청하는 프롬프트
        system_prompt = """당신은 친절하고 유능한 AI 어시스턴트입니다.
사용자의 질문 의도를 정확히 파악하여 도움이 되는 답변을 제공합니다.

중요 원칙:
1. 자연스럽고 대화하듯 답변하세요
2. 템플릿이나 정형화된 형식을 사용하지 마세요
3. 사용자가 실제로 필요로 하는 정보를 제공하세요
4. 추가로 도움이 될 만한 정보가 있다면 자연스럽게 제안하세요
5. 의사결정에 도움이 되는 인사이트를 제공하세요"""

        # 의도에 따른 프롬프트 생성
        user_prompt = self._create_intent_based_prompt(context, query, intent)

        # 여기서는 실제 LLM 호출 대신 기본 응답을 반환
        # 실제 구현에서는 LLM API를 호출해야 함
        return self.generate_fallback_response(context, query, intent)

    def _create_intent_based_prompt(self, context: str, query: str, intent: Dict[str, Any]) -> str:
        """
        의도에 따른 프롬프트 생성

        Args:
            context: 문서 컨텍스트
            query: 사용자 질문
            intent: 의도 분석 결과

        Returns:
            str: 생성된 프롬프트
        """
        if intent['type'] == 'summary':
            return f"""다음 문서를 읽고 사용자 질문에 자연스럽게 답변해주세요.

문서 정보:
{context}

사용자 질문: {query}

답변 방식:
- 핵심 내용을 먼저 간단히 설명
- 중요한 세부사항을 자연스럽게 이어서 설명
- 사용자가 추가로 알면 좋을 정보 제안
- 딱딱한 리스트 형식이 아닌 자연스러운 문장으로 연결"""

        elif intent['type'] == 'comparison':
            return f"""다음 정보를 바탕으로 비교 분석을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 비교 대상들의 주요 차이점을 먼저 설명
- 각각의 장단점을 실용적 관점에서 설명
- 상황에 따른 추천 제공
- "이런 경우엔 A가 좋고, 저런 경우엔 B가 낫다"는 식으로 설명"""

        elif intent['type'] == 'recommendation':
            return f"""다음 정보를 바탕으로 실용적인 추천을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 추천 사항을 명확하게 제시
- 추천 이유를 논리적으로 설명
- 고려사항이나 주의점도 함께 언급
- 대안이 있다면 간단히 소개"""

        elif intent['type'] == 'cost':
            return f"""다음 정보에서 비용 관련 내용을 찾아 설명해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 구체적인 금액을 먼저 제시
- 비용 구성이나 내역 설명
- 비용 대비 가치나 효과 언급
- 예산 관련 조언이 있다면 추가"""

        elif intent['is_urgent']:
            return f"""다음 정보를 바탕으로 빠르고 명확한 답변을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 핵심 답변을 먼저 제시
- 즉시 필요한 행동사항 명시
- 불필요한 설명은 생략하고 간결하게
- 긴급상황 해결에 집중"""

        else:
            return f"""다음 정보를 바탕으로 사용자 질문에 답변해주세요.

정보:
{context}

사용자 질문: {query}

자연스럽고 도움이 되는 답변을 제공해주세요."""

    def generate_fallback_response(self, context: str, query: str, intent: Dict[str, Any]) -> str:
        """
        LLM 실패 시 폴백 응답 생성

        Args:
            context: 문서 컨텍스트
            query: 사용자 질문
            intent: 의도 분석 결과

        Returns:
            str: 폴백 응답
        """
        # 컨텍스트에서 핵심 정보 추출
        lines = context.split('\n')
        key_info = []

        for line in lines:
            if any(keyword in line for keyword in ['금액', '비용', '원', '제목', '기안', '날짜']):
                key_info.append(line.strip())

        response = f"문서를 확인한 결과, "

        if intent['type'] == 'summary':
            response += f"요청하신 내용은 다음과 같습니다. "
            if key_info:
                response += ' '.join(key_info[:3])
        elif intent['type'] == 'cost':
            cost_info = [line for line in key_info if '원' in line or '금액' in line]
            if cost_info:
                response += f"비용 관련 정보입니다. {cost_info[0]}"
            else:
                response += "비용 관련 정보를 찾고 있습니다."
        else:
            if key_info:
                response += f"관련 정보를 찾았습니다. {key_info[0]}"
            else:
                response += "요청하신 정보와 관련된 내용을 검토하고 있습니다."

        return response

    def extract_key_sentences(self, content: str, num_sentences: int = 5) -> List[str]:
        """
        핵심 문장 추출 헬퍼

        Args:
            content: 문서 내용
            num_sentences: 추출할 문장 수

        Returns:
            List[str]: 핵심 문장들
        """
        if not content:
            return []

        # 문장 분리
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_sentences:
            return sentences

        # 키워드 기반 중요도 계산
        important_keywords = ['결정', '승인', '구매', '계약', '예산', '진행', '완료']
        scored_sentences = []

        for sentence in sentences:
            score = sum(1 for keyword in important_keywords if keyword in sentence)
            scored_sentences.append((sentence, score))

        # 점수 순으로 정렬하고 상위 문장 반환
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        return [sentence for sentence, _ in scored_sentences[:num_sentences]]