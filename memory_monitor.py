"""
실시간 메모리 모니터링
"""

import psutil
import time
import threading
from datetime import datetime

class MemoryMonitor:
    """메모리 모니터"""

    def __init__(self, threshold_gb=4.0):
        self.threshold_gb = threshold_gb
        self.running = False
        self.thread = None
        self.history = []

    def start(self):
        """모니터링 시작"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.daemon = True
        self.thread.start()
        print("🔍 메모리 모니터링 시작")

    def stop(self):
        """모니터링 중지"""
        self.running = False
        if self.thread:
            self.thread.join()
        print("🛑 메모리 모니터링 중지")

    def _monitor_loop(self):
        """모니터링 루프"""
        while self.running:
            mem_info = self.get_memory_info()

            # 기록
            self.history.append({
                'timestamp': datetime.now(),
                'memory_gb': mem_info['rss_gb']
            })

            # 임계값 체크
            if mem_info['rss_gb'] > self.threshold_gb:
                self._handle_memory_warning(mem_info)

            # 5초마다 체크
            time.sleep(5)

    def get_memory_info(self):
        """현재 메모리 정보"""
        process = psutil.Process()
        mem = process.memory_info()

        return {
            'rss_gb': mem.rss / 1024**3,
            'vms_gb': mem.vms / 1024**3,
            'percent': process.memory_percent()
        }

    def _handle_memory_warning(self, mem_info):
        """메모리 경고 처리"""
        print(f"⚠️ 메모리 경고: {mem_info['rss_gb']:.2f}GB > {self.threshold_gb}GB")

        # 자동 정리 시도
        import gc
        gc.collect()

        # 정리 후 재확인
        new_mem = self.get_memory_info()
        if new_mem['rss_gb'] < mem_info['rss_gb']:
            print(f"✅ 메모리 정리 성공: {mem_info['rss_gb']:.2f}GB → {new_mem['rss_gb']:.2f}GB")

    def get_report(self):
        """메모리 사용 리포트"""
        if not self.history:
            return "No data"

        avg_memory = sum(h['memory_gb'] for h in self.history) / len(self.history)
        max_memory = max(h['memory_gb'] for h in self.history)
        min_memory = min(h['memory_gb'] for h in self.history)

        return f"""
메모리 사용 리포트
==================
평균: {avg_memory:.2f} GB
최대: {max_memory:.2f} GB
최소: {min_memory:.2f} GB
샘플: {len(self.history)}개
"""

# 전역 모니터 인스턴스
monitor = MemoryMonitor(threshold_gb=4.0)
