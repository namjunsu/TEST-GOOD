#!/usr/bin/env python3
"""
Perfect RAG with Metadata - 메타데이터 추출 기능 추가 버전
간단한 통합 예시
"""

from perfect_rag import PerfectRAG
from metadata_extractor import MetadataExtractor
import pdfplumber
from pathlib import Path

class EnhancedPerfectRAG(PerfectRAG):
    """메타데이터 추출 기능이 추가된 Perfect RAG"""

    def __init__(self):
        super().__init__()
        self.metadata_extractor = MetadataExtractor()
        print("✅ 메타데이터 추출기 활성화")

    def answer(self, query: str, **kwargs):
        """검색 + 메타데이터 추출"""

        # 기존 검색 수행
        results = super().answer(query, **kwargs)

        # 각 문서에 메타데이터 추가
        if results and 'documents' in results:
            for doc in results['documents']:
                try:
                    # PDF 파일명과 내용으로 메타데이터 추출
                    file_path = doc.get('file', '')
                    file_name = Path(file_path).name if file_path else ''
                    content = doc.get('content', '')

                    # 메타데이터 추출
                    if content or file_name:
                        metadata = self.metadata_extractor.extract_all(
                            content[:3000],  # 처음 3000자만 분석
                            file_name
                        )

                        # 요약 정보 추가
                        doc['metadata'] = metadata['summary']

                        # 주요 정보를 content 앞에 추가
                        info_parts = []
                        if metadata['summary'].get('date'):
                            info_parts.append(f"📅 날짜: {metadata['summary']['date']}")
                        if metadata['summary'].get('amount'):
                            info_parts.append(f"💰 금액: {metadata['summary']['amount']:,}원")
                        if metadata['summary'].get('department'):
                            info_parts.append(f"🏢 부서: {metadata['summary']['department']}")
                        if metadata['summary'].get('doc_type'):
                            info_parts.append(f"📄 유형: {metadata['summary']['doc_type']}")

                        if info_parts:
                            doc['metadata_info'] = " | ".join(info_parts)

                except Exception as e:
                    # 메타데이터 추출 실패해도 검색은 계속
                    doc['metadata'] = {}
                    doc['metadata_info'] = ""

        return results

# 테스트 함수
def test_enhanced_search():
    """향상된 검색 테스트"""
    print("\n🚀 메타데이터 추출 기능 테스트")
    print("=" * 50)

    rag = EnhancedPerfectRAG()

    test_queries = [
        "DVR 관련 문서",
        "2024년 구매",
        "카메라부"
    ]

    for query in test_queries:
        print(f"\n검색: {query}")
        print("-" * 30)

        results = rag.search(query, top_k=3)

        if results and 'documents' in results:
            for i, doc in enumerate(results['documents'], 1):
                print(f"\n{i}. {Path(doc.get('file', '')).name}")
                if doc.get('metadata_info'):
                    print(f"   {doc['metadata_info']}")
                else:
                    print("   (메타데이터 없음)")

if __name__ == "__main__":
    test_enhanced_search()