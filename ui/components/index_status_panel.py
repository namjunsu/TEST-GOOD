"""
인덱스 상태 패널 (UI 컴포넌트)

/metrics 엔드포인트에서 실시간으로 인덱스 상태를 조회하여 표시합니다.

사용법:
    from ui.components.index_status_panel import render_index_status_panel
    render_index_status_panel(api_base_url="http://localhost:7860")
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import streamlit as st

# 프로젝트 루트 상수 (상대 경로 문제 해결)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 인제스트 상태 아이콘 매핑
INGEST_STATUS_ICONS = {
    "idle": "🟢",
    "running": "🟡",
    "failed": "🔴",
}


def fetch_index_metrics(api_base_url: str, timeout: int = 5) -> dict[str, Any]:
    """인덱스 메트릭 조회 (테스트 가능한 순수 함수)

    Args:
        api_base_url: FastAPI 백엔드 URL
        timeout: 요청 타임아웃 (초)

    Returns:
        메트릭 딕셔너리

    Raises:
        requests.exceptions.RequestException: API 호출 실패
    """
    response = requests.get(
        f"{api_base_url}/metrics",
        headers={"Cache-Control": "no-cache"},
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def _format_last_reindex(timestamp: Optional[str]) -> str:
    """최근 재색인 시각 포맷팅 (안전한 datetime 파싱)

    Args:
        timestamp: ISO8601 형식 문자열 (예: "2025-11-17T12:34:56Z")

    Returns:
        사람이 읽기 쉬운 형식 (예: "2025-11-17 12:34:56")
    """
    if not timestamp or timestamp == "unknown":
        return "N/A"

    try:
        # UTC 'Z' 처리 (Python 3.11 미만에서는 'Z'를 인식 못 함)
        ts_normalized = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_normalized)

        # UTC로 명시적 변환
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        # 파싱 실패 시 원본 반환
        return timestamp


def _get_int_metric(metrics: dict[str, Any], key: str, default: int = 0) -> int:
    """타입 안전한 정수 메트릭 추출

    Args:
        metrics: 메트릭 딕셔너리
        key: 추출할 키
        default: 기본값

    Returns:
        정수 값 (타입 보장)
    """
    value = metrics.get(key, default)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def render_index_status_panel(api_base_url: str = "http://localhost:7860"):
    """인덱스 상태 패널 렌더링

    Args:
        api_base_url: FastAPI 백엔드 URL
    """
    st.markdown("### 📊 Index Status")

    try:
        # /metrics 호출 (UX 개선: 스피너 표시)
        with st.spinner("📡 인덱스 메트릭 조회 중..."):
            metrics = fetch_index_metrics(api_base_url)

        # 상단 배지: 인덱스 버전 및 최근 재색인 시각
        col1, col2 = st.columns(2)
        with col1:
            index_version = metrics.get("index_version", "unknown")
            st.metric(label="Index Version", value=index_version)

        with col2:
            last_reindex = metrics.get("last_reindex_at", "unknown")
            last_reindex_display = _format_last_reindex(last_reindex)
            st.metric(label="Last Reindex", value=last_reindex_display)

        # 문서 수 표시 (타입 안전)
        st.markdown("#### 문서 수")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            docstore_count = _get_int_metric(metrics, "docstore_count")
            st.metric(label="DB", value=docstore_count)

        with col2:
            faiss_count = _get_int_metric(metrics, "faiss_count")
            st.metric(label="FAISS", value=faiss_count)

        with col3:
            bm25_count = _get_int_metric(metrics, "bm25_count")
            st.metric(label="BM25", value=bm25_count)

        with col4:
            unindexed_count = _get_int_metric(metrics, "unindexed_count")
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
        status_icon = INGEST_STATUS_ICONS.get(ingest_status, "⚪")
        st.markdown(f"**인제스트 상태:** {status_icon} `{ingest_status}`")

        # Reports 링크 (프로젝트 루트 기준 경로)
        st.markdown("#### 📄 Reports")

        report_files = [
            ("INGEST_DIAG_REPORT.md", BASE_DIR / "reports" / "INGEST_DIAG_REPORT.md"),
            ("chunk_stats.csv", BASE_DIR / "reports" / "chunk_stats.csv"),
            ("index_consistency.md", BASE_DIR / "reports" / "index_consistency.md"),
            ("ocr_audit.md", BASE_DIR / "reports" / "ocr_audit.md"),
        ]

        cols = st.columns(len(report_files))
        for i, (label, path) in enumerate(report_files):
            with cols[i]:
                if path.exists() and path.is_file():
                    with open(path, "rb") as f:
                        st.download_button(
                            label=label,
                            data=f,
                            file_name=label,
                            mime="text/markdown" if path.suffix == ".md" else "text/csv",
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
