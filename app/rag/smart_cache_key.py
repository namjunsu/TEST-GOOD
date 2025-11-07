#!/usr/bin/env python3
"""
Smart Cache Key Generator
Normalizes queries to improve cache hit rate through synonym handling and normalization
"""
import re
import hashlib
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
    """공백 정규화"""
    # 여러 공백을 하나로
    query = re.sub(r'\s+', ' ', query)
    return query.strip()


def normalize_punctuation(query: str) -> str:
    """구두점 정규화"""
    # 물음표, 느낌표 등 제거
    query = re.sub(r'[?!.,;:]', '', query)
    return query


def generate_smart_cache_key(query: str, mode: str = None) -> str:
    """
    Generate intelligent cache key with normalization

    Args:
        query: Original query string
        mode: Optional mode identifier

    Returns:
        Normalized cache key
    """
    # 1. 소문자 변환
    normalized = query.lower().strip()

    # 2. 공백 정규화
    normalized = normalize_whitespace(normalized)

    # 3. 구두점 정규화
    normalized = normalize_punctuation(normalized)

    # 4. 날짜 표현 정규화
    normalized = normalize_date_expressions(normalized)

    # 5. 동의어 치환
    normalized = replace_synonyms(normalized)

    # 6. 모드 추가
    if mode:
        normalized = f"{mode}:{normalized}"

    # 7. 해시 생성 (짧은 키)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# 테스트용
if __name__ == "__main__":
    test_queries = [
        ("뷰파인더 케이블 얼마?", "뷰파인더 케이블 가격"),
        ("뷰파인더 선 비용?", "뷰파인더 케이블 얼마"),
        ("문서 찾아줘", "문서 검색해줘"),
        ("자세히 알려주세요", "상세히 알려줘"),
    ]

    print("Smart Cache Key Test:")
    print("=" * 80)

    for q1, q2 in test_queries:
        key1 = generate_smart_cache_key(q1)
        key2 = generate_smart_cache_key(q2)
        match = "✅ MATCH" if key1 == key2 else "❌ DIFFERENT"

        print(f"\nQuery 1: {q1}")
        print(f"Query 2: {q2}")
        print(f"Key 1:   {key1}")
        print(f"Key 2:   {key2}")
        print(f"Result:  {match}")