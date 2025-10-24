#!/usr/bin/env python3
"""
개선된 빠른 검색 RAG - LLM 요약 + 출처 인용 강제
"""

from modules.search_module_hybrid import SearchModuleHybrid
import time
import re
import logging

logger = logging.getLogger(__name__)

class QuickFixRAG:
    """빠른 검색 + LLM 요약 - 하이브리드 모드"""

    def __init__(self, use_hybrid: bool = True):
        """
        Args:
            use_hybrid: 하이브리드 검색 사용 여부 (기본값: True)
        """
        try:
            # 하이브리드 검색 모듈 사용 시도
            self.search_module = SearchModuleHybrid(use_hybrid=use_hybrid)
            logger.info(f"✅ SearchModuleHybrid 초기화 성공 (hybrid={use_hybrid})")
        except Exception as e:
            logger.warning(f"⚠️ SearchModuleHybrid 초기화 실패, 기본 SearchModule 사용: {e}")
            from modules.search_module import SearchModule
            self.search_module = SearchModule()

        # LLM (지연 로딩)
        self.llm = None
        self.llm_loaded = False

    def answer(self, query: str, use_llm_summary: bool = True) -> str:
        """
        검색 + LLM 요약 반환

        Args:
            query: 사용자 질문
            use_llm_summary: LLM 요약 사용 여부 (기본: True)
        """

        try:
            # 1. 기안자 검색인지 확인
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter_name = drafter_match.group(1)
                search_results = self.search_module.search_by_drafter(drafter_name, top_k=200)
                if search_results:
                    return self._format_drafter_results(query, drafter_name, search_results)

            # 2. 일반 검색
            search_results = self.search_module.search_by_content(query, top_k=5)

            if not search_results:
                return "❌ 관련 문서를 찾을 수 없습니다."

            # 3. LLM 요약 사용 여부 결정
            if use_llm_summary and self._ensure_llm_loaded():
                return self._answer_with_llm_summary(query, search_results)
            else:
                # LLM 없이 검색 결과만 반환 (출처 포함)
                return self._format_search_results(query, search_results)

        except Exception as e:
            logger.error(f"❌ 검색 오류: {e}")
            return f"❌ 오류: {str(e)}"

    def _answer_with_llm_summary(self, query: str, search_results: list) -> str:
        """LLM으로 검색 결과 요약 (핵심만 추출)"""

        try:
            # 상위 3개 문서만 사용
            top_docs = search_results[:3]

            # 컨텍스트 구성 (금액/품목 정보 포함하도록 충분한 길이)
            context_chunks = []
            for doc in top_docs:
                context_chunks.append({
                    'source': doc['filename'],
                    'content': doc.get('content', '')[:3000],  # 3000자로 확장 (금액/품목 정보 포함)
                    'score': doc.get('score', 0.8),
                    'metadata': {
                        '날짜': doc.get('date', ''),
                        '카테고리': doc.get('category', ''),
                        '기안자': doc.get('department', '')
                    }
                })

            # LLM에게 핵심만 요약 요청
            response = self.llm.generate_response(query, context_chunks, max_retries=1)

            # 답변 추출
            if hasattr(response, 'answer'):
                summary = response.answer
            else:
                summary = str(response)

            # 출처 강제 추가 (LLM이 인용 안했을 경우)
            if '[' not in summary or '.pdf]' not in summary:
                # LLM이 출처를 안 달았으면 강제로 추가
                sources = [f"[{doc['filename']}]" for doc in top_docs[:2]]
                summary += f"\n\n출처: {', '.join(sources)}"

            return summary

        except Exception as e:
            logger.error(f"❌ LLM 요약 실패: {e}, 검색 결과로 대체")
            return self._format_search_results(query, search_results)

    def _format_search_results(self, query: str, search_results: list) -> str:
        """검색 결과 포매팅 (출처 강제 포함)"""

        answer = f"**{query}** 검색 결과\n\n"
        answer += f"총 {len(search_results)}개 문서 발견\n\n"

        for i, doc in enumerate(search_results, 1):
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"

            # 기안자 정보 우선 표시
            drafter = doc.get('department', '')
            if drafter and drafter != '미상':
                answer += f"   - 기안자: {drafter}\n"

            # 내용 미리보기 (짧게)
            content_preview = (doc.get('content', '')[:150] + "..."
                               if len(doc.get('content', '')) > 150
                               else doc.get('content', ''))
            answer += f"   - 내용: {content_preview}\n"

            # ✅ 출처 강제 추가
            answer += f"   - 📎 출처: [{doc['filename']}]\n\n"

        return answer

    def _format_drafter_results(self, query: str, drafter_name: str, search_results: list) -> str:
        """기안자 검색 결과 포매팅 (출처 포함)"""
        answer = f"**기안자: {drafter_name}** 검색 결과\n\n"
        answer += f"총 {len(search_results)}개 문서 발견\n\n"

        # 날짜별로 정렬 (최신순)
        sorted_results = sorted(search_results,
                                key=lambda x: x.get('date', ''),
                                reverse=True)

        for i, doc in enumerate(sorted_results[:20], 1):  # 상위 20개만
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"

            # 내용 미리보기
            content_preview = (doc.get('content', '')[:150] + "..."
                               if len(doc.get('content', '')) > 150
                               else doc.get('content', ''))
            answer += f"   - 내용: {content_preview}\n"

            # ✅ 출처 강제 추가
            answer += f"   - 📎 출처: [{doc['filename']}]\n\n"

        if len(search_results) > 20:
            answer += f"\n*(총 {len(search_results)}개 중 상위 20개 표시)*\n"

        return answer

    def _ensure_llm_loaded(self) -> bool:
        """LLM 로딩 (지연 로딩)"""
        if self.llm_loaded:
            return True

        try:
            from rag_system.qwen_llm import QwenLLM
            from config import QWEN_MODEL_PATH

            logger.info("🤖 LLM 로딩 중 (빠른 검색 요약용)...")
            self.llm = QwenLLM(model_path=QWEN_MODEL_PATH)
            self.llm_loaded = True
            logger.info("✅ LLM 로드 완료")
            return True

        except Exception as e:
            logger.warning(f"⚠️ LLM 로드 실패 (검색 결과만 반환): {e}")
            return False


if __name__ == "__main__":
    # 빠른 테스트
    print("🚀 QuickFixRAG v3 (LLM 요약 + 출처 강제)")
    print("=" * 60)

    start = time.time()
    rag = QuickFixRAG()
    init_time = time.time() - start

    print(f"⏱️  초기화 시간: {init_time:.4f}초")
    print()

    # 테스트 쿼리
    test_queries = [
        "카메라 수리",
        "HP Z8 워크스테이션 얼마"
    ]

    for query in test_queries:
        print(f"\n📝 질문: {query}")
        print("-" * 60)

        start = time.time()
        answer = rag.answer(query)
        elapsed = time.time() - start

        print(answer[:500])
        if len(answer) > 500:
            print(f"... (총 {len(answer)}자)")
        print(f"\n⏱️  응답 시간: {elapsed:.4f}초")
        print("=" * 60)
