#!/usr/bin/env python3
"""
메모리 최적화 설정
"""
import gc
import os
import sys

def optimize_memory():
    """메모리 최적화 설정"""

    # 1. 가비지 컬렉션 강화
    gc.set_threshold(700, 10, 10)  # 더 자주 GC 실행

    # 2. Python 메모리 할당자 최적화
    os.environ['PYTHONMALLOC'] = 'malloc'

    # 3. 메모리 제한 설정 (선택사항)
    # resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, -1))  # 2GB 제한

    print("✅ 메모리 최적화 설정 완료")
    print("   - 가비지 컬렉션 강화")
    print("   - Python 메모리 할당자 최적화")

    return True

def check_memory():
    """현재 메모리 사용량 체크"""
    import psutil

    process = psutil.Process()
    mem_info = process.memory_info()

    print(f"\n📊 현재 프로세스 메모리:")
    print(f"   - RSS: {mem_info.rss / 1024 / 1024:.1f} MB")
    print(f"   - VMS: {mem_info.vms / 1024 / 1024:.1f} MB")

    # 시스템 전체
    vm = psutil.virtual_memory()
    print(f"\n💻 시스템 메모리:")
    print(f"   - 전체: {vm.total / 1024 / 1024 / 1024:.1f} GB")
    print(f"   - 사용중: {vm.used / 1024 / 1024 / 1024:.1f} GB ({vm.percent}%)")
    print(f"   - 사용가능: {vm.available / 1024 / 1024 / 1024:.1f} GB")

    if vm.percent > 80:
        print("\n⚠️ 메모리 사용률이 높습니다!")
        print("   권장: Streamlit 재시작 또는 캐시 정리")

    return vm.percent

def cleanup_memory():
    """메모리 정리"""
    import gc

    print("\n🧹 메모리 정리 시작...")

    # 강제 가비지 컬렉션
    collected = gc.collect()
    print(f"   - {collected}개 객체 정리됨")

    # 캐시 정리 (가능한 경우)
    try:
        import streamlit as st
        st.cache_data.clear()
        print("   - Streamlit 캐시 정리됨")
    except:
        pass

    print("✅ 메모리 정리 완료")

if __name__ == "__main__":
    print("="*60)
    print("🔧 메모리 최적화 도구")
    print("="*60)

    optimize_memory()
    check_memory()

    # 메모리 사용률이 높으면 정리
    if check_memory() > 80:
        cleanup_memory()
        check_memory()