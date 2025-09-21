#!/usr/bin/env python3
"""
고급 메모리 최적화 시스템
- 실시간 모니터링
- 자동 메모리 관리
- 프로파일링 지원
"""
import gc
import os
import sys
import threading
import time
import tracemalloc
import weakref
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import warnings
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MemoryOptimizer:
    """고급 메모리 최적화 및 모니터링 클래스"""

    def __init__(self,
                 auto_cleanup: bool = True,
                 cleanup_threshold: float = 80.0,
                 monitoring_interval: int = 60,
                 enable_profiling: bool = False):
        """
        Args:
            auto_cleanup: 자동 메모리 정리 활성화
            cleanup_threshold: 메모리 정리 임계값 (%)
            monitoring_interval: 모니터링 간격 (초)
            enable_profiling: 메모리 프로파일링 활성화
        """
        self.auto_cleanup = auto_cleanup
        self.cleanup_threshold = cleanup_threshold
        self.monitoring_interval = monitoring_interval
        self.enable_profiling = enable_profiling

        # 모니터링 데이터
        self.memory_history = []
        self.gc_stats = defaultdict(int)
        self.leak_candidates = weakref.WeakSet()

        # 스레드 제어
        self._monitor_thread = None
        self._stop_monitoring = threading.Event()

        # 프로파일링
        self._snapshot = None
        if self.enable_profiling:
            tracemalloc.start()

        # 초기 설정
        self._setup_optimizations()

    def _setup_optimizations(self):
        """메모리 최적화 설정"""
        # 1. 가비지 컬렉션 최적화
        gc.set_threshold(700, 10, 10)  # 더 자주 GC 실행
        gc.enable()

        # 2. Python 메모리 할당자 최적화
        if 'PYTHONMALLOC' not in os.environ:
            os.environ['PYTHONMALLOC'] = 'pymalloc'

        # 3. 참조 순환 감지 활성화
        gc.set_debug(gc.DEBUG_SAVEALL)

        logger.info("✅ 메모리 최적화 설정 완료")

    def get_memory_info(self) -> Dict[str, Any]:
        """현재 메모리 정보 획득"""
        try:
            import psutil
        except ImportError:
            warnings.warn("psutil not installed. Limited memory info available.")
            return self._get_basic_memory_info()

        process = psutil.Process()
        mem_info = process.memory_info()
        vm = psutil.virtual_memory()

        info = {
            'timestamp': datetime.now().isoformat(),
            'process': {
                'rss_mb': mem_info.rss / 1024 / 1024,
                'vms_mb': mem_info.vms / 1024 / 1024,
                'percent': process.memory_percent()
            },
            'system': {
                'total_gb': vm.total / 1024 / 1024 / 1024,
                'used_gb': vm.used / 1024 / 1024 / 1024,
                'available_gb': vm.available / 1024 / 1024 / 1024,
                'percent': vm.percent
            },
            'gc': {
                'objects': len(gc.get_objects()),
                'garbage': len(gc.garbage)
            }
        }

        # 히스토리에 추가 (최대 1000개 유지)
        self.memory_history.append(info)
        if len(self.memory_history) > 1000:
            self.memory_history.pop(0)

        return info

    def _get_basic_memory_info(self) -> Dict[str, Any]:
        """기본 메모리 정보 (psutil 없을 때)"""
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)

        return {
            'timestamp': datetime.now().isoformat(),
            'process': {
                'rss_mb': usage.ru_maxrss / 1024,  # Linux에서는 KB 단위
                'user_time': usage.ru_utime,
                'system_time': usage.ru_stime
            },
            'gc': {
                'objects': len(gc.get_objects()),
                'garbage': len(gc.garbage)
            }
        }

    def cleanup_memory(self, force: bool = False) -> Dict[str, int]:
        """메모리 정리"""
        results = {
            'gc_collected': 0,
            'cache_cleared': 0,
            'weak_refs_cleared': 0
        }

        # 1. 가비지 컬렉션
        results['gc_collected'] = gc.collect()

        # 2. 순환 참조 정리
        gc.collect(2)  # 최고 세대까지 정리

        # 3. 캐시 정리
        results['cache_cleared'] = self._clear_caches()

        # 4. 약한 참조 정리
        results['weak_refs_cleared'] = len(self.leak_candidates)
        self.leak_candidates.clear()

        # 5. 강제 정리 모드
        if force:
            self._aggressive_cleanup()

        # GC 통계 업데이트
        self.gc_stats['total_cleanups'] += 1
        self.gc_stats['total_collected'] += results['gc_collected']

        logger.info(f"🧹 메모리 정리 완료: {results}")

        return results

    def _clear_caches(self) -> int:
        """각종 캐시 정리"""
        cleared = 0

        # Streamlit 캐시
        try:
            import streamlit as st
            st.cache_data.clear()
            st.cache_resource.clear()
            cleared += 1
        except:
            pass

        # functools 캐시
        try:
            import functools
            for obj in gc.get_objects():
                if isinstance(obj, functools._lru_cache_wrapper):
                    obj.cache_clear()
                    cleared += 1
        except:
            pass

        return cleared

    def _aggressive_cleanup(self):
        """공격적 메모리 정리 (주의: 성능 영향)"""
        # 모든 세대 강제 수집
        for i in range(gc.get_count()[2] + 1):
            gc.collect(i)

        # 메모리 압축 시도 (Linux)
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
        except:
            pass

    def start_monitoring(self):
        """실시간 모니터링 시작"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitoring already running")
            return

        self._stop_monitoring.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        logger.info("📊 메모리 모니터링 시작")

    def stop_monitoring(self):
        """모니터링 중지"""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

        logger.info("📊 메모리 모니터링 중지")

    def _monitor_loop(self):
        """모니터링 루프"""
        while not self._stop_monitoring.is_set():
            try:
                info = self.get_memory_info()

                # 자동 정리 확인
                if self.auto_cleanup and info['system']['percent'] > self.cleanup_threshold:
                    logger.warning(f"⚠️ 메모리 사용률 {info['system']['percent']:.1f}% - 자동 정리 시작")
                    self.cleanup_memory()

                # 메모리 누수 의심 객체 추적
                self._detect_potential_leaks()

            except Exception as e:
                logger.error(f"Monitoring error: {e}")

            self._stop_monitoring.wait(self.monitoring_interval)

    def _detect_potential_leaks(self):
        """잠재적 메모리 누수 탐지"""
        large_objects = []

        for obj in gc.get_objects():
            try:
                size = sys.getsizeof(obj)
                if size > 10 * 1024 * 1024:  # 10MB 이상
                    large_objects.append((type(obj).__name__, size))
                    self.leak_candidates.add(obj)
            except:
                continue

        if large_objects:
            logger.warning(f"🔍 대형 객체 탐지: {large_objects[:5]}")

    def get_memory_profile(self) -> Optional[List[Tuple]]:
        """메모리 프로파일 스냅샷"""
        if not self.enable_profiling:
            logger.warning("Profiling not enabled")
            return None

        snapshot = tracemalloc.take_snapshot()

        if self._snapshot:
            # 이전 스냅샷과 비교
            top_stats = snapshot.compare_to(self._snapshot, 'lineno')

            result = []
            for stat in top_stats[:10]:
                result.append({
                    'file': stat.traceback[0].filename,
                    'line': stat.traceback[0].lineno,
                    'size_diff': stat.size_diff,
                    'count_diff': stat.count_diff
                })

            self._snapshot = snapshot
            return result

        self._snapshot = snapshot

        # 첫 스냅샷
        stats = snapshot.statistics('lineno')
        result = []
        for stat in stats[:10]:
            result.append({
                'file': stat.traceback[0].filename,
                'line': stat.traceback[0].lineno,
                'size': stat.size,
                'count': stat.count
            })

        return result

    def optimize_for_environment(self, env_type: str = 'production'):
        """환경별 최적화 설정"""
        configs = {
            'development': {
                'gc_threshold': (700, 10, 10),
                'auto_cleanup': True,
                'cleanup_threshold': 70.0
            },
            'production': {
                'gc_threshold': (700, 10, 10),
                'auto_cleanup': True,
                'cleanup_threshold': 85.0
            },
            'memory_constrained': {
                'gc_threshold': (500, 5, 5),
                'auto_cleanup': True,
                'cleanup_threshold': 60.0
            }
        }

        config = configs.get(env_type, configs['production'])

        gc.set_threshold(*config['gc_threshold'])
        self.auto_cleanup = config['auto_cleanup']
        self.cleanup_threshold = config['cleanup_threshold']

        logger.info(f"✅ {env_type} 환경에 최적화 완료")

    def get_statistics(self) -> Dict[str, Any]:
        """메모리 관리 통계"""
        if not self.memory_history:
            return {}

        recent = self.memory_history[-100:]  # 최근 100개

        return {
            'monitoring': {
                'samples': len(self.memory_history),
                'duration_minutes': len(self.memory_history) * self.monitoring_interval / 60
            },
            'memory': {
                'current_mb': recent[-1]['process']['rss_mb'] if recent else 0,
                'avg_mb': sum(h['process']['rss_mb'] for h in recent) / len(recent) if recent else 0,
                'max_mb': max(h['process']['rss_mb'] for h in recent) if recent else 0
            },
            'gc': {
                'total_cleanups': self.gc_stats['total_cleanups'],
                'total_collected': self.gc_stats['total_collected'],
                'current_objects': len(gc.get_objects()),
                'garbage_objects': len(gc.garbage)
            },
            'leaks': {
                'potential_leaks': len(self.leak_candidates)
            }
        }

    def generate_report(self) -> str:
        """메모리 상태 보고서 생성"""
        info = self.get_memory_info()
        stats = self.get_statistics()

        report = []
        report.append("="*60)
        report.append("📊 메모리 상태 보고서")
        report.append("="*60)

        report.append(f"\n⏰ 시간: {info['timestamp']}")

        report.append("\n💾 프로세스 메모리:")
        report.append(f"   - RSS: {info['process']['rss_mb']:.1f} MB")
        report.append(f"   - VMS: {info['process']['vms_mb']:.1f} MB")
        report.append(f"   - 사용률: {info['process']['percent']:.1f}%")

        report.append("\n💻 시스템 메모리:")
        report.append(f"   - 전체: {info['system']['total_gb']:.1f} GB")
        report.append(f"   - 사용중: {info['system']['used_gb']:.1f} GB ({info['system']['percent']:.1f}%)")
        report.append(f"   - 사용가능: {info['system']['available_gb']:.1f} GB")

        if stats:
            report.append("\n📈 통계:")
            report.append(f"   - 모니터링 시간: {stats['monitoring']['duration_minutes']:.1f}분")
            report.append(f"   - 평균 메모리: {stats['memory']['avg_mb']:.1f} MB")
            report.append(f"   - 최대 메모리: {stats['memory']['max_mb']:.1f} MB")
            report.append(f"   - GC 실행: {stats['gc']['total_cleanups']}회")
            report.append(f"   - GC 수집: {stats['gc']['total_collected']}개")

        if info['system']['percent'] > self.cleanup_threshold:
            report.append("\n⚠️ 경고: 메모리 사용률이 높습니다!")
            report.append("   권장: 메모리 정리 또는 프로세스 재시작")

        report.append("\n" + "="*60)

        return "\n".join(report)


# 전역 인스턴스
_optimizer = None

def get_optimizer() -> MemoryOptimizer:
    """싱글톤 최적화기 반환"""
    global _optimizer
    if _optimizer is None:
        _optimizer = MemoryOptimizer()
    return _optimizer


# 편의 함수들
def optimize_memory(env: str = 'production'):
    """메모리 최적화 설정"""
    optimizer = get_optimizer()
    optimizer.optimize_for_environment(env)
    return optimizer.get_memory_info()

def check_memory():
    """현재 메모리 사용량 체크"""
    optimizer = get_optimizer()
    info = optimizer.get_memory_info()

    print(f"\n📊 현재 프로세스 메모리:")
    print(f"   - RSS: {info['process']['rss_mb']:.1f} MB")
    print(f"   - VMS: {info['process']['vms_mb']:.1f} MB")

    print(f"\n💻 시스템 메모리:")
    print(f"   - 전체: {info['system']['total_gb']:.1f} GB")
    print(f"   - 사용중: {info['system']['used_gb']:.1f} GB ({info['system']['percent']:.1f}%)")
    print(f"   - 사용가능: {info['system']['available_gb']:.1f} GB")

    if info['system']['percent'] > 80:
        print("\n⚠️ 메모리 사용률이 높습니다!")
        print("   권장: 메모리 정리 실행")

    return info['system']['percent']

def cleanup_memory():
    """메모리 정리"""
    optimizer = get_optimizer()
    results = optimizer.cleanup_memory()

    print("\n🧹 메모리 정리 결과:")
    print(f"   - GC 수집: {results['gc_collected']}개")
    print(f"   - 캐시 정리: {results['cache_cleared']}개")
    print(f"   - 약한 참조 정리: {results['weak_refs_cleared']}개")

    return results


if __name__ == "__main__":
    # 테스트
    import argparse

    parser = argparse.ArgumentParser(description="메모리 최적화 도구")
    parser.add_argument('--monitor', action='store_true', help='실시간 모니터링')
    parser.add_argument('--profile', action='store_true', help='메모리 프로파일링')
    parser.add_argument('--cleanup', action='store_true', help='메모리 정리')
    parser.add_argument('--report', action='store_true', help='상태 보고서')
    parser.add_argument('--env', default='production', help='환경 설정')

    args = parser.parse_args()

    print("="*60)
    print("🔧 고급 메모리 최적화 도구")
    print("="*60)

    # 최적화기 생성
    optimizer = MemoryOptimizer(
        auto_cleanup=True,
        enable_profiling=args.profile
    )

    # 환경 설정
    optimizer.optimize_for_environment(args.env)

    if args.monitor:
        print("\n📊 실시간 모니터링 시작 (Ctrl+C로 종료)")
        optimizer.start_monitoring()
        try:
            while True:
                time.sleep(10)
                print(".", end="", flush=True)
        except KeyboardInterrupt:
            optimizer.stop_monitoring()

    elif args.cleanup:
        results = optimizer.cleanup_memory(force=True)
        print(f"\n✅ 메모리 정리 완료: {results}")

    elif args.report:
        print(optimizer.generate_report())

    elif args.profile:
        print("\n🔍 메모리 프로파일:")
        profile = optimizer.get_memory_profile()
        if profile:
            for item in profile:
                print(f"   {item}")

    else:
        # 기본 동작
        info = optimizer.get_memory_info()
        stats = optimizer.get_statistics()

        print(f"\n현재 메모리: {info['process']['rss_mb']:.1f} MB")
        print(f"시스템 사용률: {info['system']['percent']:.1f}%")

        if info['system']['percent'] > 80:
            print("\n⚠️ 메모리 사용률 높음 - 정리 실행")
            optimizer.cleanup_memory()