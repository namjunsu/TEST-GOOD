"""
Path Validation Utility
파일 경로 검증 및 디렉터리 트래버설 방지

방송 기술관리팀 시스템 보안 강화 버전:
- RAG 문서 경로 검증
- OCR 캐시 접근 제어
- 방송 장비 로그 접근 보호
- 스트리밍 서버 설정 파일 보호
"""

from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def is_safe_path(base_dir: Path, target: Path) -> bool:
    """파일 경로가 base_dir 하위인지 검증 (디렉터리 트래버설 방지)

    Args:
        base_dir: 허용된 기준 디렉터리 (예: /home/user/docs)
        target: 검증할 파일 경로 (예: /home/user/docs/file.pdf)

    Returns:
        bool: 안전한 경로면 True, 아니면 False

    Security Features:
        - 심볼릭 링크 해석 및 실제 경로 검증
        - 상위 디렉터리 접근 차단 (../ 패턴)
        - 절대경로 기반 정확한 하위 경로 판별

    Examples:
        >>> is_safe_path(Path("/home/user/docs"), Path("/home/user/docs/file.pdf"))
        True

        >>> is_safe_path(Path("/home/user/docs"), Path("/etc/passwd"))
        False

        >>> is_safe_path(Path("/home/user/docs"), Path("/home/user/docs/../../../etc/passwd"))
        False
    """
    try:
        # base_dir은 strict=True로 반드시 존재해야 함
        base_resolved = base_dir.resolve(strict=True)

        # target은 strict=False로 존재하지 않아도 경로 검증 가능
        target_resolved = target.resolve(strict=False)

        # target이 base_dir의 하위 경로인지 확인
        target_resolved.relative_to(base_resolved)

        return True

    except FileNotFoundError:
        # base_dir이 존재하지 않음
        logger.warning(f"Base directory does not exist: {base_dir}")
        return False
    except ValueError:
        # target이 base_dir의 하위 경로가 아님
        logger.debug(f"Path {target} is not under {base_dir}")
        return False
    except Exception as e:
        # 기타 예외 (순환 참조, 권한 문제 등)
        logger.error(f"Path validation error: {e}")
        return False


def validate_and_resolve_path(
    file_path_str: Optional[str],
    base_dir: Path,
    fallback_filename: Optional[str] = None,
    must_exist: bool = True
) -> Optional[Path]:
    """파일 경로 검증 및 안전한 절대경로 반환

    Args:
        file_path_str: 검증할 파일 경로 문자열 (None 가능)
        base_dir: 허용된 기준 디렉터리
        fallback_filename: file_path_str이 None일 때 사용할 파일명
        must_exist: True면 파일이 존재해야 함, False면 존재하지 않아도 됨

    Returns:
        Optional[Path]: 안전한 절대경로 (Path 객체) 또는 None

    Security Notes:
        - 상대경로는 base_dir 기준으로 자동 변환
        - 절대경로도 base_dir 하위 여부 검증
        - 반환값은 항상 resolve()된 절대경로
        - 심볼릭 링크는 실제 경로로 해석됨

    Examples:
        >>> validate_and_resolve_path("file.pdf", Path("/home/user/docs"))
        Path("/home/user/docs/file.pdf")  # 상대경로 처리

        >>> validate_and_resolve_path("/home/user/docs/file.pdf", Path("/home/user/docs"))
        Path("/home/user/docs/file.pdf")  # 절대경로 처리

        >>> validate_and_resolve_path(None, Path("/home/user/docs"), "default.pdf")
        Path("/home/user/docs/default.pdf")  # fallback 처리

        >>> validate_and_resolve_path("../../../etc/passwd", Path("/home/user/docs"))
        None  # 디렉터리 트래버설 차단
    """
    # Step 1: base_dir 존재 여부 확인
    if not base_dir.exists():
        logger.error(f"Base directory does not exist: {base_dir}")
        return None

    # Step 2: 입력 경로 처리
    if file_path_str is None:
        if fallback_filename is None:
            logger.debug("No file path or fallback provided")
            return None
        candidate = base_dir / fallback_filename
    else:
        p = Path(file_path_str)

        # 상대경로는 base_dir 기준으로 강제 조합
        if p.is_absolute():
            candidate = p
        else:
            # 상대경로는 무조건 base_dir과 조합
            candidate = base_dir / p
            logger.debug(f"Relative path '{file_path_str}' resolved to '{candidate}'")

    # Step 3: 안전 경로 검증
    if not is_safe_path(base_dir, candidate):
        logger.warning(f"Unsafe path detected: {candidate} not under {base_dir}")
        return None

    # Step 4: 정규화된 절대경로 생성
    resolved = candidate.resolve(strict=False)

    # Step 5: 파일 존재 여부 확인 (옵션)
    if must_exist and not resolved.exists():
        logger.debug(f"File does not exist: {resolved}")
        return None

    logger.debug(f"Path validated successfully: {resolved}")
    return resolved
