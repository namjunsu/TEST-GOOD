"""
검색 결과 목록 후처리 테스트
"""

import pytest
from app.rag.render.list_postprocess import dedup_and_clean


def _mk(**kw):
    """테스트용 검색 결과 항목 생성"""
    return {
        "filename": "2025-08-26_뷰파인더_소모품_케이블_구매_건.pdf",
        "date": "2025-08-27",
        "drafter": "최새름",
        "category": "소모품",
        "content": "25. 9. 18. 오후 3:32 ... approval_form_popup.php?doc=123 ... gw.channela-mt.com ...",
        "score": 0.7,
        **kw
    }


def test_noise_removed_and_snippet_fallback():
    """노이즈 제거 및 빈 스니펫 폴백 테스트"""
    items = [
        _mk(),
        _mk(filename="2025-08-26_뷰파인더_소모품_케이블_구매_건(1).pdf", content=""),  # 빈 스니펫 폴백
    ]
    out = dedup_and_clean(items)

    # 중복 제거: 동일 파일 → 1건
    assert len(out) == 1

    s = out[0]["snippet"]

    # 노이즈 제거 확인
    assert "오후" not in s, "타임스탬프 노이즈가 남아있음"
    assert "gw.channela-mt.com" not in s, "내부 URL 노이즈가 남아있음"
    assert "approval_form_popup" not in s, "프린트뷰 URL 노이즈가 남아있음"

    # 빈 스니펫 아님
    assert len(s) > 0, "스니펫이 비어있음 (폴백 실패)"


def test_dedup_by_normalized_filename():
    """정규화된 파일명 기준 중복 제거"""
    items = [
        _mk(score=0.5),
        _mk(filename="2025-08-26_뷰파인더_소모품_케이블_구매_건(1).pdf", score=0.9),
        _mk(filename="2025-08-26_뷰파인더_소모품_케이블_구매_건_1.pdf", score=0.8),
        _mk(filename="2025 08 26 뷰파인더 소모품 케이블 구매 건.PDF", score=0.6),  # 공백, 대소문자 변형
    ]
    out = dedup_and_clean(items)

    # 모두 동일 파일로 판단 → 1건만 남음
    assert len(out) == 1, f"중복 제거 실패: {len(out)}건 남음 (예상 1건)"

    # 가장 높은 스코어(0.9)인 항목이 선택됨
    assert out[0]["score"] == 0.9


def test_sorting_date_desc():
    """날짜 내림차순 정렬 테스트"""
    a = _mk(filename="A.pdf", date="2025-06-01")
    b = _mk(filename="B.pdf", date="2025-09-01")
    c = _mk(filename="C.pdf", date="2025-03-01")

    out = dedup_and_clean([a, b, c])

    # 날짜 내림차순: 2025-09-01 > 2025-06-01 > 2025-03-01
    assert len(out) == 3
    assert out[0]["filename"] == "B.pdf"
    assert out[1]["filename"] == "A.pdf"
    assert out[2]["filename"] == "C.pdf"


def test_empty_snippet_uses_metadata_fallback():
    """빈 스니펫 시 메타데이터 기반 폴백"""
    items = [
        _mk(
            filename="test.pdf",
            content="",  # 빈 컨텐츠
            title="테스트 문서",
            drafter="홍길동",
            date="2025-10-26",
            category="구매",
        )
    ]
    out = dedup_and_clean(items)

    s = out[0]["snippet"]

    # 메타데이터 폴백 확인
    assert "테스트 문서" in s
    assert "홍길동" in s
    assert "2025-10-26" in s
    assert "구매" in s


def test_snippet_key_added():
    """snippet 키가 모든 항목에 추가되는지 확인"""
    items = [
        _mk(filename="A.pdf"),
        _mk(filename="B.pdf"),
    ]
    out = dedup_and_clean(items)

    for item in out:
        assert "snippet" in item, "snippet 키가 없음"
        assert isinstance(item["snippet"], str), "snippet 값이 문자열이 아님"
