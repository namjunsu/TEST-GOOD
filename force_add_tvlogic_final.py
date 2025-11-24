#!/usr/bin/env python3
"""
TVLogic 문서를 DB에 강제로 추가하는 스크립트
파일은 이미 processed 폴더에 있고 텍스트도 추출되어 있음
"""
import sqlite3
from pathlib import Path
import hashlib

# 경로 설정
pdf_file = Path("docs/processed/2025-08-13_TVLogic_모니터_구매_검토서.pdf")
txt_file = Path("data/extracted/2025-08-13_TVLogic_모니터_구매_검토서.txt")

# 파일 존재 확인
if not pdf_file.exists():
    print(f"❌ PDF 파일 없음: {pdf_file}")
    exit(1)

if not txt_file.exists():
    print(f"❌ 텍스트 파일 없음: {txt_file}")
    exit(1)

# 텍스트 읽기
text_content = txt_file.read_text(encoding="utf-8")

# PDF 정보
file_size = pdf_file.stat().st_size
filename = pdf_file.name

# 메타데이터 파싱 (간단하게)
title = "TVLogic 모니터 구매 검토서"
date = "2025-08-13"
year = "2025"
month = "2025-08"

# DB 경로
rel_path = str(pdf_file.relative_to(Path("docs")))

print(f"📄 파일: {filename}")
print(f"📁 경로: {rel_path}")
print(f"📝 텍스트 길이: {len(text_content)} chars")
print(f"📊 파일 크기: {file_size:,} bytes")

# DB에 추가
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()

# 기존 레코드 삭제 (중복 방지)
cursor.execute("DELETE FROM documents WHERE filename = ?", (filename,))
deleted = cursor.rowcount
if deleted > 0:
    print(f"🗑️  기존 레코드 삭제: {deleted}개")

# text_preview 생성 (처음 500자)
text_preview = text_content[:500] if text_content else ""

# 새로운 레코드 삽입
cursor.execute("""
    INSERT INTO documents (
        filename, path, title, display_date, year, month,
        page_count, file_size, text_preview, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
""", (
    filename,
    rel_path,
    title,
    date,
    year,
    month,
    5,  # 페이지 수
    file_size,
    text_preview,
))

conn.commit()

# 확인
cursor.execute("SELECT id, filename, display_date FROM documents WHERE filename = ?", (filename,))
row = cursor.fetchone()
if row:
    print(f"\n✅ DB 추가 성공!")
    print(f"   ID: {row[0]}")
    print(f"   파일명: {row[1]}")
    print(f"   날짜: {row[2]}")
else:
    print("\n❌ DB 추가 실패")

conn.close()

# 중복 파일 제거
dup_file = Path("docs/processed/2025-08-13_TVLogic_모니터_구매_검토서(1).pdf")
if dup_file.exists():
    dup_file.unlink()
    print(f"\n🗑️  중복 파일 삭제: {dup_file.name}")
