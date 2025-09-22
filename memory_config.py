"""
메모리 최적화 설정
목표: 16GB → 4GB
"""

import gc
import os

# 메모리 설정
class MemoryConfig:
    # 캐시 크기 제한 (기존 대비 50% 감소)
    MAX_CACHE_SIZE = 50  # 100 → 50
    MAX_METADATA_CACHE = 250  # 500 → 250
    MAX_PDF_CACHE = 25  # 50 → 25

    # 배치 처리 크기 최적화
    BATCH_SIZE = 5  # 10 → 5 (메모리 사용량 감소)

    # PDF 텍스트 추출 제한
    MAX_PDF_TEXT_LENGTH = 10000  # 문자 제한
    MAX_PAGES_PER_PDF = 50  # 페이지 제한

    # 가비지 컬렉션 주기
    GC_INTERVAL = 10  # 10개 문서마다 GC 실행

    # 메모리 임계값 (4GB)
    MEMORY_LIMIT_GB = 4
    MEMORY_WARNING_GB = 3.5

# 메모리 최적화 함수들
def optimize_memory():
    """메모리 최적화 실행"""
    # 강제 가비지 컬렉션
    gc.collect()
    gc.collect()  # 두 번 실행으로 확실히 정리

    # 메모리 압축 (Linux)
    if hasattr(gc, 'freeze'):
        gc.freeze()

    return True

def check_memory_usage():
    """메모리 사용량 확인 및 경고"""
    import psutil

    process = psutil.Process()
    mem_gb = process.memory_info().rss / 1024**3

    if mem_gb > MemoryConfig.MEMORY_LIMIT_GB:
        # 메모리 초과 - 캐시 정리
        return "CRITICAL"
    elif mem_gb > MemoryConfig.MEMORY_WARNING_GB:
        # 경고 수준
        return "WARNING"
    return "OK"

# 자동 메모리 관리 데코레이터
def memory_managed(func):
    """메모리 관리 데코레이터"""
    def wrapper(*args, **kwargs):
        # 실행 전 메모리 체크
        status = check_memory_usage()
        if status == "CRITICAL":
            optimize_memory()

        # 함수 실행
        result = func(*args, **kwargs)

        # 실행 후 정리
        if status != "OK":
            gc.collect()

        return result
    return wrapper
