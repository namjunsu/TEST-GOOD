#!/usr/bin/env python3
"""TVLogic 문서를 DB에 추가하는 스크립트"""
import sqlite3
import sys
from pathlib import Path

# DB 연결
db_path = Path("metadata.db")
if not db_path.exists():
    print(f"❌ DB 파일이 없습니다: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path), isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL")
cursor = conn.cursor()

print("=== TVLogic 문서 DB 추가 ===")

# 1. 기존 TVLogic 문서 삭제
cursor.execute("DELETE FROM documents WHERE filename = ?",
               ('2025-08-13_TVLogic_모니터_구매_검토서.pdf',))
print("✓ 기존 문서 삭제 완료")

# 2. 텍스트 파일 읽기
txt_path = Path("data/extracted/2025-08-13_TVLogic_모니터_구매_검토서.txt")
if txt_path.exists():
    text_preview = txt_path.read_text(encoding='utf-8')[:500]
    print(f"✓ 텍스트 파일 읽기 완료: {len(text_preview)} 문자")
else:
    text_preview = "TVLogic 모니터 구매 검토서"
    print("⚠ 텍스트 파일 없음, 기본 텍스트 사용")

# 3. 새 문서 추가
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
    text_preview,
    '["TVLogic", "모니터", "구매"]',
    'disposal',
    '2025-08-13',
    '2025-08-13_TVLogic_모니터_구매_검토서.pdf'
))

doc_id = cursor.lastrowid
print(f"✓ 문서 추가: ID={doc_id}")

# 4. FTS 인덱스 추가
try:
    cursor.execute("""
        INSERT INTO documents_fts(rowid, path, title, text_preview, keywords)
        SELECT id, path, title, text_preview, keywords
        FROM documents WHERE id = ?
    """, (doc_id,))
    print(f"✓ FTS 인덱스 추가 완료")
except Exception as e:
    print(f"⚠ FTS 인덱스 추가 실패: {e}")

# 5. 명시적 커밋
conn.commit()
print("✓ 변경사항 커밋 완료")

# 6. 확인
cursor.execute("SELECT id, filename, year, category FROM documents WHERE id = ?", (doc_id,))
row = cursor.fetchone()
if row:
    print(f"\n✅ 확인 성공!")
    print(f"  ID: {row[0]}")
    print(f"  파일명: {row[1]}")
    print(f"  연도: {row[2]}")
    print(f"  카테고리: {row[3]}")
else:
    print("\n❌ 추가 실패 - DB에서 찾을 수 없음")
    sys.exit(1)

conn.close()

# 7. WAL 체크포인트
import subprocess
print("\n=== WAL 체크포인트 실행 ===")
result = subprocess.run(['sqlite3', 'metadata.db', 'PRAGMA wal_checkpoint(FULL);'],
                       capture_output=True, text=True)
print(f"✓ WAL 체크포인트 완료: {result.stdout.strip()}")

print("\n=== 최종 확인 ===")
result = subprocess.run(['sqlite3', 'metadata.db',
                        "SELECT COUNT(*) FROM documents WHERE filename LIKE '%TVLogic%';"],
                       capture_output=True, text=True)
count = int(result.stdout.strip())
if count > 0:
    print(f"✅ 성공! TVLogic 문서가 DB에 있습니다 (개수: {count})")
else:
    print("❌ 실패! TVLogic 문서가 DB에 없습니다")
    sys.exit(1)
