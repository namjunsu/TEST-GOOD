#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

from app.data.metadata_db import MetadataDB

db = MetadataDB("metadata.db")

# TVLogic 문서 정보
doc_data = {
    "path": "year_2025/2025-08-13_TVLogic_모니터_구매_검토서.pdf",
    "filename": "2025-08-13_TVLogic_모니터_구매_검토서.pdf",
    "title": "TVLogic 모니터 구매 검토서",
    "date": "2025-08-13",
    "year": "2025",
    "month": "2025-08",
    "category": "구매",
    "drafter": "",
    "amount": 0,
    "file_size": 3451412,
    "page_count": 2,
    "text_preview": "TVLogic 모니터 구매 검토서",
    "keywords": ["TVLogic", "모니터", "구매"],
    "doctype": "disposal",
    "display_date": "2025-08-13"
}

# upsert_document 메서드가 있는지 확인
methods = [m for m in dir(db) if not m.startswith('_')]
print(f"사용 가능한 메서드: {methods}")

# 직접 SQL로 추가
import sqlite3
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()

cursor.execute("DELETE FROM documents WHERE filename = ?", (doc_data["filename"],))

cursor.execute("""
    INSERT INTO documents (
        path, filename, title, date, year, month, category,
        drafter, amount, file_size, page_count, text_preview,
        keywords, doctype, display_date, normalized_filename
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    doc_data["path"],
    doc_data["filename"],
    doc_data["title"],
    doc_data["date"],
    doc_data["year"],
    doc_data["month"],
    doc_data["category"],
    doc_data["drafter"],
    doc_data["amount"],
    doc_data["file_size"],
    doc_data["page_count"],
    doc_data["text_preview"],
    str(doc_data["keywords"]),
    doc_data["doctype"],
    doc_data["display_date"],
    doc_data["filename"]
))

doc_id = cursor.lastrowid
conn.commit()
print(f"✅ 문서 추가 완료: ID={doc_id}")

# 확인
cursor.execute("SELECT id, filename FROM documents WHERE id = ?", (doc_id,))
row = cursor.fetchone()
if row:
    print(f"✅ 확인: ID={row[0]}, 파일명={row[1]}")
else:
    print("❌ 추가되지 않음")

conn.close()
