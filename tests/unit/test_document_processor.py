"""
Unit tests for Document Processor
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from rag_modules.document.processor import DocumentProcessor
from rag_modules.core.exceptions import PDFExtractionException

class TestDocumentProcessor:
    """DocumentProcessor 단위 테스트"""

    @pytest.fixture
    def processor(self):
        """프로세서 fixture"""
        return DocumentProcessor()

    def test_supported_formats(self, processor):
        """지원 포맷 확인 테스트"""
        assert '.pdf' in processor.supported_formats
        assert '.txt' in processor.supported_formats
        assert '.docx' in processor.supported_formats

    @patch('builtins.open', new_callable=mock_open, read_data='Test content')
    def test_extract_txt_text(self, mock_file, processor):
        """TXT 텍스트 추출 테스트"""
        # When
        result = processor._extract_txt_text(Path('test.txt'))

        # Then
        assert result == 'Test content'
        mock_file.assert_called_once_with(Path('test.txt'), 'r', encoding='utf-8')

    @patch('pdfplumber.open')
    def test_extract_pdf_text_success(self, mock_pdf, processor):
        """PDF 텍스트 추출 성공 테스트"""
        # Given
        mock_page = Mock()
        mock_page.extract_text.return_value = "Page content"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        # When
        result = processor._extract_pdf_text(Path('test.pdf'))

        # Then
        assert result == "Page content"

    @patch('pdfplumber.open')
    def test_extract_pdf_text_failure(self, mock_pdf, processor):
        """PDF 텍스트 추출 실패 테스트"""
        # Given
        mock_pdf.side_effect = Exception("PDF error")

        # When & Then
        with pytest.raises(PDFExtractionException):
            processor._extract_pdf_text(Path('test.pdf'))

    def test_extract_unsupported_format(self, processor):
        """지원하지 않는 포맷 테스트"""
        with pytest.raises(PDFExtractionException) as exc:
            processor.extract_text(Path('test.xyz'))
        assert "Unsupported format" in str(exc.value)
