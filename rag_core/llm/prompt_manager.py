"""
프롬프트 관리 모듈
==================

다양한 프롬프트 템플릿을 관리하고 생성합니다.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from ..config import RAGConfig

logger = logging.getLogger(__name__)


class PromptManager:
    """프롬프트 관리 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.templates = {}
        self.custom_prompts = {}

        # 기본 템플릿 로드
        self._load_default_templates()

        # 커스텀 프롬프트 로드
        self._load_custom_prompts()

    def _load_default_templates(self) -> None:
        """기본 프롬프트 템플릿 로드"""

        # RAG 질의응답 템플릿
        self.templates['rag_qa'] = """당신은 한국어 문서를 분석하는 전문가입니다.

주어진 컨텍스트를 바탕으로 질문에 정확하고 도움이 되는 답변을 제공하세요.

컨텍스트:
{context}

질문: {question}

답변 시 다음 사항을 준수하세요:
1. 컨텍스트에 있는 정보만 사용하여 답변하세요
2. 추측하지 말고 확실한 정보만 제공하세요
3. 한국어로 자연스럽게 답변하세요
4. 핵심 내용을 명확하게 전달하세요

답변:"""

        # 요약 템플릿
        self.templates['summarize'] = """다음 문서를 간결하게 요약해주세요.

문서:
{document}

요약 시 다음 사항을 포함하세요:
1. 문서의 주요 내용
2. 핵심 날짜와 숫자
3. 중요한 결정사항이나 결과
4. 관련 담당자나 부서

요약:"""

        # 정보 추출 템플릿
        self.templates['extract_info'] = """다음 문서에서 요청된 정보를 추출하세요.

문서:
{document}

추출할 정보:
{info_type}

형식:
- 명확하고 구조화된 형태로 제시
- 불필요한 정보는 제외
- 한국어로 작성

추출 결과:"""

        # 대화형 응답 템플릿
        self.templates['conversational'] = """당신은 친근하고 전문적인 AI 어시스턴트입니다.

사용자의 질문에 자연스럽고 도움이 되는 답변을 제공하세요.

이전 대화:
{history}

컨텍스트:
{context}

사용자: {question}

어시스턴트:"""

        # 비교 분석 템플릿
        self.templates['compare'] = """다음 문서들을 비교 분석하세요.

문서 1:
{doc1}

문서 2:
{doc2}

비교 항목:
1. 공통점
2. 차이점
3. 주요 변경사항
4. 시사점

비교 분석:"""

    def _load_custom_prompts(self) -> None:
        """커스텀 프롬프트 로드"""
        custom_path = self.config.cache_dir / "custom_prompts.json"

        if custom_path.exists():
            try:
                with open(custom_path, 'r', encoding='utf-8') as f:
                    self.custom_prompts = json.load(f)
                logger.info(f"Loaded {len(self.custom_prompts)} custom prompts")
            except Exception as e:
                logger.error(f"Failed to load custom prompts: {e}")

    def save_custom_prompts(self) -> None:
        """커스텀 프롬프트 저장"""
        custom_path = self.config.cache_dir / "custom_prompts.json"

        try:
            custom_path.parent.mkdir(parents=True, exist_ok=True)
            with open(custom_path, 'w', encoding='utf-8') as f:
                json.dump(self.custom_prompts, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(self.custom_prompts)} custom prompts")
        except Exception as e:
            logger.error(f"Failed to save custom prompts: {e}")

    def get_prompt(
        self,
        template_name: str,
        **kwargs
    ) -> str:
        """
        프롬프트 생성

        Args:
            template_name: 템플릿 이름
            **kwargs: 템플릿 변수

        Returns:
            생성된 프롬프트
        """
        # 커스텀 프롬프트 우선
        if template_name in self.custom_prompts:
            template = self.custom_prompts[template_name]
        elif template_name in self.templates:
            template = self.templates[template_name]
        else:
            logger.warning(f"Template '{template_name}' not found, using default")
            template = self.templates['rag_qa']

        # 변수 치환
        try:
            prompt = template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            raise ValueError(f"Missing required variable: {e}")

        return prompt

    def create_rag_prompt(
        self,
        question: str,
        context: str,
        history: Optional[List[Dict]] = None
    ) -> str:
        """
        RAG 프롬프트 생성

        Args:
            question: 사용자 질문
            context: 검색된 컨텍스트
            history: 대화 히스토리

        Returns:
            생성된 프롬프트
        """
        # 컨텍스트 정리
        context = self._clean_context(context)

        # 히스토리가 있으면 대화형 템플릿 사용
        if history:
            history_text = self._format_history(history)
            prompt = self.get_prompt(
                'conversational',
                history=history_text,
                context=context,
                question=question
            )
        else:
            prompt = self.get_prompt(
                'rag_qa',
                context=context,
                question=question
            )

        return prompt

    def create_summary_prompt(
        self,
        document: str,
        max_length: Optional[int] = None
    ) -> str:
        """
        요약 프롬프트 생성

        Args:
            document: 요약할 문서
            max_length: 최대 요약 길이

        Returns:
            생성된 프롬프트
        """
        # 문서 길이 제한
        if max_length and len(document) > max_length:
            document = document[:max_length] + "..."

        prompt = self.get_prompt(
            'summarize',
            document=document
        )

        return prompt

    def _clean_context(self, context: str) -> str:
        """
        컨텍스트 정리

        Args:
            context: 원본 컨텍스트

        Returns:
            정리된 컨텍스트
        """
        # 중복 공백 제거
        context = ' '.join(context.split())

        # 너무 긴 경우 자르기
        max_context_length = self.config.n_ctx * 2 // 3
        if len(context) > max_context_length:
            context = context[:max_context_length] + "..."

        return context

    def _format_history(self, history: List[Dict]) -> str:
        """
        대화 히스토리 포맷팅

        Args:
            history: 대화 히스토리

        Returns:
            포맷된 히스토리
        """
        formatted = []

        for turn in history[-5:]:  # 최근 5턴만
            role = turn.get('role', 'user')
            content = turn.get('content', '')

            if role == 'user':
                formatted.append(f"사용자: {content}")
            else:
                formatted.append(f"어시스턴트: {content}")

        return "\n".join(formatted)

    def add_custom_prompt(
        self,
        name: str,
        template: str
    ) -> None:
        """
        커스텀 프롬프트 추가

        Args:
            name: 프롬프트 이름
            template: 프롬프트 템플릿
        """
        self.custom_prompts[name] = template
        self.save_custom_prompts()
        logger.info(f"Added custom prompt: {name}")

    def update_template(
        self,
        name: str,
        template: str
    ) -> None:
        """
        템플릿 업데이트

        Args:
            name: 템플릿 이름
            template: 새 템플릿
        """
        if name in self.templates:
            self.templates[name] = template
            logger.info(f"Updated template: {name}")
        else:
            logger.warning(f"Template {name} not found")

    def list_templates(self) -> Dict[str, List[str]]:
        """
        사용 가능한 템플릿 목록

        Returns:
            템플릿 목록
        """
        return {
            'default': list(self.templates.keys()),
            'custom': list(self.custom_prompts.keys())
        }