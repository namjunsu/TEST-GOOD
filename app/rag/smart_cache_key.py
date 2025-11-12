#!/usr/bin/env python3
"""
Smart Cache Key Generator
Normalizes queries to improve cache hit rate through synonym handling and normalization
"""
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, Set

# 동의어 매핑
SYNONYMS: Dict[str, Set[str]] = {
    "얼마": {"가격", "비용", "금액", "price", "cost"},
    "찾아줘": {"찾아주세요", "검색", "찾기", "검색해줘", "알려줘"},
    "자세히": {"자세하게", "상세히", "구체적으로", "세세하게", "디테일하게"},
    "뷰파인더": {"viewfinder", "뷰파인더"},
    "케이블": {"cable", "선"},
    "마이크": {"mic", "microphone", "mike"},
    "카메라": {"camera", "cam"},
}

# 역방향 매핑 생성 (빠른 조회용)
SYNONYM_MAP: Dict[str, str] = {}
for canonical, synonyms in SYNONYMS.items():
    for syn in synonyms:
        SYNONYM_MAP[syn.lower()] = canonical
    SYNONYM_MAP[canonical.lower()] = canonical


def normalize_date_expressions(query: str) -> str:
    """날짜 표현을 정규화"""
    today = datetime.now()

    # "오늘" -> 실제 날짜
    if "오늘" in query:
        query = query.replace("오늘", today.strftime("%Y년 %m월 %d일"))

    # "어제" -> 실제 날짜
    if "어제" in query:
        yesterday = today - timedelta(days=1)
        query = query.replace("어제", yesterday.strftime("%Y년 %m월 %d일"))

    # "이번달" -> 실제 연월
    if "이번달" in query or "이번 달" in query:
        query = re.sub(r"이번\s?달", today.strftime("%Y년 %m월"), query)

    return query


def replace_synonyms(query: str) -> str:
    """동의어를 표준 형태로 치환"""
    words = query.split()
    normalized_words = []

    for word in words:
        word_lower = word.lower()
        if word_lower in SYNONYM_MAP:
            normalized_words.append(SYNONYM_MAP[word_lower])
        else:
            normalized_words.append(word)

    return " ".join(normalized_words)


def normalize_whitespace(query: str) -> str:
    """공백 정규화 (모델명/기기명 통일)"""
    # 영문/숫자 조합 사이 공백 제거 (LVM 180A → LVM180A) - 반복 적용
    prev = ""
    while prev != query:
        prev = query
        query = re.sub(r"([a-z0-9])\s+([a-z0-9])", r"\1\2", query, flags=re.IGNORECASE)

    # 여러 공백을 하나로
    query = re.sub(r"\s+", " ", query)
    return query.strip()


def normalize_punctuation(query: str) -> str:
    """구두점 및 특수문자 정규화 (모델명 통일)"""
    # 물음표, 느낌표, 쉼표, 세미콜론, 콜론 제거
    query = re.sub(r"[?!.,;:]", "", query)
    # 하이픈, 슬래시, 언더스코어를 공백으로 (모델명 정규화: "LVM-180A" → "LVM 180A")
    query = re.sub(r"[-/_]", " ", query)
    return query


def _norm_key(query: str) -> str:
    """
    정규화된 쿼리 문자열 반환 (해시 없음)

    Args:
        query: 원본 쿼리 문자열

    Returns:
        정규화된 문자열 (비교/디버깅용)
    """
    # 1. 소문자 변환
    normalized = query.lower().strip()

    # 2. 구두점 정규화 (먼저 수행 - 하이픈을 공백으로)
    normalized = normalize_punctuation(normalized)

    # 3. 공백 정규화 (영문/숫자 조합 공백 제거)
    normalized = normalize_whitespace(normalized)

    # 4. 날짜 표현 정규화
    normalized = normalize_date_expressions(normalized)

    # 5. 동의어 치환
    normalized = replace_synonyms(normalized)

    return normalized


def generate_smart_cache_key(query: str, mode: str | None = None) -> str:
    """
    Generate intelligent cache key with normalization

    Args:
        query: Original query string
        mode: Optional mode identifier

    Returns:
        Normalized cache key (hashed)
    """
    # 정규화 수행
    normalized = _norm_key(query)

    # 모드 추가
    if mode:
        normalized = f"{mode}:{normalized}"

    # 해시 생성 (짧은 키)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# 테스트용
if __name__ == "__main__":
    test_queries = [
        ("뷰파인더 케이블 얼마?", "뷰파인더 케이블 가격"),
        ("뷰파인더 선 비용?", "뷰파인더 케이블 얼마"),
        ("문서 찾아줘", "문서 검색해줘"),
        ("자세히 알려주세요", "상세히 알려줘"),
        ("LVM-180A 사양?", "lvm180a 사양"),  # 모델명 정규화 테스트
        ("채널A/중계차 비용", "채널a 중계차 가격"),  # 특수문자 + 동의어
    ]

    print("Smart Cache Key Test:")
    print("=" * 80)

    for q1, q2 in test_queries:
        norm1 = _norm_key(q1)
        norm2 = _norm_key(q2)
        key1 = generate_smart_cache_key(q1)
        key2 = generate_smart_cache_key(q2)
        match = "✅ MATCH" if key1 == key2 else "❌ DIFFERENT"

        print(f"\nQuery 1:      {q1}")
        print(f"Normalized 1: {norm1}")
        print(f"Query 2:      {q2}")
        print(f"Normalized 2: {norm2}")
        print(f"Key 1:        {key1}")
        print(f"Key 2:        {key2}")
        print(f"Result:       {match}")
