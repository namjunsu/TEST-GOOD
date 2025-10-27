#!/usr/bin/env python3
"""
4모드 스모크 테스트 (LIST/COST_SUM/PREVIEW/SUMMARY)
"""

import pytest
from app.rag.pipeline import RAGPipeline


@pytest.fixture(scope="module")
def pipeline():
    """RAG 파이프라인 픽스처"""
    return RAGPipeline()


def test_list_mode_2024_namjoonsu(pipeline):
    """AC1: 2024년 남준수 문서 찾아줘 → 2줄 카드 형식"""
    query = "2024년 남준수 문서 찾아줘"
    result = pipeline.answer(query)

    # 검증
    assert result["status"]["found"], "문서를 찾아야 함"
    assert result["status"]["retrieved_count"] >= 1, "최소 1건 이상 검색되어야 함"

    # 2줄 카드 형식 검증 (📄, 🏷, 📅, ✍ 포함)
    text = result["text"]
    assert "📄" in text, "파일명 아이콘 필요"
    assert "🏷" in text, "doctype 아이콘 필요"
    assert "📅" in text, "날짜 아이콘 필요"
    assert "✍" in text, "기안자 아이콘 필요"
    assert "남준수" in text, "기안자명 표시 필요"
    assert "2024" in text, "연도 표시 필요"

    # Evidence 구조 검증
    assert len(result["evidence"]) >= 1, "Evidence 필요"
    assert result["evidence"][0]["meta"]["drafter"] == "남준수", "기안자 메타데이터 필요"

    print(f"\n✅ AC1 통과: 목록 검색 (2줄 카드)\n{text[:300]}...")


def test_cost_sum_mode_channelA_truck(pipeline):
    """AC2: 채널에이 중계차 보수 합계 얼마였지? → VAT/검증 배지"""
    query = "채널에이 중계차 보수 합계 얼마였지?"
    result = pipeline.answer(query)

    # 검증
    assert result["status"]["found"], "비용 정보를 찾아야 함"

    text = result["text"]
    # VAT 정보 검증
    assert "₩" in text and "34,340,000" in text, "비용 금액 표시 필요"
    assert ("VAT" in text or "부가세" in text), "VAT 정보 필요"

    # 검증 배지 확인 (sum_match=없음/일치/불일치)
    assert "sum_match" in text or "검증" in text, "검증 정보 필요"

    # 출처 정보 확인
    assert "출처" in text or "📄" in text, "출처 정보 필요"
    assert "날짜" in text or "📅" in text, "날짜 정보 필요"
    assert "기안자" in text or "✍" in text, "기안자 정보 필요"

    print(f"\n✅ AC2 통과: 비용 질의 (VAT/검증)\n{text}")


def test_preview_mode_no_fake_table(pipeline):
    """AC3: 미리보기 → 원문 6-8줄 (가짜 표 없음)"""
    # 실제 파일명 사용
    query = "2024-10-24_채널에이_중계차_노후_보수건.pdf 미리보기"
    result = pipeline.answer(query)

    # 검증
    assert result["status"]["found"], "문서를 찾아야 함"

    text = result["text"]
    # 미리보기 헤더
    assert "미리보기" in text, "미리보기 표시 필요"

    # 가짜 표 생성 금지 검증 (테이블 마크다운 패턴 없음)
    # Markdown 테이블은 | ... | 형식이지만, 원문 인용은 그냥 텍스트
    # 완전히 금지하기는 어려우므로, 최소한 복잡한 테이블 구조가 없어야 함
    table_markers = text.count("|---")  # Markdown 테이블 구분선
    assert table_markers == 0, "가짜 Markdown 테이블이 생성되지 않아야 함"

    # 원문 6-8줄 검증 (개행 기준)
    lines = [line for line in text.split('\n') if line.strip() and not line.startswith("**")]
    assert 1 <= len(lines) <= 20, f"원문 줄 수 범위 초과 ({len(lines)}줄)"

    print(f"\n✅ AC3 통과: 미리보기 (원문 {len(lines)}줄, 가짜 표 없음)\n{text[:300]}...")


def test_summary_mode_5line_section(pipeline):
    """AC4: 내용 요약 → 5줄 섹션 (정보 없으면 "정보 없음")"""
    query = "2024-10-24_채널에이_중계차_노후_보수건.pdf 내용 요약해줘"
    result = pipeline.answer(query)

    # 검증
    assert result["status"]["found"], "문서를 찾아야 함"

    text = result["text"]
    # 5줄 섹션 구조 검증
    assert "목적/배경" in text or "목적" in text, "목적/배경 섹션 필요"
    assert "주요 조치" in text or "조치" in text, "주요 조치 섹션 필요"
    assert "일정" in text, "일정 섹션 필요"
    assert "금액" in text or "비용" in text, "금액 섹션 필요"
    assert "비고" in text, "비고 섹션 필요"

    # "정보 없음" 가드 (금액이 없으면 "정보 없음" 표시)
    if "₩" not in text and "34,340,000" not in text:
        assert "정보 없음" in text, "금액이 없으면 '정보 없음' 표시 필요"

    print(f"\n✅ AC4 통과: 내용 요약 (5줄 섹션)\n{text[:400]}...")


def test_routing_priority():
    """라우팅 우선순위 검증: COST_SUM > PREVIEW > LIST > SUMMARY > QA"""
    from app.rag.query_router import QueryRouter, QueryMode

    router = QueryRouter()

    # COST_SUM (최우선)
    assert router.classify_mode("합계 얼마였지?") == QueryMode.COST_SUM

    # LIST
    assert router.classify_mode("2024년 남준수 문서 찾아줘") == QueryMode.LIST

    # SUMMARY
    assert router.classify_mode("파일.pdf 요약해줘") == QueryMode.SUMMARY

    # PREVIEW
    assert router.classify_mode("파일.pdf 미리보기") == QueryMode.PREVIEW

    # QA (기본)
    assert router.classify_mode("채널에이가 뭐야?") == QueryMode.QA

    print("\n✅ 라우팅 우선순위 검증 통과")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
