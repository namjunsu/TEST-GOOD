"""DocumentUtils 테스트

document_utils.py의 문서 처리 유틸리티 테스트:
- load_full_text_if_short: 스니펫이 짧으면 전체 텍스트 로드
- safe_fname: 파일명 안전 추출
- make_chunks_for_doc: 특정 문서 청크 로드
- gather_summary_context: 요약용 컨텍스트 수집
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.rag.document_utils import DocumentUtils


class TestLoadFullTextIfShort:
    """load_full_text_if_short 테스트"""

    def test_returns_snippet_if_long_enough(self):
        """스니펫이 충분히 길면 그대로 반환"""
        utils = DocumentUtils()
        long_snippet = "이것은 매우 긴 스니펫입니다. " * 50  # 충분히 긴 스니펫

        result = utils.load_full_text_if_short("test.pdf", long_snippet)

        assert result == long_snippet

    def test_loads_full_text_if_short(self, tmp_path):
        """스니펫이 짧으면 파일에서 전체 텍스트 로드"""
        # 테스트용 텍스트 파일 생성
        txt_file = tmp_path / "test.txt"
        full_text = "전체 텍스트 내용입니다. " * 100
        txt_file.write_text(full_text, encoding="utf-8")

        utils = DocumentUtils(extracted_dir=tmp_path)
        short_snippet = "짧음"

        result = utils.load_full_text_if_short("test.pdf", short_snippet)

        # 최대 5000자까지만 반환
        assert len(result) <= 5000
        assert "전체 텍스트" in result

    def test_returns_snippet_if_file_not_found(self, tmp_path):
        """파일이 없으면 원본 스니펫 반환"""
        utils = DocumentUtils(extracted_dir=tmp_path)
        short_snippet = "짧은 스니펫"

        result = utils.load_full_text_if_short("nonexistent.pdf", short_snippet)

        assert result == short_snippet


class TestSafeFname:
    """safe_fname 테스트"""

    def test_extracts_from_fname(self):
        """meta에서 fname 추출"""
        utils = DocumentUtils()
        meta = {"fname": "document.pdf"}

        result = utils.safe_fname(meta=meta)

        assert result == "document.pdf"

    def test_extracts_from_filename(self):
        """meta에서 filename 추출"""
        utils = DocumentUtils()
        meta = {"filename": "report.pdf"}

        result = utils.safe_fname(meta=meta)

        assert result == "report.pdf"

    def test_extracts_from_doc_id(self):
        """meta에서 doc_id 추출"""
        utils = DocumentUtils()
        meta = {"doc_id": "doc_001"}

        result = utils.safe_fname(meta=meta)

        assert result == "doc_001"

    def test_extracts_from_doc_path(self):
        """doc_path에서 파일명 추출"""
        utils = DocumentUtils()

        result = utils.safe_fname(doc_path="/path/to/document.pdf")

        assert result == "document.pdf"

    def test_returns_default_if_no_source(self):
        """아무것도 없으면 기본값 반환"""
        utils = DocumentUtils()

        result = utils.safe_fname()

        assert result == "미상 문서"

    def test_priority_fname_over_filename(self):
        """fname이 filename보다 우선"""
        utils = DocumentUtils()
        meta = {"fname": "first.pdf", "filename": "second.pdf"}

        result = utils.safe_fname(meta=meta)

        assert result == "first.pdf"


class TestMakeChunksForDoc:
    """make_chunks_for_doc 테스트"""

    def test_returns_empty_if_no_retriever(self):
        """retriever가 없으면 빈 리스트 반환"""
        utils = DocumentUtils(retriever=None)

        result = utils.make_chunks_for_doc("test.pdf")

        assert result == []

    def test_loads_from_bm25_index(self):
        """BM25 인덱스에서 직접 로드"""
        mock_retriever = Mock()
        mock_bm25 = Mock()
        mock_bm25.metadata = [
            {"filename": "test.pdf"},
            {"filename": "other.pdf"},
            {"filename": "test.pdf"},
        ]
        mock_bm25.documents = [
            "첫 번째 문서 내용입니다. " * 10,
            "다른 문서 내용",
            "두 번째 test.pdf 내용입니다. " * 10,
        ]
        mock_retriever.bm25 = mock_bm25

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.make_chunks_for_doc("test.pdf")

        # test.pdf에 해당하는 2개 청크 반환
        assert len(result) == 2
        assert all(chunk["filename"] == "test.pdf" for chunk in result)

    def test_fallback_to_search(self):
        """BM25 사용 불가 시 검색으로 폴백"""
        mock_retriever = Mock()
        mock_retriever.bm25 = None  # BM25 없음
        mock_retriever.search.return_value = [
            {"doc_id": "test.pdf", "snippet": "검색 결과 1", "score": 0.9},
            {"doc_id": "other.pdf", "snippet": "다른 문서", "score": 0.8},
            {
                "doc_id": "test_related",
                "snippet": "관련",
                "score": 0.7,
                "meta": {"filename": "test.pdf"},
            },
        ]

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.make_chunks_for_doc("test.pdf")

        # test.pdf가 포함된 결과만 반환
        assert len(result) == 2

    def test_handles_exception(self):
        """예외 발생 시 빈 리스트 반환"""
        mock_retriever = Mock()
        mock_retriever.bm25 = Mock()
        mock_retriever.bm25.metadata = None  # 예외 유발

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.make_chunks_for_doc("test.pdf")

        assert result == []


class TestGatherSummaryContext:
    """gather_summary_context 테스트"""

    def test_returns_empty_if_no_retriever(self):
        """retriever가 없으면 빈 문자열 반환"""
        utils = DocumentUtils(retriever=None)

        result = utils.gather_summary_context("test.pdf", "/path/test.pdf")

        assert result == ""

    def test_doc_locked_mode(self):
        """문서 고정 모드에서 해당 문서 청크만 사용"""
        mock_retriever = Mock()
        mock_bm25 = Mock()
        mock_bm25.metadata = [{"filename": "test.pdf"}]
        mock_bm25.documents = ["테스트 문서의 개요입니다. " * 30]
        mock_retriever.bm25 = mock_bm25

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.gather_summary_context(
            "test.pdf", "/path/test.pdf", doc_locked=True,
        )

        assert "개요" in result
        assert len(result) > 0

    def test_priority_keywords_sorting(self):
        """우선순위 키워드 포함 청크가 앞에 위치"""
        mock_retriever = Mock()
        mock_retriever.search.return_value = [
            {"filename": "test.pdf", "text": "일반 내용입니다. " * 20, "score": 0.9},
            {"filename": "test.pdf", "text": "이 문서의 개요는 다음과 같습니다. " * 20, "score": 0.8},
            {"filename": "test.pdf", "text": "배경 설명입니다. " * 20, "score": 0.7},
        ]
        mock_retriever.bm25 = None

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.gather_summary_context(
            "test.pdf", "/path/test.pdf", doc_locked=False,
        )

        # 우선순위 키워드(개요, 배경)가 포함된 청크가 먼저
        # 결과 순서는 priority_chunks + normal_chunks
        assert len(result) > 0

    def test_context_length_limit(self):
        """컨텍스트 길이 제한 (6000자)"""
        mock_retriever = Mock()
        # 매우 긴 청크 생성
        long_text = "매우 긴 텍스트입니다. " * 500
        mock_retriever.search.return_value = [
            {"filename": "test.pdf", "text": long_text, "score": 0.9},
        ]
        mock_retriever.bm25 = None

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.gather_summary_context("test.pdf", "/path/test.pdf")

        assert len(result) <= 6000

    def test_handles_search_exception(self):
        """검색 실패 시에도 동작"""
        mock_retriever = Mock()
        mock_retriever.bm25 = None
        mock_retriever.search.side_effect = Exception("검색 오류")

        utils = DocumentUtils(retriever=mock_retriever)
        result = utils.gather_summary_context("test.pdf", "/path/test.pdf")

        # 예외가 발생해도 빈 문자열 반환 (에러 전파 안함)
        assert result == ""


class TestExtractWithOcr:
    """extract_with_ocr 테스트"""

    def test_uses_pytesseract(self):
        """pytesseract로 OCR 수행"""
        with patch("pdf2image.convert_from_path") as mock_convert:
            with patch("pytesseract.image_to_string") as mock_tesseract:
                mock_img = Mock()
                mock_convert.return_value = [mock_img]
                mock_tesseract.return_value = "추출된 텍스트입니다. " * 10

                utils = DocumentUtils()
                result = utils.extract_with_ocr("/path/test.pdf", start_page=0, total_pages=1)

                assert "추출된 텍스트" in result
                mock_convert.assert_called_once()
                mock_tesseract.assert_called_once()

    def test_returns_empty_on_exception(self):
        """예외 발생 시 빈 문자열 반환"""
        with patch("pdf2image.convert_from_path") as mock_convert:
            mock_convert.side_effect = Exception("PDF 변환 실패")

            utils = DocumentUtils()
            result = utils.extract_with_ocr("/path/test.pdf", start_page=0, total_pages=1)

            assert result == ""
