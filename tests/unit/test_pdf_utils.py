"""
PDF 유틸리티 보안 기능 테스트
디렉터리 트래버설 차단 및 PDF 파일 접근 테스트
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# Streamlit import 전에 환경 변수 설정 (테스트 모드)
os.environ["TESTING"] = "true"

# Mock 관련 import
from unittest.mock import MagicMock, Mock, patch

# conftest.py에서 설정한 streamlit mock 참조 (덮어쓰지 않음)
st_mock = sys.modules["streamlit"]

# pdf_viewer mock 설정 (아직 없으면)
if "components.pdf_viewer" not in sys.modules:
    sys.modules["components.pdf_viewer"] = Mock()

# 이제 pdf_utils import
from utils import pdf_utils


class TestPDFUtils:
    """PDF 유틸리티 보안 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """각 테스트 전에 DOCS_ROOT 설정"""
        # 임시 디렉터리를 DOCS_ROOT로 설정
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_pdf_utils_"))
        monkeypatch.setattr(pdf_utils, "DOCS_ROOT", self.temp_dir)

        # 테스트 디렉터리 구조 생성
        (self.temp_dir / "year_2024").mkdir()
        (self.temp_dir / "year_2024" / "test.pdf").touch()
        (self.temp_dir / "year_2024" / "report.pdf").touch()
        (self.temp_dir / "year_2023").mkdir()
        (self.temp_dir / "year_2023" / "old.pdf").touch()

        # PDF가 아닌 파일
        (self.temp_dir / "year_2024" / "data.txt").touch()

        # 외부 디렉터리
        self.external_dir = Path(tempfile.mkdtemp(prefix="test_external_"))
        (self.external_dir / "secret.pdf").touch()

        yield

        # 정리
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.external_dir, ignore_errors=True)

    def test_safe_path_relative_success(self):
        """정상적인 상대경로 처리"""
        result = pdf_utils.safe_path("year_2024/test.pdf")

        assert result is not None
        assert result.is_absolute()
        assert result.name == "test.pdf"
        assert result.exists()

    def test_safe_path_absolute_within_docs(self):
        """DOCS_ROOT 내부 절대경로 허용"""
        abs_path = self.temp_dir / "year_2024" / "test.pdf"
        result = pdf_utils.safe_path(str(abs_path))

        assert result == abs_path
        assert result.exists()

    def test_safe_path_traversal_blocked(self):
        """디렉터리 트래버설 차단"""
        with pytest.raises(ValueError, match="허용 범위 밖"):
            pdf_utils.safe_path("../secret.pdf")

        with pytest.raises(ValueError, match="허용 범위 밖"):
            pdf_utils.safe_path("year_2024/../../secret.pdf")

    def test_safe_path_external_absolute_blocked(self):
        """외부 절대경로 차단"""
        external_file = self.external_dir / "secret.pdf"

        with pytest.raises(ValueError, match="허용 범위 밖"):
            pdf_utils.safe_path(str(external_file))

    def test_safe_path_non_pdf_blocked(self):
        """PDF가 아닌 파일 차단"""
        with pytest.raises(ValueError, match="PDF 파일만 허용"):
            pdf_utils.safe_path("year_2024/data.txt")

    def test_safe_path_nonexistent_file(self):
        """존재하지 않는 파일 처리"""
        with pytest.raises(FileNotFoundError, match="파일을 찾을 수 없습니다"):
            pdf_utils.safe_path("year_2024/missing.pdf")

    def test_safe_path_must_exist_false(self):
        """must_exist=False 옵션 테스트"""
        result = pdf_utils.safe_path("year_2024/future.pdf", must_exist=False)

        assert result is not None
        assert result.name == "future.pdf"
        assert not result.exists()

    def test_safe_path_directory_blocked(self):
        """디렉터리 경로 차단"""
        # 디렉터리에 .pdf 확장자 추가 (악의적 시도)
        fake_pdf_dir = self.temp_dir / "fake.pdf"
        fake_pdf_dir.mkdir()

        with pytest.raises(ValueError, match="파일이 아닌 경로"):
            pdf_utils.safe_path("fake.pdf")

        fake_pdf_dir.rmdir()

    def test_load_pdf_bytes_success(self):
        """PDF 바이트 로드 성공"""
        # 실제 PDF 헤더 작성
        pdf_file = self.temp_dir / "year_2024" / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest content")

        result = pdf_utils.load_pdf_bytes("year_2024/test.pdf")

        assert result == b"%PDF-1.4\ntest content"

    def test_load_pdf_bytes_cache_behavior(self):
        """캐싱 동작 확인"""
        pdf_file = self.temp_dir / "year_2024" / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\noriginal")

        # 첫 번째 로드
        result1 = pdf_utils.load_pdf_bytes("year_2024/test.pdf")
        assert result1 == b"%PDF-1.4\noriginal"

        # 파일 내용 변경 (캐시가 작동한다면 이전 값이 반환됨)
        # 참고: 실제 streamlit 캐시는 모킹되어 있어 캐시가 작동하지 않음
        pdf_file.write_bytes(b"%PDF-1.4\nmodified")

        # 두 번째 로드 (모킹 환경에서는 새 값 반환)
        result2 = pdf_utils.load_pdf_bytes("year_2024/test.pdf")
        assert result2 == b"%PDF-1.4\nmodified"

    def test_download_pdf_button_success(self):
        """다운로드 버튼 성공 케이스"""
        pdf_file = self.temp_dir / "year_2024" / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        # Mock download_button 설정
        st_mock.download_button.return_value = True

        result = pdf_utils.download_pdf_button("year_2024/test.pdf")

        assert result is True
        st_mock.download_button.assert_called_once()

    def test_download_pdf_button_file_not_found(self):
        """다운로드 버튼 - 파일 없음"""
        result = pdf_utils.download_pdf_button("year_2024/missing.pdf")

        assert result is False
        st_mock.warning.assert_called()

    def test_download_pdf_button_traversal_blocked(self):
        """다운로드 버튼 - 디렉터리 트래버설 차단"""
        result = pdf_utils.download_pdf_button("../../../etc/passwd")

        assert result is False
        st_mock.error.assert_called()

    def test_validate_year_folder(self):
        """연도 폴더 검증"""
        # 유효한 연도 폴더
        assert pdf_utils.validate_year_folder("year_2024") is True
        assert pdf_utils.validate_year_folder("year_2023") is True

        # 존재하지 않는 연도
        assert pdf_utils.validate_year_folder("year_2025") is False

        # 잘못된 형식
        assert pdf_utils.validate_year_folder("invalid") is False
        assert pdf_utils.validate_year_folder("20a4") is False

    def test_list_pdf_files(self):
        """PDF 파일 목록 조회"""
        # 전체 PDF 파일
        all_pdfs = pdf_utils.list_pdf_files()
        assert len(all_pdfs) == 3
        assert all(p.suffix == ".pdf" for p in all_pdfs)

        # 특정 연도 폴더
        year_pdfs = pdf_utils.list_pdf_files("year_2024")
        assert len(year_pdfs) == 2
        assert all("year_2024" in str(p) for p in year_pdfs)

    def test_list_pdf_files_empty_directory(self):
        """빈 디렉터리 처리"""
        (self.temp_dir / "empty").mkdir()
        result = pdf_utils.list_pdf_files("empty")
        assert result == []

    def test_symlink_traversal_blocked(self):
        """심볼릭 링크를 통한 우회 차단"""
        # 심볼릭 링크 생성
        symlink = self.temp_dir / "year_2024" / "link_to_external.pdf"
        external_pdf = self.external_dir / "secret.pdf"

        try:
            symlink.symlink_to(external_pdf)

            # 심볼릭 링크를 통한 접근 차단
            with pytest.raises(ValueError, match="허용 범위 밖"):
                pdf_utils.safe_path("year_2024/link_to_external.pdf")

        finally:
            if symlink.exists():
                symlink.unlink()

    def test_case_insensitive_pdf_extension(self):
        """대소문자 구분 없는 PDF 확장자 처리"""
        # 대문자 확장자 파일 생성
        upper_pdf = self.temp_dir / "year_2024" / "UPPER.PDF"
        upper_pdf.touch()

        # 정상 처리되어야 함
        result = pdf_utils.safe_path("year_2024/UPPER.PDF")
        assert result.name == "UPPER.PDF"

    def test_unicode_filename_support(self):
        """유니코드(한글) 파일명 지원"""
        korean_pdf = self.temp_dir / "year_2024" / "한글파일명.pdf"
        korean_pdf.touch()

        result = pdf_utils.safe_path("year_2024/한글파일명.pdf")
        assert result.name == "한글파일명.pdf"
        assert result.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
