"""
claimed_total 폴백 추출 테스트
2025-10-27

폴백 정규식이 본문에서 "비용 합계", "합계(VAT별도)" 등의 패턴을 정확히 추출하는지 검증합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ingest_from_docs import extract_claimed_total_fallback


def test_claimed_total_fallback_basic():
    """기본 폴백 추출: 합계(VAT별도) 34,340,000원"""
    text = """
    채널에이 방송 중계차의 노후로 장애가 발생되어 보수하고자 함.

    비용 합계(VAT별도) 34,340,000원

    종합 검토 의견:
    - 채널에이 중계차 시스템을 보수하여 특보 상황에 대비할 것을 권장함.
    """

    result = extract_claimed_total_fallback(text)
    assert result == 34340000, f"Expected 34340000, got {result}"


def test_claimed_total_fallback_variants():
    """다양한 합계 라벨 패턴 테스트"""

    # 패턴 1: 비용 합계
    text1 = "비용 합계 1,200,000원"
    assert extract_claimed_total_fallback(text1) == 1200000

    # 패턴 2: 총계
    text2 = "총계: 500,000원"
    assert extract_claimed_total_fallback(text2) == 500000

    # 패턴 3: 합계 (단, "합계 검증" 제외)
    text3 = "합계 300000원"
    assert extract_claimed_total_fallback(text3) == 300000

    # 패턴 4: 합계 검증은 무시
    text4 = "합계 검증 완료"
    assert extract_claimed_total_fallback(text4) is None


def test_claimed_total_no_table_context():
    """표 없이 합계만 있는 경우 (sum_match는 None이어야 함)"""
    text = """
    방송 프로그램 제작용 건전지 소모품 구매의 건

    1. 개요: 채널에이 방송프로그램 제작에 필요한 MIC용 건전지 구매

    총계 1,200,000원

    담당자: 최새름 010-9900-1753
    """

    result = extract_claimed_total_fallback(text)
    assert result == 1200000, f"Expected 1200000, got {result}"
    # 참고: sum_match는 None이어야 하지만 이 테스트에서는 추출만 검증


def test_claimed_total_with_currency_symbols():
    """통화 기호 포함 패턴"""

    # KRW 표기
    text1 = "합계(VAT별도) 1,500,000 KRW"
    assert extract_claimed_total_fallback(text1) == 1500000

    # ₩ 기호
    text2 = "비용 합계 ₩ 2,000,000"
    assert extract_claimed_total_fallback(text2) == 2000000


def test_claimed_total_extraction_failure():
    """추출 실패 케이스"""

    # 합계 라벨 없음
    text1 = "총 비용은 1,000,000원입니다"
    assert extract_claimed_total_fallback(text1) is None

    # 숫자 없음
    text2 = "합계: 협의 필요"
    assert extract_claimed_total_fallback(text2) is None

    # 합계 검증 (제외 패턴)
    text3 = "합계 검증: 1,000,000원"
    assert extract_claimed_total_fallback(text3) is None
