#!/usr/bin/env python3
"""
하이브리드 채팅 RAG - QuickFixRAG + Qwen LLM
검색은 초고속, 대화는 로컬 LLM 사용
"""

import time
from typing import List, Dict, Any, Optional
from quick_fix_rag import QuickFixRAG

try:
    from rag_system.qwen_llm import QwenLLM
    from rag_system.llm_singleton import LLMSingleton
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("⚠️ LLM 모듈을 불러올 수 없습니다.")

class HybridChatRAG:
    """하이브리드 채팅 RAG - 검색 + LLM 대화"""

    def __init__(self):
        # 초고속 검색 엔진
        self.search_rag = QuickFixRAG()

        # LLM 초기화 (지연 로딩)
        self.llm = None
        self.llm_loaded = False

        # 대화 컨텍스트
        self.conversation_history = []
        self.selected_documents = []

    def _ensure_llm_loaded(self):
        """LLM이 필요할 때만 로드"""
        if not LLM_AVAILABLE:
            return False

        if not self.llm_loaded:
            try:
                print("🤖 Qwen LLM 로딩 중...")
                start_time = time.time()

                # 직접 모델 경로 지정하여 로드
                from rag_system.qwen_llm import QwenLLM
                from config import QWEN_MODEL_PATH

                self.llm = QwenLLM(model_path=QWEN_MODEL_PATH)

                load_time = time.time() - start_time
                print(f"✅ LLM 로드 완료 ({load_time:.1f}초)")
                self.llm_loaded = True
                return True

            except Exception as e:
                print(f"❌ LLM 로드 실패: {e}")
                return False
        return True

    def search_only(self, query: str) -> str:
        """검색만 수행 (기존 QuickFixRAG와 동일)"""
        return self.search_rag.answer(query)

    def chat_with_documents(self, query: str, use_context: bool = True) -> str:
        """문서 기반 LLM 대화"""
        if not self._ensure_llm_loaded():
            return "❌ LLM을 사용할 수 없습니다. 검색 기능만 이용해주세요."

        # 1. 관련 문서 검색
        search_results = self._get_relevant_documents(query)

        # 2. 프롬프트 구성
        prompt = self._build_chat_prompt(query, search_results, use_context)

        # 3. LLM 응답 생성
        try:
            start_time = time.time()
            # QwenLLM은 generate_response 메서드 사용
            response = self.llm.generate_response(prompt, [])
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            response_time = time.time() - start_time

            # 4. 대화 기록 저장
            self.conversation_history.append({
                'query': query,
                'response': response_text,
                'documents': search_results,
                'timestamp': time.time()
            })

            return f"{response_text}\n\n*응답 시간: {response_time:.1f}초*"

        except Exception as e:
            return f"❌ LLM 응답 생성 실패: {e}"

    def _get_relevant_documents(self, query: str) -> List[Dict]:
        """관련 문서 검색"""
        # 기존 QuickFixRAG의 search_module 활용
        try:
            # 기안자 검색
            import re
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter_name = drafter_match.group(1)
                return self.search_rag.rag.search_module.search_by_drafter(drafter_name, top_k=5)

            # 일반 검색
            return self.search_rag.rag.search_module.search_by_content(query, top_k=5)

        except Exception as e:
            print(f"❌ 문서 검색 실패: {e}")
            return []

    def _build_chat_prompt(self, query: str, documents: List[Dict], use_context: bool) -> str:
        """대화용 프롬프트 구성"""
        prompt = """당신은 방송국 문서 관리 AI 어시스턴트입니다. 검색된 문서를 바탕으로 정확하고 도움이 되는 답변을 제공해주세요.

검색된 문서:
"""

        # 문서 정보 추가
        for i, doc in enumerate(documents[:3], 1):  # 최대 3개만
            prompt += f"\n{i}. {doc.get('filename', '제목없음')}"
            if doc.get('date'):
                prompt += f" ({doc['date']})"
            if doc.get('department'):
                prompt += f" - 기안자: {doc['department']}"

        # 대화 컨텍스트 추가
        if use_context and self.conversation_history:
            prompt += "\n\n이전 대화:"
            for hist in self.conversation_history[-2:]:  # 최근 2개만
                prompt += f"\nQ: {hist['query']}"
                prompt += f"\nA: {hist['response'][:100]}..."  # 100자만

        prompt += f"\n\n사용자 질문: {query}"
        prompt += "\n\n답변 (한국어로, 간결하고 정확하게):"

        return prompt

    def get_conversation_history(self) -> List[Dict]:
        """대화 기록 반환"""
        return self.conversation_history

    def clear_conversation(self):
        """대화 기록 초기화"""
        self.conversation_history = []
        self.selected_documents = []

def main():
    """테스트"""
    print("🚀 하이브리드 채팅 RAG 테스트")

    rag = HybridChatRAG()

    # 1. 검색 테스트
    print("\n1️⃣ 검색 테스트:")
    search_result = rag.search_only("기안자 남준수")
    print(search_result[:200] + "...")

    # 2. 채팅 테스트
    if LLM_AVAILABLE:
        print("\n2️⃣ 채팅 테스트:")
        chat_result = rag.chat_with_documents("남준수가 작성한 문서들의 특징을 분석해줘")
        print(chat_result)
    else:
        print("\n❌ LLM을 사용할 수 없어 채팅 테스트를 건너뜁니다.")

if __name__ == "__main__":
    main()