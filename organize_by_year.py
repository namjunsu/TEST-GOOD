#!/usr/bin/env python3
"""processed 폴더의 파일을 연도별로 정리"""
from pathlib import Path
import shutil
import re

processed_dir = Path("docs/processed")
docs_dir = Path("docs")

for pdf in processed_dir.glob("*.pdf"):
    # 파일명에서 연도 추출 (YYYY-MM-DD 형식)
    match = re.match(r"(\d{4})-\d{2}-\d{2}", pdf.name)
    if match:
        year = match.group(1)
        year_dir = docs_dir / f"year_{year}"
        year_dir.mkdir(exist_ok=True)
        
        dest = year_dir / pdf.name
        if not dest.exists():
            shutil.move(str(pdf), str(dest))
            print(f"이동: {pdf.name} → year_{year}/")
        else:
            print(f"이미 존재: {dest}")

print("\n✅ 연도별 정리 완료")

# 결과 확인
for year_dir in sorted(docs_dir.glob("year_*")):
    count = len(list(year_dir.glob("*.pdf")))
    print(f"  {year_dir.name}: {count}개 문서")
