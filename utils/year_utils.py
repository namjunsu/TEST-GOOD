"""
Year field utility functions
연도 필드 타입 변환 및 처리를 위한 유틸리티
"""

import re
from typing import Any, Optional

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
