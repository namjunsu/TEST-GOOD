"""
Admin Panel Component
문서 관리를 위한 관리자 UI 컴포넌트

기능:
- 문서 업로드 (drag & drop)
- 문서 삭제
- 메타데이터 편집 (기안자, 날짜 등)
- 인덱스 재빌드
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from collections.abc import Generator

# ============================================================================
# 상수 & 설정
# ============================================================================

# 문서유형 영문→한글 매핑
DOCTYPE_MAP = {
    "proposal": "기안서",
    "report": "보고서",
    "review": "검토서",
    "unknown": "미분류",
}
DOCTYPE_MAP_REVERSE = {v: k for k, v in DOCTYPE_MAP.items()}

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
INCOMING_DIR = DOCS_DIR / "incoming"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
METADATA_DB = PROJECT_ROOT / "metadata.db"

PAGE_SIZE = 20
INGEST_TIMEOUT = 300  # 5분
BM25_TIMEOUT = 120    # 2분


class TaskStatus(Enum):
    """작업 상태"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class TaskResult:
    """작업 실행 결과"""
    status: TaskStatus
    message: str
    output: str = ""


@dataclass
class Document:
    """문서 데이터 모델"""
    id: int
    filename: str
    path: str
    drafter: str | None
    date: str | None
    doctype: str | None
    claimed_total: float | None

    @property
    def display_name(self) -> str:
        """표시용 파일명 (70자 제한)"""
        return f"{self.filename[:70]}..." if len(self.filename) > 70 else self.filename

    @property
    def drafter_display(self) -> str:
        """표시용 기안자"""
        return self.drafter if self.drafter and self.drafter not in ("", "None", "정보 없음") else "정보 없음"

    @property
    def date_display(self) -> str:
        """표시용 날짜"""
        return self.date or "날짜 없음"


# ============================================================================
# DB 유틸리티
# ============================================================================


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """DB 연결 컨텍스트 매니저 - 안전한 리소스 관리"""
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_all_documents() -> list[Document]:
    """metadata.db에서 모든 문서 조회"""
    try:
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT id, filename, path, drafter, date, doctype, claimed_total
                FROM documents
                ORDER BY date DESC, filename
            """).fetchall()
            return [
                Document(
                    id=row["id"],
                    filename=row["filename"],
                    path=row["path"],
                    drafter=row["drafter"],
                    date=row["date"],
                    doctype=row["doctype"],
                    claimed_total=row["claimed_total"],
                )
                for row in rows
            ]
    except sqlite3.Error as e:
        st.error(f"DB 조회 실패: {e}")
        return []


def update_document_metadata(
    doc_id: int,
    drafter: str | None = None,
    date: str | None = None,
    doctype: str | None = None,
) -> bool:
    """문서 메타데이터 업데이트"""
    updates: list[str] = []
    params: list[str | int] = []

    if drafter is not None:
        updates.append("drafter = ?")
        params.append(drafter)
    if date is not None:
        updates.append("date = ?")
        params.append(date)
    if doctype is not None:
        updates.append("doctype = ?")
        params.append(doctype)

    if not updates:
        return True  # 변경사항 없음

    try:
        with get_db_connection() as conn:
            params.append(doc_id)
            conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"메타데이터 업데이트 실패: {e}")
        return False


def delete_document_from_db(doc_id: int) -> bool:
    """DB에서 문서 삭제"""
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"DB 삭제 실패: {e}")
        return False


# ============================================================================
# 파일 유틸리티
# ============================================================================


def delete_document_files(filename: str, file_path: str) -> tuple[bool, list[str]]:
    """
    문서 관련 파일 삭제 (PDF + 텍스트)

    Returns:
        (성공여부, 삭제된 파일 목록)
    """
    deleted: list[str] = []
    errors: list[str] = []

    # PDF 파일 삭제
    pdf_path = Path(file_path)
    if pdf_path.exists():
        try:
            pdf_path.unlink()
            deleted.append(str(pdf_path))
        except OSError as e:
            errors.append(f"PDF 삭제 실패: {e}")

    # 텍스트 파일 삭제
    txt_filename = filename.replace(".pdf", ".txt").replace(".PDF", ".txt")
    txt_path = EXTRACTED_DIR / txt_filename
    if txt_path.exists():
        try:
            txt_path.unlink()
            deleted.append(str(txt_path))
        except OSError as e:
            errors.append(f"텍스트 삭제 실패: {e}")

    if errors:
        for err in errors:
            st.warning(err)

    return len(errors) == 0, deleted


def delete_document(doc_id: int, filename: str, file_path: str) -> bool:
    """
    문서 삭제 (트랜잭션 안전)

    순서: 파일 먼저 삭제 → DB 삭제
    파일 삭제 실패 시 DB는 유지됨 (데이터 무결성 보장)
    """
    # 1. 파일 먼저 삭제
    files_ok, deleted_files = delete_document_files(filename, file_path)

    if not files_ok and not deleted_files:
        # 파일이 하나도 삭제 안 됐으면 중단
        st.error("파일 삭제 실패 - DB는 변경되지 않았습니다")
        return False

    # 2. DB 삭제
    if not delete_document_from_db(doc_id):
        st.error(f"DB 삭제 실패 - 수동으로 삭제된 파일: {deleted_files}")
        return False

    return True


# ============================================================================
# 스크립트 실행
# ============================================================================


def run_script(script_path: str, timeout: int) -> TaskResult:
    """외부 스크립트 실행"""
    import os
    try:
        # PYTHONPATH 설정하여 모듈 import 가능하게
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        result = subprocess.run(
            [sys.executable, script_path],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        output = result.stdout + result.stderr
        if result.returncode == 0:
            return TaskResult(TaskStatus.SUCCESS, "완료", output)
        return TaskResult(TaskStatus.FAILED, "실행 실패", output)

    except subprocess.TimeoutExpired:
        return TaskResult(TaskStatus.TIMEOUT, f"타임아웃 ({timeout}초 초과)", "")
    except OSError as e:
        return TaskResult(TaskStatus.FAILED, str(e), "")


def run_ingest() -> TaskResult:
    """문서 인제스트 실행"""
    return run_script("scripts/core/ingest_from_docs.py", INGEST_TIMEOUT)


def run_rebuild_bm25() -> TaskResult:
    """BM25 인덱스 재빌드"""
    return run_script("scripts/indexing/rebuild_bm25.py", BM25_TIMEOUT)


def run_rebuild_vector() -> TaskResult:
    """벡터 인덱스 재빌드

    Note: 스크립트 내에서 GPU 메모리 부족 시 자동으로 CPU 모드로 전환됩니다.
    """
    return run_script("scripts/indexing/rebuild_vector.py", BM25_TIMEOUT * 2)  # 임베딩은 더 오래 걸림


# ============================================================================
# Session State 관리
# ============================================================================


def get_admin_page() -> int:
    """현재 페이지 번호 가져오기"""
    return st.session_state.get("admin_page", 0)


def set_admin_page(page: int) -> None:
    """페이지 번호 설정"""
    st.session_state.admin_page = page


def validate_page_range(current_page: int, total_pages: int) -> int:
    """페이지 범위 검증 및 보정"""
    if total_pages == 0:
        return 0
    return max(0, min(current_page, total_pages - 1))


def is_editing(doc_id: int) -> bool:
    """편집 모드 확인"""
    return st.session_state.get(f"editing_{doc_id}", False)


def set_editing(doc_id: int, value: bool) -> None:
    """편집 모드 설정"""
    if value:
        st.session_state[f"editing_{doc_id}"] = True
    elif f"editing_{doc_id}" in st.session_state:
        del st.session_state[f"editing_{doc_id}"]


def is_confirming_delete(doc_id: int) -> bool:
    """삭제 확인 모드 확인"""
    return st.session_state.get(f"confirm_del_{doc_id}", False)


def set_confirming_delete(doc_id: int, value: bool) -> None:
    """삭제 확인 모드 설정"""
    if value:
        st.session_state[f"confirm_del_{doc_id}"] = True
    elif f"confirm_del_{doc_id}" in st.session_state:
        del st.session_state[f"confirm_del_{doc_id}"]


def cleanup_document_state(doc_id: int) -> None:
    """문서 관련 session state 정리"""
    set_editing(doc_id, False)
    set_confirming_delete(doc_id, False)


# ============================================================================
# UI 컴포넌트
# ============================================================================


def render_task_result(result: TaskResult, success_msg: str, show_log: bool = True) -> None:
    """작업 결과 표시"""
    if result.status == TaskStatus.SUCCESS:
        st.success(f"✅ {success_msg}")
    elif result.status == TaskStatus.TIMEOUT:
        st.error(f"⏱️ {result.message}")
    else:
        st.error(f"❌ {result.message}")

    if show_log and result.output:
        with st.expander("실행 로그"):
            st.code(result.output)


def render_upload_section() -> None:
    """문서 업로드 섹션"""
    st.subheader("📤 문서 업로드")

    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    uploaded_files = st.file_uploader(
        "PDF 파일을 드래그 앤 드롭하거나 선택하세요",
        type=["pdf"],
        accept_multiple_files=True,
        key="admin_upload",
    )

    if not uploaded_files:
        _render_incoming_status()
        return

    st.info(f"📁 {len(uploaded_files)}개 파일 선택됨")

    with st.expander("선택된 파일 목록", expanded=False):
        for f in uploaded_files:
            st.text(f"• {f.name} ({f.size / 1024:.1f} KB)")

    auto_ingest = st.checkbox(
        "✅ 업로드 후 자동으로 시스템에 등록",
        value=True,
        help="체크하면 업로드 완료 후 자동으로 인제스트 실행",
    )

    if st.button("📥 업로드 시작", type="primary", use_container_width=True):
        _process_upload(uploaded_files, auto_ingest)

    _render_incoming_status()


def _process_upload(uploaded_files: list, auto_ingest: bool) -> None:
    """파일 업로드 처리"""
    progress = st.progress(0)
    status = st.empty()

    success_count = 0
    for i, uploaded_file in enumerate(uploaded_files):
        status.text(f"업로드 중: {uploaded_file.name}")

        dest_path = INCOMING_DIR / uploaded_file.name
        try:
            with open(dest_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            success_count += 1
        except OSError as e:
            st.warning(f"⚠️ {uploaded_file.name} 저장 실패: {e}")

        progress.progress((i + 1) / len(uploaded_files))

    if success_count == len(uploaded_files):
        st.success(f"✅ {success_count}개 파일 업로드 완료")
        if auto_ingest:
            _run_auto_ingest(status, progress)
        else:
            st.info("💡 '인덱싱' 탭에서 '인제스트 실행' 버튼을 눌러주세요")
    else:
        st.warning(f"⚠️ {success_count}/{len(uploaded_files)}개 업로드 성공")

    status.empty()
    progress.empty()


def _run_auto_ingest(status, progress) -> None:
    """자동 인제스트 실행"""
    status.text("📥 시스템에 등록 중...")
    progress.progress(0)

    ingest_result = run_ingest()
    progress.progress(50)

    if ingest_result.status != TaskStatus.SUCCESS:
        st.error("❌ 인제스트 실패")
        with st.expander("오류 로그"):
            st.code(ingest_result.output)
        return

    status.text("🔍 BM25 인덱스 업데이트 중...")
    bm25_result = run_rebuild_bm25()
    progress.progress(70)

    if bm25_result.status != TaskStatus.SUCCESS:
        st.warning("⚠️ BM25 인덱스 재빌드 실패")
        with st.expander("BM25 로그"):
            st.code(bm25_result.output)

    status.text("🧠 벡터 인덱스 업데이트 중...")
    vector_result = run_rebuild_vector()
    progress.progress(100)

    if vector_result.status != TaskStatus.SUCCESS:
        st.warning("⚠️ 벡터 인덱스 재빌드 실패")
        with st.expander("벡터 로그"):
            st.code(vector_result.output)

    if bm25_result.status == TaskStatus.SUCCESS and vector_result.status == TaskStatus.SUCCESS:
        st.success("✅ 시스템 등록 완료! 검색 가능합니다.")
    elif bm25_result.status == TaskStatus.SUCCESS:
        st.warning("⚠️ 인제스트 완료, 벡터 인덱스만 실패 (키워드 검색은 가능)")
    else:
        st.error("❌ 인덱스 재빌드 실패")


def _render_incoming_status() -> None:
    """대기 중인 파일 현황 표시"""
    if not INCOMING_DIR.exists():
        return

    incoming_files = list(INCOMING_DIR.glob("*.pdf")) + list(INCOMING_DIR.glob("*.PDF"))
    if not incoming_files:
        return

    with st.expander(f"📂 대기 중인 파일 ({len(incoming_files)}개)", expanded=False):
        for f in incoming_files[:20]:
            st.text(f"• {f.name}")
        if len(incoming_files) > 20:
            st.text(f"... 외 {len(incoming_files) - 20}개")


def render_ingest_section() -> None:
    """인제스트 & 인덱스 섹션"""
    st.subheader("🔄 인제스트 & 인덱싱")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📥 인제스트 실행", use_container_width=True, help="새 문서를 시스템에 등록"):
            with st.spinner("인제스트 실행 중... (최대 5분)"):
                result = run_ingest()
            render_task_result(result, "인제스트 완료")

    with col2:
        if st.button("🔍 BM25 재빌드", use_container_width=True, help="키워드 검색 인덱스 재생성"):
            with st.spinner("BM25 인덱스 재빌드 중... (최대 2분)"):
                result = run_rebuild_bm25()
            render_task_result(result, "BM25 인덱스 재빌드 완료")

    with col3:
        if st.button("🧠 벡터 재빌드", use_container_width=True, help="의미 검색 인덱스 재생성 (시간 소요)"):
            with st.spinner("벡터 인덱스 재빌드 중... (최대 5분)"):
                result = run_rebuild_vector()
            render_task_result(result, "벡터 인덱스 재빌드 완료")


def render_document_list() -> None:
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
        search_lower = search_term.lower()
        docs = [
            d for d in docs
            if search_lower in d.filename.lower()
            or (d.drafter and search_lower in d.drafter.lower())
        ]
        st.write(f"검색 결과: **{len(docs)}**건")

    # 페이지네이션
    total_pages = max(1, (len(docs) - 1) // PAGE_SIZE + 1)
    saved_page = get_admin_page()
    current_page = validate_page_range(saved_page, total_pages)

    # 편집/삭제 모드가 아닐 때만 페이지 보정 (편집 중 페이지 점프 방지)
    if current_page != saved_page and not any(
        is_editing(d.id) or is_confirming_delete(d.id) for d in docs
    ):
        set_admin_page(current_page)

    _render_pagination(current_page, total_pages)

    # 현재 페이지 문서
    start_idx = current_page * PAGE_SIZE
    page_docs = docs[start_idx:start_idx + PAGE_SIZE]

    for doc in page_docs:
        _render_document_card(doc)


def _render_pagination(current_page: int, total_pages: int) -> None:
    """페이지 네비게이션"""
    if total_pages <= 1:
        return

    col1, col2, col3 = st.columns([1, 3, 1])

    with col1:
        if st.button("◀ 이전", disabled=current_page == 0):
            set_admin_page(current_page - 1)
            st.rerun()

    with col2:
        st.write(f"페이지 {current_page + 1} / {total_pages}")

    with col3:
        if st.button("다음 ▶", disabled=current_page >= total_pages - 1):
            set_admin_page(current_page + 1)
            st.rerun()


def _render_document_card(doc: Document) -> None:
    """개별 문서 카드 렌더링"""
    with st.container(border=True):
        if is_editing(doc.id):
            _render_edit_form(doc)
        elif is_confirming_delete(doc.id):
            _render_delete_confirm(doc)
        else:
            _render_document_info(doc)


def _render_document_info(doc: Document) -> None:
    """문서 기본 정보 표시"""
    col1, col2, col3 = st.columns([5, 1, 1])

    with col1:
        st.markdown(f"**{doc.display_name}**")
        st.caption(f"📅 {doc.date_display} | 👤 {doc.drafter_display}")

    with col2:
        if st.button("✏️", key=f"edit_{doc.id}", help="편집", use_container_width=True):
            set_editing(doc.id, True)
            st.rerun()

    with col3:
        if st.button("🗑️", key=f"del_{doc.id}", help="삭제", use_container_width=True):
            set_confirming_delete(doc.id, True)
            st.rerun()


def _render_edit_form(doc: Document) -> None:
    """편집 폼"""
    st.markdown(f"**✏️ 편집: {doc.filename[:50]}...**")

    with st.form(key=f"edit_form_{doc.id}"):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            new_drafter = st.text_input("기안자", value=doc.drafter or "")
        with col_b:
            new_date = st.text_input("날짜 (YYYY-MM-DD)", value=doc.date or "")
        with col_c:
            # 현재 doctype을 한글로 변환
            current_korean = DOCTYPE_MAP.get(doc.doctype or "", doc.doctype or "미분류")
            doctype_options = list(DOCTYPE_MAP.values())
            current_idx = doctype_options.index(current_korean) if current_korean in doctype_options else 0
            selected_korean = st.selectbox("문서유형", options=doctype_options, index=current_idx)
            new_doctype = DOCTYPE_MAP_REVERSE.get(selected_korean, "unknown")

        col_save, col_cancel = st.columns(2)

        with col_save:
            if st.form_submit_button("💾 저장", type="primary", use_container_width=True):
                if update_document_metadata(doc.id, new_drafter, new_date, new_doctype):
                    st.success("저장 완료")
                    set_editing(doc.id, False)
                    st.rerun()

        with col_cancel:
            if st.form_submit_button("❌ 취소", use_container_width=True):
                set_editing(doc.id, False)
                st.rerun()


def _render_delete_confirm(doc: Document) -> None:
    """삭제 확인 UI"""
    st.error("🗑️ **삭제 확인**")
    st.write("다음 문서를 삭제합니다:")
    st.code(doc.filename)
    st.warning("⚠️ PDF 파일과 텍스트 파일이 모두 삭제됩니다. 이 작업은 되돌릴 수 없습니다.")

    col_yes, col_no = st.columns(2)

    with col_yes:
        if st.button("🗑️ 삭제 확인", key=f"confirm_yes_{doc.id}", type="primary", use_container_width=True):
            if delete_document(doc.id, doc.filename, doc.path):
                st.success("삭제 완료")
                cleanup_document_state(doc.id)
                st.rerun()

    with col_no:
        if st.button("↩️ 취소", key=f"confirm_no_{doc.id}", use_container_width=True):
            set_confirming_delete(doc.id, False)
            st.rerun()


# ============================================================================
# 메인 진입점
# ============================================================================


def render_admin_panel() -> None:
    """메인 관리자 패널 렌더링"""
    st.title("⚙️ 문서 관리")

    # 현황 요약
    docs = get_all_documents()
    incoming_files = (
        list(INCOMING_DIR.glob("*.pdf")) + list(INCOMING_DIR.glob("*.PDF"))
        if INCOMING_DIR.exists()
        else []
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("📚 등록된 문서", f"{len(docs)}개")

    with col2:
        st.metric("📥 대기 중", f"{len(incoming_files)}개")

    with col3:
        no_drafter = sum(
            1 for d in docs
            if not d.drafter or d.drafter in ("", "None", "정보 없음")
        )
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
