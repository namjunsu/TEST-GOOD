#!/usr/bin/env python3
"""실패한 기안자 추출 케이스 상세 분석"""

import sqlite3
import re
from pathlib import Path
from collections import defaultdict

def analyze_failed_docs():
    """실패한 문서들의 패턴 분석"""

    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    # drafter가 없는 모든 문서
    cursor.execute("""
        SELECT id, filename
        FROM documents
        WHERE drafter IS NULL OR drafter = ''
        ORDER BY filename
    """)

    failed_docs = cursor.fetchall()
    print(f"총 {len(failed_docs)}개 문서 분석")
    print("=" * 80)

    patterns = defaultdict(list)

    for doc_id, filename in failed_docs:
        txt_file = Path('data/extracted') / filename.replace('.pdf', '.txt')

        if not txt_file.exists():
            patterns['no_text_file'].append(filename)
            continue

        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 처음 2000자에서 패턴 검색
            sample = content[:2000]

            # 1. 기안자 키워드가 아예 없는 경우
            if '기안자' not in sample and '작성자' not in sample:
                patterns['no_keyword'].append(filename)
                print(f"❌ 키워드 없음: {filename}")

            # 2. 기안자 필드는 있지만 비어있는 경우
            elif re.search(r'기안자\s*[:|]\s*(\s|$|\n)', sample):
                patterns['empty_field'].append(filename)
                print(f"⚠️  빈 필드: {filename}")
                # 샘플 출력
                match = re.search(r'(.{0,20}기안자.{0,40})', sample)
                if match:
                    print(f"    샘플: {repr(match.group(1))}")

            # 3. 기안자 대신 다른 정보가 있는 경우
            elif re.search(r'기안자\s*[:|]\s*(\d{4}|\w{2,})', sample):
                patterns['wrong_value'].append(filename)
                print(f"🔄 잘못된 값: {filename}")
                match = re.search(r'기안자\s*[:|]\s*(.{1,20})', sample)
                if match:
                    print(f"    값: {repr(match.group(1))}")

            # 4. OCR 문제로 텍스트가 깨진 경우
            elif len(sample) < 100 or sample.count(' ') < 10:
                patterns['ocr_issue'].append(filename)
                print(f"📝 OCR 문제: {filename}")
                print(f"    길이: {len(sample)}자, 공백: {sample.count(' ')}개")

            # 5. 알 수 없는 패턴
            else:
                patterns['unknown'].append(filename)
                print(f"❓ 알 수 없음: {filename}")
                # 기안자 근처 텍스트 출력
                if '기안자' in sample:
                    idx = sample.index('기안자')
                    context = sample[max(0, idx-30):min(len(sample), idx+50)]
                    print(f"    컨텍스트: {repr(context)}")

        except Exception as e:
            patterns['error'].append(filename)
            print(f"💥 오류: {filename} - {e}")

    print("\n" + "=" * 80)
    print("📊 패턴별 통계:")
    for pattern, files in patterns.items():
        print(f"  {pattern}: {len(files)}개")

    # 대표 케이스 출력
    print("\n" + "=" * 80)
    print("🔍 대표 케이스 상세 분석:")

    for pattern, files in patterns.items():
        if files and pattern != 'no_text_file':
            print(f"\n[{pattern}] 예시: {files[0]}")
            txt_file = Path('data/extracted') / files[0].replace('.pdf', '.txt')
            if txt_file.exists():
                with open(txt_file, 'r', encoding='utf-8') as f:
                    content = f.read()[:500]
                print("첫 500자:")
                print("-" * 40)
                print(content)
                print("-" * 40)

    conn.close()
    return patterns

if __name__ == "__main__":
    analyze_failed_docs()