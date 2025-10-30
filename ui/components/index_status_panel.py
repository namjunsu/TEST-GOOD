"""
인덱스 상태 패널 (UI 컴포넌트)

/metrics 엔드포인트에서 실시간으로 인덱스 상태를 조회하여 표시합니다.

사용법:
    from ui.components.index_status_panel import render_index_status_panel
    render_index_status_panel(api_base_url="http://localhost:7860")
"""

import streamlit as st
import requests
from datetime import datetime
from pathlib import Path


def render_index_status_panel(api_base_url: str = "http://localhost:7860"):
    """인덱스 상태 패널 렌더링

    Args:
        api_base_url: FastAPI 백엔드 URL
    """
    st.markdown("### 📊 Index Status")

    try:
        # /metrics 호출 (캐시 금지)
        response = requests.get(
            f"{api_base_url}/metrics",
            headers={"Cache-Control": "no-cache"},
            timeout=5
        )
        response.raise_for_status()
        metrics = response.json()

        # 상단 배지: 인덱스 버전 및 최근 재색인 시각
        col1, col2 = st.columns(2)
        with col1:
            index_version = metrics.get("index_version", "unknown")
            st.metric(label="Index Version", value=index_version)

        with col2:
            last_reindex = metrics.get("last_reindex_at", "unknown")
            if last_reindex != "unknown":
                try:
                    # ISO8601을 더 읽기 쉬운 형식으로 변환
                    dt = datetime.fromisoformat(last_reindex)
                    last_reindex_display = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    last_reindex_display = last_reindex
            else:
                last_reindex_display = "N/A"

            st.metric(label="Last Reindex", value=last_reindex_display)

        # 문서 수 표시
        st.markdown("#### 문서 수")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            docstore_count = metrics.get("docstore_count", 0)
            st.metric(label="DB", value=docstore_count)

        with col2:
            faiss_count = metrics.get("faiss_count", 0)
            st.metric(label="FAISS", value=faiss_count)

        with col3:
            bm25_count = metrics.get("bm25_count", 0)
            st.metric(label="BM25", value=bm25_count)

        with col4:
            unindexed_count = metrics.get("unindexed_count", 0)
            st.metric(label="Unindexed", value=unindexed_count)

        # 정합성 경고
        if unindexed_count > 0:
            st.warning(
                f"⚠️ 동기화 필요: {unindexed_count}개 문서가 인덱스에 없습니다. "
                f"`make reindex`를 실행하세요.",
                icon="⚠️"
            )
        else:
            st.success("✅ 모든 문서가 인덱스에 동기화되었습니다.", icon="✅")

        # 인제스트 상태
        ingest_status = metrics.get("ingest_status", "idle")
        status_icon = {
            "idle": "🟢",
            "running": "🟡",
            "failed": "🔴"
        }.get(ingest_status, "⚪")

        st.markdown(f"**인제스트 상태:** {status_icon} `{ingest_status}`")

        # Reports 링크
        st.markdown("#### 📄 Reports")

        report_files = [
            ("INGEST_DIAG_REPORT.md", "reports/INGEST_DIAG_REPORT.md"),
            ("chunk_stats.csv", "reports/chunk_stats.csv"),
            ("index_consistency.md", "reports/index_consistency.md"),
            ("ocr_audit.md", "reports/ocr_audit.md"),
        ]

        cols = st.columns(len(report_files))
        for i, (label, path) in enumerate(report_files):
            with cols[i]:
                if Path(path).exists():
                    with open(path, 'rb') as f:
                        st.download_button(
                            label=label,
                            data=f,
                            file_name=label,
                            mime="text/markdown" if path.endswith(".md") else "text/csv",
                            key=f"download_{label}"
                        )
                else:
                    st.button(label, disabled=True, key=f"disabled_{label}")

        # 새로고침 버튼
        if st.button("🔄 새로고침", key="refresh_index_status"):
            st.rerun()

    except requests.exceptions.RequestException as e:
        st.error(f"❌ /metrics 호출 실패: {e}", icon="❌")
        st.info("백엔드 서버(FastAPI)가 실행 중인지 확인하세요.")

    except Exception as e:
        st.error(f"❌ 패널 렌더링 실패: {e}", icon="❌")


# 독립 실행 (테스트용)
if __name__ == "__main__":
    st.set_page_config(page_title="Index Status", layout="wide")
    render_index_status_panel()
