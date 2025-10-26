#!/usr/bin/env python3
"""
from app.core.logging import get_logger
OCR 처리 모듈 - 스캔된 PDF 문서를 텍스트로 변환
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import time
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import pdfplumber
import hashlib
import json
import sqlite3
from datetime import datetime
import re

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)

class OCRProcessor:
    """PDF OCR 처리기"""

    def __init__(self, cache_dir: str = "./ocr_cache"):
        """
        Args:
            cache_dir: OCR 결과 캐시 디렉토리
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # SQLite 캐시 DB
        self.db_path = self.cache_dir / "ocr_cache.db"
        self._init_db()

        # Tesseract 설정 (한국어 + 영어)
        self.tesseract_config = '--oem 3 --psm 6'
        self.languages = 'kor+eng'

    def _init_db(self):
        """캐시 DB 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ocr_cache (
                file_hash TEXT PRIMARY KEY,
                file_path TEXT,
                text_content TEXT,
                is_scanned BOOLEAN,
                page_count INTEGER,
                extracted_at TIMESTAMP,
                metadata TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def _get_file_hash(self, file_path: str) -> str:
        """파일 해시 생성"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _check_cache(self, file_hash: str) -> Optional[Dict]:
        """캐시 확인"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT text_content, is_scanned, metadata
            FROM ocr_cache
            WHERE file_hash = ?
        ''', (file_hash,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'text': result[0],
                'is_scanned': result[1],
                'metadata': json.loads(result[2]) if result[2] else {}
            }
        return None

    def _save_cache(self, file_hash: str, file_path: str, text: str,
                    is_scanned: bool, page_count: int, metadata: Dict):
        """캐시 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO ocr_cache
            (file_hash, file_path, text_content, is_scanned, page_count, extracted_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_hash, file_path, text, is_scanned, page_count,
            datetime.now(), json.dumps(metadata, ensure_ascii=False)
        ))

        conn.commit()
        conn.close()

    def is_scanned_pdf(self, pdf_path: str) -> Tuple[bool, float]:
        """
        PDF가 스캔 문서인지 확인

        Returns:
            (is_scanned, confidence): 스캔 여부와 확신도(0-1)
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False, 0.0

                # 첫 3페이지만 샘플링
                sample_pages = pdf.pages[:min(3, len(pdf.pages))]

                total_chars = 0
                for page in sample_pages:
                    text = page.extract_text() or ""
                    total_chars += len(text.strip())

                # 페이지당 평균 문자 수
                avg_chars = total_chars / len(sample_pages)

                # 100자 미만이면 스캔으로 판단
                if avg_chars < 100:
                    confidence = 1.0 - (avg_chars / 100)
                    return True, confidence
                else:
                    return False, 0.0

        except Exception as e:
            logger.warning(f"스캔 여부 확인 실패: {e}")
            return False, 0.0

    def extract_with_ocr(self, pdf_path: str, force: bool = False) -> Dict:
        """
        PDF에서 OCR로 텍스트 추출

        Args:
            pdf_path: PDF 파일 경로
            force: 캐시 무시하고 강제 OCR

        Returns:
            추출 결과 딕셔너리
        """
        file_hash = self._get_file_hash(pdf_path)

        # 캐시 확인
        if not force:
            cached = self._check_cache(file_hash)
            if cached:
                logger.info(f"캐시에서 로드: {Path(pdf_path).name}")
                return cached

        logger.info(f"OCR 처리 시작: {Path(pdf_path).name}")
        start_time = time.time()

        # 먼저 일반 텍스트 추출 시도
        is_scanned, confidence = self.is_scanned_pdf(pdf_path)

        text_content = ""
        metadata = {
            'is_scanned': is_scanned,
            'scan_confidence': confidence,
            'ocr_used': False,
            'page_count': 0
        }

        try:
            if not is_scanned:
                # 일반 텍스트 추출
                with pdfplumber.open(pdf_path) as pdf:
                    metadata['page_count'] = len(pdf.pages)
                    for page in pdf.pages:
                        page_text = page.extract_text() or ""
                        text_content += page_text + "\n"

            else:
                # OCR 필요
                logger.info(f"스캔 문서 감지 (확신도: {confidence:.2f}), OCR 실행")
                metadata['ocr_used'] = True

                # PDF를 이미지로 변환
                with tempfile.TemporaryDirectory() as temp_dir:
                    images = convert_from_path(
                        pdf_path,
                        dpi=200,  # 적절한 해상도
                        output_folder=temp_dir,
                        thread_count=4
                    )

                    metadata['page_count'] = len(images)

                    # 각 페이지 OCR
                    for i, image in enumerate(images, 1):
                        logger.info(f"  페이지 {i}/{len(images)} OCR 처리 중...")

                        # 이미지 전처리 (선택적)
                        image = self._preprocess_image(image)

                        # OCR 실행
                        page_text = pytesseract.image_to_string(
                            image,
                            lang=self.languages,
                            config=self.tesseract_config
                        )

                        text_content += f"\n--- 페이지 {i} ---\n{page_text}\n"

        except Exception as e:
            logger.error(f"OCR 실패: {e}")
            metadata['error'] = str(e)

        # 텍스트 정리
        text_content = self._clean_text(text_content)

        # 처리 시간
        metadata['processing_time'] = time.time() - start_time
        logger.info(f"OCR 완료: {metadata['processing_time']:.2f}초")

        # 캐시 저장
        self._save_cache(
            file_hash, pdf_path, text_content,
            is_scanned, metadata['page_count'], metadata
        )

        return {
            'text': text_content,
            'is_scanned': is_scanned,
            'metadata': metadata
        }

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """이미지 전처리 (OCR 정확도 향상)"""
        # 그레이스케일 변환
        if image.mode != 'L':
            image = image.convert('L')

        # 추가 전처리 가능 (대비 조정, 노이즈 제거 등)
        return image

    def _clean_text(self, text: str) -> str:
        """텍스트 정리"""
        # 중복 공백 제거
        text = re.sub(r'\s+', ' ', text)

        # 중복 줄바꿈 제거
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 특수문자 정리
        text = text.replace('', '-')
        text = text.replace('', "'")

        return text.strip()

    def process_directory(self, directory: str, pattern: str = "*.pdf") -> Dict:
        """
        디렉토리 전체 OCR 처리

        Returns:
            처리 결과 통계
        """
        pdf_dir = Path(directory)
        pdf_files = list(pdf_dir.glob(pattern))

        stats = {
            'total': len(pdf_files),
            'scanned': 0,
            'ocr_processed': 0,
            'cached': 0,
            'errors': 0
        }

        logger.info(f"총 {stats['total']}개 PDF 처리 시작")

        for pdf_path in pdf_files:
            try:
                result = self.extract_with_ocr(str(pdf_path))

                if result['is_scanned']:
                    stats['scanned'] += 1

                if result['metadata'].get('ocr_used'):
                    stats['ocr_processed'] += 1
                elif result.get('text'):
                    stats['cached'] += 1

            except Exception as e:
                logger.error(f"처리 실패 {pdf_path.name}: {e}")
                stats['errors'] += 1

        return stats

    def get_cache_stats(self) -> Dict:
        """캐시 통계"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_scanned THEN 1 ELSE 0 END) as scanned,
                AVG(page_count) as avg_pages
            FROM ocr_cache
        ''')

        result = cursor.fetchone()
        conn.close()

        return {
            'total_cached': result[0],
            'scanned_docs': result[1],
            'avg_pages': result[2] or 0
        }


# 테스트 및 통합 함수
def test_ocr():
    """OCR 기능 테스트"""
    ocr = OCRProcessor()

    # 캐시 통계
    stats = ocr.get_cache_stats()
    print(f"캐시 통계: {stats}")

    # 테스트 PDF가 있다면
    test_pdf = "./test_data/sample.pdf"
    if Path(test_pdf).exists():
        result = ocr.extract_with_ocr(test_pdf)
        print(f"스캔 문서: {result['is_scanned']}")
        print(f"텍스트 길이: {len(result['text'])}")
        print(f"메타데이터: {result['metadata']}")

    return ocr


if __name__ == "__main__":
    test_ocr()