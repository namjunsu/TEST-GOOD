"""
PDF 유틸리티 함수
- 안전한 파일 접근 (디렉터리 트래버설 차단)
- 효율적인 캐시 적용
- 표준 다운로드 버튼 / 미리보기 제공

방송 기술관리팀 문서 시스템 보안 강화 버전:
- RAG 시스템 PDF 문서 안전 접근
- 연도별/부서별 문서 격리
- 심볼릭 링크 우회 차단
"""

import logging
from pathlib import Path
from typing import Optional

import streamlit as st

logger = logging.getLogger(__name__)

# 문서 루트 (settings에서 가져오기, 없으면 fallback)
try:
    from app.config.settings import settings
    DOCS_ROOT = settings.DOCS_DIR
except Exception:
    # Fallback: 프로젝트 루트 기준
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DOCS_ROOT = PROJECT_ROOT / "docs"

logger.debug(f"DOCS_ROOT initialized: {DOCS_ROOT}")


def safe_path(path_str: str, *, must_exist: bool = True) -> Path:
    """경로 안전가드 - DOCS_ROOT 밖 접근 차단

    Args:
        path_str: 검증할 파일 경로 (상대경로 권장)
        must_exist: 존재 여부까지 검증할지 여부

    Returns:
        Path: 안전하게 검증된 절대 경로

    Raises:
        ValueError: docs 루트 밖 경로이거나 PDF가 아닐 경우
        FileNotFoundError: 파일이 없을 경우
    """
    # 입력값을 Path로 변환
    p = Path(path_str)

    # 디버깅: 입력 경로 로깅
    logger.info(f"[safe_path] input: {path_str}, is_absolute: {p.is_absolute()}, DOCS_ROOT: {DOCS_ROOT}")

    # 상대경로/절대경로 처리
    if p.is_absolute():
        # 절대 경로도 허용하지만 DOCS_ROOT 하위 여부는 검증
        resolved_path = p.resolve()
    else:
        # 상대 경로는 DOCS_ROOT 기준으로 합성
        resolved_path = (DOCS_ROOT / p).resolve()

    logger.info(f"[safe_path] resolved: {resolved_path}, exists: {resolved_path.exists()}")

    # DOCS_ROOT 하위인지 검증 (디렉터리 트래버설 방지)
    try:
        resolved_path.relative_to(DOCS_ROOT)
    except ValueError:
        logger.error(f"[safe_path] Path outside DOCS_ROOT: {path_str} -> {resolved_path}, DOCS_ROOT: {DOCS_ROOT}")
        raise ValueError(f"허용 범위 밖 문서 경로: {path_str}") from None

    # PDF 파일만 허용
    if resolved_path.suffix.lower() != ".pdf":
        raise ValueError(f"PDF 파일만 허용됩니다: {resolved_path.name}")

    # 존재 여부 검증
    if must_exist:
        if not resolved_path.exists():
            logger.error(f"[safe_path] File not found: {resolved_path}")
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {resolved_path.name}")
        if not resolved_path.is_file():
            raise ValueError(f"파일이 아닌 경로입니다: {resolved_path.name}")

    logger.debug(f"Safe path validated: {resolved_path}")
    return resolved_path


@st.cache_data
def load_pdf_bytes(path_str: str) -> bytes:
    """PDF 파일을 바이트로 로드 (캐싱 적용)

    Note:
        @st.cache_data 사용 - 데이터 캐싱에 적합
        (기존 @st.cache_resource는 DB 커넥션 등 리소스용)

    Args:
        path_str: DOCS_ROOT 기준 PDF 파일 경로

    Returns:
        bytes: PDF 파일 바이트

    Raises:
        FileNotFoundError: 파일이 없을 경우
        ValueError: 허용 범위 밖 경로일 경우
    """
    safe_file_path = safe_path(path_str)
    return safe_file_path.read_bytes()


def download_pdf_button(
    file_path: str,
    label: str = "⬇ 원본 다운로드",
    key: Optional[str] = None,
    width: str = "stretch",  # 'stretch' or 'content'
    icon_only: bool = False,
) -> bool:
    """표준화된 PDF 다운로드 버튼 (한글 파일명 안전)

    Args:
        file_path: DOCS_ROOT 기준 PDF 파일 경로
        label: 버튼 라벨
        key: Streamlit 위젯 키
        width: 버튼 너비 ('stretch' 또는 'content')
        icon_only: True면 아이콘만 표시

    Returns:
        bool: 버튼 클릭 여부
    """
    try:
        safe_file_path = safe_path(file_path)
        pdf_bytes = load_pdf_bytes(file_path)

        display_label = "📥" if icon_only else label

        return st.download_button(
            label=display_label,
            data=pdf_bytes,
            file_name=safe_file_path.name,
            mime="application/pdf",
            key=key,
            use_container_width=(width == "stretch"),
            help="다운로드" if icon_only else None,
        )

    except FileNotFoundError as e:
        st.warning(f"⚠️ {e}")
        return False

    except ValueError as e:
        st.error(f"❌ {e}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error in download_pdf_button: {e}")
        st.error("❌ 다운로드 처리 중 예기치 못한 오류가 발생했습니다.")
        return False


def render_pdf_preview(
    file_path: str,
    height: int = 600,
    show_download_fallback: bool = True,
) -> bool:
    """PDF 미리보기 렌더링 (예외 처리 강화)

    Args:
        file_path: DOCS_ROOT 기준 PDF 파일 경로
        height: 뷰어 높이 (픽셀)
        show_download_fallback: 뷰어 실패 시 다운로드 버튼 표시 여부

    Returns:
        bool: 렌더링 성공 여부
    """
    from components.pdf_viewer import PDFViewer

    try:
        safe_file_path = safe_path(file_path)

        viewer = PDFViewer(str(safe_file_path), height=height)
        ok = viewer.render()

        # 렌더링 실패지만 예외는 발생하지 않은 경우 (뷰어 자체 문제)
        if not ok and show_download_fallback:
            st.info("💡 미리보기 대신 파일을 직접 다운로드할 수 있습니다.")
            download_pdf_button(
                file_path,
                key=f"fallback_download_{safe_file_path.stem}",
            )

        return ok

    except FileNotFoundError as e:
        # 파일이 실제로 없는 경우 - 다운로드 fallback 제공하지 않음
        st.warning(f"⚠️ {e}")
        return False

    except ValueError as e:
        # 경로 검증 실패 (보안 위반 등)
        st.error(f"❌ {e}")
        return False

    except Exception as e:
        # 예상치 못한 오류 - 이 경우 파일은 존재할 수 있으므로 fallback 제공
        logger.error(f"Unexpected error in render_pdf_preview: {e}")
        st.error("❌ 미리보기 렌더링 중 예기치 못한 오류가 발생했습니다.")

        if show_download_fallback:
            st.info("💡 미리보기 대신 파일을 직접 다운로드할 수 있습니다.")
            download_pdf_button(
                file_path,
                key=f"fallback_download_error_{Path(file_path).stem}",
            )

        return False


def validate_year_folder(year: str) -> bool:
    """연도별 폴더 접근 검증 (선택적 보안 강화)

    Args:
        year: 연도 문자열 (예: "2024", "year_2024")

    Returns:
        bool: 유효한 연도 폴더인지 여부
    """
    # year_YYYY 또는 YYYY 형태 허용
    import re

    if re.match(r"^(year_)?\d{4}$", year):
        year_path = DOCS_ROOT / year
        return year_path.exists() and year_path.is_dir()

    return False


def list_pdf_files(subdirectory: Optional[str] = None) -> list[Path]:
    """DOCS_ROOT 내 PDF 파일 목록 반환 (안전한 탐색)

    Args:
        subdirectory: 탐색할 하위 디렉터리 (예: "year_2024")

    Returns:
        list[Path]: PDF 파일 경로 목록
    """
    try:
        if subdirectory:
            # 디렉터리 경로 검증 (PDF 확장자 체크 없이)
            p = Path(subdirectory)
            if p.is_absolute():
                search_path = p.resolve()
            else:
                search_path = (DOCS_ROOT / p).resolve()

            # DOCS_ROOT 하위인지 확인
            try:
                search_path.relative_to(DOCS_ROOT)
            except ValueError:
                logger.warning(f"Directory outside DOCS_ROOT: {subdirectory}")
                return []

            if not search_path.exists() or not search_path.is_dir():
                return []
        else:
            search_path = DOCS_ROOT

        # PDF 파일만 필터링
        pdf_files = sorted(
            search_path.glob("**/*.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # 각 파일이 DOCS_ROOT 하위인지 재검증
        safe_files = []
        for pdf in pdf_files:
            try:
                pdf.relative_to(DOCS_ROOT)
                safe_files.append(pdf)
            except ValueError:
                logger.warning(f"Skipping file outside DOCS_ROOT: {pdf}")
                continue

        return safe_files

    except Exception as e:
        logger.error(f"Error listing PDF files: {e}")
        return []
