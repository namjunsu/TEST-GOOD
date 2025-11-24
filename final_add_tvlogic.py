#!/usr/bin/env python3
import sqlite3
import sys

# DB 연결
conn = sqlite3.connect("metadata.db", isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL")
cursor = conn.cursor()

# 기존 TVLogic 삭제
cursor.execute("DELETE FROM documents WHERE filename = ?", 
               ('2025-08-13_TVLogic_모니터_구매_검토서.pdf',))

# 새로 추가
cursor.execute("""
    INSERT INTO documents (
        path, filename, title, date, year, month, category,
        drafter, amount, file_size, page_count, text_preview,
        keywords, doctype, display_date, normalized_filename
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    'year_2025/2025-08-13_TVLogic_모니터_구매_검토서.pdf',
    '2025-08-13_TVLogic_모니터_구매_검토서.pdf',
    'TVLogic 모니터 구매 검토서',
    '2025-08-13',
    '2025',
    '2025-08',
    '구매',
    '',
    0,
    3451412,
    2,
    'TVLogic 모니터 구매 검토서 - 기안부서: 기술관리팀-보도기술관리파트',
    '["TVLogic", "모니터", "구매"]',
    'disposal',
    '2025-08-13',
    '2025-08-13_TVLogic_모니터_구매_검토서.pdf'
))

doc_id = cursor.lastrowid
print(f"✅ 문서 추가: ID={doc_id}")

# FTS 추가
cursor.execute("""
    INSERT INTO documents_fts(rowid, path, title, text_preview, keywords)
    SELECT id, path, title, text_preview, keywords 
    FROM documents WHERE id = ?
""", (doc_id,))

print(f"✅ FTS 인덱스 추가 완료")

# 확인
cursor.execute("SELECT id, filename, year FROM documents WHERE id = ?", (doc_id,))
row = cursor.fetchone()
if row:
    print(f"✅ 확인: ID={row[0]}, 파일명={row[1]}, 연도={row[2]}")
else:
    print("❌ 추가 실패")
    sys.exit(1)

conn.commit()
conn.close()

print("\n=== DB 저장 완료, WAL 체크포인트 실행 ===")
import subprocess
subprocess.run(['sqlite3', 'metadata.db', 'PRAGMA wal_checkpoint(FULL);'])

