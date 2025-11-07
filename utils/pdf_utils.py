"""
PDF 유틸리티 함수
안전한 파일 접근, 캐시, 표준 다운로드 버튼 제공
"""

import streamlit as st
from pathlib import Path
from typing import Optional

# 문서 루트 (docs 폴더)
DOCS_ROOT = Path("docs").resolve()


def safe_path(path_str: str) -> Path:
    """경로 안전가드 - docs 루트 밖 접근 차단

    Args:
        path_str: 검증할 파일 경로

    Returns:
        Path: 안전하게 검증된 경로

    Raises:
        ValueError: docs 루트 밖 경로일 경우
    """
    try:
        # 상대 경로 해결
        resolved_path = Path(path_str).resolve()

        # docs 루트 하위인지 확인
        if not str(resolved_path).startswith(str(DOCS_ROOT)):
            raise ValueError(f"허용 범위 밖 문서 경로: {path_str}")

        # 파일 존재 여부 확인
        if not resolved_path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {resolved_path.name}")

        return resolved_path

    except Exception as e:
        raise ValueError(f"경로 검증 실패: {path_str} - {e}")


@st.cache_resource
def load_pdf_bytes(path_str: str) -> bytes:
    """PDF 파일을 바이트로 로드 (캐싱 적용)

    Args:
        path_str: PDF 파일 경로

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
    icon_only: bool = False
) -> bool:
    """표준화된 PDF 다운로드 버튼 (한글 파일명 안전)

    Args:
        file_path: PDF 파일 경로
        label: 버튼 라벨
        key: Streamlit 위젯 키
        width: 버튼 너비 ('stretch' 또는 'content')
        icon_only: True면 아이콘만 표시 (기본값: False)

    Returns:
        bool: 버튼 클릭 여부
    """
    try:
        safe_file_path = safe_path(file_path)
        pdf_bytes = load_pdf_bytes(file_path)

        # 아이콘 전용 모드
        display_label = "📥" if icon_only else label

        return st.download_button(
            label=display_label,
            data=pdf_bytes,
            file_name=safe_file_path.name,
            mime="application/pdf",
            key=key,
            use_container_width=(width == "stretch"),
            help="다운로드" if icon_only else None
        )

    except FileNotFoundError:
        st.warning("⚠️ 파일을 찾을 수 없습니다. (이동/삭제 여부 확인)")
        return False

    except ValueError as e:
        st.error(f"❌ 경로 오류: {e}")
        return False

    except Exception as e:
        st.error(f"❌ 다운로드 버튼 생성 실패: {e}")
        return False


def render_pdf_preview(
    file_path: str,
    height: int = 600,
    show_download_fallback: bool = True
) -> bool:
    """PDF 미리보기 렌더링 (예외 처리 강화)

    Args:
        file_path: PDF 파일 경로
        height: 뷰어 높이 (픽셀)
        show_download_fallback: 실패 시 다운로드 버튼 표시 여부

    Returns:
        bool: 렌더링 성공 여부
    """
    from components.pdf_viewer import PDFViewer

    try:
        # 경로 검증
        safe_file_path = safe_path(file_path)

        # PDF 뷰어 렌더링
        viewer = PDFViewer(str(safe_file_path), height=height)
        return viewer.render()

    except FileNotFoundError:
        st.warning("⚠️ 파일을 찾을 수 없습니다. (이동/삭제 여부 확인)")
        if show_download_fallback:
            st.info("💡 다운로드는 가능할 수 있습니다:")
            download_pdf_button(file_path, key=f"fallback_download_{Path(file_path).name[:10]}")
        return False

    except ValueError as e:
        st.error(f"❌ 경로 오류: {e}")
        return False

    except Exception as e:
        st.error(f"❌ 미리보기에 실패했습니다: {e}")
        if show_download_fallback:
            st.info("💡 다운로드는 가능할 수 있습니다:")
            download_pdf_button(file_path, key=f"fallback_download_{Path(file_path).name[:10]}")
        return False
