"""
Admin Panel Component
문서 관리를 위한 관리자 UI 컴포넌트

기능:
- 문서 업로드 (drag & drop)
- 문서 삭제
- 메타데이터 편집 (기안자, 날짜 등)
- 인덱스 재빌드
"""

import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import streamlit as st

from app.config.settings import settings

# ============================================================================
# 상수
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
INCOMING_DIR = DOCS_DIR / "incoming"
METADATA_DB = PROJECT_ROOT / "metadata.db"

# ============================================================================
# 유틸리티 함수
# ============================================================================


def get_year_from_filename(filename: str) -> str:
    """파일명에서 연도 추출 (예: 2024-01-01_xxx.pdf -> 2024)"""
    import re
    match = re.match(r"^(\d{4})", filename)
    return match.group(1) if match else str(datetime.now().year)


def get_all_documents() -> list[dict]:
    """metadata.db에서 모든 문서 조회"""
    try:
        conn = sqlite3.connect(METADATA_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, filename, path, drafter, date, doctype, claimed_total
            FROM documents
            ORDER BY date DESC, filename
        """).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        st.error(f"DB 조회 실패: {e}")
        return []


def update_document_metadata(doc_id: int, drafter: str = None, date: str = None, doctype: str = None) -> bool:
    """문서 메타데이터 업데이트"""
    try:
        conn = sqlite3.connect(METADATA_DB)
        updates = []
        params = []

        if drafter is not None:
            updates.append("drafter = ?")
            params.append(drafter)
        if date is not None:
            updates.append("date = ?")
            params.append(date)
        if doctype is not None:
            updates.append("doctype = ?")
            params.append(doctype)

        if updates:
            params.append(doc_id)
            conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"메타데이터 업데이트 실패: {e}")
        return False


def delete_document(doc_id: int, filename: str, file_path: str) -> bool:
    """문서 삭제 (DB + 파일 + 텍스트)"""
    try:
        # 1. DB에서 삭제
        conn = sqlite3.connect(METADATA_DB)
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

        # 2. PDF 파일 삭제
        pdf_path = Path(file_path)
        if pdf_path.exists():
            pdf_path.unlink()

        # 3. 텍스트 파일 삭제
        txt_filename = filename.replace(".pdf", ".txt").replace(".PDF", ".txt")
        txt_path = PROJECT_ROOT / "data" / "extracted" / txt_filename
        if txt_path.exists():
            txt_path.unlink()

        return True
    except Exception as e:
        st.error(f"문서 삭제 실패: {e}")
        return False


def run_ingest() -> tuple[bool, str]:
    """문서 인제스트 실행"""
    try:
        result = subprocess.run(
            ["python", "scripts/core/ingest_from_docs.py"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output
    except subprocess.TimeoutExpired:
        return False, "타임아웃 (5분 초과)"
    except Exception as e:
        return False, str(e)


def run_rebuild_bm25() -> tuple[bool, str]:
    """BM25 인덱스 재빌드"""
    try:
        result = subprocess.run(
            ["python", "scripts/data/indexing/rebuild_bm25.py"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output
    except subprocess.TimeoutExpired:
        return False, "타임아웃 (2분 초과)"
    except Exception as e:
        return False, str(e)


# ============================================================================
# UI 렌더링 함수
# ============================================================================


def render_upload_section():
    """문서 업로드 섹션"""
    st.subheader("📤 문서 업로드")

    # incoming 폴더 확인/생성
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    uploaded_files = st.file_uploader(
        "PDF 파일을 드래그 앤 드롭하거나 선택하세요",
        type=["pdf"],
        accept_multiple_files=True,
        key="admin_upload"
    )

    if uploaded_files:
        st.info(f"📁 {len(uploaded_files)}개 파일 선택됨")

        col1, col2 = st.columns([3, 1])
        with col1:
            # 파일 목록 표시
            for f in uploaded_files:
                st.text(f"• {f.name} ({f.size / 1024:.1f} KB)")

        with col2:
            if st.button("📥 업로드 시작", type="primary", use_container_width=True):
                progress = st.progress(0)
                status = st.empty()

                success_count = 0
                for i, uploaded_file in enumerate(uploaded_files):
                    status.text(f"업로드 중: {uploaded_file.name}")

                    # incoming 폴더에 저장
                    dest_path = INCOMING_DIR / uploaded_file.name
                    with open(dest_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    success_count += 1
                    progress.progress((i + 1) / len(uploaded_files))

                status.empty()
                progress.empty()

                if success_count == len(uploaded_files):
                    st.success(f"✅ {success_count}개 파일 업로드 완료 (docs/incoming/)")
                    st.info("💡 '인제스트 실행' 버튼을 눌러 시스템에 등록하세요")
                else:
                    st.warning(f"⚠️ {success_count}/{len(uploaded_files)}개 업로드 성공")

    # incoming 폴더 현황
    incoming_files = list(INCOMING_DIR.glob("*.pdf")) + list(INCOMING_DIR.glob("*.PDF"))
    if incoming_files:
        with st.expander(f"📂 대기 중인 파일 ({len(incoming_files)}개)", expanded=False):
            for f in incoming_files[:20]:
                st.text(f"• {f.name}")
            if len(incoming_files) > 20:
                st.text(f"... 외 {len(incoming_files) - 20}개")


def render_ingest_section():
    """인제스트 & 인덱스 섹션"""
    st.subheader("🔄 인제스트 & 인덱싱")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 인제스트 실행", use_container_width=True, help="새 문서를 시스템에 등록"):
            with st.spinner("인제스트 실행 중... (최대 5분)"):
                success, output = run_ingest()

            if success:
                st.success("✅ 인제스트 완료")
            else:
                st.error("❌ 인제스트 실패")

            with st.expander("실행 로그"):
                st.code(output)

    with col2:
        if st.button("🔍 BM25 인덱스 재빌드", use_container_width=True, help="검색 인덱스 재생성"):
            with st.spinner("인덱스 재빌드 중... (최대 2분)"):
                success, output = run_rebuild_bm25()

            if success:
                st.success("✅ 인덱스 재빌드 완료")
            else:
                st.error("❌ 인덱스 재빌드 실패")

            with st.expander("실행 로그"):
                st.code(output)


def render_document_list():
    """문서 목록 & 관리 섹션"""
    st.subheader("📋 문서 관리")

    docs = get_all_documents()
    if not docs:
        st.info("등록된 문서가 없습니다")
        return

    st.write(f"총 **{len(docs)}**개 문서")

    # 검색 필터
    search_term = st.text_input("🔍 문서 검색", placeholder="파일명 또는 기안자 검색...")

    if search_term:
        docs = [d for d in docs if search_term.lower() in d["filename"].lower()
                or (d.get("drafter") and search_term.lower() in d["drafter"].lower())]
        st.write(f"검색 결과: **{len(docs)}**건")

    # 문서 목록 (페이지네이션)
    PAGE_SIZE = 20
    total_pages = (len(docs) - 1) // PAGE_SIZE + 1 if docs else 1

    if "admin_page" not in st.session_state:
        st.session_state.admin_page = 0

    # 페이지 네비게이션
    if total_pages > 1:
        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            if st.button("◀ 이전", disabled=st.session_state.admin_page == 0):
                st.session_state.admin_page -= 1
                st.rerun()
        with col2:
            st.write(f"페이지 {st.session_state.admin_page + 1} / {total_pages}")
        with col3:
            if st.button("다음 ▶", disabled=st.session_state.admin_page >= total_pages - 1):
                st.session_state.admin_page += 1
                st.rerun()

    # 현재 페이지 문서
    start_idx = st.session_state.admin_page * PAGE_SIZE
    page_docs = docs[start_idx:start_idx + PAGE_SIZE]

    # 문서 카드 렌더링
    for doc in page_docs:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 1])

            with col1:
                st.markdown(f"**{doc['filename'][:60]}**{'...' if len(doc['filename']) > 60 else ''}")
                st.caption(f"📅 {doc.get('date', '날짜 없음')} | 👤 {doc.get('drafter', '정보 없음')}")

            with col2:
                # 편집 버튼
                if st.button("✏️ 편집", key=f"edit_{doc['id']}", use_container_width=True):
                    st.session_state[f"editing_{doc['id']}"] = True
                    st.rerun()

            with col3:
                # 삭제 버튼
                if st.button("🗑️", key=f"del_{doc['id']}", help="문서 삭제"):
                    st.session_state[f"confirm_del_{doc['id']}"] = True
                    st.rerun()

            # 편집 폼
            if st.session_state.get(f"editing_{doc['id']}", False):
                with st.form(key=f"edit_form_{doc['id']}"):
                    new_drafter = st.text_input("기안자", value=doc.get("drafter", ""))
                    new_date = st.text_input("날짜", value=doc.get("date", ""))
                    new_doctype = st.text_input("문서유형", value=doc.get("doctype", ""))

                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.form_submit_button("💾 저장", type="primary"):
                            if update_document_metadata(doc["id"], new_drafter, new_date, new_doctype):
                                st.success("저장 완료")
                                del st.session_state[f"editing_{doc['id']}"]
                                st.rerun()
                    with col_cancel:
                        if st.form_submit_button("취소"):
                            del st.session_state[f"editing_{doc['id']}"]
                            st.rerun()

            # 삭제 확인
            if st.session_state.get(f"confirm_del_{doc['id']}", False):
                st.warning(f"⚠️ '{doc['filename']}'을(를) 정말 삭제하시겠습니까?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("🗑️ 삭제", key=f"confirm_yes_{doc['id']}", type="primary"):
                        if delete_document(doc["id"], doc["filename"], doc.get("path", "")):
                            st.success("삭제 완료")
                            del st.session_state[f"confirm_del_{doc['id']}"]
                            st.rerun()
                with col_no:
                    if st.button("취소", key=f"confirm_no_{doc['id']}"):
                        del st.session_state[f"confirm_del_{doc['id']}"]
                        st.rerun()


def render_admin_panel():
    """메인 관리자 패널 렌더링"""
    st.title("⚙️ 문서 관리")

    # 현황 요약
    docs = get_all_documents()
    incoming_files = list(INCOMING_DIR.glob("*.pdf")) + list(INCOMING_DIR.glob("*.PDF")) if INCOMING_DIR.exists() else []

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📚 등록된 문서", f"{len(docs)}개")
    with col2:
        st.metric("📥 대기 중", f"{len(incoming_files)}개")
    with col3:
        no_drafter = sum(1 for d in docs if not d.get("drafter") or d["drafter"] in ["", "None", "정보 없음"])
        st.metric("⚠️ 기안자 누락", f"{no_drafter}개")

    st.divider()

    # 탭 구성
    tab1, tab2, tab3 = st.tabs(["📤 업로드", "🔄 인덱싱", "📋 문서관리"])

    with tab1:
        render_upload_section()

    with tab2:
        render_ingest_section()

    with tab3:
        render_document_list()
