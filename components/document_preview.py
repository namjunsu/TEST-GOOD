"""
Document Preview Component
선택된 문서의 미리보기 및 질문 기능을 제공하는 컴포넌트
"""

import streamlit as st
import hashlib
from pathlib import Path
from typing import Any, Dict


def render_document_preview(rag_instance: Any, config_module: Any) -> None:
    """문서 미리보기 패널 렌더링

    Args:
        rag_instance: RAG 시스템 인스턴스 (st.session_state.rag)
        config_module: config 모듈 (config.DOCS_DIR 접근용) - app.config.settings
    """
    from components.pdf_viewer import show_pdf_preview
    from app.config.settings import DOCS_DIR

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
            # Use the full path from metadata, not just filename
            if 'path' in doc and doc['path']:
                file_path = Path(doc['path'])
            else:
                file_path = Path(DOCS_DIR) / doc['filename']
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    pdf_bytes = f.read()

                st.download_button(
                    label="📥 다운로드",
                    data=pdf_bytes,
                    file_name=doc['filename'],
                    mime="application/pdf",
                    key=f"dl_{hashlib.md5(doc['filename'].encode()).hexdigest()}",
                    width="stretch"
                )

        with col4:
            if st.button("❌ 닫기", width="stretch"):
                st.session_state.show_doc_preview = False
                if 'selected_doc' in st.session_state:
                    del st.session_state.selected_doc
                st.rerun()

        # 탭 구성: 질문/답변과 PDF 미리보기
        doc_tab1, doc_tab2 = st.tabs(["💬 문서 질문하기", "📖 PDF 미리보기"])

        with doc_tab1:
            st.success("🎯 **문서 전용 모드** - 이 문서에 대해서만 집중 분석합니다")

            # 전용 질문 입력
            col1, col2 = st.columns([5, 1])
            with col1:
                doc_query = st.text_input(
                    "이 문서에 대해 질문하세요",
                    placeholder=f"{doc['title']}에 대해 궁금한 점을 물어보세요",
                    key="doc_specific_query"
                )
            with col2:
                doc_submit = st.button("🔍 문서 검색", type="primary", key="doc_search_btn")

            # 답변 처리
            if doc_submit and doc_query:
                with st.spinner("🔍 문서를 분석하고 있습니다..."):
                    try:
                        answer = rag_instance.answer_from_specific_document(doc_query, doc['filename'])
                        st.markdown("---")
                        st.markdown(answer)
                    except FileNotFoundError as _:
                        st.error(f"📁 파일을 찾을 수 없습니다: {doc['filename']}")
                        st.info("💡 파일이 이동되었거나 삭제되었을 수 있습니다. 재인덱싱을 시도해주세요")
                    except PermissionError as _:
                        st.error(f"🔒 파일 접근 권한이 없습니다: {doc['filename']}")
                        st.info("💡 파일이 다른 프로그램에서 사용 중이거나 권한이 제한되어 있습니다")
                    except MemoryError as _:
                        st.error(f"💾 메모리 부족: 너무 큰 문서를 처리하려고 합니다")
                        st.info("💡 문서를 개별로 검색하거나 시스템을 재시작해주세요")
                    except Exception as e:
                        st.error(f"❌ 예상치 못한 오류가 발생했습니다")
                        with st.expander("🔍 상세 오류 정보"):
                            st.text(f"오류 타입: {type(e).__name__}")
                            st.text(f"오류 메시지: {str(e)}")
                            import traceback
                            st.text("\n스택 트레이스:")
                            st.text(traceback.format_exc())

        with doc_tab2:
            st.info("📖 PDF 문서를 브라우저에서 직접 확인할 수 있습니다")

            # PDF 미리보기 제어 (성능 고려)
            if 'pdf_preview_shown' not in st.session_state:
                st.session_state.pdf_preview_shown = False

            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                if st.button("👁️ PDF 미리보기 표시", type="primary", disabled=st.session_state.pdf_preview_shown):
                    st.session_state.pdf_preview_shown = True
                    st.rerun()

            with col2:
                if st.session_state.pdf_preview_shown:
                    if st.button("🔄 미리보기 숨기기"):
                        st.session_state.pdf_preview_shown = False
                        st.rerun()

            with col3:
                # 미리보기 높이 조절
                if st.session_state.pdf_preview_shown:
                    height = st.selectbox("높이", [500, 700, 900], index=1, label_visibility="collapsed")
                else:
                    height = 700

            # PDF 미리보기 표시
            if st.session_state.pdf_preview_shown:
                # Use the full path from metadata, not just filename
                if 'path' in doc and doc['path']:
                    file_path = Path(doc['path'])
                else:
                    file_path = Path(DOCS_DIR) / doc['filename']
                if file_path.exists():
                    with st.spinner("📄 PDF 로딩 중..."):
                        show_pdf_preview(file_path, height)
                else:
                    st.error("PDF 파일을 찾을 수 없습니다")

        st.markdown("---")
