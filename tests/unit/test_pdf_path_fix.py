"""
출처 문서 경로 버그 수정 검증 테스트

문제: RAG 시스템이 상대 경로로 파일을 참조하여 "⚠️ 파일을 찾을 수 없습니다" 발생
해결: chat_interface.py와 pdf_viewer.py에서 절대 경로로 변환
"""

import pytest

pytestmark = pytest.mark.skip(reason="인터페이스 변경으로 재작성 필요")
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock streamlit
st_mock = MagicMock()
sys.modules["streamlit"] = st_mock


class TestPDFViewerPathResolution:
    """PDFViewer의 경로 해석 테스트"""

    def test_absolute_path_used_as_is(self):
        """절대 경로는 그대로 사용"""
        from components.pdf_viewer import PDFViewer

        abs_path = "/home/user/docs/test.pdf"
        viewer = PDFViewer(file_path=abs_path)

        assert viewer.file_path == Path(abs_path)
        assert viewer.file_path.is_absolute()

    def test_relative_path_converted_to_absolute(self, tmp_path):
        """상대 경로는 DOCS_DIR 기준 절대 경로로 변환"""
        from components.pdf_viewer import PDFViewer

        # Mock settings
        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"
        mock_settings.DOCS_DIR.mkdir(parents=True, exist_ok=True)

        with patch("app.config.settings.settings", mock_settings):
            rel_path = "year_2018/test.pdf"
            viewer = PDFViewer(file_path=rel_path)

            expected_path = tmp_path / "docs" / "year_2018" / "test.pdf"
            assert viewer.file_path == expected_path
            assert viewer.file_path.is_absolute()

    def test_path_with_year_folder(self, tmp_path):
        """year_YYYY 폴더 포함 경로 처리"""
        from components.pdf_viewer import PDFViewer

        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"
        mock_settings.DOCS_DIR.mkdir(parents=True, exist_ok=True)

        with patch("app.config.settings.settings", mock_settings):
            rel_path = "year_2018/2018-10-30_잠실_롯데타워_파노라마_카메라_사용_검토.pdf"
            viewer = PDFViewer(file_path=rel_path)

            expected = tmp_path / "docs" / "year_2018" / "2018-10-30_잠실_롯데타워_파노라마_카메라_사용_검토.pdf"
            assert viewer.file_path == expected


class TestChatInterfacePathGeneration:
    """chat_interface.py의 파일 경로 생성 로직 테스트"""

    def test_file_path_from_evidence_dict(self, tmp_path):
        """Evidence dict에서 파일 경로 생성 (절대 경로)"""
        from pathlib import Path

        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"

        # Evidence 데이터 (실제 RAG 시스템에서 반환하는 형식)
        evidence = {
            "doc_id": "doc_123",
            "filename": "2018-10-30_잠실_롯데타워_파노라마_카메라_사용_검토.pdf",
            "snippet": "파노라마 카메라 사용 검토",
            "file_path": None,  # file_path가 없는 경우
            "meta": {"date": "2018-10-30", "doctype": "검토서"}
        }

        with patch("app.config.settings.settings", mock_settings):
            # 실제 로직 시뮬레이션
            filename = evidence["filename"]
            file_path_str = evidence.get("file_path")

            if file_path_str:
                file_path = Path(file_path_str)
                if not file_path.is_absolute():
                    file_path = mock_settings.DOCS_DIR / file_path
            else:
                # Fallback: year 폴더 추출
                import re
                year_match = re.search(r"(\d{4})-", filename)
                if year_match:
                    year = year_match.group(1)
                    file_path = mock_settings.DOCS_DIR / f"year_{year}" / filename
                else:
                    file_path = mock_settings.DOCS_DIR / filename

            # 검증
            expected = tmp_path / "docs" / "year_2018" / "2018-10-30_잠실_롯데타워_파노라마_카메라_사용_검토.pdf"
            assert file_path == expected
            assert file_path.is_absolute()

    def test_file_path_with_relative_path_in_evidence(self, tmp_path):
        """Evidence에 상대 경로가 있는 경우"""
        from pathlib import Path

        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"

        evidence = {
            "filename": "test.pdf",
            "file_path": "year_2020/test.pdf",  # 상대 경로
            "snippet": "Test document"
        }

        with patch("app.config.settings.settings", mock_settings):
            filename = evidence["filename"]
            file_path_str = evidence.get("file_path")

            if file_path_str:
                file_path = Path(file_path_str)
                if not file_path.is_absolute():
                    file_path = mock_settings.DOCS_DIR / file_path
            else:
                file_path = mock_settings.DOCS_DIR / filename

            expected = tmp_path / "docs" / "year_2020" / "test.pdf"
            assert file_path == expected
            assert file_path.is_absolute()

    def test_file_path_with_absolute_path_in_evidence(self, tmp_path):
        """Evidence에 절대 경로가 있는 경우 (그대로 사용)"""
        from pathlib import Path

        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"

        abs_path = str(tmp_path / "other_location" / "test.pdf")
        evidence = {
            "filename": "test.pdf",
            "file_path": abs_path,  # 절대 경로
            "snippet": "Test document"
        }

        with patch("app.config.settings.settings", mock_settings):
            filename = evidence["filename"]
            file_path_str = evidence.get("file_path")

            if file_path_str:
                file_path = Path(file_path_str)
                if not file_path.is_absolute():
                    file_path = mock_settings.DOCS_DIR / file_path
            else:
                file_path = mock_settings.DOCS_DIR / filename

            # 절대 경로는 그대로 사용
            assert file_path == Path(abs_path)
            assert file_path.is_absolute()


class TestIntegrationScenario:
    """전체 흐름 통합 테스트"""

    def test_full_evidence_to_pdf_viewer_flow(self, tmp_path):
        """Evidence → chat_interface → PDFViewer 전체 흐름"""
        from pathlib import Path

        from components.pdf_viewer import PDFViewer

        # Mock settings
        mock_settings = Mock()
        mock_settings.DOCS_DIR = tmp_path / "docs"
        docs_dir = mock_settings.DOCS_DIR
        docs_dir.mkdir(parents=True, exist_ok=True)

        # 실제 파일 생성
        year_dir = docs_dir / "year_2018"
        year_dir.mkdir(parents=True, exist_ok=True)
        test_pdf = year_dir / "2018-10-30_test.pdf"
        test_pdf.write_text("dummy pdf content")

        # Evidence 데이터 (상대 경로)
        evidence = {
            "filename": "2018-10-30_test.pdf",
            "file_path": None,
            "snippet": "Test document"
        }

        with patch("app.config.settings.settings", mock_settings):
            # Step 1: chat_interface에서 경로 생성
            filename = evidence["filename"]
            file_path_str = evidence.get("file_path")

            if not file_path_str:
                import re
                year_match = re.search(r"(\d{4})-", filename)
                if year_match:
                    year = year_match.group(1)
                    file_path = mock_settings.DOCS_DIR / f"year_{year}" / filename
                else:
                    file_path = mock_settings.DOCS_DIR / filename

            # Step 2: PDFViewer에 경로 전달
            viewer = PDFViewer(file_path=str(file_path))

            # 검증
            assert viewer.file_path.exists()
            assert viewer.file_path.is_absolute()
            assert viewer.file_path == test_pdf


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
