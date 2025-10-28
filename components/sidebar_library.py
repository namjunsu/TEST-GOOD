"""
Sidebar Library Component
사이드바에 문서 라이브러리 UI를 표시하는 컴포넌트
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Optional


def display_document_list(
    filtered_df: pd.DataFrame,
    df: pd.DataFrame,
    prefix: str = "doc"
) -> Optional[pd.DataFrame]:
    """문서 리스트를 표시하는 헬퍼 함수

    Args:
        filtered_df: 필터링된 문서 DataFrame
        df: 전체 문서 DataFrame
        prefix: 버튼 키 prefix (고유성 보장)

    Returns:
        빈 DataFrame 또는 None
    """
    if isinstance(filtered_df, pd.DataFrame) and not filtered_df.empty:
        doc_counter = 0  # 전역 고유 카운터
        for year in sorted(filtered_df['year'].unique(), reverse=True):
            year_docs = filtered_df[filtered_df['year'] == year]

            # 연도 구분선
            st.markdown(f"### {year}년 ({len(year_docs)}개)")

            # 문서 리스트 - 날짜와 문서명
            for _, row in year_docs.iterrows():
                # 날짜 처리
                if row['date'] and len(row['date']) >= 10:
                    date_str = row['date'][5:10]  # MM-DD
                else:
                    date_str = "     "  # 날짜 없으면 공백

                # 제목 처리 (길면 자르기)
                title = row['title'][:30] + "..." if len(row['title']) > 30 else row['title']

                # 날짜와 제목을 함께 표시
                button_text = f"[{date_str}] {title}"

                # 고유한 키 생성 (prefix, 카운터, 파일명 조합)
                unique_key = f"{prefix}_{doc_counter}_{row['filename'][:10]}"
                doc_counter += 1

                # 심플한 버튼으로 문서 선택
                if st.button(button_text, key=unique_key, width="stretch"):
                    st.session_state.selected_doc = row
                    st.session_state.show_doc_preview = True
                    st.rerun()
    else:
        # 문서가 없거나 데이터프레임이 비어있을 때
        if not isinstance(filtered_df, pd.DataFrame):
            st.error("문서 목록을 불러올 수 없습니다.")
        elif filtered_df.empty:
            if df.empty:
                st.warning("문서가 없습니다. docs 폴더에 PDF 파일을 추가해주세요.")
            else:
                st.caption("표시할 문서가 없습니다.")

        return pd.DataFrame()


def render_sidebar_library(rag_instance) -> None:
    """사이드바에 문서 라이브러리 UI 렌더링

    Args:
        rag_instance: RAG 시스템 인스턴스 (st.session_state.rag)
    """
    from utils.document_loader import load_documents

    # 사이드바에도 로고 표시 (흰색 버전, 작게)
    if Path('logo_inverted.png').exists():
        st.image('logo_inverted.png', width=200)
    elif Path('logo.png').exists():
        st.image('logo.png', width=200)
    st.markdown("---")

    # 자동 인덱싱 상태 표시
    st.markdown("### 자동 인덱싱")
    if 'auto_indexer' in st.session_state:
        stats = st.session_state.auto_indexer.get_statistics()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("PDF", f"{stats['pdf_count']}개")
        with col2:
            st.metric("TXT", f"{stats['txt_count']}개")

        # 마지막 업데이트
        if stats['last_update'] != 'Never':
            st.caption(f"마지막 체크: {stats['last_update'][:16]}")

    st.markdown("---")

    # 문서 라이브러리 요약 (DB 기반)
    st.markdown("### 📚 문서 라이브러리")
    try:
        from modules.metadata_db import MetadataDB
        db = MetadataDB()

        # 총 문서 수
        stats = db.get_statistics()
        st.metric("총 문서", f"{stats['total_documents']}건")

        # 최근 문서 (expander)
        with st.expander("최근 10건", expanded=False):
            # 최근 문서 조회
            import sqlite3
            conn = sqlite3.connect("metadata.db")
            cursor = conn.execute("""
                SELECT filename, title, page_count, created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            conn.close()

            if rows:
                for row in rows:
                    filename, title, page_count, created_at = row
                    title_short = title[:25] + "..." if len(title) > 25 else title
                    st.caption(f"📄 {title_short}")
                    st.caption(f"   {page_count}p · {created_at[:10]}")
            else:
                st.caption("문서가 없습니다")

    except Exception as e:
        st.error(f"DB 접근 실패: {e}")

    st.markdown("---")

    # 수동 재인덱싱 버튼
    if 'auto_indexer' in st.session_state:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("새로고침", key="refresh_index", width="stretch"):
                with st.spinner("인덱싱 중..."):
                    result = st.session_state.auto_indexer.check_new_files()
                    if result['new']:
                        st.success(f"✅ {len(result['new'])}개 새 파일 인덱싱 완료!")
                        # RAG 시스템 리로드
                        if 'rag' in st.session_state:
                            del st.session_state.rag
                        st.rerun()
                    else:
                        st.info("변경사항 없음")

        with col2:
            if st.button("♻️ 전체재인덱싱", key="force_reindex", width="stretch"):
                with st.spinner("전체 재인덱싱 중..."):
                    result = st.session_state.auto_indexer.force_reindex()
                    st.success(f"✅ {result['total']}개 파일 재인덱싱 완료!")
                    # RAG 시스템 리로드
                    if 'rag' in st.session_state:
                        del st.session_state.rag
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📂 문서 라이브러리")

    # 빠른 문서 개수만 먼저 표시
    if hasattr(rag_instance, 'metadata_cache'):
        doc_count = len(rag_instance.metadata_cache)
        st.caption(f"📚 {doc_count}개 문서")

    # 문서 로드 (캐시됨 - @st.cache_data 덕분에 빠름)
    with st.spinner("문서 목록 로드 중..."):
        df = load_documents(rag_instance)
        st.session_state.documents_df = df

    # 문서 목록이 로드된 경우 탭 표시
    if not df.empty:
        # 전체 문서 개수를 작게 표시
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"전체 {len(df)}개 문서")

        # 탭 구성
        tab1, tab2 = st.tabs(["📁 문서 검색", "📅 연도별"])

        with tab1:
            # 검색창
            search_query = st.text_input(
                "문서 검색",
                placeholder="제목, 파일명, 기안자 입력...",
                label_visibility="collapsed",
                key="doc_search_input"
            )

            # 검색 처리
            if search_query:
                # 검색 결과
                mask = (df['title'].str.contains(search_query, case=False, na=False) |
                       df['filename'].str.contains(search_query, case=False, na=False) |
                       df['drafter'].str.contains(search_query, case=False, na=False))
                filtered_df = df[mask]

                if len(filtered_df) > 0:
                    st.success(f"검색 결과: {len(filtered_df)}개")
                else:
                    st.warning("검색 결과가 없습니다")
                    filtered_df = pd.DataFrame()
            else:
                # 검색어가 없으면 전체 문서 표시
                filtered_df = df if not df.empty else pd.DataFrame()

            # 검색 탭에서 문서 리스트 표시
            display_document_list(filtered_df, df, "search")

        with tab2:
            # 연도 선택
            if not df.empty and 'year' in df.columns:
                years = sorted(df['year'].unique(), reverse=True)

                # 연도별 문서 개수 포함하여 표시
                year_counts = df['year'].value_counts().to_dict()
                year_options = [f"{year}년 ({year_counts.get(year, 0)}개)" for year in years]

                selected_year_str = st.selectbox(
                    "연도 선택",
                    year_options,
                    label_visibility="collapsed",
                    key="year_select"
                )

                # 선택된 연도 추출 (연도없음 처리)
                if selected_year_str == "연도없음":
                    selected_year = 0
                    filtered_df = df[df['year'] == 0]
                else:
                    selected_year = int(selected_year_str.split("년")[0])
                    filtered_df = df[df['year'] == selected_year]

                # 선택된 연도 정보
                if selected_year == 0:
                    st.info(f"연도 정보 없는 문서 {len(filtered_df)}개")
                else:
                    st.info(f"{selected_year}년 문서 {len(filtered_df)}개")

                # 연도별 탭에서 문서 리스트 표시
                display_document_list(filtered_df, df, "year")
            else:
                st.info("문서가 없습니다")

    # CSS 스타일은 페이지 시작 시 로드됨 (load_all_css)

    # 시스템 정보
    st.markdown("---")
    st.markdown("### 시스템 정보")
    if not df.empty and 'year' in df.columns:
        year_range = f"{df['year'].min()}년 ~ {df['year'].max()}년"
    else:
        year_range = "데이터 없음"

    st.info(f"""
    **모델**: Qwen2.5-7B
    **문서**: {len(df)}개
    **기간**: {year_range}
    """)
