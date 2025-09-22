"""
Document processing module
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pdfplumber
from ..core.exceptions import PDFExtractionException

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """문서 처리 클래스"""

    def __init__(self):
        self.supported_formats = ['.pdf', '.txt', '.docx']

    def extract_text(self, file_path: Path) -> str:
        """문서에서 텍스트 추출"""
        if file_path.suffix == '.pdf':
            return self._extract_pdf_text(file_path)
        elif file_path.suffix == '.txt':
            return self._extract_txt_text(file_path)
        else:
            raise PDFExtractionException(f"Unsupported format: {file_path.suffix}")

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """PDF 텍스트 추출"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
                return '\n'.join(text)
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise PDFExtractionException(str(e))

    def _extract_txt_text(self, txt_path: Path) -> str:
        """TXT 텍스트 추출"""
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"TXT extraction failed: {e}")
            raise PDFExtractionException(str(e))
