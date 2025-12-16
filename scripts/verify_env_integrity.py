#!/usr/bin/env python3
"""
AI-CHAT 환경 무결성 검증 스크립트

CI/CD 파이프라인 및 테스트 실행 전 환경변수 무결성을 검증합니다.
.env 파일의 필수 설정값이 올바르게 설정되어 있는지 확인합니다.

Exit codes:
    0: 검증 성공
    1: 경고 발생 (진행 가능)
    2: 치명적 오류 (진행 불가)
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

# ANSI 색상 코드
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def log(level: str, message: str):
    """로그 출력"""
    colors = {
        "INFO": GREEN,
        "WARN": YELLOW,
        "FATAL": RED,
        "SUCCESS": GREEN
    }
    color = colors.get(level, NC)
    print(f"{color}[{level}]{NC} {message}")


def verify_dotenv_file() -> Tuple[bool, List[str]]:
    """
    .env 파일 존재 및 로드 가능 여부 확인

    Returns:
        (성공 여부, 오류 메시지 리스트)
    """
    errors = []
    env_path = Path(".env")

    if not env_path.exists():
        errors.append(".env 파일이 없습니다")
        return False, errors

    try:
        from dotenv import dotenv_values
        env_vars = dotenv_values(".env")

        if not env_vars:
            errors.append(".env 파일이 비어있거나 형식이 잘못되었습니다")
            return False, errors

        log("SUCCESS", f".env 파일 로드 완료 ({len(env_vars)}개 변수)")
        return True, []

    except ImportError:
        errors.append("python-dotenv 패키지가 설치되지 않았습니다")
        return False, errors
    except Exception as e:
        errors.append(f".env 파일 로드 실패: {e}")
        return False, errors


def verify_model_path() -> Tuple[bool, List[str]]:
    """
    MODEL_PATH 검증

    Returns:
        (성공 여부, 오류 메시지 리스트)
    """
    errors = []

    from dotenv import dotenv_values
    env_vars = dotenv_values(".env")

    model_path = env_vars.get("MODEL_PATH", "")

    # 1. 설정 여부 확인
    if not model_path:
        errors.append("MODEL_PATH가 .env에 설정되지 않았습니다")
        return False, errors

    # 2. 파일 존재 확인
    model_file = Path(model_path)
    if not model_file.exists():
        errors.append(f"MODEL_PATH 파일이 없습니다: {model_path}")
        return False, errors

    if not model_file.is_file():
        errors.append(f"MODEL_PATH가 파일이 아닙니다: {model_path}")
        return False, errors

    # 3. 파일 크기 확인 (최소 100MB)
    file_size = model_file.stat().st_size
    if file_size < 100 * 1024 * 1024:
        errors.append(f"MODEL_PATH 파일이 너무 작습니다: {file_size / 1024 / 1024:.1f}MB (최소 100MB 필요)")
        return False, errors

    log("SUCCESS", f"MODEL_PATH 검증 완료: {model_path} ({file_size / 1024 / 1024:.1f}MB)")
    return True, []


def verify_critical_vars() -> Tuple[bool, List[str]]:
    """
    필수 환경변수 검증

    Returns:
        (성공 여부, 경고 메시지 리스트)
    """
    warnings = []

    from dotenv import dotenv_values
    env_vars = dotenv_values(".env")

    # 권장 설정값
    recommended = {
        "CHAT_FORMAT": "auto",
        "RAG_MIN_SCORE": "0.35",
        "MODE": "AUTO",
    }

    for var, recommended_value in recommended.items():
        actual_value = env_vars.get(var)
        if not actual_value:
            warnings.append(f"{var}가 설정되지 않았습니다 (권장: {recommended_value})")
        elif actual_value != recommended_value:
            log("INFO", f"{var}={actual_value} (권장: {recommended_value})")

    return True, warnings


def verify_shell_environment():
    """
    현재 셸 환경변수 오염 여부 확인

    Returns:
        (성공 여부, 경고 메시지 리스트)
    """
    warnings = []

    # 오염 가능성 있는 변수들
    polluting_vars = [
        "MODEL_PATH",
        "CHAT_FORMAT",
        "N_CTX",
        "N_GPU_LAYERS",
        "LLM_MODEL_PATH",
        "QWEN_MODEL_PATH"
    ]

    for var in polluting_vars:
        if var in os.environ:
            warnings.append(f"셸 환경변수 {var}가 설정되어 있습니다 (.env를 덮어쓸 수 있음)")

    if warnings:
        log("WARN", "다음 스크립트로 정리하세요: scripts/cleanup_shell_env.sh")

    return len(warnings) == 0, warnings


def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("AI-CHAT 환경 무결성 검증")
    print("=" * 80)
    print()

    fatal_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. .env 파일 검증
    log("INFO", "1/4 .env 파일 검증 중...")
    success, errors = verify_dotenv_file()
    if not success:
        fatal_errors.extend(errors)
    print()

    # .env가 없으면 더 이상 진행 불가
    if fatal_errors:
        log("FATAL", "치명적 오류가 발생했습니다:")
        for error in fatal_errors:
            print(f"  - {error}")
        print()
        print("=" * 80)
        sys.exit(2)

    # 2. MODEL_PATH 검증
    log("INFO", "2/4 MODEL_PATH 검증 중...")
    success, errors = verify_model_path()
    if not success:
        fatal_errors.extend(errors)
    print()

    # 3. 필수 환경변수 검증
    log("INFO", "3/4 필수 환경변수 검증 중...")
    success, warnings = verify_critical_vars()
    all_warnings.extend(warnings)
    print()

    # 4. 셸 환경 오염 검사
    log("INFO", "4/4 셸 환경 오염 검사 중...")
    success, warnings = verify_shell_environment()
    all_warnings.extend(warnings)
    print()

    # 결과 요약
    print("=" * 80)
    if fatal_errors:
        log("FATAL", f"검증 실패: {len(fatal_errors)}개 치명적 오류")
        for error in fatal_errors:
            print(f"  ❌ {error}")
        print()
        print("=" * 80)
        sys.exit(2)

    if all_warnings:
        log("WARN", f"경고: {len(all_warnings)}개 경고 발생")
        for warning in all_warnings:
            print(f"  ⚠️  {warning}")
        print()
        log("WARN", "경고가 있지만 진행은 가능합니다")
        print("=" * 80)
        sys.exit(1)

    log("SUCCESS", "✅ 모든 검증 통과!")
    print("=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[사용자 중단]")
        sys.exit(130)
    except Exception as e:
        log("FATAL", f"예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
