#!/usr/bin/env python3
"""
개선된 사이드바 컴포넌트
문서가 많아도 보기 편한 UI
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List

def render_improved_sidebar(documents_df: pd.DataFrame):
    """개선된 사이드바 렌더링"""

    st.markdown("### 📁 문서 라이브러리")

    # 1. 빠른 통계
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("전체", f"{len(documents_df)}", delta=None, label_visibility="collapsed")
    with col2:
        pdf_count = len(documents_df[documents_df['filename'].str.endswith('.pdf')])
        st.metric("PDF", f"{pdf_count}", delta=None, label_visibility="collapsed")
    with col3:
        today_count = len(documents_df[documents_df['date'] == datetime.now().strftime('%Y-%m-%d')])
        st.metric("오늘", f"{today_count}", delta=None, label_visibility="collapsed")

    st.markdown("---")

    # 2. 검색 & 필터 탭
    tab1, tab2, tab3 = st.tabs(["🔍 검색", "📅 연도별", "📂 타입별"])

    with tab1:
        # 검색
        search_query = st.text_input("검색어", placeholder="문서명, 기안자, 키워드...", label_visibility="collapsed")

        if search_query:
            # 검색 결과
            mask = (documents_df['title'].str.contains(search_query, case=False, na=False) |
                   documents_df['filename'].str.contains(search_query, case=False, na=False) |
                   documents_df['drafter'].str.contains(search_query, case=False, na=False))
            results = documents_df[mask]

            if len(results) > 0:
                st.caption(f"검색 결과: {len(results)}개")

                # 상위 10개만 표시
                for idx, row in results.head(10).iterrows():
                    if st.button(f"📄 {row['title'][:30]}...", key=f"search_{idx}", use_container_width=True):
                        st.session_state.selected_doc = row['filename']

                if len(results) > 10:
                    st.caption(f"... 외 {len(results)-10}개 더 있음")
            else:
                st.info("검색 결과가 없습니다")

    with tab2:
        # 연도별 그룹
        year_groups = documents_df.groupby('year').size().sort_index(ascending=False)

        # 연도 선택 (접을 수 있는 형태)
        selected_year = st.selectbox(
            "연도 선택",
            options=["전체"] + list(year_groups.index),
            format_func=lambda x: f"{x}년 ({year_groups.get(x, len(documents_df))}개)" if x != "전체" else f"전체 ({len(documents_df)}개)",
            label_visibility="collapsed"
        )

        if selected_year != "전체":
            year_docs = documents_df[documents_df['year'] == selected_year]

            # 월별 그룹
            month_groups = year_docs.groupby(year_docs['date'].str[5:7]).size()

            # 월 선택
            selected_month = st.selectbox(
                "월 선택",
                options=["전체"] + list(month_groups.index),
                format_func=lambda x: f"{x}월 ({month_groups.get(x, len(year_docs))}개)" if x != "전체" else f"전체 ({len(year_docs)}개)",
                label_visibility="collapsed"
            )

            # 문서 목록 (페이지네이션)
            if selected_month != "전체":
                docs_to_show = year_docs[year_docs['date'].str[5:7] == selected_month]
            else:
                docs_to_show = year_docs

            # 페이지네이션
            items_per_page = 15
            total_pages = (len(docs_to_show) - 1) // items_per_page + 1

            if total_pages > 1:
                page = st.number_input("페이지", min_value=1, max_value=total_pages, value=1, label_visibility="collapsed")
            else:
                page = 1

            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page

            # 문서 표시
            for idx, row in docs_to_show.iloc[start_idx:end_idx].iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button(f"📄 {row['title'][:25]}...", key=f"year_{idx}", use_container_width=True):
                        st.session_state.selected_doc = row['filename']
                with col2:
                    st.caption(row['date'][8:10] + "일")

    with tab3:
        # 타입별 그룹
        type_counts = {
            "구매": len(documents_df[documents_df['category'] == '구매']),
            "수리": len(documents_df[documents_df['category'] == '수리']),
            "검토": len(documents_df[documents_df['category'] == '검토']),
            "소모품": len(documents_df[documents_df['category'] == '소모품']),
            "기타": len(documents_df[documents_df['category'] == '기타'])
        }

        # 타입 선택
        selected_type = st.selectbox(
            "문서 타입",
            options=list(type_counts.keys()),
            format_func=lambda x: f"{x} ({type_counts[x]}개)",
            label_visibility="collapsed"
        )

        # 해당 타입 문서들
        type_docs = documents_df[documents_df['category'] == selected_type]

        # 최근 20개만 표시
        st.caption(f"최근 {min(20, len(type_docs))}개")
        for idx, row in type_docs.head(20).iterrows():
            if st.button(f"📄 {row['title'][:30]}...", key=f"type_{idx}", use_container_width=True):
                st.session_state.selected_doc = row['filename']

        if len(type_docs) > 20:
            st.caption(f"... 외 {len(type_docs)-20}개 더 있음")

    # 4. 최근 문서 (하단 고정)
    st.markdown("---")
    with st.expander("📆 최근 추가된 문서", expanded=False):
        recent_docs = documents_df.nlargest(10, 'date')
        for idx, row in recent_docs.iterrows():
            if st.button(f"🆕 {row['title'][:30]}...", key=f"recent_{idx}", use_container_width=True):
                st.session_state.selected_doc = row['filename']


def render_compact_sidebar(documents_df: pd.DataFrame):
    """초간단 컴팩트 사이드바"""

    st.markdown("### 📁 문서 ({})".format(len(documents_df)))

    # 검색만
    search = st.text_input("🔍", placeholder="검색...", label_visibility="collapsed")

    if search:
        # 검색 결과
        mask = documents_df['title'].str.contains(search, case=False, na=False)
        results = documents_df[mask]

        for idx, row in results.head(10).iterrows():
            # 초간단 버튼
            if st.button(row['title'][:35], key=f"doc_{idx}"):
                st.session_state.selected_doc = row['filename']

        if len(results) > 10:
            st.caption(f"+{len(results)-10}개")
    else:
        # 최근 10개만
        st.caption("최근 문서")
        for idx, row in documents_df.head(10).iterrows():
            if st.button(row['title'][:35], key=f"doc_{idx}"):
                st.session_state.selected_doc = row['filename']


if __name__ == "__main__":
    # 테스트용 더미 데이터
    import numpy as np

    dates = pd.date_range('2020-01-01', periods=224, freq='D')
    df = pd.DataFrame({
        'filename': [f"doc_{i}.pdf" for i in range(224)],
        'title': [f"문서 제목 {i}" for i in range(224)],
        'date': dates.strftime('%Y-%m-%d'),
        'year': dates.year,
        'category': np.random.choice(['구매', '수리', '검토', '소모품', '기타'], 224),
        'drafter': np.random.choice(['김과장', '이대리', '박부장', '미상'], 224)
    })

    st.sidebar.title("개선된 사이드바 테스트")

    # 모드 선택
    mode = st.sidebar.radio("모드", ["개선된 UI", "컴팩트 모드"])

    if mode == "개선된 UI":
        render_improved_sidebar(df)
    else:
        render_compact_sidebar(df)