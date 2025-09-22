#!/usr/bin/env python3
"""
테스트 실행 스크립트
"""

import sys
import subprocess

def run_tests():
    """테스트 실행"""

    print("="*60)
    print("🧪 테스트 실행")
    print("="*60)

    commands = [
        # 단위 테스트
        ["pytest", "tests/unit", "-v", "--tb=short"],

        # 통합 테스트
        ["pytest", "tests/integration", "-v", "-m", "integration"],

        # 커버리지 리포트
        ["pytest", "--cov=rag_modules", "--cov-report=term-missing"],

        # HTML 리포트 생성
        ["pytest", "--cov=rag_modules", "--cov-report=html"]
    ]

    for cmd in commands:
        print(f"\n실행: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ 테스트 실패: {result.stderr}")
        else:
            print(f"✅ 테스트 통과")

    print("\n📊 커버리지 리포트: htmlcov/index.html")

if __name__ == "__main__":
    run_tests()
