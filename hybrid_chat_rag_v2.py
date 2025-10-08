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

try:
    from rag_system.qwen_llm import QwenLLM
    from config import QWEN_MODEL_PATH
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("⚠️ LLM 모듈을 불러올 수 없습니다.")

class UnifiedRAG:
    """통합 RAG - 자동으로 검색/AI 선택"""

    def __init__(self):
        # 검색 엔진
        self.search_rag = QuickFixRAG()

        # LLM (지연 로딩)
        self.llm = None
        self.llm_loaded = False

        # 대화 기록
        self.conversation_history = []

    def answer(self, query: str) -> str:
        """
        통합 답변 - 자동으로 모드 선택
        간단한 질문 → 빠른 검색
        복잡한 질문 → AI 분석
        """
        # 질문 분석
        needs_ai = self._needs_ai_analysis(query)

        # 디버깅 정보
        print(f"\n🔍 질문: {query}")
        print(f"📊 AI 분석 필요: {needs_ai}")
        print(f"🤖 LLM 사용 가능: {LLM_AVAILABLE}")

        if needs_ai and LLM_AVAILABLE:
            # AI 분석 필요
            print("✅ AI 분석 모드 선택")
            return self._ai_answer(query)
        else:
            # 빠른 검색으로 충분
            print("⚡ 빠른 검색 모드 선택")
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

        return f"{result}\n\n*🔍 빠른 검색 ({elapsed:.2f}초)*"

    def _ai_answer(self, query: str) -> str:
        """AI 분석 답변"""
        if not self._ensure_llm_loaded():
            # LLM 못 쓰면 빠른 검색으로 대체
            return self._quick_answer(query)

        start_time = time.time()

        # 1. 문서 검색
        documents = self._search_documents(query)

        if not documents:
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

            return f"{answer}\n\n*🤖 AI 분석 ({elapsed:.1f}초)*"

        except Exception as e:
            print(f"❌ AI 분석 실패: {e}")
            # 실패 시 빠른 검색으로 대체
            return self._quick_answer(query)

    def _ensure_llm_loaded(self) -> bool:
        """LLM 로딩"""
        if not LLM_AVAILABLE:
            return False

        if not self.llm_loaded:
            try:
                print("🤖 AI 모델 로딩 중...")
                self.llm = QwenLLM(model_path=QWEN_MODEL_PATH)
                self.llm_loaded = True
                print("✅ AI 준비 완료")
                return True
            except Exception as e:
                print(f"❌ AI 로드 실패: {e}")
                return False
        return True

    def _search_documents(self, query: str) -> List[Dict]:
        """문서 검색"""
        try:
            # 기안자 검색
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter = drafter_match.group(1)
                return self.search_rag.rag.search_module.search_by_drafter(drafter, top_k=5)

            # 일반 검색
            return self.search_rag.rag.search_module.search_by_content(query, top_k=5)

        except Exception as e:
            print(f"❌ 검색 실패: {e}")
            return []

    def _build_prompt(self, query: str, documents: List[Dict]) -> str:
        """AI용 프롬프트 생성"""
        prompt = """당신은 방송국 기술관리팀의 문서 분석 AI입니다.
검색된 문서를 바탕으로 실무에 도움이 되는 구체적인 답변을 제공하세요.

검색된 문서:
"""

        # 문서 내용 추가
        for i, doc in enumerate(documents[:3], 1):
            prompt += f"\n[문서 {i}]\n"
            prompt += f"파일: {doc.get('filename', '알수없음')}\n"

            if doc.get('date'):
                prompt += f"날짜: {doc['date']}\n"
            if doc.get('drafter'):
                prompt += f"기안자: {doc['drafter']}\n"

            # 문서 내용
            if doc.get('content'):
                content = doc['content'][:2000]  # 최대 2000자
                prompt += f"내용:\n{content}\n"

            prompt += "\n---\n"

        # 이전 대화
        if self.conversation_history:
            prompt += "\n이전 대화:\n"
            for hist in self.conversation_history[-2:]:
                prompt += f"Q: {hist['query']}\n"
                prompt += f"A: {hist['response'][:100]}...\n"

        prompt += f"\n질문: {query}\n\n"
        prompt += """답변 요구사항:
- 문서 내용을 바탕으로 구체적 답변
- 금액, 업체명, 장비명 등 실무 정보 포함
- 표 형식으로 정리 (필요시)
- 명확하고 간결하게

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
    print("🚀 통합 RAG 테스트\n")

    rag = UnifiedRAG()

    # 테스트 질문들
    test_queries = [
        "DVR 관련 문서 찾아줘",  # → 빠른 검색
        "중계차 보수건 내용을 요약해줘",  # → AI 분석
        "기안자 남준수",  # → 빠른 검색
        "2024년과 2025년 구매 문서를 비교 분석해줘"  # → AI 분석
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*50}")
        print(f"질문 {i}: {query}")
        print(f"{'='*50}")

        answer = rag.answer(query)
        print(answer)
        print()

if __name__ == "__main__":
    main()
