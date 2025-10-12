#!/usr/bin/env python3
"""
표 추출 기능 테스트
pdfplumber의 extract_tables() 기능을 테스트하고 결과 품질을 확인합니다.
"""

import pdfplumber
from pathlib import Path
import sys

def test_table_extraction(pdf_path: Path):
    """PDF에서 표 추출 테스트"""
    print(f"\n🧪 테스트: {pdf_path.name}")
    print("="*80)

    with pdfplumber.open(pdf_path) as pdf:
        total_tables = 0

        for page_num, page in enumerate(pdf.pages[:5], 1):  # 최대 5페이지
            # 일반 텍스트 추출
            text = page.extract_text() or ""

            # 표 추출
            tables = page.extract_tables()

            print(f"\n📄 페이지 {page_num}:")
            print(f"  텍스트 길이: {len(text)}자")
            print(f"  표 개수: {len(tables)}개")

            if tables:
                total_tables += len(tables)
                for i, table in enumerate(tables, 1):
                    print(f"\n  📊 표 {i}:")
                    print(f"    행 수: {len(table)}개")
                    print(f"    열 수: {len(table[0]) if table else 0}개")

                    # 표 내용 샘플 출력 (첫 3행)
                    print(f"    샘플:")
                    for row in table[:3]:
                        row_text = " | ".join([str(cell or '').strip()[:20] for cell in row])
                        print(f"      {row_text}")

        print(f"\n📊 총 표 개수: {total_tables}개")
        return total_tables > 0

def format_table_as_markdown(table):
    """표를 마크다운 형식으로 변환"""
    if not table or not table[0]:
        return ""

    lines = []

    # 헤더 (첫 번째 행)
    header = " | ".join([str(cell or '').strip() for cell in table[0]])
    lines.append(header)

    # 구분선
    separator = " | ".join(["---"] * len(table[0]))
    lines.append(separator)

    # 데이터 행
    for row in table[1:]:
        row_text = " | ".join([str(cell or '').strip() for cell in row])
        lines.append(row_text)

    return "\n".join(lines)

def main():
    # 테스트할 PDF 파일 목록
    docs_dir = Path("docs")

    # 2025년 문서 중 일부 샘플링
    test_files = list(docs_dir.glob("year_2025/*.pdf"))[:5]

    if not test_files:
        print("❌ 테스트할 PDF 파일을 찾을 수 없습니다")
        return

    print("📚 표 추출 기능 테스트")
    print("="*80)

    has_tables_count = 0
    total_tested = 0

    for pdf_path in test_files:
        try:
            has_tables = test_table_extraction(pdf_path)
            if has_tables:
                has_tables_count += 1
            total_tested += 1
        except Exception as e:
            print(f"❌ 오류: {pdf_path.name} - {e}")

    print("\n" + "="*80)
    print(f"✅ 테스트 완료: {has_tables_count}/{total_tested}개 파일에서 표 발견")

    # 마크다운 변환 테스트
    if test_files:
        print("\n📝 마크다운 변환 테스트:")
        with pdfplumber.open(test_files[0]) as pdf:
            for page in pdf.pages[:2]:
                tables = page.extract_tables()
                if tables:
                    print(f"\n표 마크다운 변환:")
                    print(format_table_as_markdown(tables[0]))
                    break

if __name__ == "__main__":
    main()
