#!/usr/bin/env python3
"""
실시간 시스템 모니터링
======================

세계 최고 개발자가 만든 완벽한 모니터링 시스템
GPU, CPU, 메모리, 응답시간을 실시간으로 모니터링합니다.
"""

import time
import psutil
import GPUtil
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import threading
import queue
import logging

logger = logging.getLogger(__name__)


class SystemMonitor:
    """실시간 시스템 모니터링 클래스"""

    def __init__(self):
        self.metrics_queue = queue.Queue()
        self.metrics_history = []
        self.max_history = 1000  # 최대 1000개 메트릭 보관
        self.monitoring = False
        self.thread = None

    def get_system_metrics(self):
        """현재 시스템 메트릭 수집"""
        metrics = {
            'timestamp': datetime.now(),
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_gb': psutil.virtual_memory().used / (1024**3),
            'disk_percent': psutil.disk_usage('/').percent,
        }

        # GPU 메트릭 (사용 가능한 경우)
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                metrics['gpu_percent'] = gpu.load * 100
                metrics['gpu_memory_mb'] = gpu.memoryUsed
                metrics['gpu_temp'] = gpu.temperature
            else:
                metrics['gpu_percent'] = 0
                metrics['gpu_memory_mb'] = 0
                metrics['gpu_temp'] = 0
        except:
            metrics['gpu_percent'] = 0
            metrics['gpu_memory_mb'] = 0
            metrics['gpu_temp'] = 0

        # 네트워크 메트릭
        net_io = psutil.net_io_counters()
        metrics['net_sent_mb'] = net_io.bytes_sent / (1024**2)
        metrics['net_recv_mb'] = net_io.bytes_recv / (1024**2)

        return metrics

    def monitor_loop(self):
        """백그라운드 모니터링 루프"""
        while self.monitoring:
            try:
                metrics = self.get_system_metrics()
                self.metrics_queue.put(metrics)
                self.metrics_history.append(metrics)

                # 히스토리 크기 제한
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history.pop(0)

                time.sleep(1)  # 1초마다 업데이트
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(5)

    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
            logger.info("System monitoring started")

    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("System monitoring stopped")

    def get_latest_metrics(self):
        """최신 메트릭 가져오기"""
        try:
            return self.metrics_queue.get_nowait()
        except queue.Empty:
            return None

    def get_metrics_df(self, minutes=5):
        """메트릭 히스토리를 DataFrame으로 반환"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.metrics_history if m['timestamp'] > cutoff]

        if recent_metrics:
            return pd.DataFrame(recent_metrics)
        return pd.DataFrame()


def create_dashboard():
    """Streamlit 대시보드 생성"""

    st.set_page_config(
        page_title="AI-CHAT System Monitor",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.title("🎯 AI-CHAT System Monitor")
    st.caption("세계 최고 개발자가 만든 실시간 모니터링 시스템")

    # 세션 상태 초기화
    if 'monitor' not in st.session_state:
        st.session_state.monitor = SystemMonitor()
        st.session_state.monitor.start_monitoring()

    monitor = st.session_state.monitor

    # 자동 새로고침 설정
    auto_refresh = st.checkbox("자동 새로고침 (1초)", value=True)
    if auto_refresh:
        time.sleep(1)
        st.rerun()

    # 메트릭 가져오기
    latest = monitor.get_latest_metrics()
    df = monitor.get_metrics_df(minutes=5)

    if latest:
        # 실시간 메트릭 표시
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "🖥️ CPU",
                f"{latest['cpu_percent']:.1f}%",
                delta=f"{latest['cpu_percent'] - 50:.1f}%" if latest['cpu_percent'] > 50 else None
            )

        with col2:
            st.metric(
                "💾 Memory",
                f"{latest['memory_gb']:.1f}GB ({latest['memory_percent']:.1f}%)",
                delta=f"{latest['memory_percent'] - 80:.1f}%" if latest['memory_percent'] > 80 else None
            )

        with col3:
            st.metric(
                "🎮 GPU",
                f"{latest['gpu_percent']:.1f}%",
                delta=f"🌡️ {latest['gpu_temp']}°C" if latest['gpu_temp'] > 0 else "N/A"
            )

        with col4:
            st.metric(
                "💿 Disk",
                f"{latest['disk_percent']:.1f}%",
                delta="Warning!" if latest['disk_percent'] > 90 else None
            )

    # 그래프 표시
    if not df.empty:
        # CPU & Memory 차트
        col1, col2 = st.columns(2)

        with col1:
            fig_cpu = go.Figure()
            fig_cpu.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['cpu_percent'],
                mode='lines',
                name='CPU %',
                line=dict(color='#ff4b4b', width=2)
            ))
            fig_cpu.update_layout(
                title="CPU Usage",
                xaxis_title="Time",
                yaxis_title="Percent (%)",
                height=300,
                yaxis=dict(range=[0, 100])
            )
            st.plotly_chart(fig_cpu, use_container_width=True)

        with col2:
            fig_mem = go.Figure()
            fig_mem.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['memory_percent'],
                mode='lines',
                name='Memory %',
                line=dict(color='#00cc88', width=2)
            ))
            fig_mem.update_layout(
                title="Memory Usage",
                xaxis_title="Time",
                yaxis_title="Percent (%)",
                height=300,
                yaxis=dict(range=[0, 100])
            )
            st.plotly_chart(fig_mem, use_container_width=True)

        # GPU 차트 (사용 가능한 경우)
        if 'gpu_percent' in df.columns and df['gpu_percent'].max() > 0:
            fig_gpu = go.Figure()
            fig_gpu.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['gpu_percent'],
                mode='lines',
                name='GPU %',
                line=dict(color='#ffa500', width=2)
            ))
            fig_gpu.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['gpu_temp'],
                mode='lines',
                name='GPU Temp °C',
                line=dict(color='#ff69b4', width=2),
                yaxis='y2'
            ))
            fig_gpu.update_layout(
                title="GPU Usage & Temperature",
                xaxis_title="Time",
                yaxis_title="Usage (%)",
                yaxis2=dict(
                    title="Temperature (°C)",
                    overlaying='y',
                    side='right'
                ),
                height=300
            )
            st.plotly_chart(fig_gpu, use_container_width=True)

    # 시스템 정보
    with st.expander("📊 상세 시스템 정보"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("하드웨어")
            st.write(f"CPU 코어: {psutil.cpu_count()}")
            st.write(f"총 메모리: {psutil.virtual_memory().total / (1024**3):.1f}GB")

            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    st.write(f"GPU: {gpu.name}")
                    st.write(f"GPU 메모리: {gpu.memoryTotal}MB")
            except:
                st.write("GPU: N/A")

        with col2:
            st.subheader("프로세스")
            # 상위 5개 CPU 사용 프로세스
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                processes.append(proc.info)

            df_proc = pd.DataFrame(processes)
            df_proc = df_proc.sort_values('cpu_percent', ascending=False).head(5)
            st.dataframe(df_proc, hide_index=True)

    # 알림
    if latest:
        if latest['cpu_percent'] > 90:
            st.error("⚠️ CPU 사용률이 매우 높습니다!")
        if latest['memory_percent'] > 90:
            st.error("⚠️ 메모리 사용률이 매우 높습니다!")
        if latest['gpu_temp'] > 85:
            st.warning("🌡️ GPU 온도가 높습니다!")


if __name__ == "__main__":
    create_dashboard()