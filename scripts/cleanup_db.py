#!/usr/bin/env python3
"""
DB에서 물리 파일이 없는 레코드 삭제
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

# DB 연결
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()

# 모든 문서 조회
cursor.execute("SELECT id, filename, path FROM documents")
rows = cursor.fetchall()

print(f"DB 총 레코드: {len(rows)}개")

# 물리 파일 없는 레코드 찾기
to_delete = []
for doc_id, filename, path in rows:
    pdf_path = Path(path)
    if not pdf_path.exists():
        to_delete.append((doc_id, filename, path))
        print(f"❌ 물리 파일 없음: {filename} (path={path})")

if to_delete:
    print(f"\n삭제할 레코드: {len(to_delete)}개")
    for doc_id, filename, path in to_delete:
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        print(f"  ✓ 삭제: {filename}")

    conn.commit()
    print(f"\n✅ {len(to_delete)}개 레코드 삭제 완료")
else:
    print("\n✅ 모든 레코드가 물리 파일과 일치합니다")

conn.close()

# 최종 확인
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM documents")
final_count = cursor.fetchone()[0]
conn.close()

print(f"\n최종 DB 레코드 수: {final_count}개")
