"""
Year field utility functions
연도 필드 타입 변환 및 처리를 위한 유틸리티
"""

from typing import Any, List, Union, Optional


def safe_year_to_int(year_value: Any) -> Optional[int]:
    """안전하게 year 값을 정수로 변환

    Args:
        year_value: 변환할 year 값 (str, int, or None)

    Returns:
        정수로 변환된 year 또는 None
    """
    if year_value is None or year_value == '':
        return None

    try:
        # 문자열이면 정수로 변환
        if isinstance(year_value, str):
            # '연도없음', 'N/A' 등의 특수 값 처리
            if year_value in ['연도없음', 'N/A', '없음', '-']:
                return None
            return int(year_value)
        # 이미 정수면 그대로 반환
        elif isinstance(year_value, int):
            return year_value
        else:
            return None
    except (ValueError, TypeError):
        return None


def normalize_year_list(years: List[Any]) -> List[int]:
    """year 리스트를 정규화하여 정수 리스트로 변환

    Args:
        years: year 값들의 리스트

    Returns:
        정수로 변환된 year 리스트 (None 값 제외)
    """
    normalized = []
    for year in years:
        converted = safe_year_to_int(year)
        if converted is not None and converted > 0:  # 0이나 음수는 제외
            normalized.append(converted)

    # 중복 제거하고 정렬
    return sorted(list(set(normalized)), reverse=True)


def compare_year(df_year: Any, target_year: Union[int, str]) -> bool:
    """DataFrame의 year 값과 대상 year 값을 비교

    Args:
        df_year: DataFrame의 year 값
        target_year: 비교할 대상 year 값

    Returns:
        두 값이 같으면 True
    """
    # 둘 다 정수로 변환하여 비교
    df_int = safe_year_to_int(df_year)
    target_int = safe_year_to_int(target_year)

    if df_int is None or target_int is None:
        # 하나라도 None이면 문자열로 비교
        return str(df_year) == str(target_year)

    return df_int == target_int


def get_year_display(year_value: Any, default: str = "연도없음") -> str:
    """year 값을 표시용 문자열로 변환

    Args:
        year_value: year 값
        default: None일 때 표시할 기본값

    Returns:
        표시용 문자열
    """
    year_int = safe_year_to_int(year_value)
    if year_int is None:
        return default
    return f"{year_int}년"