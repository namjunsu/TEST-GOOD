#!/usr/bin/env python3
"""
프로덕션 레벨 성능 모니터링 시스템
Prometheus + Grafana 스타일 메트릭스
"""

import time
from pathlib import Path

def create_monitoring_system():
    """모니터링 시스템 생성"""

    print("="*60)
    print("📊 프로덕션 성능 모니터링 시스템 구축")
    print("="*60)

    # 모니터링 디렉토리 생성
    Path('monitoring').mkdir(exist_ok=True)

    # 1. 메트릭스 수집기
    metrics_collector = '''"""
Performance Metrics Collector
실시간 성능 데이터 수집
"""

import time
import psutil
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from collections import deque
import threading

class MetricsCollector:
    """성능 메트릭 수집기"""

    def __init__(self, max_history=1000):
        self.metrics_history = deque(maxlen=max_history)
        self.current_metrics = {}
        self.collection_thread = None
        self.running = False

        # 메트릭 카테고리
        self.categories = {
            'system': self._collect_system_metrics,
            'application': self._collect_app_metrics,
            'cache': self._collect_cache_metrics,
            'search': self._collect_search_metrics
        }

    def start_collection(self):
        """메트릭 수집 시작"""
        self.running = True
        self.collection_thread = threading.Thread(target=self._collection_loop)
        self.collection_thread.daemon = True
        self.collection_thread.start()
        print("📊 메트릭 수집 시작")

    def stop_collection(self):
        """메트릭 수집 중지"""
        self.running = False
        if self.collection_thread:
            self.collection_thread.join()
        print("🛑 메트릭 수집 중지")

    def _collection_loop(self):
        """수집 루프"""
        while self.running:
            metrics = self.collect_all_metrics()
            self.metrics_history.append(metrics)
            time.sleep(1)  # 1초마다 수집

    def collect_all_metrics(self) -> Dict:
        """모든 메트릭 수집"""
        timestamp = datetime.now().isoformat()
        metrics = {'timestamp': timestamp}

        for category, collector in self.categories.items():
            try:
                metrics[category] = collector()
            except Exception as e:
                metrics[category] = {'error': str(e)}

        self.current_metrics = metrics
        return metrics

    def _collect_system_metrics(self) -> Dict:
        """시스템 메트릭 수집"""
        process = psutil.Process()

        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_rss_mb': process.memory_info().rss / 1024**2,
            'memory_percent': process.memory_percent(),
            'disk_usage_percent': psutil.disk_usage('/').percent,
            'thread_count': process.num_threads(),
            'open_files': len(process.open_files())
        }

    def _collect_app_metrics(self) -> Dict:
        """애플리케이션 메트릭"""
        return {
            'uptime_seconds': time.time() - self.start_time if hasattr(self, 'start_time') else 0,
            'requests_total': getattr(self, 'request_count', 0),
            'errors_total': getattr(self, 'error_count', 0),
            'active_connections': getattr(self, 'active_connections', 0)
        }

    def _collect_cache_metrics(self) -> Dict:
        """캐시 메트릭"""
        return {
            'cache_hits': getattr(self, 'cache_hits', 0),
            'cache_misses': getattr(self, 'cache_misses', 0),
            'cache_size': getattr(self, 'cache_size', 0),
            'hit_rate': self._calculate_hit_rate()
        }

    def _collect_search_metrics(self) -> Dict:
        """검색 메트릭"""
        return {
            'searches_total': getattr(self, 'search_count', 0),
            'avg_search_time_ms': getattr(self, 'avg_search_time', 0),
            'pdf_processed': getattr(self, 'pdf_count', 0),
            'parallel_workers': getattr(self, 'worker_count', 8)
        }

    def _calculate_hit_rate(self) -> float:
        """캐시 히트율 계산"""
        hits = getattr(self, 'cache_hits', 0)
        misses = getattr(self, 'cache_misses', 0)
        total = hits + misses
        return hits / total if total > 0 else 0.0

    def get_current_metrics(self) -> Dict:
        """현재 메트릭 조회"""
        return self.current_metrics

    def get_metrics_history(self, minutes: int = 5) -> List[Dict]:
        """메트릭 히스토리 조회"""
        # 최근 N분 데이터
        entries_per_minute = 60  # 1초마다 수집하므로
        num_entries = minutes * entries_per_minute
        return list(self.metrics_history)[-num_entries:]

    def export_metrics(self, filepath: str = 'metrics.json'):
        """메트릭 내보내기"""
        with open(filepath, 'w') as f:
            json.dump({
                'current': self.current_metrics,
                'history': list(self.metrics_history)
            }, f, indent=2)
        print(f"📁 메트릭 저장: {filepath}")

# 전역 수집기 인스턴스
collector = MetricsCollector()
'''

    # 2. 성능 프로파일러
    profiler_code = '''"""
Performance Profiler
코드 성능 프로파일링
"""

import cProfile
import pstats
import io
from contextlib import contextmanager
import time
from functools import wraps
from typing import Callable, Any

class PerformanceProfiler:
    """성능 프로파일러"""

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.timings = {}

    @contextmanager
    def profile_block(self, name: str):
        """코드 블록 프로파일링"""
        start_time = time.perf_counter()

        self.profiler.enable()
        try:
            yield
        finally:
            self.profiler.disable()
            elapsed = time.perf_counter() - start_time

            # 타이밍 기록
            if name not in self.timings:
                self.timings[name] = []
            self.timings[name].append(elapsed)

            print(f"⏱️ {name}: {elapsed*1000:.2f}ms")

    def profile_function(self, func: Callable) -> Callable:
        """함수 프로파일링 데코레이터"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.profile_block(func.__name__):
                return func(*args, **kwargs)
        return wrapper

    def get_stats(self, top_n: int = 10) -> str:
        """프로파일링 통계"""
        s = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=s)
        stats.sort_stats('cumulative')
        stats.print_stats(top_n)
        return s.getvalue()

    def get_timing_report(self) -> Dict:
        """타이밍 리포트"""
        report = {}
        for name, times in self.timings.items():
            report[name] = {
                'count': len(times),
                'total_ms': sum(times) * 1000,
                'avg_ms': (sum(times) / len(times)) * 1000 if times else 0,
                'min_ms': min(times) * 1000 if times else 0,
                'max_ms': max(times) * 1000 if times else 0
            }
        return report

# 전역 프로파일러
profiler = PerformanceProfiler()

# 사용 예시 데코레이터
def measure_performance(func):
    """성능 측정 데코레이터"""
    return profiler.profile_function(func)
'''

    # 3. 대시보드
    dashboard_code = '''"""
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
'''

    # 4. 알림 시스템
    alerting_code = '''"""
Performance Alerting System
임계값 기반 알림
"""

from typing import Dict, List, Callable
import smtplib
from email.mime.text import MIMEText
import logging

logger = logging.getLogger(__name__)

class AlertManager:
    """알림 관리자"""

    def __init__(self):
        self.thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'error_rate': 0.1,
            'response_time_ms': 1000
        }
        self.alert_history = []
        self.alert_callbacks = []

    def check_thresholds(self, metrics: Dict):
        """임계값 확인"""
        alerts = []

        # CPU 체크
        cpu = metrics.get('system', {}).get('cpu_percent', 0)
        if cpu > self.thresholds['cpu_percent']:
            alerts.append({
                'level': 'WARNING',
                'metric': 'cpu_percent',
                'value': cpu,
                'threshold': self.thresholds['cpu_percent'],
                'message': f'CPU usage high: {cpu:.1f}%'
            })

        # 메모리 체크
        mem = metrics.get('system', {}).get('memory_percent', 0)
        if mem > self.thresholds['memory_percent']:
            alerts.append({
                'level': 'WARNING',
                'metric': 'memory_percent',
                'value': mem,
                'threshold': self.thresholds['memory_percent'],
                'message': f'Memory usage high: {mem:.1f}%'
            })

        # 알림 처리
        for alert in alerts:
            self._handle_alert(alert)

        return alerts

    def _handle_alert(self, alert: Dict):
        """알림 처리"""
        # 히스토리 기록
        self.alert_history.append({
            'timestamp': datetime.now(),
            **alert
        })

        # 콜백 실행
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        # 로그 출력
        logger.warning(f"ALERT: {alert['message']}")

    def add_callback(self, callback: Callable):
        """알림 콜백 추가"""
        self.alert_callbacks.append(callback)

    def get_alert_summary(self) -> Dict:
        """알림 요약"""
        if not self.alert_history:
            return {'total': 0}

        return {
            'total': len(self.alert_history),
            'by_level': self._count_by_level(),
            'by_metric': self._count_by_metric(),
            'recent': self.alert_history[-10:]
        }

    def _count_by_level(self) -> Dict:
        """레벨별 카운트"""
        counts = {}
        for alert in self.alert_history:
            level = alert['level']
            counts[level] = counts.get(level, 0) + 1
        return counts

    def _count_by_metric(self) -> Dict:
        """메트릭별 카운트"""
        counts = {}
        for alert in self.alert_history:
            metric = alert['metric']
            counts[metric] = counts.get(metric, 0) + 1
        return counts

# 전역 알림 관리자
alert_manager = AlertManager()
'''

    # 파일 저장
    files = {
        'monitoring/metrics_collector.py': metrics_collector,
        'monitoring/performance_profiler.py': profiler_code,
        'monitoring/dashboard.py': dashboard_code,
        'monitoring/alerting.py': alerting_code
    }

    for filepath, code in files.items():
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(code)
        print(f"  ✅ {Path(filepath).name} 생성 완료")

    # __init__.py 생성
    with open('monitoring/__init__.py', 'w') as f:
        f.write("""from .metrics_collector import MetricsCollector, collector
from .performance_profiler import PerformanceProfiler, profiler, measure_performance
from .alerting import AlertManager, alert_manager

__all__ = [
    'MetricsCollector', 'collector',
    'PerformanceProfiler', 'profiler', 'measure_performance',
    'AlertManager', 'alert_manager'
]
""")

    print("\n✅ 모니터링 시스템 구축 완료!")
    return True

def main():
    """메인 실행"""

    # 모니터링 시스템 생성
    create_monitoring_system()

    print("\n" + "="*60)
    print("🎯 프로덕션 모니터링 시스템 구축 완료!")
    print("="*60)

    print("\n📊 모니터링 기능:")
    print("  • 실시간 메트릭 수집 (CPU, Memory, Cache)")
    print("  • 성능 프로파일링 (함수별 실행 시간)")
    print("  • 대시보드 (Streamlit 기반)")
    print("  • 알림 시스템 (임계값 기반)")
    print("  • 히스토리 추적 (최대 1000개)")

    print("\n🚀 실행 방법:")
    print("  streamlit run monitoring/dashboard.py")

    print("\n🏆 엔터프라이즈급 모니터링 시스템 완성!")

if __name__ == "__main__":
    main()