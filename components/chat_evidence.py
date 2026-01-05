"""
Chat Evidence Components
출처 문서 표시 관련 UI 컴포넌트

책임:
- 문서 카드 렌더링
- Evidence 섹션 표시
- 유사 문서 추천 표시
- 파일 경로 해석
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import streamlit as st

from app.config.settings import settings
from app.core.logging import get_logger
from utils.pdf_utils import download_pdf_button, render_pdf_preview

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# ============================================================================
# 상수
# ============================================================================

MAX_EVIDENCE_DISPLAY = 20
FILENAME_TRUNCATE_LENGTH = 70
SUMMARY_TRUNCATE_LENGTH = 40


# ============================================================================
# 파일 경로 유틸리티
# ============================================================================


def resolve_file_path(filename: str, file_path_str: str | None = None) -> Path:
    """파일 경로 해석 (year 폴더 지원, PDF 우선)

    DB의 file_path 또는 filename에서 실제 파일 경로를 생성합니다.
    TXT 파일명이 주어진 경우 원본 PDF를 우선적으로 찾습니다.

    Args:
        filename: 파일명 (예: "file.txt" 또는 "file.pdf")
        file_path_str: DB에 저장된 경로 문자열 (선택)

    Returns:
        Path: 절대 파일 경로 (PDF 우선, 없으면 원본)
    """
    if file_path_str:
        file_path = Path(file_path_str)
        if not file_path.is_absolute():
            # 'docs/'로 시작하면 제거 (중복 방지)
            path_str = str(file_path)
            if path_str.startswith("docs/"):
                path_str = path_str[5:]
            file_path = settings.DOCS_DIR / path_str

        # TXT 파일인 경우 PDF 원본 찾기 시도
        if file_path.suffix.lower() == ".txt":
            pdf_path = file_path.with_suffix(".pdf")
            if pdf_path.exists():
                logger.debug(f"📄 TXT → PDF 변환: {file_path.name} → {pdf_path.name}")
                return pdf_path

        return file_path

    # Fallback: filename에서 year 추출
    year_match = re.search(r"(\d{4})-", filename)
    base_path = settings.DOCS_DIR / f"year_{year_match.group(1)}" / filename if year_match else settings.DOCS_DIR / filename

    # TXT 파일인 경우 PDF 원본 찾기 시도
    if base_path.suffix.lower() == ".txt":
        pdf_path = base_path.with_suffix(".pdf")
        if pdf_path.exists():
            logger.debug(f"📄 TXT → PDF 변환: {base_path.name} → {pdf_path.name}")
            return pdf_path

    return base_path


def extract_evidence_metadata(ev: dict | Any) -> dict:
    """Evidence 객체에서 메타데이터 추출

    Args:
        ev: Evidence dict 또는 객체

    Returns:
        dict: {doc_id, filename, snippet, file_path_str, meta}
    """
    if isinstance(ev, dict):
        meta = ev.get("meta", {})
        # filename을 여러 소스에서 찾기 (우선순위: filename > meta.filename > doc_id)
        filename = (
            ev.get("filename")
            or (meta.get("filename") if isinstance(meta, dict) else None)
            or ev.get("doc_id")
            or "unknown"
        )
        return {
            "doc_id": ev.get("doc_id") or ev.get("chunk_id", "unknown"),
            "filename": filename,
            "snippet": ev.get("snippet") or ev.get("content", "") or ev.get("text", ""),
            "file_path_str": ev.get("file_path") or ev.get("path"),
            "meta": meta,
        }

    # 객체인 경우
    meta = getattr(ev, "meta", {})
    filename = (
        getattr(ev, "filename", None)
        or (meta.get("filename") if isinstance(meta, dict) else None)
        or getattr(ev, "doc_id", None)
        or "unknown"
    )
    return {
        "doc_id": getattr(ev, "doc_id", None) or getattr(ev, "chunk_id", "unknown"),
        "filename": filename,
        "snippet": getattr(ev, "snippet", None) or getattr(ev, "content", "") or getattr(ev, "text", ""),
        "file_path_str": getattr(ev, "file_path", None) or getattr(ev, "path", None),
        "meta": meta,
    }


# ============================================================================
# UI 컴포넌트
# ============================================================================


def render_doc_card(
    index: int,
    filename: str,
    file_path: Path | None,
    doctype: str | None,
    display_date: str | None,
    drafter: str | None,
    summary: str,
    msg_idx: int = 0,
) -> None:
    """문서 카드 렌더링 (리스트 형식)

    1행: 번호 + 파일명 + 메타칩 + 요약
    2행: 미리보기/다운로드 버튼

    Args:
        index: 카드 번호 (1부터 시작)
        filename: 파일명
        file_path: 실제 파일 경로
        doctype: 문서 타입
        display_date: 날짜
        drafter: 기안자
        summary: 요약 텍스트
        msg_idx: 메시지 인덱스 (키 충돌 방지용)
    """
    # 고유 키 생성
    file_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
    unique_key = f"{msg_idx}_{index}_{file_hash}"
    session_key = f"show_preview_{unique_key}"

    # 메타정보 구성
    meta_parts = []
    if display_date:
        meta_parts.append(display_date)
    if drafter:
        meta_parts.append(drafter)
    meta_str = " · ".join(meta_parts) if meta_parts else ""

    # 요약 (40자로 단축)
    summary_short = summary[:SUMMARY_TRUNCATE_LENGTH].strip()
    if len(summary) > SUMMARY_TRUNCATE_LENGTH:
        summary_short += "..."

    # 한 줄 리스트 형식
    list_line = f"**{index}.** 📄 **{filename}**"
    if meta_str:
        list_line += f" `{meta_str}`"
    if summary_short:
        list_line += f" — {summary_short}"

    st.markdown(list_line)

    # 액션 버튼 - 파일이 실제로 존재하고 유효한 PDF인 경우만 표시
    file_exists = (
        file_path is not None
        and filename != "unknown"
        and file_path.suffix.lower() == ".pdf"
        and file_path.exists()
    )

    if file_exists:
        col1, col2, col3 = st.columns([1, 1, 8])

        with col1:
            preview_key = f"preview_btn_{unique_key}"
            current_state = st.session_state.get(session_key, False)
            icon = "📖" if current_state else "🔎"

            if st.button(icon, key=preview_key, help="미리보기", use_container_width=True):
                st.session_state[session_key] = not current_state

        with col2:
            download_pdf_button(
                file_path=str(file_path),
                key=f"download_{unique_key}",
                width="stretch",
                icon_only=True,
            )

        # PDF 미리보기
        if st.session_state.get(session_key, False):
            st.markdown(f"**📄 {filename}**")
            render_pdf_preview(
                file_path=str(file_path),
                height=500,
                show_download_fallback=True,
            )


def display_evidence_section(evidence_list: list, msg_idx: int) -> None:
    """출처 문서 섹션 표시

    Args:
        evidence_list: 출처 문서 리스트
        msg_idx: 메시지 인덱스
    """
    display_evidence = evidence_list[:MAX_EVIDENCE_DISPLAY]
    has_more = len(evidence_list) > MAX_EVIDENCE_DISPLAY

    # expander 열림 상태 유지 (미리보기 버튼 클릭 시 닫히는 현상 방지)
    expander_key = f"evidence_expander_{msg_idx}"
    is_expanded = st.session_state.get(expander_key, False)

    with st.expander(f"📚 출처 문서 ({len(display_evidence)}건)", expanded=is_expanded):
        # expander가 열리면 상태 저장
        st.session_state[expander_key] = True
        for i, ev in enumerate(display_evidence, 1):
            # 메타데이터 추출
            ev_data = extract_evidence_metadata(ev)

            # 파일 경로 생성
            file_path = resolve_file_path(ev_data["filename"], ev_data["file_path_str"])

            logger.debug(
                f"[출처 문서] filename={ev_data['filename']}, "
                f"generated_path={file_path}, exists={file_path.exists()}"
            )

            # 메타 데이터
            meta = ev_data["meta"]
            doctype = meta.get("doctype") if isinstance(meta, dict) else None
            display_date = meta.get("date") or meta.get("display_date") if isinstance(meta, dict) else None
            drafter = meta.get("drafter") if isinstance(meta, dict) else None

            # 카드 렌더링
            render_doc_card(
                index=i,
                filename=ev_data["filename"],
                file_path=file_path,
                doctype=doctype,
                display_date=display_date,
                drafter=drafter,
                summary=ev_data["snippet"],
                msg_idx=msg_idx,
            )

            # 여백
            if i < len(display_evidence):
                st.markdown("")

        # 더 보기 정보
        if has_more:
            st.markdown("---")
            remaining = len(evidence_list) - MAX_EVIDENCE_DISPLAY
            st.info(f"📄 {remaining}건의 문서가 더 있습니다. (현재 상위 {MAX_EVIDENCE_DISPLAY}건만 표시)")


def display_similar_documents_section(similar_docs: list, msg_idx: int) -> None:
    """유사 문서 추천 섹션 표시

    Args:
        similar_docs: 유사 문서 리스트
        msg_idx: 메시지 인덱스
    """
    if not similar_docs:
        return

    # expander 열림 상태 유지 (미리보기 버튼 클릭 시 닫히는 현상 방지)
    expander_key = f"similar_expander_{msg_idx}"
    is_expanded = st.session_state.get(expander_key, False)

    with st.expander(f"🔗 유사 문서 추천 ({len(similar_docs)}건)", expanded=is_expanded):
        # expander가 열리면 상태 저장
        st.session_state[expander_key] = True
        for i, doc in enumerate(similar_docs, 1):
            filename = doc.get("filename", "unknown")
            similarity = doc.get("similarity", 0)
            date = doc.get("date", "")
            drafter = doc.get("drafter", "")
            category = doc.get("category", "")

            # 유사도 백분율
            similarity_pct = int(similarity * 100)

            # 파일 경로 생성
            file_path = resolve_file_path(filename)

            # 유사도 텍스트
            similarity_text = f"[유사도 {similarity_pct}%]"

            render_doc_card(
                index=i,
                filename=filename,
                file_path=file_path,
                doctype=category,
                display_date=date,
                drafter=drafter,
                summary=similarity_text,
                msg_idx=msg_idx + 1000,  # 키 충돌 방지
            )

            if i < len(similar_docs):
                st.markdown("")
