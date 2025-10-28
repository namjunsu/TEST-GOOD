#!/usr/bin/env python3
"""
페이지별 텍스트 API 테스트

metadata_db.get_page_text() 메서드의 동작을 검증합니다.
"""

import pytest
from modules.metadata_db import MetadataDB


@pytest.fixture
def metadata_db():
    """MetadataDB 인스턴스 생성"""
    return MetadataDB(db_path="metadata.db")


def test_get_page_text_api_exists(metadata_db):
    """get_page_text API 존재 여부 확인"""
    assert hasattr(metadata_db, "get_page_text"), "get_page_text 메서드가 없습니다"
    assert callable(metadata_db.get_page_text), "get_page_text가 호출 가능하지 않습니다"


@pytest.mark.integration
def test_get_page_text_basic(metadata_db):
    """get_page_text 기본 동작 테스트"""

    # DB에서 첫 번째 문서 조회
    cursor = metadata_db.conn.execute(
        "SELECT filename, page_count FROM documents WHERE page_count > 0 LIMIT 1"
    )
    row = cursor.fetchone()

    if not row:
        pytest.skip("테스트용 문서가 없습니다")

    filename = row["filename"]
    page_count = row["page_count"]

    print(f"\n테스트 문서: {filename} (총 {page_count}쪽)")

    # 첫 페이지 추출 테스트
    page1_text = metadata_db.get_page_text(filename, 1)

    print(f"  page1_text type: {type(page1_text)}")
    print(f"  page1_text value: {repr(page1_text)}")

    assert page1_text is not None, f"첫 페이지 추출 실패 (None 반환): filename={filename}"
    assert len(page1_text) > 0, f"추출된 텍스트가 비어 있음: filename={filename}, len={len(page1_text)}"

    print(f"  Page 1: {len(page1_text)}자 추출")
    print(f"  미리보기: {page1_text[:100]}...")

    # 캐시 테스트 (두 번째 호출은 빠름)
    import time

    # 첫 호출 (DB + PDF 파싱)
    start = time.time()
    text1 = metadata_db.get_page_text(filename, 1)
    elapsed1 = time.time() - start

    # 두 번째 호출 (캐시)
    start = time.time()
    text2 = metadata_db.get_page_text(filename, 1)
    elapsed2 = time.time() - start

    assert text1 == text2, "캐시된 텍스트가 다름"
    assert elapsed2 < elapsed1 * 0.5, f"캐시 효과 없음: {elapsed1:.3f}s vs {elapsed2:.3f}s"

    print(f"  캐시 효과: {elapsed1:.3f}s → {elapsed2:.3f}s (x{elapsed1/elapsed2:.1f})")


@pytest.mark.integration
def test_get_page_text_edge_cases(metadata_db):
    """get_page_text 예외 케이스 테스트"""

    # DB에서 문서 조회
    cursor = metadata_db.conn.execute(
        "SELECT filename, page_count FROM documents WHERE page_count > 0 LIMIT 1"
    )
    row = cursor.fetchone()

    if not row:
        pytest.skip("테스트용 문서가 없습니다")

    filename = row["filename"]
    page_count = row["page_count"]

    # 1. 존재하지 않는 문서
    result = metadata_db.get_page_text("nonexistent.pdf", 1)
    assert result is None, "존재하지 않는 문서에서 None 반환 실패"

    # 2. 범위 초과 페이지
    result = metadata_db.get_page_text(filename, page_count + 100)
    assert result is None, "페이지 범위 초과 시 None 반환 실패"

    # 3. 음수 페이지
    result = metadata_db.get_page_text(filename, -1)
    assert result is None, "음수 페이지에서 None 반환 실패"

    print(f"✅ 예외 케이스 처리 정상")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
