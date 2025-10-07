#!/usr/bin/env python3
"""
콘텐츠 검색 기능 테스트
일부 문서만 처리해서 콘텐츠 검색이 작동하는지 확인
"""

import os
import sqlite3
from pathlib import Path
from everything_like_search import EverythingLikeSearch
import pdfplumber

def test_content_extraction():
    """몇 개 문서만 선택해서 콘텐츠 추출 테스트"""
    print("🧪 콘텐츠 추출 테스트")

    docs_dir = Path("docs")
    pdf_files = list(docs_dir.rglob("*.pdf"))[:10]  # 처음 10개만

    search_engine = EverythingLikeSearch()

    for pdf_path in pdf_files:
        print(f"\n📄 테스트: {pdf_path.name}")

        # 콘텐츠 추출
        content = search_engine._extract_text_content(pdf_path)

        if content:
            print(f"✅ 추출 성공: {len(content)}자")
            print(f"미리보기: {content[:200]}...")

            # 기안자나 중요 키워드 검색
            if '기안자' in content:
                print("🎯 '기안자' 발견!")
            if '최새름' in content:
                print("🎯 '최새름' 발견!")
            if '남준수' in content:
                print("🎯 '남준수' 발견!")
        else:
            print("❌ 텍스트 없음 (스캔 문서)")

def test_manual_db_update():
    """수동으로 몇 개 문서만 DB에 콘텐츠 추가"""
    print("\n🔧 수동 DB 업데이트 테스트")

    # 직접 DB 연결
    db_path = Path("everything_index.db")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 기존 문서 중 몇 개 선택
    cursor.execute("SELECT id, filename, path FROM files LIMIT 5")
    rows = cursor.fetchall()

    search_engine = EverythingLikeSearch()

    for row in rows:
        file_id, filename, file_path = row
        print(f"\n📝 업데이트: {filename}")

        # 콘텐츠 추출
        content = search_engine._extract_text_content(Path(file_path))

        if content:
            # DB 업데이트
            cursor.execute("UPDATE files SET content = ? WHERE id = ?", (content, file_id))
            print(f"✅ 콘텐츠 저장: {len(content)}자")

            # 기안자 검색
            if '기안자' in content:
                print("🎯 기안자 정보 포함!")
        else:
            print("❌ 콘텐츠 없음")

    conn.commit()
    conn.close()

    # 검색 테스트
    print("\n🔍 콘텐츠 검색 테스트")
    results = search_engine.search('기안자', limit=5)
    print(f"검색 결과: {len(results)}개")

    for i, result in enumerate(results, 1):
        print(f"{i}. {result['filename']}")
        if result.get('content'):
            preview = result['content'][:100]
            print(f"   콘텐츠: {preview}...")

if __name__ == "__main__":
    test_content_extraction()
    test_manual_db_update()