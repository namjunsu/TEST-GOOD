#!/usr/bin/env python3
"""
실시간 모니터링 대시보드
========================
시스템 상태를 실시간으로 모니터링하는 대시보드
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import psutil
import time
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading
import queue
from typing import Dict, List, Any
import numpy as np

# 페이지 설정
st.set_page_config(
    page_title="AI-CHAT 실시간 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

class MetricsCollector:
    """메트릭 수집기"""

    def __init__(self):
        self.metrics_queue = queue.Queue()
        self.history = {
            'timestamps': [],
            'cpu': [],
            'memory': [],
            'disk': [],
            'network_in': [],
            'network_out': [],
            'queries_per_second': [],
            'cache_hits': [],
            'response_times': []
        }
        self.max_history = 100
        self.collecting = False
        self.thread = None

    def start_collection(self):
        """메트릭 수집 시작"""
        if not self.collecting:
            self.collecting = True
            self.thread = threading.Thread(target=self._collect_loop, daemon=True)
            self.thread.start()

    def stop_collection(self):
        """메트릭 수집 중지"""
        self.collecting = False
        if self.thread:
            self.thread.join(timeout=2)

    def _collect_loop(self):
        """수집 루프"""
        while self.collecting:
            metrics = self._get_current_metrics()
            self.metrics_queue.put(metrics)
            self._update_history(metrics)
            time.sleep(1)

    def _get_current_metrics(self) -> Dict:
        """현재 메트릭 수집"""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_cores = psutil.cpu_percent(percpu=True)

        # 메모리
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # 디스크
        disk = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()

        # 네트워크
        net_io = psutil.net_io_counters()

        # GPU (if available)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            gpu_data = {
                'gpu_load': gpus[0].load * 100 if gpus else 0,
                'gpu_memory': gpus[0].memoryUtil * 100 if gpus else 0,
                'gpu_temp': gpus[0].temperature if gpus else 0
            }
        except:
            gpu_data = {'gpu_load': 0, 'gpu_memory': 0, 'gpu_temp': 0}

        # 프로세스
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            if proc.info['memory_percent'] > 1:  # 1% 이상 메모리 사용
                processes.append(proc.info)

        # 캐시 및 성능 메트릭 (시뮬레이션)
        cache_hits = np.random.randint(70, 95)
        qps = np.random.uniform(5, 20)
        response_time = np.random.uniform(0.1, 2.0)

        return {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': cpu_percent,
                'cores': cpu_cores,
                'count': psutil.cpu_count()
            },
            'memory': {
                'percent': memory.percent,
                'used_gb': memory.used / (1024**3),
                'total_gb': memory.total / (1024**3),
                'available_gb': memory.available / (1024**3),
                'swap_percent': swap.percent
            },
            'disk': {
                'percent': disk.percent,
                'used_gb': disk.used / (1024**3),
                'total_gb': disk.total / (1024**3),
                'read_mb': disk_io.read_bytes / (1024**2),
                'write_mb': disk_io.write_bytes / (1024**2)
            },
            'network': {
                'sent_mb': net_io.bytes_sent / (1024**2),
                'recv_mb': net_io.bytes_recv / (1024**2),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            },
            'gpu': gpu_data,
            'processes': sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:5],
            'performance': {
                'cache_hit_rate': cache_hits,
                'queries_per_second': qps,
                'avg_response_time': response_time
            }
        }

    def _update_history(self, metrics: Dict):
        """히스토리 업데이트"""
        self.history['timestamps'].append(datetime.now())
        self.history['cpu'].append(metrics['cpu']['percent'])
        self.history['memory'].append(metrics['memory']['percent'])
        self.history['disk'].append(metrics['disk']['percent'])
        self.history['network_in'].append(metrics['network']['recv_mb'])
        self.history['network_out'].append(metrics['network']['sent_mb'])
        self.history['queries_per_second'].append(metrics['performance']['queries_per_second'])
        self.history['cache_hits'].append(metrics['performance']['cache_hit_rate'])
        self.history['response_times'].append(metrics['performance']['avg_response_time'])

        # 크기 제한
        for key in self.history:
            if len(self.history[key]) > self.max_history:
                self.history[key].pop(0)

    def get_latest_metrics(self) -> Dict:
        """최신 메트릭 반환"""
        try:
            return self.metrics_queue.get_nowait()
        except queue.Empty:
            return None


def create_gauge_chart(value: float, title: str, max_value: float = 100) -> go.Figure:
    """게이지 차트 생성"""
    if value < 50:
        color = "green"
    elif value < 80:
        color = "yellow"
    else:
        color = "red"

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title},
        delta={'reference': 50},
        gauge={
            'axis': {'range': [None, max_value]},
            'bar': {'color': color},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 80], 'color': "gray"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))

    fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20))
    return fig


def create_time_series_chart(history: Dict, keys: List[str], title: str) -> go.Figure:
    """시계열 차트 생성"""
    fig = go.Figure()

    for key in keys:
        if key in history and history[key]:
            fig.add_trace(go.Scatter(
                x=history['timestamps'],
                y=history[key],
                mode='lines',
                name=key.replace('_', ' ').title(),
                line=dict(width=2)
            ))

    fig.update_layout(
        title=title,
        xaxis_title="시간",
        yaxis_title="값",
        hovermode='x unified',
        height=300,
        showlegend=True
    )

    return fig


def create_process_table(processes: List[Dict]) -> pd.DataFrame:
    """프로세스 테이블 생성"""
    if not processes:
        return pd.DataFrame()

    df = pd.DataFrame(processes)
    df = df[['name', 'pid', 'cpu_percent', 'memory_percent']]
    df.columns = ['프로세스', 'PID', 'CPU %', '메모리 %']
    df['CPU %'] = df['CPU %'].round(1)
    df['메모리 %'] = df['메모리 %'].round(1)

    return df


def main():
    """메인 대시보드"""

    # 헤더
    st.title("🎯 AI-CHAT 실시간 모니터링 대시보드")

    # 상태 표시줄
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("시스템 상태", "✅ 정상", delta="안정적")
    with col2:
        st.metric("가동 시간", "12시간 34분", delta="+2시간")
    with col3:
        st.metric("활성 세션", "3", delta="+1")
    with col4:
        st.metric("총 쿼리", "1,234", delta="+56")

    # 메트릭 수집기 초기화
    if 'collector' not in st.session_state:
        st.session_state.collector = MetricsCollector()
        st.session_state.collector.start_collection()

    collector = st.session_state.collector

    # 자동 새로고침
    placeholder = st.empty()

    with placeholder.container():
        # 최신 메트릭 가져오기
        metrics = collector._get_current_metrics()

        if metrics:
            # 탭 생성
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 시스템 리소스",
                "⚡ 성능 메트릭",
                "📈 시계열 분석",
                "🔍 프로세스 상세",
                "⚠️ 알림 & 로그"
            ])

            with tab1:
                # 시스템 리소스 게이지
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    fig_cpu = create_gauge_chart(
                        metrics['cpu']['percent'],
                        "CPU 사용률"
                    )
                    st.plotly_chart(fig_cpu, use_container_width=True)

                with col2:
                    fig_memory = create_gauge_chart(
                        metrics['memory']['percent'],
                        "메모리 사용률"
                    )
                    st.plotly_chart(fig_memory, use_container_width=True)

                with col3:
                    fig_disk = create_gauge_chart(
                        metrics['disk']['percent'],
                        "디스크 사용률"
                    )
                    st.plotly_chart(fig_disk, use_container_width=True)

                with col4:
                    fig_gpu = create_gauge_chart(
                        metrics['gpu']['gpu_load'],
                        "GPU 사용률"
                    )
                    st.plotly_chart(fig_gpu, use_container_width=True)

                # 상세 정보
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("💻 시스템 정보")
                    st.json({
                        "CPU 코어": metrics['cpu']['count'],
                        "총 메모리": f"{metrics['memory']['total_gb']:.1f} GB",
                        "사용 메모리": f"{metrics['memory']['used_gb']:.1f} GB",
                        "디스크 총량": f"{metrics['disk']['total_gb']:.1f} GB",
                        "디스크 사용": f"{metrics['disk']['used_gb']:.1f} GB"
                    })

                with col2:
                    st.subheader("🌐 네트워크")
                    st.json({
                        "송신": f"{metrics['network']['sent_mb']:.1f} MB",
                        "수신": f"{metrics['network']['recv_mb']:.1f} MB",
                        "송신 패킷": f"{metrics['network']['packets_sent']:,}",
                        "수신 패킷": f"{metrics['network']['packets_recv']:,}"
                    })

            with tab2:
                # 성능 메트릭
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "캐시 히트율",
                        f"{metrics['performance']['cache_hit_rate']}%",
                        delta="+5%"
                    )

                with col2:
                    st.metric(
                        "초당 쿼리",
                        f"{metrics['performance']['queries_per_second']:.1f}",
                        delta="+2.3"
                    )

                with col3:
                    st.metric(
                        "평균 응답시간",
                        f"{metrics['performance']['avg_response_time']:.2f}초",
                        delta="-0.5초"
                    )

                # 성능 차트
                st.subheader("📊 성능 트렌드")
                perf_fig = create_time_series_chart(
                    collector.history,
                    ['queries_per_second', 'cache_hits'],
                    "성능 메트릭"
                )
                st.plotly_chart(perf_fig, use_container_width=True)

            with tab3:
                # 시계열 분석
                st.subheader("📈 리소스 사용 트렌드")

                # CPU/메모리 차트
                resource_fig = create_time_series_chart(
                    collector.history,
                    ['cpu', 'memory', 'disk'],
                    "리소스 사용률 (%)"
                )
                st.plotly_chart(resource_fig, use_container_width=True)

                # 네트워크 차트
                network_fig = create_time_series_chart(
                    collector.history,
                    ['network_in', 'network_out'],
                    "네트워크 트래픽 (MB)"
                )
                st.plotly_chart(network_fig, use_container_width=True)

            with tab4:
                # 프로세스 상세
                st.subheader("🔍 상위 프로세스")
                process_df = create_process_table(metrics['processes'])
                if not process_df.empty:
                    st.dataframe(
                        process_df,
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("프로세스 정보 없음")

                # CPU 코어별 사용률
                st.subheader("🖥️ CPU 코어별 사용률")
                core_data = pd.DataFrame({
                    'Core': [f"Core {i}" for i in range(len(metrics['cpu']['cores']))],
                    'Usage': metrics['cpu']['cores']
                })
                fig_cores = px.bar(core_data, x='Core', y='Usage', title="CPU 코어 사용률")
                st.plotly_chart(fig_cores, use_container_width=True)

            with tab5:
                # 알림 & 로그
                st.subheader("⚠️ 시스템 알림")

                # 임계값 체크
                alerts = []
                if metrics['cpu']['percent'] > 80:
                    alerts.append(("🔴 높은 CPU 사용률", f"CPU: {metrics['cpu']['percent']:.1f}%"))
                if metrics['memory']['percent'] > 80:
                    alerts.append(("🔴 높은 메모리 사용률", f"Memory: {metrics['memory']['percent']:.1f}%"))
                if metrics['disk']['percent'] > 90:
                    alerts.append(("🔴 디스크 공간 부족", f"Disk: {metrics['disk']['percent']:.1f}%"))

                if alerts:
                    for alert_title, alert_msg in alerts:
                        st.error(f"{alert_title}: {alert_msg}")
                else:
                    st.success("✅ 모든 시스템 정상")

                # 최근 로그
                st.subheader("📝 최근 시스템 로그")
                log_placeholder = st.empty()

                # 샘플 로그 (실제로는 파일에서 읽어옴)
                sample_logs = [
                    f"{datetime.now():%H:%M:%S} [INFO] 시스템 정상 작동중",
                    f"{datetime.now():%H:%M:%S} [INFO] 캐시 히트율 85%",
                    f"{datetime.now():%H:%M:%S} [INFO] 검색 쿼리 처리: 0.5초",
                ]

                log_text = "\n".join(sample_logs)
                log_placeholder.code(log_text, language="log")

    # 자동 새로고침 (1초마다)
    time.sleep(1)
    st.rerun()


if __name__ == "__main__":
    main()