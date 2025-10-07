#!/usr/bin/env python3
"""
데이터베이스 동기화 스크립트
metadata.db의 기안자 정보를 everything_index.db의 department 컬럼에 동기화
"""

import sqlite3
import os
from pathlib import Path

def sync_databases():
    """두 데이터베이스간 기안자 정보 동기화"""

    # 파일 존재 확인
    metadata_db = "config/metadata.db"
    everything_db = "everything_index.db"

    if not os.path.exists(metadata_db):
        print(f"❌ {metadata_db} 파일이 없습니다.")
        return False

    if not os.path.exists(everything_db):
        print(f"❌ {everything_db} 파일이 없습니다.")
        return False

    print("🔄 데이터베이스 동기화 시작...")

    # metadata.db에서 기안자 정보 읽기
    meta_conn = sqlite3.connect(metadata_db)
    meta_cursor = meta_conn.cursor()

    meta_cursor.execute("SELECT path, drafter FROM documents WHERE drafter IS NOT NULL")
    drafters_data = meta_cursor.fetchall()
    print(f"📊 metadata.db에서 {len(drafters_data)}개 기안자 정보 발견")

    # everything_index.db 업데이트
    everything_conn = sqlite3.connect(everything_db)
    everything_cursor = everything_conn.cursor()

    updated_count = 0
    for file_path, drafter in drafters_data:
        # 파일명 추출
        filename = Path(file_path).name

        # everything_index.db에서 해당 파일 찾기
        everything_cursor.execute("SELECT id FROM files WHERE filename = ?", (filename,))
        result = everything_cursor.fetchone()

        if result:
            file_id = result[0]
            # department 컬럼을 기안자 정보로 업데이트
            everything_cursor.execute("UPDATE files SET department = ? WHERE id = ?", (drafter, file_id))
            updated_count += 1
            print(f"✅ {filename} -> 기안자: {drafter}")

    everything_conn.commit()
    print(f"🎉 {updated_count}개 파일의 기안자 정보 동기화 완료")

    # 동기화 결과 확인
    everything_cursor.execute("SELECT filename, department FROM files WHERE department LIKE '%남준수%'")
    results = everything_cursor.fetchall()
    print(f"\n✅ 남준수 기안자 문서 검색 확인: {len(results)}개")
    for r in results:
        print(f"  - {r[0]} (기안자: {r[1]})")

    meta_conn.close()
    everything_conn.close()

    return True

if __name__ == "__main__":
    success = sync_databases()
    if success:
        print("\n🚀 데이터베이스 동기화가 완료되었습니다!")
        print("이제 웹 인터페이스에서 '기안자 남준수 문서 찾아줘' 검색이 정상 작동할 것입니다.")
    else:
        print("\n❌ 데이터베이스 동기화 실패")