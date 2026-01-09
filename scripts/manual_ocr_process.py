#!/usr/bin/env python3
"""
수동 OCR 처리 스크립트
rejected 폴더의 PDF 파일을 OCR 처리하여 metadata.db에 추가

PyMuPDF(fitz)를 사용하여 poppler 없이 PDF를 이미지로 변환
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import pdfplumber
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_text_simple(pdf_path: Path) -> tuple[str, dict]:
    """pdfplumber로 텍스트 추출 (OCR 없이)"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_pages.append(text)

            full_text = "\n\n".join(text_pages)
            metadata = {
                "page_count": len(pdf.pages),
                "file_size": pdf_path.stat().st_size,
            }

            logger.info(f"추출된 텍스트 길이: {len(full_text)} 문자")
            logger.info(f"페이지 수: {metadata['page_count']}")
            if metadata['page_count'] > 0:
                logger.info(f"페이지당 평균: {len(full_text) / metadata['page_count']:.0f} 문자")

            return full_text, metadata
    except Exception as e:
        logger.error(f"추출 실패: {e}")
        return "", {}


def ocr_extract_with_pymupdf(pdf_path: Path) -> tuple[str, dict]:
    """PyMuPDF + Tesseract를 사용한 OCR 추출 (poppler 불필요)"""
    try:
        logger.info("PyMuPDF를 사용한 OCR 추출 시작...")

        doc = fitz.open(pdf_path)
        text_pages = []
        page_count = len(doc)

        for page_num, page in enumerate(doc, start=1):
            logger.info(f"페이지 {page_num}/{page_count} OCR 처리 중...")

            # PDF 페이지를 이미지로 변환 (300 DPI)
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))

            # PIL Image로 변환
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Tesseract OCR 실행 (한글+영어)
            text = pytesseract.image_to_string(img, lang='kor+eng')
            text_pages.append(text)

            logger.info(f"  → {len(text)} 문자 추출됨")

        doc.close()

        full_text = "\n\n".join(text_pages)
        metadata = {
            "page_count": page_count,
            "file_size": pdf_path.stat().st_size,
        }

        logger.info(f"OCR 완료: 총 {len(full_text)} 문자 추출됨")
        return full_text, metadata

    except Exception as e:
        logger.error(f"OCR 추출 실패: {e}", exc_info=True)
        return "", {}


def update_metadata_db(filename: str, text: str, metadata: dict):
    """metadata.db 업데이트"""
    try:
        from app.data.metadata_db import MetadataDB
        import re

        db = MetadataDB(db_path="metadata.db")

        # 기존 레코드가 있는지 확인
        existing = db.get_document(filename)

        if existing:
            # 업데이트
            logger.info(f"기존 레코드 업데이트: {filename}")
            conn = db._get_conn()
            conn.execute(
                """
                UPDATE documents
                SET text_preview = ?, page_count = ?
                WHERE filename = ?
                """,
                (text[:5000], metadata.get("page_count", 0), filename)
            )
            conn.commit()
        else:
            # 새로 삽입
            logger.info(f"새 레코드 삽입: {filename}")
            # 파일명에서 날짜 추출
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
            date = date_match.group(1) if date_match else None

            # 직접 INSERT (upsert_document 메서드가 없을 수 있음)
            conn = db._get_conn()
            conn.execute(
                """
                INSERT INTO documents (filename, path, text_preview, page_count, date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filename, f"docs/rejected/{filename}", text[:5000], metadata.get("page_count", 0), date)
            )
            conn.commit()

        logger.info("✅ metadata.db 업데이트 완료")

    except Exception as e:
        logger.error(f"DB 업데이트 실패: {e}", exc_info=True)


def main():
    pdf_path = Path("/home/user/Desktop/AI/AI-CHAT/docs/rejected/2018-06-27_마스터_싱크제너레이터_구매_건.pdf")

    if not pdf_path.exists():
        logger.error(f"파일을 찾을 수 없습니다: {pdf_path}")
        return

    logger.info(f"파일 처리 시작: {pdf_path.name}")

    # 1단계: 일반 텍스트 추출 시도
    text, metadata = extract_text_simple(pdf_path)

    if not text or len(text) < 100:
        logger.warning("텍스트가 부족합니다. OCR을 실행합니다...")

        # 2단계: PyMuPDF + OCR
        text, metadata = ocr_extract_with_pymupdf(pdf_path)

    if text:
        logger.info("=" * 80)
        logger.info("추출된 텍스트 미리보기 (처음 1000자):")
        logger.info("=" * 80)
        print(text[:1000])
        logger.info("=" * 80)

        # 전체 텍스트 저장 (rejected 폴더 + extracted 폴더)
        output_path = pdf_path.with_suffix(".txt")
        output_path.write_text(text, encoding="utf-8")
        logger.info(f"전체 텍스트 저장: {output_path}")

        # extracted 폴더에도 복사
        extracted_path = Path("data/extracted") / output_path.name
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(text, encoding="utf-8")
        logger.info(f"extracted 폴더에도 저장: {extracted_path}")

        # metadata.db 업데이트
        update_metadata_db(pdf_path.name, text, metadata)

        logger.info("✅ 처리 완료!")
    else:
        logger.error("❌ 텍스트 추출 실패")


if __name__ == "__main__":
    main()
