#!/usr/bin/env python3
"""빠른 기능 테스트 (초기화 건너뛰기)"""
import time

def quick_test():
    print("=" * 60)
    print("⚡ 빠른 시스템 테스트")
    print("=" * 60)

    # 1. 웹 인터페이스 체크
    print("\n1. Web Interface 확인...")
    try:
        import streamlit as st
        import web_interface
        print("✅ Web interface 모듈 정상")
    except Exception as e:
        print(f"❌ Web interface 오류: {e}")

    # 2. 간단한 질문 테스트 (캐시된 인스턴스 사용)
    print("\n2. 캐시된 RAG 인스턴스로 테스트...")
    try:
        # 기존 캐시 사용 시도
        from pathlib import Path
        cache_file = Path("config/cache/metadata_cache.pkl")
        if cache_file.exists():
            print(f"✅ 캐시 파일 존재: {cache_file}")

            # 빠른 초기화 테스트
            import sys
            sys.stdout = open('/dev/null', 'w')  # 로그 숨기기
            from perfect_rag import PerfectRAG
            rag = PerfectRAG()
            sys.stdout = sys.__stdout__  # 로그 복원

            print("✅ RAG 인스턴스 생성 완료")

            # 간단한 응답 테스트
            test_query = "시스템 테스트"
            print(f"\n질문: '{test_query}'")
            start = time.time()
            response = rag.answer(test_query)
            elapsed = time.time() - start

            if response:
                print(f"✅ 응답 성공 ({elapsed:.2f}초)")
                print(f"응답 미리보기: {response[:100]}...")
            else:
                print(f"⚠️ 빈 응답")
        else:
            print("⚠️ 캐시 파일 없음 - 첫 실행시 시간이 걸립니다")

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")

    # 3. 시스템 상태
    print("\n3. 시스템 리소스...")
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"✅ 메모리 사용: {memory_mb:.1f} MB")

        cpu_percent = process.cpu_percent(interval=1)
        print(f"✅ CPU 사용: {cpu_percent:.1f}%")
    except:
        print("⚠️ psutil 없음")

    print("\n" + "=" * 60)
    print("✨ 빠른 테스트 완료")
    print("=" * 60)

if __name__ == "__main__":
    quick_test()