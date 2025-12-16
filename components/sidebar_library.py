"""
Sidebar Library Component
사이드바에 문서 라이브러리 UI를 표시하는 컴포넌트
"""

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app.config.settings import settings
from scripts.utils.lock import is_reindexing, reindexing_lock
from utils.year_utils import safe_year_to_int

# ============================================================================
# 디자인 토큰 (사이드바 블루 톤)
# ============================================================================

THEME_PRIMARY = "#2A7FBE"  # 포커스/강조
THEME_INK = "#E9F4FF"  # 텍스트(밝은 청백)
THEME_CARD_BG = "rgba(255,255,255,0.10)"  # 카드 바탕 (투명도)
THEME_CARD_BG_H = "rgba(255,255,255,0.18)"  # hover 바탕
THEME_BORDER = "rgba(255,255,255,0.22)"  # 경계선
THEME_MUTED = "#CFE6FF"  # 아이콘/서브텍스트


# ============================================================================
# 유틸리티 함수
# ============================================================================


def _hash_key(*parts: str) -> str:
    """세션 키를 위한 해시 생성 (경로 길이 문제 해결)"""
    h = hashlib.md5("|".join(map(str, parts)).encode("utf-8", "ignore")).hexdigest()
    return h[:12]


def _as_dict(row) -> dict[str, Any]:
    """pandas Series를 dict로 안전하게 변환"""
    try:
        return row.to_dict()  # pd.Series → dict
    except Exception:
        return dict(row) if isinstance(row, dict) else {"title": "unknown"}


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_metrics() -> dict:
    """백엔드 /metrics 조회 (캐시 5초)"""
    try:
        import requests

        r = requests.get("http://localhost:7860/metrics", timeout=0.8)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def _ensure_year_norm(df: pd.DataFrame) -> pd.DataFrame:
    """year_norm 컬럼이 없으면 추가 (사전 계산으로 성능 개선)"""
    if "year_norm" not in df.columns and "year" in df.columns:
        df = df.assign(year_norm=df["year"].apply(safe_year_to_int))
    return df


def _ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """필수 컬럼이 없으면 빈 값으로 추가"""
    required = ["title", "filename", "drafter", "year", "date"]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df


def _apply_sidebar_theme() -> None:
    """사이드바 블루 톤 통일 CSS 적용"""
    st.markdown(
        f"""
<style>
/* 공통 텍스트 컬러 */
section[data-testid="stSidebar"] * {{
  color: {THEME_INK};
}}

/* 입력창(검색) */
section[data-testid="stSidebar"] input[type="text"] {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  color: {THEME_INK};
  border-radius: 10px;
  padding: 8px 12px;
}}
section[data-testid="stSidebar"] input[type="text"]:focus {{
  outline: 0;
  border-color: {THEME_MUTED};
  box-shadow: 0 0 0 2px rgba(42,127,190,0.25);
}}
section[data-testid="stSidebar"] input[type="text"]::placeholder {{
  color: rgba(233,244,255,0.5);
}}

/* Expander(연도별 접기/펼치기) 카드 */
section[data-testid="stSidebar"] details[data-testid="stExpander"] {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  border-radius: 12px;
  overflow: hidden;
  margin: 10px 0;
}}
/* Expander 헤더 바 */
section[data-testid="stSidebar"] details[data-testid="stExpander"] summary {{
  background: {THEME_CARD_BG};
  padding: 8px 12px;
  border-bottom: 1px solid {THEME_BORDER};
}}
/* 헤더 hover */
section[data-testid="stSidebar"] details[data-testid="stExpander"] summary:hover {{
  background: {THEME_CARD_BG_H};
}}
/* Expander 안쪽 컨텐츠 */
section[data-testid="stSidebar"] details[data-testid="stExpander"] > div[role="region"] {{
  background: transparent;
  padding: 8px 12px 12px 12px;
}}
/* Expander 아이콘(chevron) 색상 */
section[data-testid="stSidebar"] details[data-testid="stExpander"] summary svg {{
  stroke: {THEME_MUTED} !important;
}}

/* 버튼(미리보기 열기 등) – 블루 카드 스타일 */
section[data-testid="stSidebar"] button[kind="secondary"],
section[data-testid="stSidebar"] button[kind="primary"] {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  color: {THEME_INK};
  border-radius: 10px;
  padding: 8px 16px;
  font-weight: 500;
  transition: all 0.2s ease;
}}
section[data-testid="stSidebar"] button[kind="secondary"]:hover,
section[data-testid="stSidebar"] button[kind="primary"]:hover {{
  background: {THEME_CARD_BG_H};
  border-color: {THEME_MUTED};
  transform: translateY(-1px);
}}
section[data-testid="stSidebar"] button[kind="primary"] {{
  background: {THEME_PRIMARY};
  border-color: {THEME_PRIMARY};
}}
section[data-testid="stSidebar"] button[kind="primary"]:hover {{
  background: #3a8fce;
  border-color: #3a8fce;
}}
/* 버튼 비활성 색 */
section[data-testid="stSidebar"] button[disabled] {{
  opacity: 0.6;
  cursor: not-allowed;
}}

/* Selectbox/Radio 등 선택 위젯 */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  border-radius: 10px;
  color: {THEME_INK};
}}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div:hover {{
  border-color: {THEME_MUTED};
}}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stRadio > label {{
  color: {THEME_INK};
}}

/* Metric 카드 스타일링 */
section[data-testid="stSidebar"] div[data-testid="stMetric"] {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  border-radius: 10px;
  padding: 12px;
}}

/* Caption 색상 */
section[data-testid="stSidebar"] .stCaption {{
  color: {THEME_MUTED};
}}

/* Info/Warning/Error 박스 */
section[data-testid="stSidebar"] div[data-testid="stAlert"] {{
  background: {THEME_CARD_BG};
  border: 1px solid {THEME_BORDER};
  border-radius: 10px;
}}
</style>
""",
        unsafe_allow_html=True,
    )


# ============================================================================
# 문서 리스트 표시 (위젯 축소 버전)
# ============================================================================


def display_document_list(
    filtered_df: pd.DataFrame, df: pd.DataFrame, prefix: str = "doc",
) -> pd.DataFrame:
    """문서 리스트를 표시하는 헬퍼 함수 (위젯 최소화)

    Args:
        filtered_df: 필터링된 문서 DataFrame
        df: 전체 문서 DataFrame
        prefix: 버튼 키 prefix (고유성 보장)

    Returns:
        항상 DataFrame 반환 (비어 있을 수 있음)
    """
    # 빈 DataFrame 처리
    if not isinstance(filtered_df, pd.DataFrame) or filtered_df.empty:
        if not isinstance(filtered_df, pd.DataFrame):
            st.error("문서 목록을 불러올 수 없습니다.")
        elif df.empty:
            st.warning("문서가 없습니다. docs 폴더에 PDF 파일을 추가해주세요.")
        else:
            st.caption("표시할 문서가 없습니다.")
        return pd.DataFrame()

    # year_norm 컬럼 확보
    filtered_df = _ensure_year_norm(filtered_df)

    # 연도별 그룹화 (정수형 year_norm 기준)
    years = sorted(
        [y for y in filtered_df["year_norm"].unique() if pd.notna(y)], reverse=True,
    )
    if len(years) == 0 and filtered_df["year_norm"].isna().any():
        years = [0]  # 미상 전용 그룹

    for year in years:
        # 그룹 필터링 (year_norm 기반)
        if year != 0:
            group = filtered_df[filtered_df["year_norm"] == year]
        else:
            group = filtered_df[filtered_df["year_norm"].isna()]

        year_display = int(year) if year else "미상"
        st.markdown(f"### {year_display}년 ({len(group)}개)")

        # 옵션 생성 (dict 리스트)
        options = []
        labels = []
        for _, row in group.iterrows():
            row_dict = _as_dict(row)
            date_str = (
                row_dict.get("date", "")[5:10]
                if isinstance(row_dict.get("date"), str) and len(row_dict.get("date", "")) >= 10
                else "     "
            )
            title = row_dict.get("title", "제목 없음")
            title_short = title[:30] + "..." if len(title) > 30 else title
            label = f"[{date_str}] {title_short}"

            options.append(row_dict)
            labels.append(label)

        # selectbox로 문서 선택 (위젯 1개로 축소)
        if options:
            # format_func에서 사용할 labels 고정
            def make_format_func(label_list):
                return lambda i: label_list[i]

            selected_idx = st.selectbox(
                "문서 선택",
                options=range(len(options)),
                format_func=make_format_func(labels),
                key=f"{prefix}_select_{_hash_key(str(year), str(len(options)))}",
                label_visibility="collapsed",
            )

            if selected_idx is not None:
                selected_doc = options[selected_idx]
                # 버튼으로 미리보기 열기
                if st.button(
                    "📖 미리보기 열기",
                    key=f"{prefix}_open_{_hash_key(str(year), str(selected_idx))}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state.selected_doc = selected_doc
                    st.session_state.show_doc_preview = True
                    st.session_state.pdf_preview_shown = False

    return filtered_df


# ============================================================================
# 사이드바 메인 렌더링
# ============================================================================


def render_sidebar_library(rag_instance) -> None:
    """사이드바에 문서 라이브러리 UI 렌더링

    Args:
        rag_instance: RAG 시스템 인스턴스 (st.session_state.rag)
    """
    from utils.document_loader import load_documents

    # 사이드바에도 로고 표시 (흰색 버전, 작게)
    if Path("logo_inverted.png").exists():
        st.image("logo_inverted.png", width=200)
    elif Path("logo.png").exists():
        st.image("logo.png", width=200)
    st.markdown("---")

    # 사이드바 블루 톤 통일 CSS
    _apply_sidebar_theme()

    # =========================================================================
    # 📚 사용자 중심: 검색 가능한 문서 수 (핵심 정보)
    # =========================================================================
    st.markdown("### 📚 총 인덱스 문서")
    try:
        from app.data.metadata_db import MetadataDB
        from config.indexing import ALLOWED_EXTS

        db = MetadataDB()

        # 통합 카운트 API 사용 - 고유 문서 수 (중복 제외, 허용 확장자만)
        allowed_ext_list = [ext.replace(".", "") for ext in ALLOWED_EXTS]
        unique_count = db.count_unique_documents(allowed_ext=tuple(allowed_ext_list))

        # 🎯 사용자에게 가장 중요한 정보: AI가 검색 가능한 문서 수
        st.metric("검색 가능 문서", f"{unique_count}건", help="AI가 답변에 사용할 수 있는 실제 문서 수")

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

        # [PATCH 3] 카운트 불일치 체크 및 경고 + stale 메트릭 (캐시 적용)
        metrics_data = _fetch_metrics()
        stale_entries = metrics_data.get("stale_index_entries", 0)

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
                drop_rebuild = st.checkbox(
                    "Drop & Rebuild (안전 모드)",
                    help="전체 인덱스를 삭제 후 재구축 (가장 깔끔)",
                    key="drop_rebuild_checkbox",
                )
            with col2:
                reindex_button = st.button("🔄 전체 재색인", key="fix_mismatch")

            if reindex_button:
                if "auto_indexer" in st.session_state:
                    try:
                        with reindexing_lock(timeout_sec=3.0), st.spinner(
                            "전체 재인덱싱 중..."
                            + (" (Drop & Rebuild)" if drop_rebuild else ""),
                        ):
                            st.info("🔒 락 획득, 안전 재색인 시작")

                            if drop_rebuild:
                                # Drop & Rebuild 모드: everything_index.db 삭제 후 재생성
                                import os
                                import sqlite3

                                try:
                                    if Path("everything_index.db").exists():
                                        os.remove("everything_index.db")
                                    # 새 DB 생성 (자동 인덱서가 다시 만듦)
                                    conn = sqlite3.connect("everything_index.db")
                                    conn.execute(
                                        """
                                            CREATE TABLE IF NOT EXISTS files (
                                                filename TEXT,
                                                path TEXT,
                                                PRIMARY KEY (filename)
                                            )
                                        """,
                                    )
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
                            Path("var/last_full_reindex.txt").write_text(
                                datetime.now().isoformat(),
                            )

                            if "rag" in st.session_state:
                                del st.session_state.rag
                            st.rerun()
                    except RuntimeError as e:
                        st.error(f"❌ 동시 작업으로 대기 초과: {e}")
                        st.stop()

        # 최근 문서 (expander) - 단일 진실원 사용
        with st.expander("최근 10건", expanded=False):
            try:
                # settings에서 DB 경로 가져오기 (단일 진실원)
                import sqlite3

                db_path = getattr(settings, "METADATA_DB_PATH", "metadata.db")
                conn = sqlite3.connect(db_path)
                rows = conn.execute(
                    """
                    SELECT filename, title, page_count, created_at
                    FROM documents
                    ORDER BY created_at DESC
                    LIMIT 10
                """,
                ).fetchall()
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
                st.caption(f"최근 문서 조회 실패: {e}")

    except Exception as e:
        st.error(f"DB 접근 실패: {e}")

    st.markdown("---")

    # =========================================================================
    # 🛠️ 관리자용: 시스템 상태 및 물리 파일 정보
    # =========================================================================
    with st.expander("🛠️ 시스템 상태 (관리자용)", expanded=False):
        st.caption("**물리 파일 스캔 정보**")

        # 실시간 파일 카운트 (2025-12-16: 캐시 대신 직접 스캔)
        try:
            import subprocess

            # PDF 파일 수 (docs/year_* 폴더)
            pdf_result = subprocess.run(
                ["find", "docs/", "-name", "*.pdf"],
                capture_output=True, text=True, timeout=5,
            )
            pdf_count = len([f for f in pdf_result.stdout.strip().split("\n") if f])

            # DB 문서 수
            db_count = unique_count

            col1, col2 = st.columns(2)
            with col1:
                st.metric("PDF 파일", f"{pdf_count}개", help="폴더에 존재하는 물리 PDF 개수")
            with col2:
                st.metric("DB 문서", f"{db_count}건", help="데이터베이스에 등록된 문서 수")

            # 차이 계산
            if pdf_count != db_count:
                diff = abs(pdf_count - db_count)
                if pdf_count > db_count:
                    st.caption(f"⚠️ 미등록 파일: {diff}개 (인덱싱 필요)")
                else:
                    st.caption(f"⚠️ DB에만 존재: {diff}건 (파일 삭제됨)")
            else:
                st.caption("✅ 파일과 DB 동기화됨")

            # 현재 시간
            from datetime import datetime
            st.caption(f"🕒 조회 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        except Exception as e:
            st.caption(f"파일 스캔 실패: {e}")

    st.markdown("---")

    # 수동 재인덱싱 버튼
    if "auto_indexer" in st.session_state:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("새로고침", key="refresh_index", use_container_width=True):
                with st.spinner("인덱싱 중..."):
                    result = st.session_state.auto_indexer.check_new_files()
                    if result["new"]:
                        st.success(f"✅ {len(result['new'])}개 새 파일 인덱싱 완료!")
                        # RAG 시스템 리로드
                        if "rag" in st.session_state:
                            del st.session_state.rag
                        st.rerun()
                    else:
                        st.info("변경사항 없음")

        with col2:
            if st.button("♻️ 전체재인덱싱", key="force_reindex", use_container_width=True):
                try:
                    with reindexing_lock(timeout_sec=3.0), st.spinner("전체 재인덱싱 중..."):
                        result = st.session_state.auto_indexer.force_reindex()
                        st.success(f"✅ {result['total']}개 파일 재인덱싱 완료!")
                        # RAG 시스템 리로드
                        if "rag" in st.session_state:
                            del st.session_state.rag
                        st.rerun()
                except RuntimeError as e:
                    st.error(f"❌ 동시 작업으로 대기 초과: {e}")
                    st.stop()

    st.markdown("---")
    st.markdown("### 📂 문서 라이브러리")

    # 빠른 문서 개수만 먼저 표시
    if hasattr(rag_instance, "metadata_cache"):
        doc_count = len(rag_instance.metadata_cache)
        st.caption(f"📚 {doc_count}개 문서")

    # 문서 로드 (캐시됨 - @st.cache_data 덕분에 빠름)
    with st.spinner("문서 목록 로드 중..."):
        df = load_documents(rag_instance)
        # None 체크 및 빈 DataFrame 대체
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            df = pd.DataFrame()
        # 필수 컬럼 및 year_norm 확보
        df = _ensure_required_columns(df)
        df = _ensure_year_norm(df)
        st.session_state.documents_df = df

    # 문서 목록이 로드된 경우 탭 표시
    if not df.empty:
        # 검색 인덱스 카운트를 session_state에서 가져오기
        if "search_count" in st.session_state:
            search_count = st.session_state.search_count
        else:
            # session_state에 없으면 DB에서 조회
            try:
                from app.data.metadata_db import MetadataDB

                temp_db = MetadataDB()
                search_count = temp_db.count_search_index()
                st.session_state.search_count = search_count
                temp_db.close()
            except Exception:
                search_count = (
                    df["filename"].nunique() if "filename" in df.columns else len(df)
                )

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
                key="doc_search_input",
            )

            # 검색 처리
            if search_query:
                # 검색 결과
                mask = (
                    df["title"].str.contains(search_query, case=False, na=False)
                    | df["filename"].str.contains(search_query, case=False, na=False)
                    | df["drafter"].str.contains(search_query, case=False, na=False)
                )
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
            if not df.empty and "year_norm" in df.columns:
                # year_norm 기반으로 연도 목록 추출 (성능 개선)
                years = sorted(
                    [y for y in df["year_norm"].unique() if pd.notna(y)], reverse=True,
                )
                if len(years) == 0 and df["year_norm"].isna().any():
                    years = [0]  # 미상 전용

                # 연도별 문서 개수 (year_norm 기반 - 빠름)
                year_counts = {}
                for year in years:
                    if year != 0:
                        count = len(df[df["year_norm"] == year])
                    else:
                        count = len(df[df["year_norm"].isna()])
                    year_counts[year] = count

                year_display = [int(y) if y else "미상" for y in years]
                year_options = [
                    f"{year_display[i]}년 ({year_counts[years[i]]}개)"
                    for i in range(len(years))
                ]

                selected_year_str = st.selectbox(
                    "연도 선택",
                    year_options,
                    label_visibility="collapsed",
                    key="year_select",
                )

                # 선택된 연도 추출 및 필터링
                if selected_year_str:
                    selected_idx = year_options.index(selected_year_str)
                    selected_year = years[selected_idx]

                    # year_norm 기반 필터링 (apply(lambda) 제거)
                    if selected_year != 0:
                        filtered_df = df[df["year_norm"] == selected_year]
                    else:
                        filtered_df = df[df["year_norm"].isna()]
                else:
                    filtered_df = pd.DataFrame()

                # 선택된 연도 정보
                if selected_year == 0:
                    st.info(f"연도 정보 없는 문서 {len(filtered_df)}개")
                else:
                    st.info(f"{int(selected_year)}년 문서 {len(filtered_df)}개")

                # 연도별 탭에서 문서 리스트 표시
                display_document_list(filtered_df, df, "year")
            else:
                st.info("문서가 없습니다")

    # CSS 스타일은 페이지 시작 시 로드됨 (load_all_css)

    # 시스템 정보
    st.markdown("---")
    st.markdown("### 시스템 정보")
    if not df.empty and "year_norm" in df.columns:
        # year_norm 기반으로 min/max 계산 (성능 개선)
        years = [y for y in df["year_norm"].unique() if pd.notna(y)]
        if years:
            year_range = f"{int(min(years))}년 ~ {int(max(years))}년"
        else:
            year_range = "데이터 없음"
    else:
        year_range = "데이터 없음"

    st.info(
        f"""
    **모델**: {settings.RAG_MODEL}
    **문서**: {len(df)}개
    **기간**: {year_range}
    """,
    )
