#!/usr/bin/env python3
"""
빠른 수정: LLM 없이 검색만 하는 RAG
문제 해결용 임시 솔루션
"""

from perfect_rag import PerfectRAG
import time

class QuickFixRAG:
    """LLM 답변 생성 문제 우회용 RAG"""

    def __init__(self):
        self.rag = PerfectRAG()

    def answer(self, query: str) -> str:
        """검색 결과만 반환 (LLM 답변 생성 제외)"""

        try:
            # 1. 기안자 검색인지 확인
            import re
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter_name = drafter_match.group(1)
                # 전체 개수 확인을 위해 많은 수로 검색
                search_results = self.rag.search_module.search_by_drafter(drafter_name, top_k=200)
                if search_results:
                    # 기안자로 작성된 문서 우선 표시
                    return self._format_drafter_results(query, drafter_name, search_results)

            # 2. 일반 검색
            search_results = self.rag.search_module.search_by_content(query, top_k=5)

            if not search_results:
                return "❌ 관련 문서를 찾을 수 없습니다."

            # 2. 검색 결과 포매팅 (LLM 없이)
            answer = f"**{query}** 검색 결과\n\n"
            answer += f"총 {len(search_results)}개 문서 발견\n\n"

            for i, doc in enumerate(search_results, 1):
                answer += f"**{i}. {doc['filename']}**\n"
                if doc.get('date'):
                    answer += f"   - 날짜: {doc['date']}\n"
                if doc.get('category'):
                    answer += f"   - 카테고리: {doc['category']}\n"

                # 기안자 정보 우선 표시 (department 필드에 저장됨)
                drafter = doc.get('department', '')
                if drafter and drafter not in ['영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출']:
                    answer += f"   - 기안자: {drafter}\n"
                elif doc.get('extracted_dept'):
                    answer += f"   - 부서: {doc['extracted_dept']}\n"

                answer += "\n"

            return answer

        except Exception as e:
            return f"❌ 검색 중 오류 발생: {e}"

    def _format_drafter_results(self, query: str, drafter_name: str, search_results) -> str:
        """기안자별 검색 결과 포매팅"""
        total_count = len(search_results)
        answer = f"**{query}** 검색 결과\n\n"
        answer += f"📝 **{drafter_name}** 기안자가 작성한 문서: **{total_count}개** (최신순)\n\n"

        # 처음 15개만 상세히 표시
        display_count = min(15, total_count)

        for i, doc in enumerate(search_results[:display_count], 1):
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"
            answer += f"   - 기안자: {doc.get('department', '')}\n"
            answer += "\n"

        # 나머지가 있으면 요약 정보 추가
        if total_count > display_count:
            remaining = total_count - display_count
            answer += f"📋 **추가 {remaining}개 문서**가 더 있습니다.\n\n"

            # 연도별 통계
            year_stats = {}
            for doc in search_results:
                if doc.get('date'):
                    year = doc['date'][:4]
                    year_stats[year] = year_stats.get(year, 0) + 1

            if year_stats:
                answer += "📊 **연도별 분포:**\n"
                for year in sorted(year_stats.keys(), reverse=True):
                    answer += f"   - {year}년: {year_stats[year]}개\n"

        return answer

def main():
    """테스트"""
    print("🚀 빠른 수정 RAG 테스트")

    rag = QuickFixRAG()

    test_queries = [
        "기안자 남준수 문서 찾아줘",
        "DVR 관련 문서",
        "카메라 수리 비용"
    ]

    for query in test_queries:
        print(f"\n📌 {query}")
        print("-" * 50)

        start = time.time()
        response = rag.answer(query)
        elapsed = time.time() - start

        print(response)
        print(f"⏱️ 응답 시간: {elapsed:.2f}초")

if __name__ == "__main__":
    main()