#!/usr/bin/env python3
"""
텍스트 정규화 모듈 (범용 RAG 코드 검색 강화)

모델/부품 코드의 일관된 정규화를 위한 핵심 모듈.
인제스트와 쿼리에서 동일한 규칙을 적용하여 재현성을 보장합니다.

주요 기능:
1. NFKC 정규화 + 공백 압축 + 대문자 고정
2. 하이픈 계열 통일 (en-dash, em-dash, minus → hyphen)
3. 코드 변형 자동 생성 (하이픈/공백/무공백 3종)
"""

import re
import unicodedata
from typing import List, Set


# 하이픈 계열 유니코드 문자 (U+2010~U+2014, U+2212)
HYPHEN_VARIANTS = {
    '\u2010',  # hyphen
    '\u2011',  # non-breaking hyphen
    '\u2012',  # figure dash
    '\u2013',  # en dash
    '\u2014',  # em dash
    '\u2212',  # minus sign
}

# 정규표현식: 모든 하이픈 변형
HYPHEN_PATTERN = re.compile(r'[\u2010\u2011\u2012\u2013\u2014\u2212]')

# 코드 추출 Denylist (오탐 방지)
CODE_DENYLIST = {
    # 방송 용어 (오탐 빈도 높음)
    "ONAIR", "OFFAIR",
    # 일반 용어 (4-8자 영문 코드 패턴 오탐 방지)
    "EMAIL", "TSHIRT", "THIS", "THAT", "HAVE", "BEEN", "WERE", "WILL",
    "FROM", "WITH", "WHEN", "WHAT", "WHERE", "WHICH", "ABOUT", "COULD",
    "WOULD", "SHOULD", "THEIR", "THERE", "THESE", "THOSE",
}

# 코드 패턴 정규식 (우선순위 높은 순서)
# 주의: \b는 한글 경계를 인식하지 못하므로 lookahead/lookbehind 사용
CODE_PATTERNS = [
    # [우선순위 1] 멀티세그먼트 코드 (1~4 세그먼트, 3~20자): XRN-1620B2, BE-68, COM/GROUPWARE/APPROVAL/APPROVAL
    # 각 세그먼트: 1~6자, 구분자: -, /, 공백
    re.compile(
        r'(?<![A-Z0-9])[A-Z]{1,4}[A-Z0-9]*[-/\s]+[A-Z0-9]{1,6}(?:[-/\s]+[A-Z0-9]{1,6}){0,2}(?![A-Z0-9])',
        re.IGNORECASE
    ),
    # [우선순위 2] 혼합형 (공백 포함 제품명): DeckLink 4K Extreme 12G
    re.compile(r'(?<![A-Za-z])[A-Z][a-z]+(?:\s+[A-Z0-9]+[A-Za-z0-9]*)+(?![A-Za-z])'),
    # [우선순위 3] 단일형 (영문+숫자 밀착): LVM180A, GS724Tv6, FX3 (최소 1숫자)
    re.compile(r'(?<![A-Z0-9])[A-Z]{2,}\d+[A-Za-z0-9]*(?![A-Z0-9])', re.IGNORECASE),
    # [우선순위 4] 순수 영문 코드 (4~30자): ODIN, KONA, ATEYAA, INTERRUPTIBLEFOLDBACK (Patch A 보완)
    re.compile(r'(?<![A-Z])[A-Z]{4,30}(?![A-Z])', re.IGNORECASE),
]


def normalize_text(text: str) -> str:
    """범용 텍스트 정규화

    Args:
        text: 원본 텍스트

    Returns:
        정규화된 텍스트

    정규화 순서:
    1. NFKC 유니코드 정규화 (호환 문자 통일)
    2. 하이픈 계열 통일 (→ ASCII hyphen '-')
    3. 공백 압축 (연속 공백 → 단일 공백)
    """
    if not text:
        return ""

    # 1. NFKC 정규화
    text = unicodedata.normalize('NFKC', text)

    # 2. 하이픈 계열 통일
    text = HYPHEN_PATTERN.sub('-', text)

    # 3. 공백 압축
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def normalize_code(code: str, uppercase: bool = True) -> str:
    """코드/모델번호 정규화 (순수 영숫자만 - 특수문자/공백 제거)

    Args:
        code: 원본 코드 (예: "xrn-1620b2", "LVM 180A", "EX-3")
        uppercase: 영문을 대문자로 변환할지 여부 (기본: True)

    Returns:
        정규화된 코드 (순수 영숫자만)

    예:
        "xrn-1620b2" → "XRN1620B2"
        "LVM 180A" → "LVM180A"
        "EX-3" → "EX3"
        "DeckLink‐4K" (en-dash) → "DECKLINK4K"
    """
    if not code:
        return ""

    # 기본 정규화 (NFKC + 하이픈 통일 + 공백 압축)
    code = normalize_text(code)

    # 영문 대문자 변환
    if uppercase:
        code = code.upper()

    # 순수 영숫자만 남기기 (하이픈, 공백, 특수문자 모두 제거)
    code = re.sub(r'[^A-Z0-9]', '', code)

    return code


def generate_variants(code: str) -> List[str]:
    """코드 변형 생성 (하이픈/공백/무공백 3종)

    Args:
        code: 정규화된 코드 (예: "XRN-1620B2")

    Returns:
        변형 리스트 (중복 제거)

    예:
        "XRN-1620B2" → ["XRN-1620B2", "XRN 1620B2", "XRN1620B2"]
        "LVM-180A" → ["LVM-180A", "LVM 180A", "LVM180A"]
    """
    if not code:
        return []

    # 정규화 먼저 적용
    code = normalize_code(code)

    variants = set()

    # 원본
    variants.add(code)

    # 하이픈 → 공백
    if '-' in code:
        variants.add(code.replace('-', ' '))

    # 하이픈/공백 → 제거 (무공백)
    variants.add(code.replace('-', '').replace(' ', ''))

    # 슬래시도 동일 처리
    if '/' in code:
        variants.add(code.replace('/', ' '))
        variants.add(code.replace('/', '-'))

    return sorted(variants)


def extract_codes(text: str, normalize_result: bool = True) -> List[str]:
    """텍스트에서 코드 패턴 추출

    Args:
        text: 검색할 텍스트
        normalize_result: 추출된 코드를 정규화할지 여부

    Returns:
        추출된 코드 리스트 (중복 제거, 길이순 내림차순)

    예:
        "LVM-180A와 XRN-1620B2 장비" → ["LVM-180A", "XRN-1620B2"]
    """
    if not text:
        return []

    codes = set()

    # 먼저 텍스트를 정규화 (하이픈 통일 등)
    normalized_text = normalize_text(text)

    for pattern in CODE_PATTERNS:
        matches = pattern.findall(normalized_text)
        codes.update(matches)

    if normalize_result:
        codes = {normalize_code(c) for c in codes}

    # Denylist 필터링 (정규화된 형태로 비교)
    codes = {
        c for c in codes
        if normalize_code(c, uppercase=True) not in CODE_DENYLIST
    }

    # 길이순 내림차순 정렬 (긴 코드 우선)
    return sorted(codes, key=lambda x: (-len(x), x))


def is_code_query(query: str) -> bool:
    """쿼리에 코드 패턴이 포함되어 있는지 검사

    Args:
        query: 검색 쿼리

    Returns:
        코드 패턴 포함 여부
    """
    codes = extract_codes(query, normalize_result=False)
    return len(codes) > 0


def expand_query_with_variants(query: str) -> str:
    """쿼리에서 코드를 찾아 변형 확장

    Args:
        query: 원본 쿼리 (예: "XRN-1620B2 사양")

    Returns:
        변형 포함 쿼리 (예: "XRN-1620B2 OR XRN1620B2 OR XRN 1620B2 사양")

    주의:
        FTS5 MATCH 쿼리에 사용 시 OR 연산자로 연결됨
    """
    codes = extract_codes(query, normalize_result=True)

    if not codes:
        return normalize_text(query)

    # 각 코드의 변형 생성
    expanded_terms = []
    for code in codes:
        variants = generate_variants(code)
        # OR 그룹으로 묶기: (A OR B OR C)
        if len(variants) > 1:
            expanded_terms.append(f"({' OR '.join(variants)})")
        else:
            expanded_terms.append(variants[0])

    # 원본 쿼리에서 코드 제외한 나머지 텍스트
    remaining_query = query
    for code in codes:
        remaining_query = remaining_query.replace(code, '')

    remaining_query = normalize_text(remaining_query)

    # 조합
    if remaining_query:
        return f"{' '.join(expanded_terms)} {remaining_query}"
    else:
        return ' '.join(expanded_terms)


def normalize_filename(filename: str) -> str:
    """파일명 정규화 (확장자 유지)

    Args:
        filename: 원본 파일명 (예: "LVM‐180A_manual.pdf")

    Returns:
        정규화된 파일명 (예: "LVM-180A_MANUAL.PDF")
    """
    if not filename:
        return ""

    # 확장자 분리
    parts = filename.rsplit('.', 1)
    stem = parts[0]
    ext = parts[1] if len(parts) > 1 else ""

    # 본문 정규화
    stem = normalize_code(stem, uppercase=True)

    # 확장자는 소문자 유지 (관례)
    if ext:
        return f"{stem}.{ext.lower()}"
    else:
        return stem


# 테스트 케이스 (doctest)
if __name__ == "__main__":
    import doctest
    doctest.testmod()

    # 수동 테스트
    print("=== 정규화 테스트 ===")
    test_cases = [
        "xrn-1620b2",
        "LVM 180A",
        "DeckLink‐4K Extreme",  # en-dash
        "NR−3516P−A",  # minus sign
        "GS724Tv6",
    ]

    for case in test_cases:
        normalized = normalize_code(case)
        variants = generate_variants(normalized)
        print(f"{case:30} → {normalized:20} → {variants}")

    print("\n=== 코드 추출 테스트 ===")
    text = "LVM-180A와 XRN-1620B2 장비를 DeckLink 4K Extreme 12G로 교체"
    codes = extract_codes(text)
    print(f"텍스트: {text}")
    print(f"추출: {codes}")

    print("\n=== 쿼리 확장 테스트 ===")
    query = "XRN-1620B2 사양서"
    expanded = expand_query_with_variants(query)
    print(f"원본: {query}")
    print(f"확장: {expanded}")
