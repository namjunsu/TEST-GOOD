#!/usr/bin/env python3
"""모든 문서의 텍스트 추출 품질 검사"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pdfplumber

def main():
    # DB 연결
    conn = sqlite3.connect("metadata.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 모든 PDF 문서 조회
    cursor.execute("""
        SELECT id, path, filename, page_count
        FROM documents
        WHERE filename LIKE '%.pdf'
        ORDER BY filename
    """)
    docs = cursor.fetchall()

    print(f"총 {len(docs)} PDF 문서 검사 시작...\n")

    poor_quality_files = []
    zero_char_files = []
    low_char_files = []

    for idx, doc in enumerate(docs, 1):
        filename = doc['filename']
        file_path = doc['path']

        pdf_path = Path(file_path)
        if not pdf_path.exists():
            print(f"⚠️  파일 없음: {file_path}")
            continue

        try:
            # pdfplumber로 텍스트 추출 테스트
            with pdfplumber.open(pdf_path) as pdf:
                total_chars = 0
                page_count = len(pdf.pages)

                for page in pdf.pages:
                    text = page.extract_text() or ""
                    total_chars += len(text)

                avg_chars_per_page = total_chars / page_count if page_count > 0 else 0

                # 품질 판정
                if total_chars == 0:
                    zero_char_files.append({
                        'filename': filename,
                        'path': str(pdf_path),
                        'pages': page_count,
                        'total_chars': total_chars,
                        'avg_chars': avg_chars_per_page
                    })
                elif total_chars < 100 or avg_chars_per_page < 50:
                    low_char_files.append({
                        'filename': filename,
                        'path': str(pdf_path),
                        'pages': page_count,
                        'total_chars': total_chars,
                        'avg_chars': avg_chars_per_page
                    })

        except Exception as e:
            print(f"⚠️  {filename}: {e}")
            continue

        # 진행률 표시
        if idx % 50 == 0:
            print(f"진행: {idx}/{len(docs)} 문서 검사 완료...")

    # 결과 정리
    poor_quality_files = zero_char_files + low_char_files

    print("\n" + "="*80)
    print("검사 결과 요약")
    print("="*80)
    print(f"총 문서 수: {len(docs)}")
    print(f"0자 추출: {len(zero_char_files)}개")
    print(f"저품질 추출 (<100자 or <50자/페이지): {len(low_char_files)}개")
    print(f"OCR 필요 총계: {len(poor_quality_files)}개")

    # 0자 추출 파일 목록
    if zero_char_files:
        print("\n" + "="*80)
        print("⚠️  0자 추출 파일 (최우선 OCR 필요)")
        print("="*80)
        for file_info in zero_char_files[:20]:  # 최대 20개만 표시
            print(f"\n파일: {file_info['filename']}")
            print(f"  경로: {file_info['path']}")
            print(f"  페이지: {file_info['pages']}p")
            print(f"  추출: 0자")

    # 저품질 추출 파일 목록
    if low_char_files:
        print("\n" + "="*80)
        print("⚠️  저품질 추출 파일 (OCR 권장)")
        print("="*80)
        for file_info in low_char_files[:20]:  # 최대 20개만 표시
            print(f"\n파일: {file_info['filename']}")
            print(f"  경로: {file_info['path']}")
            print(f"  페이지: {file_info['pages']}p")
            print(f"  추출: {file_info['total_chars']}자 (평균 {file_info['avg_chars']:.1f}자/페이지)")

    # 파일 목록을 텍스트로 저장
    output_file = Path("reports/poor_extraction_files.txt")
    output_file.parent.mkdir(exist_ok=True)

    with output_file.open('w', encoding='utf-8') as f:
        f.write("OCR 필요 파일 목록\n")
        f.write("="*80 + "\n\n")
        f.write(f"총 {len(poor_quality_files)}개 파일\n\n")

        f.write("0자 추출 파일:\n")
        f.write("-"*80 + "\n")
        for file_info in zero_char_files:
            f.write(f"{file_info['path']}\n")

        f.write("\n저품질 추출 파일:\n")
        f.write("-"*80 + "\n")
        for file_info in low_char_files:
            f.write(f"{file_info['path']}\n")

    print(f"\n✅ 파일 목록 저장: {output_file}")

    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
