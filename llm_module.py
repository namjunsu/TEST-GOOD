#!/usr/bin/env python3
"""
LLM 처리 모듈 - Perfect RAG에서 분리된 LLM 관련 기능
2025-09-29 리팩토링

이 모듈은 Qwen/Llama 모델 처리, 프롬프트 관리, 응답 생성 등
LLM 관련 기능을 담당합니다.
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

# LLM 관련 모듈들
try:
    from rag_system.qwen_llm import QwenLLM
    from rag_system.llm_singleton import LLMSingleton
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMModule:
    """LLM 처리 통합 모듈"""

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}
        self.llm = None
        self.model_path = self.config.get('model_path', './models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf')

        # 프롬프트 템플릿들
        self._init_prompts()

        # LLM 초기화 (preload 옵션이 있으면)
        if self.config.get('preload_llm', False):
            self.load_llm()

    def _init_prompts(self):
        """프롬프트 템플릿 초기화"""
        self.prompts = {
            'conversational_system': """당신은 친절하고 유능한 AI 어시스턴트입니다.
사용자의 질문 의도를 정확히 파악하여 도움이 되는 답변을 제공합니다.

중요 원칙:
1. 자연스럽고 대화하듯 답변하세요
2. 템플릿이나 정형화된 형식을 사용하지 마세요
3. 사용자가 실제로 필요로 하는 정보를 제공하세요
4. 추가로 도움이 될 만한 정보가 있다면 자연스럽게 제안하세요
5. 의사결정에 도움이 되는 인사이트를 제공하세요""",

            'summary': """다음 문서를 읽고 사용자 질문에 자연스럽게 답변해주세요.

문서 정보:
{context}

사용자 질문: {query}

답변 방식:
- 핵심 내용을 먼저 간단히 설명
- 중요한 세부사항을 자연스럽게 이어서 설명
- 사용자가 추가로 알면 좋을 정보 제안
- 딱딱한 리스트 형식이 아닌 자연스러운 문장으로 연결""",

            'comparison': """다음 정보를 바탕으로 비교 분석을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 비교 대상들의 주요 차이점을 먼저 설명
- 각각의 장단점을 실용적 관점에서 설명
- 상황에 따른 추천 제공
- "이런 경우엔 A가 좋고, 저런 경우엔 B가 낫다"는 식으로 설명""",

            'recommendation': """다음 정보를 바탕으로 실용적인 추천을 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 가장 적합한 선택을 먼저 제시
- 그 이유를 실용적 관점에서 설명
- 대안이 있다면 함께 언급
- 고려사항이나 주의점 안내""",

            'analysis': """다음 정보를 분석하여 인사이트를 제공해주세요.

정보:
{context}

사용자 질문: {query}

답변 방식:
- 데이터나 정보의 핵심 패턴 파악
- 중요한 트렌드나 변화 설명
- 실무적 시사점 제공
- 향후 고려사항 제안""",

            'smart_summary': """다음 내용을 읽고 핵심만 간단히 3-5줄로 요약하세요.

제목: {title}
내용:
{content}

요약 원칙:
1. 가장 중요한 정보 위주로
2. 구체적인 수치나 날짜 포함
3. 실무적으로 필요한 핵심만
4. 간결하고 명확하게""",

            'fallback': """다음 정보를 바탕으로 사용자 질문에 답변해주세요.

정보:
{context}

질문: {query}

가능한 자연스럽고 도움이 되는 답변을 제공하세요."""
        }

    def load_llm(self) -> bool:
        """LLM 모델 로드 (싱글톤 사용)"""
        if not LLM_AVAILABLE:
            logger.error("LLM modules not available")
            return False

        if self.llm is None:
            try:
                if not LLMSingleton.is_loaded():
                    logger.info("🤖 LLM 모델 최초 로딩 중...")
                else:
                    logger.info("♻️ LLM 모델 재사용")

                start = time.time()
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                elapsed = time.time() - start

                if elapsed > 1.0:
                    logger.info(f"✅ LLM 로드 완료 ({elapsed:.1f}초)")

                return True
            except Exception as e:
                logger.error(f"❌ LLM 로드 실패: {e}")
                return False
        return True

    def generate_response(self, context: str, query: str,
                         intent_type: str = 'general',
                         temperature: float = 0.7,
                         max_tokens: int = 1500) -> str:
        """
        LLM을 사용하여 응답 생성

        Args:
            context: 컨텍스트 정보
            query: 사용자 질문
            intent_type: 의도 유형 (summary, comparison, recommendation 등)
            temperature: 생성 온도
            max_tokens: 최대 토큰 수

        Returns:
            생성된 응답
        """
        # LLM 로드 확인
        if not self.load_llm():
            return self._generate_fallback_response_simple(context, query)

        # 프롬프트 선택
        if intent_type in self.prompts:
            user_prompt = self.prompts[intent_type].format(
                context=context[:3000],  # 컨텍스트 제한
                query=query
            )
        else:
            user_prompt = self.prompts['fallback'].format(
                context=context[:3000],
                query=query
            )

        try:
            # LLM 응답 생성
            response = self.llm.generate_response(
                question=query,
                context_chunks=[{'content': context, 'title': 'Context', 'filename': ''}]
            )

            # 응답 후처리
            return self._format_response(response)

        except Exception as e:
            logger.error(f"LLM 응답 생성 오류: {e}")
            return self._generate_fallback_response_simple(context, query)

    def generate_smart_summary(self, text: str, title: str = "") -> str:
        """
        스마트 요약 생성

        Args:
            text: 요약할 텍스트
            title: 문서 제목

        Returns:
            요약된 텍스트
        """
        if not self.load_llm():
            return self._extract_key_sentences(text, 3)

        try:
            user_prompt = self.prompts['smart_summary'].format(
                title=title or "문서",
                content=text[:2000]
            )

            response = self.llm.generate_response(
                question=user_prompt,
                context_chunks=[{'content': text[:2000], 'title': title or '문서', 'filename': ''}]
            )

            return self._format_response(response)

        except Exception as e:
            logger.error(f"요약 생성 오류: {e}")
            return self._extract_key_sentences(text, 3)

    def generate_conversational_response(self, context: str, query: str,
                                        intent: Dict[str, Any]) -> str:
        """
        자연스러운 대화형 응답 생성

        Args:
            context: 문서 컨텍스트
            query: 사용자 질문
            intent: 의도 정보

        Returns:
            대화형 응답
        """
        intent_type = intent.get('type', 'general')
        confidence = intent.get('confidence', 0.5)

        # 신뢰도가 낮으면 일반 응답
        if confidence < 0.3:
            intent_type = 'fallback'

        return self.generate_response(
            context=context,
            query=query,
            intent_type=intent_type,
            temperature=0.7
        )

    def generate_analysis_response(self, data: Dict[str, Any], query: str) -> str:
        """
        데이터 분석 응답 생성

        Args:
            data: 분석할 데이터
            query: 사용자 질문

        Returns:
            분석 응답
        """
        # 데이터를 텍스트로 변환
        context = self._format_data_for_analysis(data)

        return self.generate_response(
            context=context,
            query=query,
            intent_type='analysis',
            temperature=0.5
        )

    def prepare_context(self, content: str, max_length: int = 2000) -> str:
        """
        LLM 입력을 위한 컨텍스트 준비

        Args:
            content: 원본 콘텐츠
            max_length: 최대 길이

        Returns:
            준비된 컨텍스트
        """
        if not content:
            return ""

        # 길이 제한
        if len(content) <= max_length:
            return content

        # 중요한 부분 추출
        # 시작과 끝 부분을 포함
        start_len = max_length // 2
        end_len = max_length - start_len

        prepared = content[:start_len] + "\n...\n" + content[-end_len:]

        return prepared

    def _format_response(self, raw_response: str) -> str:
        """응답 포맷팅"""
        if not raw_response:
            return ""

        # 불필요한 공백 제거
        response = raw_response.strip()

        # 중복된 줄바꿈 제거
        response = re.sub(r'\n{3,}', '\n\n', response)

        # 템플릿 마커 제거
        markers = ['답변:', '응답:', 'Answer:', 'Response:']
        for marker in markers:
            if response.startswith(marker):
                response = response[len(marker):].strip()

        return response

    def _format_data_for_analysis(self, data: Dict[str, Any]) -> str:
        """분석을 위한 데이터 포맷팅"""
        lines = []

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  - {sub_key}: {sub_value}")
            elif isinstance(value, list):
                lines.append(f"{key}: {', '.join(map(str, value[:10]))}")
            else:
                lines.append(f"{key}: {value}")

        return '\n'.join(lines)

    def _extract_key_sentences(self, text: str, num_sentences: int = 3) -> str:
        """핵심 문장 추출 (폴백용)"""
        if not text:
            return ""

        # 문장 분리
        sentences = re.split(r'[.!?]\s+', text)

        # 길이가 긴 문장 우선 선택
        valid_sentences = [s for s in sentences if len(s) > 20]
        valid_sentences.sort(key=len, reverse=True)

        # 상위 N개 선택
        key_sentences = valid_sentences[:num_sentences]

        return '. '.join(key_sentences) + '.'

    def _generate_fallback_response_simple(self, context: str, query: str) -> str:
        """간단한 폴백 응답 생성"""
        if not context:
            return "죄송합니다. 관련 정보를 찾을 수 없습니다."

        # 컨텍스트에서 핵심 정보 추출
        lines = context.split('\n')
        relevant_lines = []

        query_keywords = query.lower().split()

        for line in lines[:20]:  # 처음 20줄만 확인
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in query_keywords):
                relevant_lines.append(line)

        if relevant_lines:
            response = "찾은 정보:\n\n"
            response += '\n'.join(relevant_lines[:5])
        else:
            response = f"다음은 관련 문서의 내용입니다:\n\n{context[:500]}"

        return response

    def get_prompt_template(self, intent_type: str) -> str:
        """프롬프트 템플릿 반환"""
        return self.prompts.get(intent_type, self.prompts['fallback'])

    def update_prompt_template(self, intent_type: str, template: str):
        """프롬프트 템플릿 업데이트"""
        self.prompts[intent_type] = template

    def clear_llm(self):
        """LLM 인스턴스 정리"""
        self.llm = None
        logger.info("LLM instance cleared")