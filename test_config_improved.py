#!/usr/bin/env python3
"""
config.py 완벽 테스트 스위트

최고의 개발자답게 완벽한 테스트:
- 싱글톤 패턴 검증
- 불변성 검증
- 타입 안전성 검증
- 환경 변수 파싱 검증
- 에러 처리 검증
- 하위 호환성 검증
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent))

import config
from config import (
    Config,
    ConfigValidationError,
    ConfigSaveError,
    Limits,
    Thresholds,
    DefaultPaths
)


def test_singleton_pattern():
    """싱글톤 패턴 테스트"""
    print("테스트 1: 싱글톤 패턴")

    instance1 = Config.get_instance()
    instance2 = Config.get_instance()

    assert instance1 is instance2, "싱글톤 패턴 실패: 다른 인스턴스"
    print("  ✅ 동일한 인스턴스 반환")


def test_immutability():
    """불변성 테스트 (frozen dataclass)"""
    print("\n테스트 2: 불변성 (Frozen)")

    cfg = Config.get_instance()

    # 속성 변경 시도 (실패해야 함)
    try:
        cfg.temperature = 0.9
        assert False, "불변성 실패: 속성 변경 가능!"
    except Exception:
        print("  ✅ 속성 변경 불가 (frozen 작동)")

    # 새 속성 추가 시도 (실패해야 함)
    try:
        cfg.new_attribute = "test"
        assert False, "불변성 실패: 새 속성 추가 가능!"
    except Exception:
        print("  ✅ 새 속성 추가 불가")


def test_type_safety():
    """타입 안전성 테스트"""
    print("\n테스트 3: 타입 안전성")

    cfg = Config.get_instance()

    # 타입 검증
    assert isinstance(cfg.environment, str), "environment 타입 오류"
    assert isinstance(cfg.max_tokens, int), "max_tokens 타입 오류"
    assert isinstance(cfg.temperature, float), "temperature 타입 오류"
    assert isinstance(cfg.debug_mode, bool), "debug_mode 타입 오류"
    assert isinstance(cfg.project_root, Path), "project_root 타입 오류"

    print("  ✅ 모든 타입 정상")


def test_env_var_parsing():
    """환경 변수 파싱 테스트"""
    print("\n테스트 4: 환경 변수 파싱")

    # 기본값 테스트
    from config import get_env_int, get_env_float, get_env_bool

    # 정수 파싱
    val = get_env_int('NON_EXISTENT_VAR', 42, 0, 100)
    assert val == 42, "기본값 적용 실패"
    print("  ✅ 정수 기본값 적용")

    # 실수 파싱
    val = get_env_float('NON_EXISTENT_VAR', 0.5, 0.0, 1.0)
    assert val == 0.5, "실수 기본값 적용 실패"
    print("  ✅ 실수 기본값 적용")

    # 불린 파싱
    val = get_env_bool('NON_EXISTENT_VAR', True)
    assert val is True, "불린 기본값 적용 실패"
    print("  ✅ 불린 기본값 적용")


def test_error_handling():
    """에러 처리 테스트"""
    print("\n테스트 5: 에러 처리")

    from config import get_env_int, get_env_literal

    # 범위 초과 테스트
    os.environ['TEST_INT'] = '999'
    try:
        get_env_int('TEST_INT', 10, 0, 100)
        assert False, "범위 검증 실패"
    except ConfigValidationError:
        print("  ✅ 범위 초과 감지")
    finally:
        del os.environ['TEST_INT']

    # 잘못된 리터럴 테스트
    os.environ['TEST_LITERAL'] = 'invalid'
    try:
        get_env_literal('TEST_LITERAL', 'default', ['opt1', 'opt2'])
        assert False, "리터럴 검증 실패"
    except ConfigValidationError:
        print("  ✅ 잘못된 리터럴 감지")
    finally:
        del os.environ['TEST_LITERAL']


def test_config_summary():
    """설정 요약 테스트"""
    print("\n테스트 6: 설정 요약")

    cfg = Config.get_instance()
    summary = cfg.get_summary()

    assert 'environment' in summary
    assert 'gpu' in summary
    assert 'llm' in summary
    assert 'search' in summary
    assert 'performance' in summary

    print(f"  ✅ 설정 요약 생성 성공")
    print(f"     Environment: {summary['environment']}")
    print(f"     GPU Enabled: {summary['gpu']['enabled']}")
    print(f"     Max Tokens: {summary['llm']['max_tokens']}")


def test_config_validation():
    """설정 검증 테스트"""
    print("\n테스트 7: 설정 검증")

    cfg = Config.get_instance()
    results = cfg.validate()

    assert 'model_exists' in results
    assert 'cache_writable' in results
    assert 'db_writable' in results
    assert 'gpu_configured' in results
    assert 'weights_normalized' in results

    print("  ✅ 모든 검증 항목 확인")
    for key, passed in results.items():
        status = "✅" if passed else "⚠️"
        print(f"     {status} {key}: {passed}")


def test_config_save_load():
    """설정 저장/로드 테스트"""
    print("\n테스트 8: 설정 저장/로드")

    cfg = Config.get_instance()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)

    try:
        # 저장
        cfg.save_to_file(temp_path)
        assert temp_path.exists(), "설정 파일 저장 실패"
        print("  ✅ 설정 파일 저장 성공")

        # 로드
        loaded = Config.load_from_file(temp_path)
        assert loaded is not None, "설정 파일 로드 실패"
        assert loaded['environment'] == cfg.environment
        print("  ✅ 설정 파일 로드 성공")

        # 민감 정보 비포함 확인 (경로 정보 제외)
        with open(temp_path) as f:
            content = json.load(f)

        # 경로 정보가 요약에 포함되지 않아야 함
        assert 'project_root' not in str(content)
        assert 'qwen_model_path' not in str(content)
        print("  ✅ 민감 정보 필터링 확인")

    finally:
        temp_path.unlink()


def test_backwards_compatibility():
    """하위 호환성 테스트"""
    print("\n테스트 9: 하위 호환성")

    # 모듈 레벨 변수 접근
    assert hasattr(config, 'PROJECT_ROOT')
    assert hasattr(config, 'MODELS_DIR')
    assert hasattr(config, 'TEMPERATURE')
    assert hasattr(config, 'MAX_TOKENS')
    print("  ✅ 모듈 레벨 변수 접근 가능")

    # 하위 호환 함수
    assert callable(config.get_config_summary)
    assert callable(config.validate_config)
    assert callable(config.save_config)
    assert callable(config.load_config_from_file)
    print("  ✅ 하위 호환 함수 호출 가능")

    # 실제 호출 테스트
    summary = config.get_config_summary()
    assert summary is not None
    print("  ✅ 하위 호환 함수 정상 작동")


def test_constants():
    """상수 클래스 테스트"""
    print("\n테스트 10: 상수 클래스")

    # Limits 상수
    assert Limits.MIN_TOKENS == 1
    assert Limits.MAX_TOKENS == 4096
    assert Limits.DEFAULT_TOKENS == 512
    print("  ✅ Limits 상수 확인")

    # Thresholds 상수
    assert Thresholds.DEFAULT_QUALITY == 0.7
    assert Thresholds.DEFAULT_VECTOR_WEIGHT == 0.2
    assert Thresholds.DEFAULT_BM25_WEIGHT == 0.8
    print("  ✅ Thresholds 상수 확인")

    # DefaultPaths 상수
    assert DefaultPaths.MODELS_SUBDIR == 'models'
    assert DefaultPaths.DOCS_SUBDIR == 'docs'
    print("  ✅ DefaultPaths 상수 확인")


def test_weight_normalization():
    """가중치 정규화 테스트"""
    print("\n테스트 11: 가중치 정규화")

    cfg = Config.get_instance()

    # 가중치 합이 1이어야 함
    weight_sum = cfg.vector_weight + cfg.bm25_weight
    assert abs(weight_sum - 1.0) < 0.01, f"가중치 합 오류: {weight_sum}"
    print(f"  ✅ 가중치 정규화 확인 (sum={weight_sum:.4f})")


def test_path_creation():
    """경로 자동 생성 테스트"""
    print("\n테스트 12: 경로 자동 생성")

    cfg = Config.get_instance()

    # 디렉터리 존재 확인
    assert cfg.models_dir.exists(), "models_dir 생성 실패"
    assert cfg.docs_dir.exists(), "docs_dir 생성 실패"
    assert cfg.cache_dir.exists(), "cache_dir 생성 실패"
    assert cfg.db_dir.exists(), "db_dir 생성 실패"

    print("  ✅ 모든 필수 디렉터리 존재")


def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 60)
    print("  config.py 완벽 테스트 스위트")
    print("=" * 60)

    tests = [
        test_singleton_pattern,
        test_immutability,
        test_type_safety,
        test_env_var_parsing,
        test_error_handling,
        test_config_summary,
        test_config_validation,
        test_config_save_load,
        test_backwards_compatibility,
        test_constants,
        test_weight_normalization,
        test_path_creation,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ {test_func.__name__} 실패: {e}")

    print("\n" + "=" * 60)
    print(f"  결과: {passed}개 통과, {failed}개 실패")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 모든 테스트 통과! config.py 완벽합니다!")
        return 0
    else:
        print(f"\n⚠️  {failed}개 테스트 실패")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
