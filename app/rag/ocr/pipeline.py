#!/usr/bin/env python3
"""
OCR 파이프라인 공통 모듈 (v2.0)
모든 OCR 작업에서 재사용

v2.0 변경사항:
- PaddleOCR 엔진 추가 (한국어 정확도 향상)
- engine 파라미터로 Tesseract/PaddleOCR 선택 가능
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pytesseract
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

# PaddleOCR 전역 인스턴스 (thread-safe lazy loading)
_paddle_ocr_instance = None
_paddle_ocr_lock = threading.Lock()


def _get_paddleocr():
    """PaddleOCR 인스턴스 반환 (thread-safe 싱글톤)"""
    global _paddle_ocr_instance
    if _paddle_ocr_instance is None:
        with _paddle_ocr_lock:
            # Double-check locking pattern
            if _paddle_ocr_instance is None:
                from paddleocr import PaddleOCR
                logger.info("PaddleOCR 초기화 중...")
                _paddle_ocr_instance = PaddleOCR(
                    use_textline_orientation=True,
                    lang="korean"
                )
    return _paddle_ocr_instance


def ocr_extract_pdf(
    pdf_path: Path,
    dpi: int = 300,
    lang: str = "kor+eng",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    engine: Literal["tesseract", "paddleocr"] = "paddleocr"
) -> str:
    """PDF를 OCR로 텍스트 추출

    Args:
        pdf_path: PDF 파일 경로
        dpi: 이미지 변환 해상도 (기본 300)
        lang: Tesseract 언어 (기본 kor+eng, paddleocr는 무시)
        progress_callback: 진행 상황 콜백 (optional)
        engine: OCR 엔진 선택 ("tesseract" 또는 "paddleocr", 기본 paddleocr)

    Returns:
        추출된 텍스트 (페이지별 구분)

    Raises:
        FileNotFoundError: PDF 파일이 없을 때
        RuntimeError: OCR 실패 시
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일 없음: {pdf_path}")

    try:
        logger.info(f"OCR 추출 시작: {pdf_path.name} (engine={engine}, dpi={dpi})")

        # PDF → 이미지 변환
        images = convert_from_path(str(pdf_path), dpi=dpi)

        # 엔진별 OCR 수행
        if engine == "paddleocr":
            return _ocr_with_paddleocr(images, progress_callback)
        else:
            return _ocr_with_tesseract(images, lang, progress_callback)

    except Exception as e:
        logger.error(f"OCR 실패: {pdf_path.name} - {e}")
        raise RuntimeError(f"OCR 실패: {e}") from e


def _ocr_with_tesseract(
    images,
    lang: str,
    progress_callback: Optional[Callable[[int, int], None]]
) -> str:
    """Tesseract OCR 수행"""
    text_pages = []
    for i, image in enumerate(images, 1):
        logger.debug(f"  페이지 {i}/{len(images)} OCR 중 (Tesseract)...")

        if progress_callback:
            progress_callback(i, len(images))

        text = pytesseract.image_to_string(image, lang=lang)
        if text.strip():
            text_pages.append(f"[OCR 페이지 {i}]\n{text}")

    full_text = "\n\n".join(text_pages)
    logger.info(f"Tesseract OCR 완료: {len(full_text):,}자 추출")
    return full_text


def _ocr_with_paddleocr(
    images,
    progress_callback: Optional[Callable[[int, int], None]]
) -> str:
    """PaddleOCR 수행"""
    ocr = _get_paddleocr()
    text_pages = []

    for i, image in enumerate(images, 1):
        logger.debug(f"  페이지 {i}/{len(images)} OCR 중 (PaddleOCR)...")

        if progress_callback:
            progress_callback(i, len(images))

        # PIL Image → numpy array
        img_array = np.array(image)

        # OCR 실행
        result = ocr.predict(img_array)

        # rec_texts에서 텍스트 추출
        if result and len(result) > 0:
            rec_texts = result[0]["rec_texts"]
            if rec_texts:
                page_text = "\n".join(rec_texts)
                text_pages.append(f"[OCR 페이지 {i}]\n{page_text}")

    full_text = "\n\n".join(text_pages)
    logger.info(f"PaddleOCR 완료: {len(full_text):,}자 추출")
    return full_text


def update_document_text(
    db_path: str,
    filename: str,
    full_text: str,
    use_transaction: bool = True
) -> bool:
    """documents 테이블의 text_preview 업데이트

    Args:
        db_path: DB 파일 경로
        filename: 문서 파일명
        full_text: OCR 추출 텍스트
        use_transaction: 트랜잭션 사용 여부

    Returns:
        업데이트 성공 여부

    Note:
        - documents 테이블 업데이트 → FTS5 자동 동기화됨 (트리거)
        - v2.1: sqlite_helpers.connect_metadata() 사용
    """
    from app.utils.sqlite_helpers import connect_metadata

    conn = None
    try:
        conn = connect_metadata(db_path, enable_row_factory=False)

        if use_transaction:
            conn.execute("BEGIN IMMEDIATE")

        conn.execute(
            """
            UPDATE documents
            SET text_preview = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE filename = ?
            """,
            (full_text, filename),
        )

        if use_transaction:
            conn.commit()

        logger.info(f"DB 업데이트 완료: {filename} ({len(full_text):,}자)")
        return True

    except Exception as e:
        logger.error(f"DB 업데이트 실패: {filename} - {e}")
        if conn and use_transaction:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if conn:
            conn.close()
