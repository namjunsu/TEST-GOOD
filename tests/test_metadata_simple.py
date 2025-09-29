#!/usr/bin/env python3
"""
메타데이터 추출 간단 테스트
"""

from metadata_extractor import MetadataExtractor
from pathlib import Path
import pdfplumber

def test_metadata():
    """PDF에서 메타데이터 추출 테스트"""

    extractor = MetadataExtractor()

    # PDF 파일 몇 개 테스트
    pdf_dir = Path("./docs")
    pdf_files = list(pdf_dir.glob("**/2024*.pdf"))[:3]  # 2024년 파일 3개만

    print("📊 메타데이터 추출 테스트")
    print("=" * 60)

    for pdf_path in pdf_files:
        print(f"\n📄 {pdf_path.name}")
        print("-" * 40)

        try:
            # PDF 텍스트 읽기 (첫 페이지만)
            with pdfplumber.open(pdf_path) as pdf:
                text = pdf.pages[0].extract_text() if pdf.pages else ""

            # 메타데이터 추출
            metadata = extractor.extract_all(text[:1000], pdf_path.name)
            summary = metadata['summary']

            # 결과 출력
            if summary.get('date'):
                print(f"  📅 날짜: {summary['date']}")
            if summary.get('amount'):
                print(f"  💰 금액: {summary['amount']:,}원")
            if summary.get('department'):
                print(f"  🏢 부서: {summary['department']}")
            if summary.get('doc_type'):
                print(f"  📑 유형: {summary['doc_type']}")
            if summary.get('contact'):
                print(f"  👤 담당: {summary['contact']}")

            if not summary:
                print("  ❌ 메타데이터 없음")

        except Exception as e:
            print(f"  ⚠️ 오류: {e}")

    print("\n✅ 테스트 완료!")
    print("\n💡 이 기능을 perfect_rag.py에 추가하면")
    print("   모든 검색 결과에 이런 정보가 자동으로 표시됩니다!")

if __name__ == "__main__":
    test_metadata()