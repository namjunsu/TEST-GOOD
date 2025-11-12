"""
Document Preview Component
선택된 문서의 미리보기 및 질문 기능을 제공하는 컴포넌트
"""

import streamlit as st
import hashlib
from pathlib import Path
from typing import Any, Dict

from utils.path_validator import validate_and_resolve_path


def render_document_preview(rag_instance: Any, config_module: Any) -> None:
    """문서 미리보기 패널 렌더링

    Args:
        rag_instance: RAG 시스템 인스턴스 (st.session_state.rag)
        config_module: config 모듈 (config.settings.DOCS_DIR 접근용) - app.config.settings
    """
    from components.pdf_viewer import show_pdf_preview
    from app.config.settings import settings

    # 선택된 문서 미리보기 (사이드바에서 선택시)
    if 'selected_doc' in st.session_state and st.session_state.get('show_doc_preview', False):
        doc: Dict[str, str] = st.session_state.selected_doc

        # 문서 정보 헤더
        st.markdown(f"### 📄 {doc['title']}")

        # 메타데이터와 컨트롤 버튼
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])

        with col1:
            st.caption(f"**기안자**: {doc['drafter'] if doc['drafter'] != '미상' else '미상'} | **날짜**: {doc['date']}")

        with col2:
            st.caption(f"**카테고리**: {doc['category']} | **파일**: {doc['filename']}")

        with col3:
            # 파일 경로 검증 (디렉터리 트래버설 방지)
            file_path = validate_and_resolve_path(
                file_path_str=doc.get('path'),
                base_dir=Path(settings.DOCS_DIR).parent,  # docs의 상위 디렉터리 (프로젝트 루트)
                fallback_filename=f"docs/{doc.get('filename')}" if doc.get('filename') else None
            )

            if file_path and file_path.exists():
                with open(file_path, 'rb') as f:
                    pdf_bytes = f.read()

                st.download_button(
                    label="📥 다운로드",
                    data=pdf_bytes,
                    file_name=doc.get('filename', 'document.pdf'),
                    mime="application/pdf",
                    key=f"dl_{hashlib.md5(doc.get('filename', 'unknown').encode()).hexdigest()}",
                    width="stretch"
                )
            else:
                st.warning("⚠️ 파일을 찾을 수 없거나 접근이 거부되었습니다")

        with col4:
            if st.button("❌ 닫기", key="close_preview_btn", use_container_width=True):
                st.session_state.show_doc_preview = False
                if 'selected_doc' in st.session_state:
                    del st.session_state.selected_doc
                # st.rerun() 제거 - 버튼 클릭 시 자동 재렌더링 (버그 수정 2025-10-31)

        # PDF 미리보기 섹션 (탭 제거, 직접 표시)
        st.info("📖 PDF 문서를 브라우저에서 직접 확인할 수 있습니다")

        # PDF 미리보기 제어 (성능 고려)
        if 'pdf_preview_shown' not in st.session_state:
            st.session_state.pdf_preview_shown = False

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            if st.button("👁️ PDF 미리보기 표시", type="primary", disabled=st.session_state.pdf_preview_shown):
                st.session_state.pdf_preview_shown = True
                # st.rerun() 제거 - Streamlit 자동 재렌더링 사용 (버그 수정 2025-10-31)

        with col2:
            if st.session_state.pdf_preview_shown:
                if st.button("🔄 미리보기 숨기기"):
                    st.session_state.pdf_preview_shown = False
                    # st.rerun() 제거 - session_state 안정성 향상 (버그 수정 2025-10-31)

        with col3:
            # 미리보기 높이 조절
            if st.session_state.pdf_preview_shown:
                height = st.selectbox("높이", [500, 700, 900], index=1, label_visibility="collapsed")
            else:
                height = 700

        # PDF 미리보기 표시
        if st.session_state.pdf_preview_shown:
            # 파일 경로 검증 (디렉터리 트래버설 방지)
            file_path = validate_and_resolve_path(
                file_path_str=doc.get('path'),
                base_dir=Path(settings.DOCS_DIR).parent,  # docs의 상위 디렉터리 (프로젝트 루트)
                fallback_filename=f"docs/{doc.get('filename')}" if doc.get('filename') else None
            )

            if file_path and file_path.exists():
                with st.spinner("📄 PDF 로딩 중..."):
                    show_pdf_preview(file_path, height)
            else:
                st.error("⚠️ PDF 파일을 찾을 수 없거나 접근이 거부되었습니다")

        st.markdown("---")
