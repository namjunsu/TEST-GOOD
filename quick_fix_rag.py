#!/usr/bin/env python3
"""
빠른 수정: LLM 없이 검색만 하는 RAG (SearchModule 직접 사용)
perfect_rag.py 의존성 제거 버전
"""

from modules.search_module import SearchModule
import time
import re

class QuickFixRAG:
    """LLM 답변 생성 문제 우회용 RAG"""

    def __init__(self):
        self.search_module = SearchModule()  # 직접 사용 (0.012초 vs 2.2초)
        self.unified_rag = None  # 지연 로딩 (필요할 때만)

    def answer(self, query: str) -> str:
        """검색 결과만 반환 (LLM 답변 생성 제외)"""

        try:
            # 1. 기안자 검색인지 확인
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter_name = drafter_match.group(1)
                # 전체 개수 확인을 위해 많은 수로 검색
                search_results = self.search_module.search_by_drafter(drafter_name, top_k=200)
                if search_results:
                    # 기안자로 작성된 문서 우선 표시
                    return self._format_drafter_results(query, drafter_name, search_results)

            # 2. 일반 검색
            search_results = self.search_module.search_by_content(query, top_k=5)

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
                if drafter and drafter != '미상':
                    answer += f"   - 기안자: {drafter}\n"

                # 내용 미리보기
                content_preview = (doc.get('content', '')[:200] + "..."
                                   if len(doc.get('content', '')) > 200
                                   else doc.get('content', ''))
                answer += f"   - 내용: {content_preview}\n\n"

            return answer

        except Exception as e:
            return f"❌ 오류: {str(e)}"

    def _format_drafter_results(self, query: str, drafter_name: str, search_results: list) -> str:
        """기안자 검색 결과 포매팅"""
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
            answer += f"   - 내용: {content_preview}\n\n"

        if len(search_results) > 20:
            answer += f"\n*(총 {len(search_results)}개 중 상위 20개 표시)*\n"

        return answer

    def answer_from_specific_document(self, query: str, filename: str) -> str:
        """특정 문서에 대한 질문 답변 (문서 내용 요약)"""
        try:
            # 1. 문서 찾기
            from pathlib import Path
            import pdfplumber

            # docs 폴더에서 파일 찾기
            docs_dir = Path("docs")
            pdf_files = list(docs_dir.rglob(filename))

            if not pdf_files:
                return f"❌ 문서를 찾을 수 없습니다: {filename}"

            pdf_path = pdf_files[0]

            # 2. PDF 텍스트 추출
            text = ""
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages[:5]:  # 처음 5페이지만
                        text += page.extract_text() or ""
            except Exception as e:
                return f"❌ PDF 읽기 실패: {str(e)}"

            if not text.strip():
                return "❌ 문서에서 텍스트를 추출할 수 없습니다."

            # 3. 간단한 요약 생성 (LLM 없이)
            lines = [line.strip() for line in text.split('\n') if line.strip()]

            answer = f"**📄 {filename}**\n\n"
            answer += "**문서 내용:**\n\n"

            # 처음 20줄 또는 500자
            preview_lines = lines[:20]
            preview = '\n'.join(preview_lines)
            if len(preview) > 500:
                preview = preview[:500] + "..."

            answer += preview
            answer += f"\n\n*(총 {len(text)} 글자, {len(lines)} 줄)*"

            return answer

        except Exception as e:
            return f"❌ 오류: {str(e)}"

    def get_unified_rag(self):
        """UnifiedRAG 지연 로딩 (필요할 때만)"""
        if self.unified_rag is None:
            from hybrid_chat_rag_v2 import UnifiedRAG
            self.unified_rag = UnifiedRAG()
        return self.unified_rag


if __name__ == "__main__":
    # 빠른 테스트
    print("🚀 QuickFixRAG v2 (SearchModule 직접 사용)")
    print("=" * 60)

    start = time.time()
    rag = QuickFixRAG()
    init_time = time.time() - start

    print(f"⏱️  초기화 시간: {init_time:.4f}초")
    print()

    # 테스트 쿼리
    test_queries = [
        "카메라 수리",
        "기안자 박선희"
    ]

    for query in test_queries:
        print(f"\n📝 질문: {query}")
        print("-" * 60)

        start = time.time()
        answer = rag.answer(query)
        elapsed = time.time() - start

        print(answer)
        print(f"\n⏱️  응답 시간: {elapsed:.4f}초")
        print("=" * 60)
