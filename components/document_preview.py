"""
Document Preview Component
선택된 문서의 미리보기 및 질문 기능을 제공하는 컴포넌트
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import streamlit as st

from utils.path_validator import validate_and_resolve_path
from utils.pdf_utils import (
    MAX_PDF_BYTES,
    MAX_PDF_MB,
    generate_file_hash,
    load_pdf_bytes_with_limit,
)

if TYPE_CHECKING:
    pass


def _doc_safe_get(doc: dict[str, Any], key: str, default: str = "미상") -> str:
    """문서 딕셔너리에서 안전하게 값 추출"""
    v = doc.get(key)
    return str(v) if v not in (None, "", "None") else default


def render_document_preview(rag_instance: Any, config_module: Any) -> None:
    """
    문서 미리보기 패널 렌더링

    Args:
        rag_instance: RAG 시스템 인스턴스 (st.session_state.rag)
        config_module: 구성 모듈(예: app.config.settings). settings.DOCS_DIR를 포함해야 함.
    """
    # 외부에서 주입된 설정 사용 (테스트/DI 대응)
    settings = getattr(config_module, "settings", None)
    if settings is None or not hasattr(settings, "DOCS_DIR"):
        st.error("구성 오류: settings.DOCS_DIR 미정의")
        return

    from components.pdf_viewer import show_pdf_preview

    # selected_doc가 None이거나 show_doc_preview가 False면 종료
    if "selected_doc" not in st.session_state or not st.session_state.get("show_doc_preview", False):
        return

    doc_raw = st.session_state.selected_doc

    # pandas Series인 경우 dict로 변환
    doc: dict[str, Any] = doc_raw.to_dict() if hasattr(doc_raw, "to_dict") else doc_raw

    title = _doc_safe_get(doc, "title", "알 수 없음")
    drafter = _doc_safe_get(doc, "drafter")
    date = _doc_safe_get(doc, "date")
    category = _doc_safe_get(doc, "category", "-")
    filename = _doc_safe_get(doc, "filename", "document.pdf")

    # 경로 1회 검증 후 재사용
    resolved_path: Path | None = validate_and_resolve_path(
        file_path_str=doc.get("path"),
        base_dir=Path(settings.DOCS_DIR).parent,
        fallback_filename=f"docs/{filename}" if filename else None,
    )

    # 문서별 상태 키(미리보기 토글). 파일 경로/파일명 해시로 고유화
    id_seed = str(resolved_path) if resolved_path else filename
    doc_key = generate_file_hash(id_seed, length=10)
    preview_state_key = f"pdf_preview_shown__{doc_key}"

    if preview_state_key not in st.session_state:
        st.session_state[preview_state_key] = False

    st.markdown(f"### 📄 {title}")

    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        st.caption(f"**기안자**: {drafter} | **날짜**: {date}")
    with col2:
        st.caption(f"**카테고리**: {category} | **파일**: {filename}")

    with col3:
        if resolved_path and resolved_path.exists():
            # 대용량 차단 + 캐시 로드
            pdf_bytes = load_pdf_bytes_with_limit(str(resolved_path), MAX_PDF_BYTES)
            if pdf_bytes is not None:
                st.download_button(
                    label="📥 다운로드",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    key=f"dl_{doc_key}",
                    use_container_width=True,
                )
            else:
                st.warning(f"⚠️ 파일이 너무 크거나 접근할 수 없습니다 (>{MAX_PDF_MB:.0f}MB)")
        else:
            st.warning("⚠️ 파일을 찾을 수 없거나 접근이 거부되었습니다")

    with col4:
        if st.button("❌ 닫기", key=f"close_preview_{doc_key}", use_container_width=True):
            st.session_state.show_doc_preview = False
            st.session_state.pop("selected_doc", None)

    # 얇은 배너 스타일로 표시
    st.markdown(
        """
        <div class="doc-preview-banner">
            <span class="icon">📖</span>
            <span>PDF 문서를 브라우저에서 직접 확인할 수 있습니다.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 토글 버튼(표시/숨김 통합)
    c1, c2 = st.columns([1, 3])
    with c1:
        toggled = st.button(
            "👁️ 미리보기 토글",
            key=f"toggle_preview_{doc_key}",
            use_container_width=True,
            type="primary",
        )
        if toggled:
            st.session_state[preview_state_key] = not st.session_state[preview_state_key]

    # 높이 선택(표시 중일 때만)
    height = 700
    if st.session_state[preview_state_key]:
        with c2:
            height = st.selectbox("미리보기 높이", [500, 700, 900], index=1)

    # 실제 미리보기
    if st.session_state[preview_state_key]:
        if resolved_path and resolved_path.exists():
            with st.spinner("📄 PDF 로딩 중..."):
                show_pdf_preview(str(resolved_path), height)
        else:
            st.error("⚠️ PDF 파일을 찾을 수 없거나 접근이 거부되었습니다")

    st.markdown("---")
