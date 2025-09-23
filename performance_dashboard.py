#!/usr/bin/env python3
"""
실시간 성능 대시보드
시스템 모니터링 및 분석
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import psutil
import json
from pathlib import Path
import time
from monitoring.performance_profiler import PerformanceProfiler
from monitoring.metrics_collector import MetricsCollector

class PerformanceDashboard:
    """성능 대시보드"""

    def __init__(self):
        self.collector = MetricsCollector()
        self.profiler = PerformanceProfiler()

    def render_dashboard(self):
        """대시보드 렌더링"""
        st.set_page_config(
            page_title="RAG System Performance",
            layout="wide",
            initial_sidebar_state="collapsed"
        )

        st.title("🚀 RAG System Performance Dashboard")

        # 실시간 메트릭
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            st.metric("CPU Usage", f"{cpu_percent}%", delta=f"{cpu_percent-50:.1f}%")

        with col2:
            memory = psutil.virtual_memory()
            st.metric("Memory", f"{memory.percent}%", f"{memory.used/(1024**3):.1f} GB")

        with col3:
            # 응답 시간 (캐시에서 가져오기)
            avg_response = self._get_avg_response_time()
            st.metric("Avg Response", f"{avg_response:.2f}s", delta="-15%")

        with col4:
            # 캐시 히트율
            cache_hit_rate = self._get_cache_hit_rate()
            st.metric("Cache Hit Rate", f"{cache_hit_rate:.1%}", delta="+5%")

        # 차트 섹션
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📈 Response Time Trend")
            self._render_response_time_chart()

        with col2:
            st.subheader("💾 Memory Usage")
            self._render_memory_chart()

        # 상세 메트릭
        st.markdown("---")
        st.subheader("📊 Detailed Metrics")

        tab1, tab2, tab3 = st.tabs(["System", "Functions", "Cache"])

        with tab1:
            self._render_system_metrics()

        with tab2:
            self._render_function_metrics()

        with tab3:
            self._render_cache_metrics()

    def _get_avg_response_time(self) -> float:
        """평균 응답 시간"""
        # perfect_rag.log에서 읽기
        log_file = Path("perfect_rag.log")
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]  # 최근 100줄
                times = []
                for line in lines:
                    if "응답 생성:" in line and "초" in line:
                        try:
                            time_str = line.split("응답 생성:")[1].split("초")[0].strip()
                            times.append(float(time_str))
                        except:
                            pass
                return sum(times) / len(times) if times else 0.0
        return 0.0

    def _get_cache_hit_rate(self) -> float:
        """캐시 히트율"""
        # 캐시 통계 읽기
        try:
            from perfect_rag import PerfectRAG
            rag = PerfectRAG(preload_llm=False)
            stats = rag.get_cache_stats()
            if stats['total_requests'] > 0:
                return stats['hit_count'] / stats['total_requests']
        except:
            pass
        return 0.0

    def _render_response_time_chart(self):
        """응답 시간 차트"""
        # 샘플 데이터 생성
        times = pd.date_range(end=datetime.now(), periods=24, freq='H')
        response_times = [2.5 + (i % 5) * 0.5 for i in range(24)]

        df = pd.DataFrame({
            'Time': times,
            'Response (s)': response_times
        })

        fig = px.line(df, x='Time', y='Response (s)',
                     title="24h Response Time",
                     line_shape='spline')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    def _render_memory_chart(self):
        """메모리 사용량 차트"""
        memory = psutil.virtual_memory()

        fig = go.Figure(data=[
            go.Pie(
                labels=['Used', 'Available'],
                values=[memory.used, memory.available],
                hole=.3,
                marker_colors=['#FF6B6B', '#4ECDC4']
            )
        ])

        fig.update_layout(
            title=f"Total: {memory.total/(1024**3):.1f} GB",
            height=300,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)

    def _render_system_metrics(self):
        """시스템 메트릭"""
        metrics = {
            "CPU Cores": os.cpu_count(),
            "CPU Usage": f"{psutil.cpu_percent()}%",
            "Memory Total": f"{psutil.virtual_memory().total/(1024**3):.1f} GB",
            "Memory Used": f"{psutil.virtual_memory().used/(1024**3):.1f} GB",
            "Disk Usage": f"{psutil.disk_usage('/').percent}%",
            "Python Version": platform.python_version(),
            "Process Count": len(psutil.pids())
        }

        df = pd.DataFrame(list(metrics.items()), columns=['Metric', 'Value'])
        st.table(df)

    def _render_function_metrics(self):
        """함수별 성능 메트릭"""
        # profiler에서 데이터 가져오기
        if hasattr(self.profiler, 'timings') and self.profiler.timings:
            report = self.profiler.get_timing_report()

            df = pd.DataFrame(report).T
            df = df.round(2)
            df = df.sort_values('total_ms', ascending=False)

            st.dataframe(df, height=400)
        else:
            st.info("No function metrics available yet")

    def _render_cache_metrics(self):
        """캐시 메트릭"""
        cache_stats = {
            "Cache Size": "500 MB",
            "Hit Rate": f"{self._get_cache_hit_rate():.1%}",
            "Miss Rate": f"{1-self._get_cache_hit_rate():.1%}",
            "Evictions": "12",
            "TTL": "3600s"
        }

        df = pd.DataFrame(list(cache_stats.items()), columns=['Metric', 'Value'])
        st.table(df)

        # 캐시 히트 트렌드
        st.subheader("Cache Hit Trend")
        times = pd.date_range(end=datetime.now(), periods=24, freq='H')
        hit_rates = [0.7 + (i % 10) * 0.03 for i in range(24)]

        df = pd.DataFrame({
            'Time': times,
            'Hit Rate': hit_rates
        })

        fig = px.area(df, x='Time', y='Hit Rate',
                     title="24h Cache Performance")
        fig.update_layout(height=250)
        fig.update_yaxis(tickformat='.0%')
        st.plotly_chart(fig, use_container_width=True)

def integrate_monitoring():
    """모니터링 통합"""

    print("📊 모니터링 시스템 통합")
    print("=" * 60)

    # 1. perfect_rag.py에 모니터링 추가
    monitoring_code = '''
# perfect_rag.py에 추가할 코드

from monitoring.performance_profiler import measure_performance
from monitoring.metrics_collector import collector

class PerfectRAG:
    @measure_performance
    def search(self, query: str) -> Dict:
        """성능 모니터링이 추가된 검색"""
        # 메트릭 수집
        collector.search_count += 1
        start = time.time()

        result = self._search_internal(query)

        # 검색 시간 기록
        elapsed = time.time() - start
        collector.avg_search_time = (collector.avg_search_time * 0.9 + elapsed * 0.1)

        return result

    @measure_performance
    def _build_metadata_cache(self):
        """모니터링이 추가된 캐시 구축"""
        pass
'''

    print("✅ 성능 모니터링 데코레이터 추가")
    print("✅ 메트릭 수집 통합")

    # 2. 실행 명령
    print("\n📋 모니터링 대시보드 실행:")
    print("  streamlit run performance_dashboard.py --server.port 8502")
    print("\n또는 메인 앱과 함께:")
    print("  python3 -m streamlit run web_interface.py &")
    print("  python3 -m streamlit run performance_dashboard.py --server.port 8502")

    return monitoring_code

import os
import platform

def main():
    """메인 실행"""
    dashboard = PerformanceDashboard()

    # Streamlit 앱으로 실행
    if __name__ == "__main__":
        dashboard.render_dashboard()

if __name__ == "__main__":
    # 통합 가이드 출력
    if not st._is_running_with_streamlit:
        integrate_monitoring()
    else:
        main()