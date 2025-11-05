"""
Sidebar Library Component
사이드바에 문서 라이브러리 UI를 표시하는 컴포넌트
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Optional
from utils.year_utils import safe_year_to_int, normalize_year_list, compare_year
from scripts.utils.lock import reindexing_lock, is_reindexing
from app.config.settings import RAG_MODEL


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
        # year 필드를 정수로 변환하여 정렬 (year_utils 사용)
        years = filtered_df['year'].unique()
        valid_years = normalize_year_list(years)

        for year in valid_years:
            # year_utils의 compare_year 함수를 사용하여 안전하게 비교
            year_docs = filtered_df[
                filtered_df['year'].apply(lambda x: compare_year(x, year))
            ]

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
                if st.button(button_text, key=unique_key, use_container_width=True):
                    st.session_state.selected_doc = row
                    st.session_state.show_doc_preview = True
                    # pdf_preview_shown 초기화 (새 문서 선택 시)
                    st.session_state.pdf_preview_shown = False
                    # st.rerun() 제거 - Streamlit 자동 재렌더링 (버그 수정 2025-10-31)
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

    # 자동 인덱싱 상태 표시 (물리 파일 수)
    st.markdown("### 📁 파일 스캔 (물리)")
    if 'auto_indexer' in st.session_state:
        stats = st.session_state.auto_indexer.get_statistics()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("PDF", f"{stats['pdf_count']}개")
        with col2:
            st.metric("TXT", f"{stats['txt_count']}개")
        # 물리 파일 총 개수 표시
        physical_total = stats['pdf_count'] + stats['txt_count']
        st.caption(f"물리 파일 총계: {physical_total}개")

        # 마지막 업데이트
        if stats['last_update'] != 'Never':
            st.caption(f"마지막 체크: {stats['last_update'][:16]}")

    st.markdown("---")

    # 문서 라이브러리 요약 (DB 기반)
    st.markdown("### 📚 문서 라이브러리")
    try:
        from modules.metadata_db import MetadataDB
        from config.indexing import ALLOWED_EXTS

        db = MetadataDB()

        # 통합 카운트 API 사용 - 고유 문서 수 (중복 제외, 허용 확장자만)
        allowed_ext_list = [ext.replace(".", "") for ext in ALLOWED_EXTS]
        unique_count = db.count_unique_documents(allowed_ext=tuple(allowed_ext_list))
        st.metric("총 문서", f"{unique_count}건", help="MetadataDB 기준")

        # 확장자별 카운트 (물리 파일 기준)
        ext_counts = db.count_by_extension()

        # 검색 인덱스 카운트 (패치 2025-10-31: MetadataDB 단일 소스 강제)
        import os
        index_source = os.getenv("INDEX_SOURCE", "metadata")

        if index_source == "metadata":
            # MetadataDB를 단일 소스로 사용 (권장)
            search_count = db.count_unique_documents(allowed_ext=tuple(allowed_ext_list))
        else:
            # 레거시 BM25 인덱스 참조 (deprecated)
            search_count = db.count_search_index()

        # session_state에 저장하여 아래에서도 사용 가능하게 함
        st.session_state.search_count = search_count
        st.session_state.unique_count = unique_count

        # [PATCH 3] 카운트 불일치 체크 및 경고 + stale 메트릭
        stale_entries = 0
        try:
            import requests
            # /metrics 엔드포인트에서 stale_index_entries 가져오기
            resp = requests.get("http://localhost:7860/metrics", timeout=2)
            if resp.status_code == 200:
                metrics_data = resp.json()
                stale_entries = metrics_data.get("stale_index_entries", 0)
        except:
            pass  # 백엔드가 실행되지 않았을 수 있음

        # 불일치 또는 stale 항목 존재 시 경고
        has_mismatch = (unique_count != search_count) or (stale_entries > 0)

        # [LOCK] 재색인 진행 중 체크
        if is_reindexing():
            st.warning("⚙️ 재색인 진행 중… 잠시 후 재시도해주세요")
            st.stop()

        if has_mismatch:
            warning_msg = f"⚠️ 지표 불일치: 라이브러리 {unique_count} / 검색 인덱스 {search_count}"
            if stale_entries > 0:
                warning_msg += f" (삭제 필요: {stale_entries}건)"
            st.warning(warning_msg)

            # [PATCH 4] 안전 모드 재색인 옵션
            col1, col2 = st.columns([3, 1])
            with col1:
                drop_rebuild = st.checkbox("Drop & Rebuild (안전 모드)",
                    help="전체 인덱스를 삭제 후 재구축 (가장 깔끔)",
                    key="drop_rebuild_checkbox")
            with col2:
                reindex_button = st.button("🔄 전체 재색인", key="fix_mismatch")

            if reindex_button:
                if 'auto_indexer' in st.session_state:
                    try:
                        with reindexing_lock(timeout_sec=3.0):
                            with st.spinner("전체 재인덱싱 중..." + (" (Drop & Rebuild)" if drop_rebuild else "")):
                                st.info("🔒 락 획득, 안전 재색인 시작")

                                if drop_rebuild:
                                    # Drop & Rebuild 모드: everything_index.db 삭제 후 재생성
                                    import os
                                    import sqlite3
                                    try:
                                        if os.path.exists("everything_index.db"):
                                            os.remove("everything_index.db")
                                        # 새 DB 생성 (자동 인덱서가 다시 만듦)
                                        conn = sqlite3.connect("everything_index.db")
                                        conn.execute("""
                                            CREATE TABLE IF NOT EXISTS files (
                                                filename TEXT,
                                                path TEXT,
                                                PRIMARY KEY (filename)
                                            )
                                        """)
                                        conn.commit()
                                        conn.close()
                                        st.info("🗑️ 기존 인덱스 삭제 완료")
                                    except Exception as e:
                                        st.error(f"Drop 실패: {e}")

                                result = st.session_state.auto_indexer.force_reindex()
                                st.success(f"✅ {result['total']}개 파일 재인덱싱 완료!")

                                # 타임스탬프 기록
                                from datetime import datetime
                                Path("var").mkdir(exist_ok=True)
                                Path("var/last_full_reindex.txt").write_text(datetime.now().isoformat())

                                if 'rag' in st.session_state:
                                    del st.session_state.rag
                                st.rerun()
                    except RuntimeError as e:
                        st.error(f"❌ 동시 작업으로 대기 초과: {e}")

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
                try:
                    with reindexing_lock(timeout_sec=3.0):
                        with st.spinner("전체 재인덱싱 중..."):
                            result = st.session_state.auto_indexer.force_reindex()
                            st.success(f"✅ {result['total']}개 파일 재인덱싱 완료!")
                            # RAG 시스템 리로드
                            if 'rag' in st.session_state:
                                del st.session_state.rag
                            st.rerun()
                except RuntimeError as e:
                    st.error(f"❌ 동시 작업으로 대기 초과: {e}")

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
        # 검색 인덱스 카운트를 session_state에서 가져오기
        if 'search_count' in st.session_state:
            search_count = st.session_state.search_count
        else:
            # session_state에 없으면 DB에서 조회
            try:
                from modules.metadata_db import MetadataDB
                temp_db = MetadataDB()
                search_count = temp_db.count_search_index()
                st.session_state.search_count = search_count
                temp_db.close()
            except:
                search_count = df['filename'].nunique() if 'filename' in df.columns else len(df)

        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"검색 가능: {search_count}개 문서")

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
                # year_utils를 사용하여 year 필드 정규화
                years_raw = df['year'].unique()
                years = normalize_year_list(years_raw)

                # 연도별 문서 개수 포함하여 표시
                year_counts = {}
                for year in years:
                    # compare_year를 사용하여 정확한 카운트
                    count = len(df[df['year'].apply(lambda x: compare_year(x, year))])
                    year_counts[year] = count

                year_options = [f"{year}년 ({year_counts[year]}개)" for year in years]

                selected_year_str = st.selectbox(
                    "연도 선택",
                    year_options,
                    label_visibility="collapsed",
                    key="year_select"
                )

                # 선택된 연도 추출
                if selected_year_str:
                    selected_year = int(selected_year_str.split("년")[0])
                    # compare_year를 사용하여 안전하게 필터링
                    filtered_df = df[df['year'].apply(lambda x: compare_year(x, selected_year))]
                else:
                    filtered_df = pd.DataFrame()

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
        # year_utils를 사용하여 안전하게 min/max 계산
        years = normalize_year_list(df['year'].unique())
        if years:
            year_range = f"{min(years)}년 ~ {max(years)}년"
        else:
            year_range = "데이터 없음"
    else:
        year_range = "데이터 없음"

    st.info(f"""
    **모델**: {RAG_MODEL}
    **문서**: {len(df)}개
    **기간**: {year_range}
    """)
