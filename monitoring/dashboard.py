"""
Performance Dashboard
실시간 성능 대시보드
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import time

# Import monitoring modules
from monitoring.metrics_collector import collector
from monitoring.performance_profiler import profiler

def create_dashboard():
    """성능 대시보드 생성"""

    st.set_page_config(
        page_title="RAG System Performance",
        page_icon="📊",
        layout="wide"
    )

    st.title("🎯 RAG System Performance Dashboard")

    # 실시간 메트릭
    col1, col2, col3, col4 = st.columns(4)

    # 자동 새로고침
    placeholder = st.empty()

    while True:
        with placeholder.container():
            metrics = collector.get_current_metrics()

            # 시스템 메트릭
            with col1:
                st.metric(
                    "CPU Usage",
                    f"{metrics.get('system', {}).get('cpu_percent', 0):.1f}%",
                    delta=None
                )
                st.metric(
                    "Memory",
                    f"{metrics.get('system', {}).get('memory_rss_mb', 0):.0f} MB",
                    delta=None
                )

            # 캐시 메트릭
            with col2:
                cache_metrics = metrics.get('cache', {})
                st.metric(
                    "Cache Hit Rate",
                    f"{cache_metrics.get('hit_rate', 0)*100:.1f}%",
                    delta=None
                )
                st.metric(
                    "Cache Size",
                    cache_metrics.get('cache_size', 0),
                    delta=None
                )

            # 검색 메트릭
            with col3:
                search_metrics = metrics.get('search', {})
                st.metric(
                    "Total Searches",
                    search_metrics.get('searches_total', 0),
                    delta=None
                )
                st.metric(
                    "Avg Search Time",
                    f"{search_metrics.get('avg_search_time_ms', 0):.0f}ms",
                    delta=None
                )

            # 애플리케이션 메트릭
            with col4:
                app_metrics = metrics.get('application', {})
                uptime = app_metrics.get('uptime_seconds', 0)
                st.metric(
                    "Uptime",
                    f"{uptime//3600:.0f}h {(uptime%3600)//60:.0f}m",
                    delta=None
                )
                st.metric(
                    "Errors",
                    app_metrics.get('errors_total', 0),
                    delta=None
                )

            # 그래프 섹션
            st.subheader("📈 Performance Trends")

            # 메트릭 히스토리 가져오기
            history = collector.get_metrics_history(minutes=5)

            if history:
                # CPU & Memory 차트
                fig_system = go.Figure()

                timestamps = [h['timestamp'] for h in history]
                cpu_values = [h.get('system', {}).get('cpu_percent', 0) for h in history]
                mem_values = [h.get('system', {}).get('memory_rss_mb', 0) for h in history]

                fig_system.add_trace(go.Scatter(
                    x=timestamps,
                    y=cpu_values,
                    name='CPU %',
                    line=dict(color='blue')
                ))

                fig_system.add_trace(go.Scatter(
                    x=timestamps,
                    y=mem_values,
                    name='Memory MB',
                    yaxis='y2',
                    line=dict(color='red')
                ))

                fig_system.update_layout(
                    title='System Resources',
                    yaxis=dict(title='CPU %'),
                    yaxis2=dict(title='Memory MB', overlaying='y', side='right'),
                    hovermode='x unified'
                )

                st.plotly_chart(fig_system, use_container_width=True)

            # 프로파일링 결과
            st.subheader("⚡ Performance Profiling")

            timing_report = profiler.get_timing_report()
            if timing_report:
                df_timing = pd.DataFrame.from_dict(timing_report, orient='index')
                st.dataframe(df_timing)

        time.sleep(1)  # 1초마다 업데이트

if __name__ == "__main__":
    # 메트릭 수집 시작
    collector.start_collection()

    try:
        # 대시보드 실행
        create_dashboard()
    finally:
        # 정리
        collector.stop_collection()
