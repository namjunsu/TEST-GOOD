"""
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
