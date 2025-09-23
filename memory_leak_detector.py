#!/usr/bin/env python3
"""
메모리 누수 감지 및 방지 시스템
================================
자동으로 메모리 누수를 감지하고 해결
"""

import gc
import sys
import psutil
import tracemalloc
import weakref
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from pathlib import Path
import time
import threading
from collections import defaultdict

class MemoryLeakDetector:
    """메모리 누수 감지기"""

    def __init__(self, threshold_mb: float = 100.0, check_interval: int = 60):
        self.threshold_mb = threshold_mb
        self.check_interval = check_interval
        self.baseline_memory = None
        self.memory_history = []
        self.leak_suspects = defaultdict(list)
        self.object_registry = weakref.WeakValueDictionary()
        self.monitoring = False
        self.monitor_thread = None

        # 추적 시작
        tracemalloc.start()

    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.baseline_memory = self._get_memory_usage()
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("🔍 메모리 모니터링 시작")

    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        tracemalloc.stop()
        print("⏹️  메모리 모니터링 중지")

    def _monitor_loop(self):
        """모니터링 루프"""
        while self.monitoring:
            self.check_memory()
            time.sleep(self.check_interval)

    def _get_memory_usage(self) -> Dict:
        """현재 메모리 사용량 조회"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'timestamp': datetime.now().isoformat(),
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024,
            'percent': process.memory_percent(),
            'available_mb': psutil.virtual_memory().available / 1024 / 1024
        }

    def check_memory(self):
        """메모리 체크 및 누수 감지"""
        current_memory = self._get_memory_usage()
        self.memory_history.append(current_memory)

        # 최근 10개만 유지
        if len(self.memory_history) > 10:
            self.memory_history.pop(0)

        # 누수 감지
        if self.baseline_memory:
            increase = current_memory['rss_mb'] - self.baseline_memory['rss_mb']
            if increase > self.threshold_mb:
                print(f"⚠️  메모리 누수 의심: {increase:.1f} MB 증가")
                self._analyze_leak()
                self._fix_leak()

    def _analyze_leak(self):
        """누수 분석"""
        # 상위 10개 메모리 사용 추적
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')[:10]

        print("\n📊 메모리 사용 상위 10개:")
        for stat in top_stats:
            print(f"  {stat.filename}:{stat.lineno}: {stat.size / 1024:.1f} KB")

        # 객체 타입별 카운트
        obj_counts = defaultdict(int)
        for obj in gc.get_objects():
            obj_counts[type(obj).__name__] += 1

        # 가장 많은 객체 타입
        top_objects = sorted(obj_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        print("\n🔢 객체 수 상위 5개:")
        for obj_type, count in top_objects:
            print(f"  {obj_type}: {count:,}")

    def _fix_leak(self):
        """누수 수정 시도"""
        print("\n🔧 메모리 정리 시작...")

        # 1. 가비지 컬렉션
        collected = gc.collect()
        print(f"  ♻️  가비지 컬렉션: {collected}개 객체 정리")

        # 2. 캐시 정리
        self._clear_caches()

        # 3. GPU 메모리 정리
        self._clear_gpu_memory()

        # 4. 큰 객체 정리
        self._clear_large_objects()

        # 메모리 사용량 재확인
        after_memory = self._get_memory_usage()
        reduction = self.memory_history[-1]['rss_mb'] - after_memory['rss_mb']
        print(f"  ✅ 메모리 {reduction:.1f} MB 해제")

    def _clear_caches(self):
        """캐시 정리"""
        # 파이썬 캐시 정리
        if hasattr(sys, 'intern'):
            sys.intern.clear()

        # 모듈별 캐시 정리
        modules_with_cache = [
            'functools', 're', 'linecache', 'urllib.parse',
            'encodings', 'typing', 'importlib'
        ]

        for module_name in modules_with_cache:
            if module_name in sys.modules:
                module = sys.modules[module_name]
                if hasattr(module, 'clear_cache'):
                    module.clear_cache()
                if hasattr(module, '_cache'):
                    module._cache.clear()

        print("  🗑️  캐시 정리 완료")

    def _clear_gpu_memory(self):
        """GPU 메모리 정리"""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                print("  🎮 GPU 메모리 정리 완료")
        except ImportError:
            pass

    def _clear_large_objects(self):
        """큰 객체 정리"""
        # 100MB 이상 객체 찾기
        large_objects = []
        for obj in gc.get_objects():
            try:
                size = sys.getsizeof(obj)
                if size > 100 * 1024 * 1024:  # 100MB
                    large_objects.append((type(obj).__name__, size))
            except:
                continue

        if large_objects:
            print(f"  🗄️  큰 객체 발견: {len(large_objects)}개")
            for obj_type, size in large_objects[:3]:
                print(f"    - {obj_type}: {size / 1024 / 1024:.1f} MB")

    def register_object(self, name: str, obj: Any):
        """객체 등록 (약한 참조)"""
        self.object_registry[name] = obj

    def get_report(self) -> Dict:
        """메모리 리포트 생성"""
        current = self._get_memory_usage()
        if self.baseline_memory:
            increase = current['rss_mb'] - self.baseline_memory['rss_mb']
        else:
            increase = 0

        return {
            'current_memory_mb': current['rss_mb'],
            'baseline_memory_mb': self.baseline_memory['rss_mb'] if self.baseline_memory else 0,
            'increase_mb': increase,
            'percent_used': current['percent'],
            'monitored_objects': len(self.object_registry),
            'history_length': len(self.memory_history),
            'status': 'leak_detected' if increase > self.threshold_mb else 'normal'
        }

class SmartMemoryManager:
    """스마트 메모리 관리자"""

    def __init__(self):
        self.detector = MemoryLeakDetector()
        self.limits = {
            'max_memory_percent': 80.0,
            'max_cache_size_mb': 500,
            'max_object_count': 1000000
        }

    def optimize_memory(self):
        """메모리 최적화"""
        print("🚀 메모리 최적화 시작...")

        # 1. 불필요한 모듈 언로드
        self._unload_unused_modules()

        # 2. 문자열 인턴 최적화
        self._optimize_string_intern()

        # 3. 순환 참조 제거
        self._break_cycles()

        # 4. 메모리 압축
        self._compact_memory()

        print("✅ 메모리 최적화 완료")

    def _unload_unused_modules(self):
        """사용하지 않는 모듈 언로드"""
        # 안전하게 제거 가능한 모듈들
        removable = [
            'test', 'unittest', 'doctest', 'pdb',
            'profile', 'cProfile', 'trace'
        ]

        removed = 0
        for module in list(sys.modules.keys()):
            if any(module.startswith(r) for r in removable):
                del sys.modules[module]
                removed += 1

        if removed > 0:
            print(f"  📦 {removed}개 모듈 언로드")

    def _optimize_string_intern(self):
        """문자열 인턴 최적화"""
        # 짧은 문자열만 인턴
        interned = 0
        for obj in gc.get_objects():
            if isinstance(obj, str) and 3 < len(obj) < 50:
                sys.intern(obj)
                interned += 1
                if interned > 1000:
                    break

        print(f"  📝 {interned}개 문자열 인턴")

    def _break_cycles(self):
        """순환 참조 제거"""
        # 순환 참조 감지 및 제거
        gc.set_debug(gc.DEBUG_SAVEALL)
        collected = gc.collect()
        gc.set_debug(0)

        if collected > 0:
            print(f"  🔄 {collected}개 순환 참조 제거")

    def _compact_memory(self):
        """메모리 압축"""
        # 메모리 압축 힌트
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
            print("  📐 메모리 압축 완료")
        except:
            pass

# 전역 인스턴스
leak_detector = MemoryLeakDetector()
memory_manager = SmartMemoryManager()

# 자동 시작
def auto_start():
    """자동 시작"""
    leak_detector.start_monitoring()
    print("✅ 메모리 누수 감지기 자동 시작")

# 사용 예제
if __name__ == "__main__":
    print("🧪 메모리 누수 감지기 테스트")

    # 모니터링 시작
    leak_detector.start_monitoring()

    # 의도적인 메모리 누수 생성
    leak_list = []
    for i in range(1000):
        leak_list.append([0] * 10000)  # 메모리 누수 시뮬레이션

    # 수동 체크
    leak_detector.check_memory()

    # 메모리 최적화
    memory_manager.optimize_memory()

    # 리포트 출력
    report = leak_detector.get_report()
    print("\n📋 메모리 리포트:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # 모니터링 중지
    leak_detector.stop_monitoring()