#!/usr/bin/env python3
"""
통합 RAG 시스템 - 자동으로 최적 모드 선택
간단한 질문 → 빠른 검색
복잡한 질문 → AI 분석
"""

import time
import re
from typing import List, Dict, Any, Optional
from quick_fix_rag import QuickFixRAG
from app.core.logging import get_logger
from utils.error_handler import handle_errors

# 로거 초기화
logger = get_logger(__name__)

try:
    from rag_system.qwen_llm import QwenLLM
    from config import QWEN_MODEL_PATH
    LLM_AVAILABLE = True
    logger.info("LLM 모듈 로드 성공")
except ImportError as e:
    LLM_AVAILABLE = False
    logger.warning(f"LLM 모듈을 불러올 수 없습니다: {e}")

class UnifiedRAG:
    """통합 RAG - 자동으로 검색/AI 선택"""

    def __init__(self):
        logger.info("UnifiedRAG 초기화 시작")

        try:
            # 검색 엔진
            self.search_rag = QuickFixRAG()
            logger.info("QuickFixRAG 초기화 성공")
        except Exception as e:
            logger.error("QuickFixRAG 초기화 실패", exception=e)
            raise

        # LLM (지연 로딩)
        self.llm = None
        self.llm_loaded = False

        # 대화 기록
        self.conversation_history = []

        logger.info("UnifiedRAG 초기화 완료")

    @handle_errors(context="UnifiedRAG.answer")
    def answer(self, query: str) -> str:
        """
        통합 답변 - 자동으로 모드 선택
        간단한 질문 → 빠른 검색
        복잡한 질문 → AI 분석
        """
        logger.info(f"질문 수신: {query}")

        # 질문 분석
        needs_ai = self._needs_ai_analysis(query)

        # 디버깅 정보
        logger.debug(f"AI 분석 필요: {needs_ai}, LLM 사용 가능: {LLM_AVAILABLE}")

        if needs_ai and LLM_AVAILABLE:
            # AI 분석 필요
            logger.info("AI 분석 모드 선택")
            return self._ai_answer(query)
        else:
            # 빠른 검색으로 충분
            logger.info("빠른 검색 모드 선택")
            return self._quick_answer(query)

    def _needs_ai_analysis(self, query: str) -> bool:
        """AI 분석이 필요한 질문인지 판단"""

        # AI가 필요한 키워드
        ai_keywords = [
            # 분석/설명
            '요약', '분석', '비교', '설명', '왜', '어떻게',
            '특징', '차이', '공통점', '패턴', '추천',
            '이유', '원인', '결과', '영향', '관계',
            # 내용 요청
            '내용', '알려', '말해', '정리', '상세', '자세',
            '구체적', '전체', '모든', '다', '전부'
        ]

        # 간단한 검색 키워드 (우선순위 높음)
        simple_keywords = [
            '찾아', '보여', '검색', '있어', '목록', '리스트',
            '몇 개', '개수', '언제', '누가', '어디', '어느'
        ]

        query_lower = query.lower()

        # 간단한 키워드가 있으면 빠른 검색 (우선)
        for keyword in simple_keywords:
            if keyword in query_lower:
                return False

        # AI 키워드가 있으면 AI 분석
        for keyword in ai_keywords:
            if keyword in query_lower:
                return True

        # 애매하면 질문 길이로 판단 (25자 이상 = AI)
        return len(query) > 25

    def _quick_answer(self, query: str) -> str:
        """빠른 검색 답변"""
        with logger.timer("빠른 검색"):
            start_time = time.time()
            result = self.search_rag.answer(query)
            elapsed = time.time() - start_time

            # 대화 기록 저장
            self.conversation_history.append({
                'query': query,
                'response': result,
                'mode': 'quick',
                'timestamp': time.time()
            })

            logger.info(f"빠른 검색 완료: {elapsed:.2f}초")
            return f"{result}\n\n*🔍 빠른 검색 ({elapsed:.2f}초)*"

    def _ai_answer(self, query: str) -> str:
        """AI 분석 답변"""
        if not self._ensure_llm_loaded():
            # LLM 못 쓰면 빠른 검색으로 대체
            logger.warning("LLM 로드 실패, 빠른 검색으로 대체")
            return self._quick_answer(query)

        with logger.timer("AI 분석"):
            start_time = time.time()

            # 1. 문서 검색
            documents = self._search_documents(query)

            if not documents:
                logger.warning("관련 문서를 찾을 수 없음")
                return "관련 문서를 찾을 수 없습니다."

            # 2. 프롬프트 생성
            prompt = self._build_prompt(query, documents)

            # 3. LLM 응답
            try:
                response = self.llm.generate_response(prompt, [])

                # 텍스트 추출
                if hasattr(response, 'answer'):
                    answer = response.answer
                elif hasattr(response, 'content'):
                    answer = response.content
                else:
                    answer = str(response)

                elapsed = time.time() - start_time

                # 대화 기록
                self.conversation_history.append({
                    'query': query,
                    'response': answer,
                    'mode': 'ai',
                    'timestamp': time.time()
                })

                logger.info(f"AI 분석 완료: {elapsed:.1f}초")
                return f"{answer}\n\n*🤖 AI 분석 ({elapsed:.1f}초)*"

            except Exception as e:
                logger.error("AI 분석 실패, 빠른 검색으로 대체", exception=e)
                # 실패 시 빠른 검색으로 대체
                return self._quick_answer(query)

    def _ensure_llm_loaded(self) -> bool:
        """LLM 로딩"""
        if not LLM_AVAILABLE:
            logger.warning("LLM 모듈이 사용 불가능합니다")
            return False

        if not self.llm_loaded:
            try:
                logger.info("AI 모델 로딩 중...")
                self.llm = QwenLLM(model_path=QWEN_MODEL_PATH)
                self.llm_loaded = True
                logger.info("AI 모델 로딩 완료")
                return True
            except Exception as e:
                logger.error("AI 모델 로드 실패", exception=e)
                return False
        return True

    def _search_documents(self, query: str) -> List[Dict]:
        """문서 검색"""
        try:
            # 기안자 검색
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter = drafter_match.group(1)
                logger.debug(f"기안자 검색: {drafter}")
                return self.search_rag.search_module.search_by_drafter(drafter, top_k=5)

            # 일반 검색
            logger.debug(f"일반 검색: {query}")
            return self.search_rag.search_module.search_by_content(query, top_k=5)

        except Exception as e:
            logger.error("문서 검색 실패", exception=e)
            return []

    def _classify_query_complexity(self, query: str) -> str:
        """질문 복잡도 분류: simple(단순), complex(복잡)"""
        # 단순 질문 패턴
        simple_patterns = [
            '금액', '가격', '비용', '얼마',
            '언제', '날짜', '일자',
            '누가', '기안자', '담당자',
            '어디', '장소', '위치',
            '무엇', '장비', '제품'
        ]

        # 복잡한 질문 패턴
        complex_patterns = [
            '왜', '이유', '원인',
            '어떻게', '방법',
            '적절', '타당', '평가',
            '비교', '차이',
            '분석', '검토',
            '문제', '해결',
            '상세', '자세'
        ]

        query_lower = query.lower()

        # 복잡한 질문 우선 체크
        if any(pattern in query_lower for pattern in complex_patterns):
            return 'complex'

        # 단순 질문 체크
        if any(pattern in query_lower for pattern in simple_patterns):
            return 'simple'

        # 기본값: 중간 복잡도로 처리 (complex로 분류)
        return 'complex'

    def _build_prompt(self, query: str, documents: List[Dict]) -> str:
        """AI용 프롬프트 생성 (적응형 CoT - 질문에 따라 자동 선택)"""

        # 질문 복잡도 분류
        query_type = self._classify_query_complexity(query)

        # 기본 프롬프트
        prompt = """당신은 방송국 기술관리팀의 문서 분석 전문 AI입니다.
주어진 여러 문서 중 질문에 가장 적합한 문서를 선택하여 정확하고 상세한 답변을 제공하세요.

⚠️ 중요 원칙:
- 여러 문서가 제공되면 관련도 점수와 내용을 보고 가장 적합한 문서 선택
- 문서의 실제 내용만 사용 (추측/상상 절대 금지)
- 모든 정보는 반드시 [파일명.pdf] 형식으로 출처 명시
- 표, 금액, 날짜, 장비명 등 세부사항을 정확히 전달
- 불확실한 정보는 "문서에 명시되지 않음"으로 표시

검색된 문서 (관련도 순):
"""

        # 문서 내용 추가 (Top-3 문서 전달 - AI가 선택)
        for i, doc in enumerate(documents[:3], 1):
            filename = doc.get('filename', '알수없음')
            score = doc.get('score', 0)
            prompt += f"\n[문서 {i}: {filename}] (관련도: {score}점)\n"

            if doc.get('date'):
                prompt += f"날짜: {doc['date']}\n"
            if doc.get('drafter'):
                prompt += f"기안자: {doc['drafter']}\n"

            # 적응형 컨텍스트: 질문과 문서 특성에 따라 길이 자동 조절
            if doc.get('content'):
                full_content = doc['content']

                # 질문 복잡도 분석
                detail_keywords = ['상세', '자세히', '전체', '모두', '전부', '내용', '표', '목록']
                simple_keywords = ['언제', '누가', '어디', '금액', '가격', '날짜']

                is_detail_query = any(kw in query for kw in detail_keywords)
                is_simple_query = any(kw in query for kw in simple_keywords) and not is_detail_query

                # Top-3 전달 시 각 문서는 짧게 (토큰 절약)
                if is_simple_query and len(full_content) > 3000:
                    # 간단한 질문: 핵심만 추출 (3000자)
                    content = full_content[:3000]
                    prompt += f"\n실제 내용 (요약):\n{content}\n"
                elif len(full_content) < 3000:
                    # 짧은 문서: 전체 사용
                    prompt += f"\n실제 내용:\n{full_content}\n"
                else:
                    # 상세 질문: 최대 5000자 (기존 12000에서 축소)
                    content = full_content[:5000]
                    prompt += f"\n실제 내용:\n{content}\n"
            else:
                prompt += "\n(문서 내용 없음 - 스캔 문서)\n"

            prompt += "\n---\n"

        prompt += f"\n사용자 질문: {query}\n\n"

        # 적응형 프롬프트: 질문 유형에 따라 다른 지시사항
        if query_type == 'simple':
            # 단순 질문: 빠르고 직접적인 답변
            prompt += """답변 요구사항:
1. **간결하게**: 질문에 대한 직접적인 답변만
2. **출처 명시**: [파일명.pdf] 형식으로 표시
3. **핵심 정보**: 금액/날짜/이름 등 정확히 전달

답변 형식:
[파일명.pdf]에 따르면, [답변]

답변:"""
        else:
            # 복잡한 질문: Chain-of-Thought로 체계적 분석
            prompt += """답변 작성 단계 (Chain-of-Thought):
1. **문서 분석**: 질문과 관련된 핵심 정보 파악
2. **정보 추출**: 날짜, 금액, 장비명, 업체명 등 구체적 데이터 수집
3. **구조화**: 표가 있다면 표 형식으로, 목록이면 목록으로 정리
4. **검증**: 모든 정보가 문서에 실제 존재하는지 확인
5. **작성**: 출처를 명시하며 명확하고 완전한 답변 작성

답변 형식:
[파일명.pdf]에 따르면...
- 핵심 정보 1
- 핵심 정보 2
- 세부 사항 (표/금액/날짜 포함)

답변 예시:
[2025-07-17_미러클랩_카메라_삼각대_기술검토서.pdf]에 따르면...
- 장비: Leofoto LVC-253C (820,000원)
- 목적: Miller DS20 삼각대 파손으로 대체품 검토

답변:"""

        return prompt

    def get_conversation_history(self) -> List[Dict]:
        """대화 기록 반환"""
        return self.conversation_history

    def clear_conversation(self):
        """대화 기록 초기화"""
        self.conversation_history = []

def main():
    """테스트"""
    logger.info("통합 RAG 테스트 시작")

    try:
        rag = UnifiedRAG()

        # 테스트 질문들
        test_queries = [
            "DVR 관련 문서 찾아줘",  # → 빠른 검색
            "중계차 보수건 내용을 요약해줘",  # → AI 분석
            "기안자 남준수",  # → 빠른 검색
            "2024년과 2025년 구매 문서를 비교 분석해줘"  # → AI 분석
        ]

        for i, query in enumerate(test_queries, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"질문 {i}: {query}")
            logger.info(f"{'='*50}")

            answer = rag.answer(query)
            logger.info(f"답변:\n{answer}\n")

        logger.info("통합 RAG 테스트 완료")

    except Exception as e:
        logger.error("테스트 실패", exception=e)

if __name__ == "__main__":
    main()
