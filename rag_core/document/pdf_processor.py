"""
PDF 문서 처리 모듈
==================

PDF 파일의 텍스트 추출, OCR, 메타데이터 추출을 담당합니다.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pdfplumber
import PyPDF2
from datetime import datetime
import re

from ..exceptions import PDFExtractionException, handle_errors
from ..config import RAGConfig

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF 문서 처리 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.ocr_processor = None
        if config.ocr_enabled:
            self._init_ocr()

    def _init_ocr(self) -> None:
        """OCR 프로세서 초기화"""
        try:
            from ..utils.ocr import OCRProcessor
            self.ocr_processor = OCRProcessor(self.config)
        except ImportError:
            logger.warning("OCR module not available")

    @handle_errors(default_return="")
    def extract_text(self, file_path: Path) -> str:
        """
        PDF 파일에서 텍스트 추출

        Args:
            file_path: PDF 파일 경로

        Returns:
            추출된 텍스트

        Raises:
            PDFExtractionException: 텍스트 추출 실패 시
        """
        try:
            # pdfplumber로 시도
            text = self._extract_with_pdfplumber(file_path)
            if text and len(text.strip()) > 50:
                return text

            # PyPDF2로 재시도
            text = self._extract_with_pypdf2(file_path)
            if text and len(text.strip()) > 50:
                return text

            # OCR로 최종 시도
            if self.ocr_processor:
                text = self.ocr_processor.extract_text(file_path)
                if text:
                    return text

            raise PDFExtractionException(f"Failed to extract text from {file_path}")

        except Exception as e:
            logger.error(f"PDF extraction failed for {file_path}: {e}")
            raise PDFExtractionException(str(e))

    def _extract_with_pdfplumber(self, file_path: Path) -> str:
        """pdfplumber를 사용한 텍스트 추출"""
        text_parts = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"pdfplumber extraction failed: {e}")
            return ""

    def _extract_with_pypdf2(self, file_path: Path) -> str:
        """PyPDF2를 사용한 텍스트 추출"""
        text_parts = []
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"PyPDF2 extraction failed: {e}")
            return ""

    @handle_errors(default_return={})
    def extract_metadata(self, file_path: Path) -> Dict:
        """
        PDF 메타데이터 추출

        Args:
            file_path: PDF 파일 경로

        Returns:
            메타데이터 딕셔너리
        """
        metadata = {
            'filename': file_path.name,
            'path': str(file_path),
            'size': file_path.stat().st_size,
            'modified': datetime.fromtimestamp(file_path.stat().st_mtime),
            'pages': 0,
            'title': '',
            'author': '',
            'subject': ''
        }

        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                metadata['pages'] = len(pdf_reader.pages)

                if pdf_reader.metadata:
                    metadata['title'] = pdf_reader.metadata.get('/Title', '')
                    metadata['author'] = pdf_reader.metadata.get('/Author', '')
                    metadata['subject'] = pdf_reader.metadata.get('/Subject', '')

        except Exception as e:
            logger.debug(f"Metadata extraction failed: {e}")

        # 파일명에서 추가 정보 추출
        metadata.update(self._parse_filename(file_path.name))

        return metadata

    def _parse_filename(self, filename: str) -> Dict:
        """파일명에서 정보 추출"""
        info = {}

        # 날짜 패턴 (YYYY-MM-DD)
        date_match = re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})', filename)
        if date_match:
            info['date'] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

        # 연도 추출
        year_match = re.search(r'20\d{2}', filename)
        if year_match:
            info['year'] = year_match.group()

        # 카테고리 추출
        if '구매' in filename:
            info['category'] = 'purchase'
        elif '수리' in filename:
            info['category'] = 'repair'
        elif '폐기' in filename:
            info['category'] = 'disposal'
        elif '검토' in filename:
            info['category'] = 'review'

        return info

    def process_batch(self, file_paths: List[Path]) -> List[Dict]:
        """
        여러 PDF 파일 일괄 처리

        Args:
            file_paths: PDF 파일 경로 리스트

        Returns:
            처리 결과 리스트
        """
        results = []
        for file_path in file_paths:
            try:
                text = self.extract_text(file_path)
                metadata = self.extract_metadata(file_path)
                results.append({
                    'path': file_path,
                    'text': text,
                    'metadata': metadata,
                    'success': True
                })
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results.append({
                    'path': file_path,
                    'error': str(e),
                    'success': False
                })
        return results