#!/usr/bin/env python3
"""
Reindexing Lock Utility
재색인 동시 실행 방지를 위한 파일 기반 Mutex
"""
import os
import time
from contextlib import contextmanager


LOCK_FILE = "var/locks/reindexing.lock"


def is_reindexing() -> bool:
    """재색인 중인지 확인"""
    return os.path.exists(LOCK_FILE)


@contextmanager
def reindexing_lock(timeout_sec: float = 1.5, poll_ms: int = 200):
    """
    재색인 락 컨텍스트 매니저

    Args:
        timeout_sec: 락 획득 대기 타임아웃 (초)
        poll_ms: 폴링 간격 (밀리초)

    Raises:
        RuntimeError: 타임아웃 시간 내 락 획득 실패

    Example:
        with reindexing_lock():
            # 재색인 작업
            pass
    """
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    start = time.time()

    while True:
        try:
            # 원자적 락 파일 생성
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)

            try:
                yield
            finally:
                try:
                    os.remove(LOCK_FILE)
                except FileNotFoundError:
                    pass
            return

        except FileExistsError:
            if time.time() - start > timeout_sec:
                raise RuntimeError("reindexing.lock held by another process")
            time.sleep(poll_ms / 1000.0)
