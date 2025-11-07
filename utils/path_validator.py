"""
Path Validation Utility
파일 경로 검증 및 디렉터리 트래버설 방지
"""

from pathlib import Path
from typing import Optional


def is_safe_path(base_dir: Path, file_path: Path) -> bool:
    """파일 경로가 base_dir 하위인지 검증 (디렉터리 트래버설 방지)

    Args:
        base_dir: 허용된 기준 디렉터리 (예: /home/user/docs)
        file_path: 검증할 파일 경로 (예: /home/user/docs/file.pdf)

    Returns:
        bool: 안전한 경로면 True, 아니면 False

    Examples:
        >>> is_safe_path(Path("/home/user/docs"), Path("/home/user/docs/file.pdf"))
        True

        >>> is_safe_path(Path("/home/user/docs"), Path("/etc/passwd"))
        False

        >>> is_safe_path(Path("/home/user/docs"), Path("/home/user/docs/../../../etc/passwd"))
        False
    """
    try:
        # 절대 경로로 변환 (심볼릭 링크 해석 포함)
        base_dir_resolved = base_dir.resolve()
        file_path_resolved = file_path.resolve()

        # file_path가 base_dir의 하위 경로인지 확인
        # relative_to()는 하위 경로가 아니면 ValueError 발생
        file_path_resolved.relative_to(base_dir_resolved)

        return True
    except (ValueError, RuntimeError):
        # ValueError: 하위 경로가 아님
        # RuntimeError: 순환 참조 등
        return False


def validate_and_resolve_path(
    file_path_str: Optional[str],
    base_dir: Path,
    fallback_filename: Optional[str] = None
) -> Optional[Path]:
    """파일 경로 검증 및 안전한 경로 반환

    Args:
        file_path_str: 검증할 파일 경로 문자열 (None 가능)
        base_dir: 허용된 기준 디렉터리
        fallback_filename: file_path_str이 None일 때 사용할 파일명

    Returns:
        Optional[Path]: 안전한 경로 (Path 객체) 또는 None

    Examples:
        >>> validate_and_resolve_path("docs/file.pdf", Path("/home/user/docs"))
        Path("/home/user/docs/file.pdf")

        >>> validate_and_resolve_path(None, Path("/home/user/docs"), "file.pdf")
        Path("/home/user/docs/file.pdf")

        >>> validate_and_resolve_path("../../../etc/passwd", Path("/home/user/docs"))
        None
    """
    # file_path_str이 None이면 fallback_filename 사용
    if file_path_str is None:
        if fallback_filename is None:
            return None
        file_path = base_dir / fallback_filename
    else:
        file_path = Path(file_path_str)

    # 안전한 경로인지 검증
    if not is_safe_path(base_dir, file_path):
        return None

    # 파일 존재 여부 확인
    if not file_path.exists():
        return None

    return file_path
