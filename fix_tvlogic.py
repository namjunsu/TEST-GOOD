#!/usr/bin/env python3
import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

# 텍스트 파일 읽기
txt_path = Path("data/extracted/2025-08-13_TVLogic_모니터_구매_검토서.txt")
text_content = txt_path.read_text(encoding='utf-8')[:500] if txt_path.exists() else ""

# DB에 직접 추가
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()

# 먼저 기존 것 삭제
cursor.execute("DELETE FROM documents WHERE filename = ?", ('2025-08-13_TVLogic_모니터_구매_검토서.pdf',))

# 새로 추가
cursor.execute("""
    INSERT INTO documents (
        path, filename, title, date, year, month, category,
        drafter, amount, file_size, page_count, text_preview, 
        keywords, doctype, display_date, normalized_filename
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    'processed/2025-08-13_TVLogic_모니터_구매_검토서.pdf',
    '2025-08-13_TVLogic_모니터_구매_검토서.pdf',
    'TVLogic 모니터 구매 검토서',
    '2025-08-13',
    '2025',
    '08',
    '구매',
    '',
    0,
    3451412,
    2,
    text_content,
    '["TVLogic", "모니터", "구매"]',
    'disposal',
    '2025-08-13',
    '2025-08-13_TVLogic_모니터_구매_검토서.pdf'
))

conn.commit()
print(f"✅ TVLogic 문서 DB 추가 완료 (ID: {cursor.lastrowid})")

# 확인
cursor.execute("SELECT id, filename FROM documents WHERE filename LIKE '%TVLogic%'")
for row in cursor.fetchall():
    print(f"  확인: ID={row[0]}, 파일명={row[1]}")

conn.close()
