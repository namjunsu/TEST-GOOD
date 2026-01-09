#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.document_loader import load_documents

df = load_documents()

print("=" * 80)
print("load_documents() 결과 확인")
print("=" * 80)

if df.empty:
    print("❌ DataFrame이 비어있습니다.")
else:
    print(f"총 문서 수: {len(df)}")
    print(f"컬럼: {list(df.columns)}")

    # year 컬럼 타입 확인
    if 'year' in df.columns:
        print(f"\nyear 컬럼 타입: {df['year'].dtype}")
        print(f"year 샘플 값 (처음 5개):")
        for idx, row in df.head(5).iterrows():
            print(f"  {row['filename'][:50]:50} year={row['year']} (type={type(row['year']).__name__})")

    # 2018년 문서 확인
    if 'filename' in df.columns:
        docs_2018 = df[df['filename'].str.contains('2018', na=False)]
        print(f"\n2018년 문서: {len(docs_2018)}개")
        if len(docs_2018) > 0:
            print("샘플:")
            for idx, row in docs_2018.head(3).iterrows():
                year_val = row.get('year', 'N/A')
                print(f"  {row['filename']} → year={year_val} (type={type(year_val).__name__})")
