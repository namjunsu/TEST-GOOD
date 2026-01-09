#!/usr/bin/env python3
"""
미등록 PDF 파일 찾기
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

# 물리적 파일 목록
docs_dir = Path("docs")
pdf_files = set()
for pdf in docs_dir.rglob("*.pdf"):
    pdf_files.add(pdf.name)

print(f"물리 PDF 파일: {len(pdf_files)}개")

# DB 등록 파일 목록
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()
cursor.execute("SELECT filename FROM documents")
db_files = set(row[0] for row in cursor.fetchall())
conn.close()

print(f"DB 등록 문서: {len(db_files)}개")

# 미등록 파일 찾기
missing = pdf_files - db_files
print(f"\n미등록 파일: {len(missing)}개")

if missing:
    print("\n미등록 파일 목록:")
    for i, filename in enumerate(sorted(missing), 1):
        # 파일 경로 찾기
        for pdf_path in docs_dir.rglob(filename):
            print(f"{i}. {filename}")
            print(f"   경로: {pdf_path}")
            break
