"""
Year field utility functions
연도 필드 타입 변환 및 처리를 위한 유틸리티
"""

import re
from typing import Any, List, Union, Optional

YEAR_PATTERN = re.compile(r"(\d{4})")  # 4자리 숫자만 추출


def safe_year_to_int(year_value: Any) -> Optional[int]:
    """안전하게 year 값을 정수로 변환

    Args:
        year_value: 변환할 year 값 (str, int, or None)

    Returns:
        정수로 변환된 year 또는 None

    Examples:
        >>> safe_year_to_int("2024년")
        2024
        >>> safe_year_to_int(" 2024 ")
        2024
        >>> safe_year_to_int("2024.")
        2024
        >>> safe_year_to_int("연도없음")
        None
    """
    if year_value is None:
        return None

    # 문자열 처리
    if isinstance(year_value, str):
        s = year_value.strip()

        # 특수 문자열 처리
        if s in ["", "연도없음", "N/A", "없음", "-", "none", "None"]:
            return None

        # "2024년", "2024.", " 2024 " 등 숫자만 추출
        match = YEAR_PATTERN.search(s)
        if match:
            year_int = int(match.group(1))
            return year_int if year_int > 0 else None

        return None

    # 정수형 처리
    if isinstance(year_value, int):
        return year_value if year_value > 0 else None

    return None


def normalize_year_list(years: List[Any]) -> List[int]:
    """year 리스트를 정규화하여 정수 리스트로 변환

    Args:
        years: year 값들의 리스트

    Returns:
        정수로 변환된 year 리스트 (None 값 제외, 중복 제거, 내림차순 정렬)

    Examples:
        >>> normalize_year_list(["2024년", 2023, " 2022 ", "2024"])
        [2024, 2023, 2022]
    """
    normalized = []
    for y in years:
        converted = safe_year_to_int(y)
        if converted:
            normalized.append(converted)

    # 중복 제거하고 정렬
    return sorted(set(normalized), reverse=True)


def compare_year(df_year: Any, target_year: Union[int, str]) -> bool:
    """DataFrame의 year 값과 대상 year 값을 비교 (정수 기준 우선)

    Args:
        df_year: DataFrame의 year 값
        target_year: 비교할 대상 year 값

    Returns:
        두 값이 같으면 True

    Examples:
        >>> compare_year("2024년", "2024")
        True
        >>> compare_year(" 2024 ", 2024)
        True
    """
    # 둘 다 정수로 변환하여 비교
    df_int = safe_year_to_int(df_year)
    target_int = safe_year_to_int(target_year)

    # 둘 다 정수로 파싱 가능하면 정수 비교
    if df_int is not None and target_int is not None:
        return df_int == target_int

    # 둘 다 파싱 불가한 문자열일 경우에만 문자열 비교
    return str(df_year).strip() == str(target_year).strip()


def get_year_display(year_value: Any, default: str = "연도없음") -> str:
    """year 값을 표시용 문자열로 변환

    Args:
        year_value: year 값
        default: None일 때 표시할 기본값

    Returns:
        표시용 문자열

    Examples:
        >>> get_year_display("2024년")
        '2024년'
        >>> get_year_display(2024)
        '2024년'
        >>> get_year_display("N/A")
        '연도없음'
    """
    year_int = safe_year_to_int(year_value)
    return f"{year_int}년" if year_int else default
