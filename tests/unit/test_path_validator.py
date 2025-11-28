"""
Path Validator 보안 기능 테스트
디렉터리 트래버설 방지 및 경로 검증 테스트
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import os
import sys

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.path_validator import is_safe_path, validate_and_resolve_path


class TestPathValidator:
    """경로 검증 유틸리티 테스트"""

    @pytest.fixture
    def test_dir(self):
        """테스트용 임시 디렉터리 생성"""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_path_validator_"))

        # 테스트 파일/디렉터리 구조 생성
        (temp_dir / "docs").mkdir()
        (temp_dir / "docs" / "year_2024").mkdir()
        (temp_dir / "docs" / "year_2024" / "test.pdf").touch()
        (temp_dir / "data").mkdir()
        (temp_dir / "data" / "cache.txt").touch()

        # 심볼릭 링크 테스트용
        (temp_dir / "secret").mkdir()
        (temp_dir / "secret" / "password.txt").write_text("secret_data")

        yield temp_dir

        # 정리
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_is_safe_path_valid_subdirectory(self, test_dir):
        """정상적인 하위 디렉터리 접근"""
        base = test_dir / "docs"
        target = test_dir / "docs" / "year_2024" / "test.pdf"

        assert is_safe_path(base, target) is True

    def test_is_safe_path_outside_base(self, test_dir):
        """base_dir 외부 경로 차단"""
        base = test_dir / "docs"
        target = test_dir / "secret" / "password.txt"

        assert is_safe_path(base, target) is False

    def test_is_safe_path_traversal_attack(self, test_dir):
        """디렉터리 트래버설 공격 차단"""
        base = test_dir / "docs"

        # ../를 사용한 상위 디렉터리 접근 시도
        attack_path = test_dir / "docs" / ".." / ".." / "etc" / "passwd"
        assert is_safe_path(base, attack_path) is False

        # 실제로 존재하는 상위 경로로의 접근
        attack_path2 = test_dir / "docs" / ".." / "secret" / "password.txt"
        assert is_safe_path(base, attack_path2) is False

    def test_is_safe_path_nonexistent_base(self):
        """존재하지 않는 base_dir 처리"""
        base = Path("/nonexistent/base")
        target = Path("/nonexistent/base/file.txt")

        # strict=True로 인해 False 반환
        assert is_safe_path(base, target) is False

    def test_is_safe_path_symlink(self, test_dir):
        """심볼릭 링크를 통한 우회 차단"""
        base = test_dir / "docs"

        # 심볼릭 링크 생성 (외부 디렉터리 가리킴)
        symlink = test_dir / "docs" / "link_to_secret"
        symlink.symlink_to(test_dir / "secret")

        # 심볼릭 링크를 통한 접근 차단 확인
        target = symlink / "password.txt"
        assert is_safe_path(base, target) is False

        # 정리
        symlink.unlink()

    def test_validate_and_resolve_relative_path(self, test_dir):
        """상대경로 처리 및 정규화"""
        base = test_dir / "docs"

        # 상대경로를 base_dir 기준으로 처리
        result = validate_and_resolve_path("year_2024/test.pdf", base)

        assert result is not None
        assert result.is_absolute()
        assert result == (test_dir / "docs" / "year_2024" / "test.pdf").resolve()

    def test_validate_and_resolve_absolute_path(self, test_dir):
        """절대경로 검증"""
        base = test_dir / "docs"
        target_file = test_dir / "docs" / "year_2024" / "test.pdf"

        result = validate_and_resolve_path(str(target_file), base)

        assert result is not None
        assert result == target_file.resolve()

    def test_validate_and_resolve_fallback(self, test_dir):
        """fallback 파일명 처리"""
        base = test_dir / "docs" / "year_2024"

        # None 입력 시 fallback 사용
        result = validate_and_resolve_path(None, base, "test.pdf")

        assert result is not None
        assert result.name == "test.pdf"
        assert result == (test_dir / "docs" / "year_2024" / "test.pdf").resolve()

    def test_validate_and_resolve_traversal_blocked(self, test_dir):
        """디렉터리 트래버설 차단 확인"""
        base = test_dir / "docs"

        # 다양한 트래버설 패턴 차단
        attacks = [
            "../secret/password.txt",
            "../../secret/password.txt",
            "./../secret/password.txt",
            "year_2024/../../secret/password.txt",
        ]

        for attack in attacks:
            result = validate_and_resolve_path(attack, base)
            assert result is None, f"Failed to block: {attack}"

    def test_validate_and_resolve_must_exist_false(self, test_dir):
        """존재하지 않는 파일 허용 모드"""
        base = test_dir / "docs"

        # 존재하지 않는 파일이지만 must_exist=False
        result = validate_and_resolve_path(
            "new_file.txt", base, must_exist=False
        )

        assert result is not None
        assert result == (test_dir / "docs" / "new_file.txt").resolve()

    def test_validate_and_resolve_nonexistent_base(self):
        """존재하지 않는 base_dir 처리"""
        base = Path("/nonexistent/base")

        result = validate_and_resolve_path("file.txt", base)
        assert result is None

    def test_validate_and_resolve_empty_input(self, test_dir):
        """빈 입력 처리"""
        base = test_dir / "docs"

        # 파일명과 fallback 모두 None
        result = validate_and_resolve_path(None, base, None)
        assert result is None

    def test_real_world_rag_scenarios(self, test_dir):
        """실제 RAG 시스템 시나리오 테스트"""
        # 1. 문서 디렉터리 접근
        docs_base = test_dir / "docs"

        # 정상 문서 접근
        assert validate_and_resolve_path("year_2024/test.pdf", docs_base) is not None

        # 2. 캐시 디렉터리 격리
        cache_base = test_dir / "data"

        # 캐시는 data 디렉터리만 접근 가능
        assert validate_and_resolve_path("cache.txt", cache_base) is not None
        assert validate_and_resolve_path("../docs/year_2024/test.pdf", cache_base) is None

        # 3. 상대경로 자동 처리
        assert validate_and_resolve_path("year_2024/test.pdf", docs_base) is not None

    def test_security_boundary_cases(self, test_dir):
        """보안 경계 케이스 테스트"""
        base = test_dir / "docs"

        # 1. 빈 문자열
        result = validate_and_resolve_path("", base, must_exist=False)
        assert result == base.resolve()  # 빈 문자열은 base_dir 자체

        # 2. 현재 디렉터리 (.)
        result = validate_and_resolve_path(".", base, must_exist=False)
        assert result == base.resolve()

        # 3. 이중 슬래시
        result = validate_and_resolve_path("year_2024//test.pdf", base)
        assert result is not None  # 정규화되어 처리됨


if __name__ == "__main__":
    # 테스트 실행
    pytest.main([__file__, "-v", "--tb=short"])