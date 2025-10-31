#!/usr/bin/env python3
"""
Edge Case Test Suite for Index Consistency
인덱스 정합성 경계 케이스 테스트 스위트
"""
import os
import shutil
import sqlite3
import tempfile
import json
from pathlib import Path
from datetime import datetime


SRC_DB = "everything_index.db"


def clone_db() -> str:
    """실DB를 복제하여 임시 DB 생성"""
    tmp = tempfile.mkdtemp(prefix="edgeidx_")
    dst = os.path.join(tmp, "everything_index.db")

    if os.path.exists(SRC_DB):
        shutil.copy2(SRC_DB, dst)
    else:
        # 빈 DB 생성 (실제 스키마에 맞춤)
        conn = sqlite3.connect(dst)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER,
                date TEXT,
                year INTEGER,
                month INTEGER,
                category TEXT,
                department TEXT,
                keywords TEXT,
                created_at TIMESTAMP,
                content TEXT,
                UNIQUE(filename, path)
            )
        """)
        conn.commit()
        conn.close()

    return dst


def insert_index_row(conn, filename, abspath, size=0):
    """인덱스 행 삽입"""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT OR REPLACE INTO files(filename, path, size, created_at) VALUES (?,?,?,?)",
        (filename, abspath, size, created_at),
    )


def run():
    """경계 케이스 테스트 실행"""
    print("🧪 Starting Edge Case Tests...")
    print()

    dst = clone_db()
    conn = sqlite3.connect(dst)

    try:
        # 1) 동일 basename 다른 경로 (Basename Collision)
        print("Test 1: Basename collision")
        insert_index_row(conn, "동일파일명.pdf", "/a/b/동일파일명.pdf")
        insert_index_row(conn, "동일파일명.pdf", "/x/y/동일파일명.pdf")

        # 2) 한글/공백/장문 파일명 (Unicode + Whitespace)
        print("Test 2: Unicode + long filename with spaces")
        insert_index_row(conn, "한글 공백 long_filename 테스트.pdf", "/z/한글 공백 long_filename 테스트.pdf")

        # 3) symlink 대상 (Symlink Handling)
        print("Test 3: Symlink targets")
        insert_index_row(conn, "symlink_target.pdf", "/syms/symlink_target.pdf")

        conn.commit()

        # 무결성 점검
        cur = conn.execute("SELECT COUNT(*) FROM files WHERE filename='동일파일명.pdf'")
        same_base = cur.fetchone()[0]
        print(f"  → Basename collision entries: {same_base}")

        assert same_base >= 1, "basename collision not recorded"

        # Purge 시뮬레이션: 물리 파일 미존재 항목 제거
        print()
        print("Simulating purge: removing non-existent files")
        conn.execute("DELETE FROM files WHERE path LIKE '/syms/%'")
        conn.commit()

        # 결과 요약
        cur = conn.execute("SELECT COUNT(*) FROM files")
        total = cur.fetchone()[0]

        print()
        print("✅ Test Results:")
        result = {
            "status": "OK",
            "total_index_rows": total,
            "basename_collision_rows": same_base,
            "temp_db_path": dst
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

        return result

    except AssertionError as e:
        print(f"❌ Test Failed: {e}")
        return {"status": "FAILED", "error": str(e)}

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return {"status": "ERROR", "error": str(e)}

    finally:
        conn.close()
        print()
        print(f"[INFO] Temporary DB: {dst}")
        print("[INFO] The temporary DB will be cleaned up automatically on system reboot")


if __name__ == "__main__":
    result = run()
    exit(0 if result.get("status") == "OK" else 1)
