#!/usr/bin/env python3
"""
고급 성능 최적화 시스템

주요 기능:
- 실시간 성능 모니터링 및 분석
- 자동 병목 현상 감지
- 동적 리소스 최적화
- 쿼리 최적화 및 캐싱
- 병렬 처리 관리
- 시스템 프로파일링
- 성능 보고서 생성
"""

import os
import sys
import time
import json
import threading
import psutil
import gc
import hashlib
import logging
import pickle
import sqlite3
import weakref
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import OrderedDict, deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta
import numpy as np
from functools import wraps, lru_cache
import traceback
import warnings

# GPU 지원 체크
try:
    import pynvml
    pynvml.nvmlInit()
    GPU_AVAILABLE = True
except:
    GPU_AVAILABLE = False
    warnings.warn("NVIDIA GPU monitoring not available")

@dataclass
class PerformanceMetrics:
    """성능 메트릭 데이터클래스"""
    timestamp: float
    operation: str
    duration: float
    cpu_percent: float
    memory_percent: float
    gpu_percent: Optional[float] = None
    gpu_memory: Optional[float] = None
    io_read: float = 0
    io_write: float = 0
    network_sent: float = 0
    network_recv: float = 0
    cache_hits: int = 0
    cache_misses: int = 0
    error_count: int = 0
    throughput: float = 0
    details: Dict[str, Any] = field(default_factory=dict)

class PerformanceMonitor:
    """실시간 성능 모니터링"""

    def __init__(self, sampling_interval: float = 1.0, history_size: int = 1000):
        self.sampling_interval = sampling_interval
        self.history_size = history_size

        # 메트릭 히스토리
        self.metrics_history = deque(maxlen=history_size)
        self.operation_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'errors': 0
        })

        # 모니터링 스레드
        self.monitoring = False
        self.monitor_thread = None
        self.lock = threading.RLock()

        # 시스템 정보
        self.cpu_count = psutil.cpu_count()
        self.total_memory = psutil.virtual_memory().total

        # GPU 정보
        if GPU_AVAILABLE:
            self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.gpu_name = pynvml.nvmlDeviceGetName(self.gpu_handle).decode('utf-8')
        else:
            self.gpu_handle = None
            self.gpu_name = None

        # 네트워크 초기값
        self.last_net_io = psutil.net_io_counters()
        self.last_disk_io = psutil.disk_io_counters()

        self.logger = logging.getLogger(__name__)

    def start(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("Performance monitoring started")

    def stop(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.logger.info("Performance monitoring stopped")

    def _monitor_loop(self):
        """모니터링 루프"""
        while self.monitoring:
            try:
                metrics = self._collect_metrics()
                with self.lock:
                    self.metrics_history.append(metrics)
                time.sleep(self.sampling_interval)
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")

    def _collect_metrics(self) -> PerformanceMetrics:
        """시스템 메트릭 수집"""
        # CPU & Memory
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()

        # GPU (if available)
        gpu_percent = None
        gpu_memory = None
        if self.gpu_handle:
            try:
                gpu_util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
                gpu_percent = gpu_util.gpu
                gpu_memory = gpu_util.memory
            except:
                pass

        # I/O
        current_net = psutil.net_io_counters()
        current_disk = psutil.disk_io_counters()

        net_sent = current_net.bytes_sent - self.last_net_io.bytes_sent
        net_recv = current_net.bytes_recv - self.last_net_io.bytes_recv
        disk_read = current_disk.read_bytes - self.last_disk_io.read_bytes
        disk_write = current_disk.write_bytes - self.last_disk_io.write_bytes

        self.last_net_io = current_net
        self.last_disk_io = current_disk

        return PerformanceMetrics(
            timestamp=time.time(),
            operation='system',
            duration=0,
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            gpu_percent=gpu_percent,
            gpu_memory=gpu_memory,
            io_read=disk_read,
            io_write=disk_write,
            network_sent=net_sent,
            network_recv=net_recv
        )

    @contextmanager
    def measure(self, operation: str):
        """작업 성능 측정 컨텍스트 매니저"""
        start_time = time.time()
        start_cpu = psutil.cpu_percent(interval=None)
        start_mem = psutil.virtual_memory().percent

        try:
            yield
            error_occurred = False
        except Exception as e:
            error_occurred = True
            raise
        finally:
            duration = time.time() - start_time

            metrics = PerformanceMetrics(
                timestamp=start_time,
                operation=operation,
                duration=duration,
                cpu_percent=psutil.cpu_percent(interval=None) - start_cpu,
                memory_percent=psutil.virtual_memory().percent - start_mem,
                error_count=1 if error_occurred else 0
            )

            with self.lock:
                self.metrics_history.append(metrics)
                stats = self.operation_stats[operation]
                stats['count'] += 1
                stats['total_time'] += duration
                stats['min_time'] = min(stats['min_time'], duration)
                stats['max_time'] = max(stats['max_time'], duration)
                if error_occurred:
                    stats['errors'] += 1

    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """통계 반환"""
        with self.lock:
            if operation:
                stats = self.operation_stats.get(operation, {})
                if stats and stats['count'] > 0:
                    stats['avg_time'] = stats['total_time'] / stats['count']
                return stats

            # 전체 통계
            total_stats = {
                'operations': dict(self.operation_stats),
                'system': self._analyze_system_metrics(),
                'bottlenecks': self._detect_bottlenecks()
            }

            return total_stats

    def _analyze_system_metrics(self) -> Dict[str, Any]:
        """시스템 메트릭 분석"""
        if not self.metrics_history:
            return {}

        recent_metrics = list(self.metrics_history)[-100:]  # 최근 100개

        cpu_values = [m.cpu_percent for m in recent_metrics if m.operation == 'system']
        mem_values = [m.memory_percent for m in recent_metrics if m.operation == 'system']

        analysis = {
            'cpu': {
                'current': cpu_values[-1] if cpu_values else 0,
                'avg': np.mean(cpu_values) if cpu_values else 0,
                'max': np.max(cpu_values) if cpu_values else 0,
                'std': np.std(cpu_values) if cpu_values else 0
            },
            'memory': {
                'current': mem_values[-1] if mem_values else 0,
                'avg': np.mean(mem_values) if mem_values else 0,
                'max': np.max(mem_values) if mem_values else 0,
                'used_gb': psutil.virtual_memory().used / (1024**3)
            }
        }

        # GPU 분석
        if GPU_AVAILABLE and self.gpu_handle:
            gpu_values = [m.gpu_percent for m in recent_metrics if m.gpu_percent is not None]
            if gpu_values:
                analysis['gpu'] = {
                    'name': self.gpu_name,
                    'current': gpu_values[-1],
                    'avg': np.mean(gpu_values),
                    'max': np.max(gpu_values)
                }

        return analysis

    def _detect_bottlenecks(self) -> List[Dict[str, Any]]:
        """병목 현상 감지"""
        bottlenecks = []

        system_stats = self._analyze_system_metrics()

        # CPU 병목
        if system_stats.get('cpu', {}).get('avg', 0) > 80:
            bottlenecks.append({
                'type': 'CPU',
                'severity': 'high' if system_stats['cpu']['avg'] > 90 else 'medium',
                'message': f"High CPU usage: {system_stats['cpu']['avg']:.1f}%",
                'recommendation': 'Consider parallel processing or optimization'
            })

        # 메모리 병목
        if system_stats.get('memory', {}).get('avg', 0) > 80:
            bottlenecks.append({
                'type': 'Memory',
                'severity': 'high' if system_stats['memory']['avg'] > 90 else 'medium',
                'message': f"High memory usage: {system_stats['memory']['avg']:.1f}%",
                'recommendation': 'Consider memory optimization or caching'
            })

        # 느린 작업 감지
        for op, stats in self.operation_stats.items():
            if stats['count'] > 0 and stats['max_time'] > 10:
                bottlenecks.append({
                    'type': 'Slow Operation',
                    'operation': op,
                    'severity': 'high' if stats['max_time'] > 30 else 'medium',
                    'message': f"Slow operation '{op}': max {stats['max_time']:.1f}s",
                    'recommendation': 'Optimize algorithm or use caching'
                })

        return bottlenecks

class QueryOptimizer:
    """쿼리 최적화 및 캐싱"""

    def __init__(self, cache_size: int = 1000, ttl: int = 3600):
        self.cache_size = cache_size
        self.ttl = ttl

        # 다층 캐시
        self.memory_cache = OrderedDict()  # 메모리 캐시
        self.disk_cache_path = Path("cache/query_cache.db")
        self.disk_cache_path.parent.mkdir(parents=True, exist_ok=True)

        # 쿼리 통계
        self.query_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'cache_hits': 0,
            'patterns': []
        })

        # 쿼리 패턴 학습
        self.common_patterns = []
        self.pattern_lock = threading.RLock()

        self._init_disk_cache()
        self.logger = logging.getLogger(__name__)

    def _init_disk_cache(self):
        """디스크 캐시 초기화"""
        conn = sqlite3.connect(str(self.disk_cache_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB,
                timestamp REAL,
                hits INTEGER DEFAULT 0
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)')
        conn.commit()
        conn.close()

    def optimize_query(self, query: str) -> str:
        """쿼리 최적화"""
        # 1. 정규화
        optimized = self._normalize_query(query)

        # 2. 패턴 매칭
        for pattern in self.common_patterns:
            if pattern['regex'].search(optimized):
                optimized = pattern['optimizer'](optimized)

        # 3. 통계 수집
        self._collect_query_stats(query, optimized)

        return optimized

    def _normalize_query(self, query: str) -> str:
        """쿼리 정규화"""
        # 공백 정리
        normalized = ' '.join(query.split())

        # 대소문자 정규화 (한글 제외)
        words = []
        for word in normalized.split():
            if not any('\uac00' <= char <= '\ud7a3' for char in word):
                word = word.lower()
            words.append(word)

        return ' '.join(words)

    def cache_get(self, key: str) -> Optional[Any]:
        """캐시 조회"""
        # 1. 메모리 캐시 확인
        if key in self.memory_cache:
            value, timestamp = self.memory_cache[key]
            if time.time() - timestamp < self.ttl:
                self.memory_cache.move_to_end(key)
                return value
            else:
                del self.memory_cache[key]

        # 2. 디스크 캐시 확인
        conn = sqlite3.connect(str(self.disk_cache_path))
        cursor = conn.execute(
            'SELECT value, timestamp FROM cache WHERE key = ?',
            (key,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            value_blob, timestamp = row
            if time.time() - timestamp < self.ttl:
                value = pickle.loads(value_blob)
                # 메모리로 승격
                self._promote_to_memory(key, value, timestamp)
                return value

        return None

    def cache_set(self, key: str, value: Any):
        """캐시 저장"""
        timestamp = time.time()

        # 1. 메모리 캐시 저장
        with self.pattern_lock:
            self.memory_cache[key] = (value, timestamp)
            if len(self.memory_cache) > self.cache_size:
                # LRU 제거
                oldest_key, (oldest_val, oldest_time) = self.memory_cache.popitem(last=False)
                # 디스크로 이동
                self._demote_to_disk(oldest_key, oldest_val, oldest_time)

        # 2. 비동기 디스크 저장 (백그라운드)
        threading.Thread(
            target=self._save_to_disk,
            args=(key, value, timestamp),
            daemon=True
        ).start()

    def _promote_to_memory(self, key: str, value: Any, timestamp: float):
        """디스크에서 메모리로 승격"""
        with self.pattern_lock:
            self.memory_cache[key] = (value, timestamp)
            if len(self.memory_cache) > self.cache_size:
                self.memory_cache.popitem(last=False)

    def _demote_to_disk(self, key: str, value: Any, timestamp: float):
        """메모리에서 디스크로 강등"""
        self._save_to_disk(key, value, timestamp)

    def _save_to_disk(self, key: str, value: Any, timestamp: float):
        """디스크에 저장"""
        try:
            value_blob = pickle.dumps(value)
            conn = sqlite3.connect(str(self.disk_cache_path))
            conn.execute(
                'INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)',
                (key, value_blob, timestamp)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Failed to save to disk cache: {e}")

    def _collect_query_stats(self, original: str, optimized: str):
        """쿼리 통계 수집"""
        # 패턴 추출
        words = optimized.split()
        if len(words) >= 2:
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
            for bigram in bigrams:
                self.query_stats[bigram]['count'] += 1

    def learn_patterns(self):
        """자주 사용되는 패턴 학습"""
        # 빈도 높은 패턴 식별
        frequent_patterns = []
        for pattern, stats in self.query_stats.items():
            if stats['count'] > 10:
                frequent_patterns.append((pattern, stats['count']))

        # 정렬 및 저장
        frequent_patterns.sort(key=lambda x: x[1], reverse=True)
        self.common_patterns = [p[0] for p in frequent_patterns[:50]]

        self.logger.info(f"Learned {len(self.common_patterns)} query patterns")

    def clear_cache(self, older_than: Optional[int] = None):
        """캐시 정리"""
        # 메모리 캐시 정리
        self.memory_cache.clear()

        # 디스크 캐시 정리
        conn = sqlite3.connect(str(self.disk_cache_path))
        if older_than:
            threshold = time.time() - older_than
            conn.execute('DELETE FROM cache WHERE timestamp < ?', (threshold,))
        else:
            conn.execute('DELETE FROM cache')
        conn.commit()
        conn.close()

        self.logger.info("Cache cleared")

class ParallelProcessor:
    """병렬 처리 관리자"""

    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers or min(8, (psutil.cpu_count() or 1) + 4)
        self.thread_executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.process_executor = ProcessPoolExecutor(max_workers=self.max_workers // 2)

        # 작업 큐 및 통계
        self.active_tasks = weakref.WeakSet()
        self.task_stats = defaultdict(lambda: {
            'submitted': 0,
            'completed': 0,
            'failed': 0,
            'total_time': 0
        })

        self.logger = logging.getLogger(__name__)

    def map_threaded(self, func: Callable, items: List,
                     chunk_size: int = 1) -> List[Any]:
        """스레드 기반 병렬 처리"""
        results = []
        futures = []

        # 청크 단위로 분할
        chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

        start_time = time.time()

        for chunk in chunks:
            future = self.thread_executor.submit(self._process_chunk, func, chunk)
            futures.append(future)
            self.active_tasks.add(future)

        # 결과 수집
        for future in as_completed(futures):
            try:
                chunk_results = future.result()
                results.extend(chunk_results)
                self.task_stats['threaded']['completed'] += len(chunk_results)
            except Exception as e:
                self.logger.error(f"Thread processing failed: {e}")
                self.task_stats['threaded']['failed'] += 1

        self.task_stats['threaded']['total_time'] += time.time() - start_time

        return results

    def map_multiprocess(self, func: Callable, items: List,
                        chunk_size: int = 1) -> List[Any]:
        """프로세스 기반 병렬 처리 (CPU 집약적 작업용)"""
        results = []
        futures = []

        chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

        start_time = time.time()

        for chunk in chunks:
            future = self.process_executor.submit(self._process_chunk, func, chunk)
            futures.append(future)

        for future in as_completed(futures):
            try:
                chunk_results = future.result()
                results.extend(chunk_results)
                self.task_stats['multiprocess']['completed'] += len(chunk_results)
            except Exception as e:
                self.logger.error(f"Process execution failed: {e}")
                self.task_stats['multiprocess']['failed'] += 1

        self.task_stats['multiprocess']['total_time'] += time.time() - start_time

        return results

    def _process_chunk(self, func: Callable, chunk: List) -> List[Any]:
        """청크 처리"""
        results = []
        for item in chunk:
            try:
                result = func(item)
                results.append(result)
            except Exception as e:
                self.logger.warning(f"Item processing failed: {e}")
                results.append(None)
        return results

    def get_optimal_chunk_size(self, total_items: int,
                              estimated_time_per_item: float) -> int:
        """최적 청크 크기 계산"""
        # 목표: 각 워커가 최소 0.1초, 최대 10초 작업
        min_chunk_time = 0.1
        max_chunk_time = 10.0

        min_chunk_size = max(1, int(min_chunk_time / estimated_time_per_item))
        max_chunk_size = max(1, int(max_chunk_time / estimated_time_per_item))

        # 워커 수에 맞춰 조정
        ideal_chunks = self.max_workers * 4  # 워커당 4개 청크
        ideal_chunk_size = max(1, total_items // ideal_chunks)

        # 범위 내로 제한
        optimal_size = min(max_chunk_size, max(min_chunk_size, ideal_chunk_size))

        return optimal_size

    def shutdown(self, wait: bool = True):
        """리소스 정리"""
        self.thread_executor.shutdown(wait=wait)
        self.process_executor.shutdown(wait=wait)
        self.logger.info("Parallel processor shutdown")

class PerformanceOptimizer:
    """통합 성능 최적화 시스템"""

    def __init__(self, enable_monitoring: bool = True,
                 enable_caching: bool = True,
                 enable_parallel: bool = True):

        # 컴포넌트 초기화
        self.monitor = PerformanceMonitor() if enable_monitoring else None
        self.query_optimizer = QueryOptimizer() if enable_caching else None
        self.parallel_processor = ParallelProcessor() if enable_parallel else None

        # 최적화 규칙
        self.optimization_rules = []
        self._load_optimization_rules()

        # 통계
        self.optimization_stats = {
            'optimizations_applied': 0,
            'performance_gains': [],
            'errors_prevented': 0
        }

        self.logger = logging.getLogger(__name__)

        # 모니터링 시작
        if self.monitor:
            self.monitor.start()

    def _load_optimization_rules(self):
        """최적화 규칙 로드"""
        self.optimization_rules = [
            {
                'name': 'cache_frequent_queries',
                'condition': lambda stats: stats.get('cache_hits', 0) < stats.get('total_queries', 1) * 0.3,
                'action': self._increase_cache_size,
                'priority': 1
            },
            {
                'name': 'parallelize_slow_operations',
                'condition': lambda stats: any(op['max_time'] > 5 for op in stats.get('operations', {}).values()),
                'action': self._enable_parallelization,
                'priority': 2
            },
            {
                'name': 'memory_optimization',
                'condition': lambda stats: stats.get('system', {}).get('memory', {}).get('avg', 0) > 70,
                'action': self._optimize_memory,
                'priority': 3
            }
        ]

    @contextmanager
    def optimize(self, operation: str):
        """최적화 컨텍스트 매니저"""
        start_time = time.time()

        # 사전 최적화
        self._apply_pre_optimizations(operation)

        try:
            if self.monitor:
                with self.monitor.measure(operation):
                    yield self
            else:
                yield self
        finally:
            # 사후 최적화
            duration = time.time() - start_time
            self._apply_post_optimizations(operation, duration)

    def _apply_pre_optimizations(self, operation: str):
        """사전 최적화 적용"""
        # 캐시 확인
        if self.query_optimizer and 'query' in operation.lower():
            # 캐시 프리페치 등
            pass

        # 메모리 정리
        if psutil.virtual_memory().percent > 80:
            gc.collect()

    def _apply_post_optimizations(self, operation: str, duration: float):
        """사후 최적화 적용"""
        if duration > 10:  # 10초 이상 걸린 작업
            self.logger.warning(f"Slow operation detected: {operation} took {duration:.1f}s")

            # 자동 최적화 규칙 적용
            if self.monitor:
                stats = self.monitor.get_stats()
                for rule in self.optimization_rules:
                    if rule['condition'](stats):
                        rule['action']()
                        self.optimization_stats['optimizations_applied'] += 1

    def _increase_cache_size(self):
        """캐시 크기 증가"""
        if self.query_optimizer:
            self.query_optimizer.cache_size = min(10000, self.query_optimizer.cache_size * 2)
            self.logger.info(f"Increased cache size to {self.query_optimizer.cache_size}")

    def _enable_parallelization(self):
        """병렬 처리 활성화/증가"""
        if self.parallel_processor:
            self.parallel_processor.max_workers = min(16, self.parallel_processor.max_workers + 2)
            self.logger.info(f"Increased parallel workers to {self.parallel_processor.max_workers}")

    def _optimize_memory(self):
        """메모리 최적화"""
        # 강제 가비지 컬렉션
        gc.collect()

        # 캐시 정리
        if self.query_optimizer:
            self.query_optimizer.clear_cache(older_than=1800)  # 30분 이상 오래된 캐시

        self.logger.info("Memory optimization applied")

    def get_optimization_report(self) -> Dict[str, Any]:
        """최적화 보고서 생성"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'optimization_stats': self.optimization_stats,
            'system_status': {},
            'recommendations': []
        }

        if self.monitor:
            stats = self.monitor.get_stats()
            report['system_status'] = stats.get('system', {})
            report['bottlenecks'] = stats.get('bottlenecks', [])
            report['operation_stats'] = stats.get('operations', {})

        if self.query_optimizer:
            report['cache_stats'] = {
                'memory_cache_size': len(self.query_optimizer.memory_cache),
                'common_patterns': len(self.query_optimizer.common_patterns)
            }

        if self.parallel_processor:
            report['parallel_stats'] = dict(self.parallel_processor.task_stats)

        # 권장사항 생성
        report['recommendations'] = self._generate_recommendations(report)

        return report

    def _generate_recommendations(self, report: Dict) -> List[str]:
        """최적화 권장사항 생성"""
        recommendations = []

        # CPU 최적화
        cpu_avg = report.get('system_status', {}).get('cpu', {}).get('avg', 0)
        if cpu_avg > 70:
            recommendations.append(f"High CPU usage ({cpu_avg:.1f}%). Consider optimizing algorithms or adding parallel processing.")

        # 메모리 최적화
        mem_avg = report.get('system_status', {}).get('memory', {}).get('avg', 0)
        if mem_avg > 70:
            recommendations.append(f"High memory usage ({mem_avg:.1f}%). Consider implementing memory-efficient data structures or caching.")

        # 병목 현상
        bottlenecks = report.get('bottlenecks', [])
        for bottleneck in bottlenecks[:3]:  # 상위 3개만
            recommendations.append(f"{bottleneck['type']}: {bottleneck['recommendation']}")

        return recommendations

    def shutdown(self):
        """리소스 정리"""
        if self.monitor:
            self.monitor.stop()

        if self.parallel_processor:
            self.parallel_processor.shutdown()

        self.logger.info("Performance optimizer shutdown")

# 편의 함수들
def profile_performance(func):
    """성능 프로파일링 데코레이터"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        optimizer = PerformanceOptimizer()

        with optimizer.optimize(func.__name__):
            result = func(*args, **kwargs)

        # 성능 리포트
        report = optimizer.get_optimization_report()
        if report['bottlenecks']:
            logging.warning(f"Performance issues in {func.__name__}: {report['bottlenecks']}")

        optimizer.shutdown()
        return result

    return wrapper

def optimize_batch_processing(items: List, processor: Callable,
                            use_parallel: bool = True) -> List:
    """배치 처리 최적화"""
    optimizer = PerformanceOptimizer()

    if use_parallel and optimizer.parallel_processor and len(items) > 10:
        # 병렬 처리
        chunk_size = optimizer.parallel_processor.get_optimal_chunk_size(
            len(items), 0.1  # 예상 처리 시간
        )
        results = optimizer.parallel_processor.map_threaded(
            processor, items, chunk_size
        )
    else:
        # 순차 처리
        results = [processor(item) for item in items]

    optimizer.shutdown()
    return results

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Performance Optimizer")
    parser.add_argument('--monitor', action='store_true', help='Start monitoring')
    parser.add_argument('--report', action='store_true', help='Generate report')
    parser.add_argument('--test', action='store_true', help='Run tests')
    args = parser.parse_args()

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.monitor:
        print("🚀 Starting Performance Monitor")
        print("=" * 50)

        optimizer = PerformanceOptimizer()

        try:
            print("Monitoring system performance... (Press Ctrl+C to stop)")
            while True:
                time.sleep(5)
                stats = optimizer.monitor.get_stats()
                system = stats.get('system', {})

                print(f"\n📊 System Status:")
                print(f"  CPU: {system.get('cpu', {}).get('current', 0):.1f}%")
                print(f"  Memory: {system.get('memory', {}).get('current', 0):.1f}%")

                if system.get('gpu'):
                    print(f"  GPU: {system['gpu'].get('current', 0):.1f}%")

                bottlenecks = stats.get('bottlenecks', [])
                if bottlenecks:
                    print(f"\n⚠️ Bottlenecks detected:")
                    for b in bottlenecks:
                        print(f"  - {b['message']}")

        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
        finally:
            optimizer.shutdown()

    elif args.report:
        print("📊 Generating Performance Report")
        print("=" * 50)

        optimizer = PerformanceOptimizer()

        # 간단한 테스트 작업 실행
        with optimizer.optimize("test_operation"):
            time.sleep(2)
            _ = [i**2 for i in range(1000000)]  # CPU 작업

        report = optimizer.get_optimization_report()

        print("\n📈 Performance Report:")
        print(f"Timestamp: {report['timestamp']}")
        print(f"Optimizations Applied: {report['optimization_stats']['optimizations_applied']}")

        print("\n🖥️ System Status:")
        for key, value in report.get('system_status', {}).items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    if isinstance(v, (int, float)):
                        print(f"    {k}: {v:.2f}")
            else:
                print(f"  {key}: {value}")

        print("\n💡 Recommendations:")
        for rec in report['recommendations']:
            print(f"  • {rec}")

        optimizer.shutdown()

    elif args.test:
        print("🧪 Running Performance Tests")
        print("=" * 50)

        # 테스트 1: 캐시 성능
        print("\n1. Cache Performance Test:")
        optimizer = QueryOptimizer()

        test_queries = ["test query " + str(i % 10) for i in range(100)]

        start = time.time()
        for q in test_queries:
            optimizer.optimize_query(q)

        print(f"  Query optimization: {time.time() - start:.3f}s for 100 queries")

        # 테스트 2: 병렬 처리
        print("\n2. Parallel Processing Test:")
        processor = ParallelProcessor()

        def slow_func(x):
            time.sleep(0.01)
            return x * x

        items = list(range(100))

        # 순차 처리
        start = time.time()
        sequential_results = [slow_func(x) for x in items]
        seq_time = time.time() - start

        # 병렬 처리
        start = time.time()
        parallel_results = processor.map_threaded(slow_func, items, chunk_size=10)
        par_time = time.time() - start

        print(f"  Sequential: {seq_time:.3f}s")
        print(f"  Parallel: {par_time:.3f}s")
        print(f"  Speedup: {seq_time/par_time:.2f}x")

        processor.shutdown()

        print("\n✅ Tests completed")

    else:
        parser.print_help()