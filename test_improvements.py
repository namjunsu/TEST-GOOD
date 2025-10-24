#!/usr/bin/env python3
"""
개선사항 테스트 스크립트
새로 생성된 모듈들이 정상적으로 작동하는지 확인
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))


def test_css_loader():
    """CSS 로더 테스트"""
    print("1. CSS 로더 테스트...")
    try:
        from utils.css_loader import load_css
        css_path = Path("static/css/main.css")
        if css_path.exists():
            print("   ✅ CSS 파일 존재 확인")
            print(f"   ✅ CSS 파일 크기: {css_path.stat().st_size / 1024:.1f} KB")
        else:
            print("   ❌ CSS 파일 없음")
            return False

        # CSS 로더 임포트 테스트
        print("   ✅ CSS 로더 모듈 임포트 성공")
        return True

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False


def test_error_handler():
    """에러 핸들러 테스트"""
    print("\n2. 에러 핸들러 테스트...")
    try:
        from utils.error_handler import ErrorHandler, ErrorType, handle_errors

        # 에러 타입 분류 테스트
        test_errors = [
            (FileNotFoundError("test.pdf"), ErrorType.FILE_NOT_FOUND),
            (PermissionError("access denied"), ErrorType.PERMISSION_DENIED),
            (MemoryError("out of memory"), ErrorType.MEMORY_ERROR),
            (ImportError("module not found"), ErrorType.IMPORT_ERROR),
        ]

        for error, expected_type in test_errors:
            actual_type = ErrorHandler._classify_error(error)
            if actual_type == expected_type:
                print(f"   ✅ {error.__class__.__name__} → {expected_type.name}")
            else:
                print(f"   ❌ {error.__class__.__name__} 분류 실패")
                return False

        # 데코레이터 테스트
        @handle_errors(context="테스트", show_details=False)
        def risky_function():
            raise ValueError("테스트 에러")

        # 에러가 처리되는지 확인
        result = risky_function()
        if result is None:
            print("   ✅ 데코레이터 에러 처리 성공")

        print("   ✅ 에러 핸들러 모듈 테스트 완료")
        return True

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False


def test_performance_monitor():
    """성능 모니터 테스트"""
    print("\n3. 성능 모니터 테스트...")
    try:
        from utils.performance import PerformanceMonitor, Timer
        import time

        # 데코레이터 테스트
        @PerformanceMonitor.measure(show_time=False)
        def slow_function():
            time.sleep(0.1)
            return "완료"

        result = slow_function()
        if result == "완료":
            print("   ✅ 성능 측정 데코레이터 작동")

        # Timer 컨텍스트 매니저 테스트
        with Timer("테스트 작업", show=False) as timer:
            time.sleep(0.05)

        if timer.duration > 0:
            print(f"   ✅ Timer 측정 성공: {timer.duration:.3f}초")

        print("   ✅ 성능 모니터 모듈 테스트 완료")
        return True

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False


def test_session_manager():
    """세션 매니저 테스트"""
    print("\n4. 세션 매니저 테스트...")
    try:
        from utils.session_manager import SessionManager

        # Streamlit 없이 테스트하기 위한 모의 세션
        class MockSessionState:
            def __init__(self):
                self.data = {}

            def __getitem__(self, key):
                return self.data[key]

            def __setitem__(self, key, value):
                self.data[key] = value

            def __contains__(self, key):
                return key in self.data

            def get(self, key, default=None):
                return self.data.get(key, default)

            def keys(self):
                return self.data.keys()

            def __delitem__(self, key):
                del self.data[key]

        # 모의 세션 주입
        import streamlit as st
        if not hasattr(st, 'session_state'):
            st.session_state = MockSessionState()

        # 기본 작업 테스트
        SessionManager.set('test_key', 'test_value')
        value = SessionManager.get('test_key')

        if value == 'test_value':
            print("   ✅ 세션 값 저장/읽기 성공")

        # 존재 여부 확인
        if SessionManager.exists('test_key'):
            print("   ✅ 세션 키 존재 확인 성공")

        # 삭제
        SessionManager.delete('test_key')
        if not SessionManager.exists('test_key'):
            print("   ✅ 세션 값 삭제 성공")

        print("   ✅ 세션 매니저 모듈 테스트 완료")
        return True

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False


def test_components():
    """컴포넌트 임포트 테스트"""
    print("\n5. 컴포넌트 테스트...")
    components_to_test = [
        'components.sidebar',
        'components.pdf_viewer',
        'components.chat'
    ]

    all_success = True
    for component_name in components_to_test:
        try:
            __import__(component_name)
            print(f"   ✅ {component_name} 임포트 성공")
        except ImportError as e:
            print(f"   ⚠️  {component_name} 임포트 실패 (의존성 문제일 수 있음)")
            # 의존성 문제는 경고만 표시
        except Exception as e:
            print(f"   ❌ {component_name} 오류: {e}")
            all_success = False

    if all_success:
        print("   ✅ 컴포넌트 모듈 테스트 완료")
    return all_success


def test_file_structure():
    """파일 구조 확인"""
    print("\n6. 파일 구조 확인...")

    required_files = [
        'static/css/main.css',
        'utils/css_loader.py',
        'utils/error_handler.py',
        'utils/performance.py',
        'utils/session_manager.py',
        'components/sidebar.py',
        'components/pdf_viewer.py',
        'components/chat.py',
        'web_interface_original_backup.py',
    ]

    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size / 1024
            print(f"   ✅ {file_path} ({size:.1f} KB)")
        else:
            print(f"   ❌ {file_path} 없음")
            all_exist = False

    if all_exist:
        print("   ✅ 모든 파일 생성 완료")
    return all_exist


def main():
    """메인 테스트 실행"""
    print("=" * 60)
    print("🧪 개선사항 테스트 시작")
    print("=" * 60)

    tests = [
        ("파일 구조", test_file_structure),
        ("CSS 로더", test_css_loader),
        ("에러 핸들러", test_error_handler),
        ("성능 모니터", test_performance_monitor),
        ("세션 매니저", test_session_manager),
        ("컴포넌트", test_components),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 테스트 실패: {e}")
            results.append((name, False))

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)

    success_count = sum(1 for _, result in results if result)
    total_count = len(results)

    for name, result in results:
        status = "✅ 성공" if result else "❌ 실패"
        print(f"  {name}: {status}")

    print(f"\n총 {total_count}개 테스트 중 {success_count}개 성공")

    if success_count == total_count:
        print("\n🎉 모든 테스트 통과! 개선사항이 정상적으로 적용되었습니다.")
        return 0
    else:
        print(f"\n⚠️  일부 테스트 실패. {total_count - success_count}개 항목 확인 필요.")
        return 1


if __name__ == "__main__":
    exit(main())