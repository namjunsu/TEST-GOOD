#!/usr/bin/env python3
"""누락된 PDF 처리 스크립트

year_* 폴더에 있지만 DB에 없는 PDF들을 OCR 처리하여 DB에 추가합니다.

사용법:
    python scripts/ops/process_missing_pdfs.py
    python scripts/ops/process_missing_pdfs.py --dry-run
    python scripts/ops/process_missing_pdfs.py --limit 10
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Optional

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.parse.doctype import classify_document
from app.rag.parse.parse_meta import MetaParser
from app.rag.parse.parse_tables import TableParser
from app.rag.preprocess.clean_text import TextCleaner

logger = get_logger(__name__)

DOCS_DIR = PROJECT_ROOT / "docs"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
DB_PATH = PROJECT_ROOT / "metadata.db"


def get_all_pdfs() -> list[Path]:
    """year_* 폴더의 모든 PDF 경로 반환"""
    pdfs = []
    for year_dir in DOCS_DIR.glob("year_*"):
        if year_dir.is_dir():
            pdfs.extend(year_dir.glob("*.pdf"))
    return sorted(pdfs)


def get_db_filenames() -> set[str]:
    """DB에 등록된 파일명 집합 반환"""
    db = MetadataDB(db_path=str(DB_PATH))
    conn = db._get_conn()
    rows = conn.execute("SELECT filename FROM documents").fetchall()
    return {row[0] for row in rows}


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, dict[str, Any]]:
    """PDF 텍스트 추출 (OCR fallback 포함)"""
    try:
        import pdfplumber

        text_pages = []
        metadata = {}

        with pdfplumber.open(pdf_path) as pdf:
            metadata["page_count"] = len(pdf.pages)
            metadata["file_size"] = pdf_path.stat().st_size

            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_pages.append(text)

        full_text = "\n\n".join(text_pages)

        # OCR fallback: 페이지당 평균 300자 미만이면 OCR 시도
        page_count = metadata.get("page_count", 1)
        avg_chars = len(full_text) / page_count if page_count > 0 else 0

        if not full_text or avg_chars < 300:
            logger.info(f"텍스트 부족 ({avg_chars:.0f}자/페이지), OCR 시도: {pdf_path.name}")
            ocr_text = ocr_extract(pdf_path)
            if ocr_text:
                full_text = ocr_text

        return full_text, metadata

    except Exception as e:
        logger.error(f"PDF 추출 실패: {pdf_path.name} - {e}")
        return "", {}


def ocr_extract(pdf_path: Path) -> str:
    """OCR을 사용한 PDF 텍스트 추출"""
    try:
        import pytesseract
        from pdf2image import convert_from_path

        logger.info(f"OCR 추출 시작: {pdf_path.name}")
        images = convert_from_path(pdf_path, dpi=300)

        text_pages = []
        for _i, image in enumerate(images, 1):
            text = pytesseract.image_to_string(image, lang="kor+eng")
            if text.strip():
                text_pages.append(text)

        full_text = "\n\n".join(text_pages)
        logger.info(f"OCR 완료: {pdf_path.name}, {len(full_text)}자")
        return full_text

    except Exception as e:
        logger.error(f"OCR 실패: {pdf_path.name} - {e}")
        return ""


def compute_hash(file_path: Path) -> str:
    """파일 SHA1 해시"""
    sha1 = hashlib.sha1()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha1.update(chunk)
    return sha1.hexdigest()


def process_single_pdf(
    pdf_path: Path,
    meta_parser: MetaParser,
    table_parser: TableParser,
    text_cleaner: TextCleaner,
    db: Optional[MetadataDB],
    dry_run: bool = False,
) -> dict[str, Any]:
    """단일 PDF 처리"""
    result = {
        "filename": pdf_path.name,
        "status": "unknown",
        "reason": "",
    }

    try:
        # 1. 텍스트 추출
        text, pdf_meta = extract_text_from_pdf(pdf_path)
        if not text:
            result["status"] = "failed"
            result["reason"] = "텍스트 추출 실패"
            return result

        # 2. 텍스트 정제
        cleaned_text = text_cleaner.clean(text)

        # 3. 메타데이터 파싱 (metadata dict, title, content 필요)
        meta = meta_parser.parse({}, title=pdf_path.name, content=text)

        # 4. 문서 유형 분류 (text, filename만 필요)
        doctype_result = classify_document(text, pdf_path.name)
        doctype = doctype_result.get("doctype", "미분류") if isinstance(doctype_result, dict) else str(doctype_result)

        # 5. 표 파싱 (text만 필요)
        _table_data = table_parser.parse(text)

        # 6. DB 저장
        if not dry_run and db is not None:
            # 추출 텍스트 저장
            EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
            txt_path = EXTRACTED_DIR / (pdf_path.stem + ".txt")
            txt_path.write_text(cleaned_text, encoding="utf-8")

            # DB add_document (upsert 역할)
            doc_data: dict[str, Any] = {
                "filename": pdf_path.name,
                "path": str(pdf_path.relative_to(PROJECT_ROOT)),
                "date": meta.get("date"),
                "drafter": meta.get("drafter"),
                "department": meta.get("department"),
                "doctype": doctype,
                "page_count": pdf_meta.get("page_count", 1),
                "file_size": pdf_meta.get("file_size", 0),
                "file_hash": compute_hash(pdf_path),
                "text_length": len(cleaned_text),
            }
            db.add_document(doc_data)

        result["status"] = "success"
        result["doctype"] = doctype
        result["drafter"] = meta.get("drafter")
        result["text_length"] = len(cleaned_text)

    except Exception as e:
        result["status"] = "failed"
        result["reason"] = str(e)
        logger.error(f"처리 실패: {pdf_path.name} - {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="누락된 PDF 처리")
    parser.add_argument("--dry-run", action="store_true", help="실제 저장 없이 테스트")
    parser.add_argument("--limit", type=int, help="처리할 최대 파일 수")
    args = parser.parse_args()

    print("=" * 60)
    print("📥 누락된 PDF 처리 시작")
    print("=" * 60)

    # 누락 파일 찾기
    all_pdfs = get_all_pdfs()
    db_filenames = get_db_filenames()

    missing_pdfs = [p for p in all_pdfs if p.name not in db_filenames]

    print(f"📁 전체 PDF: {len(all_pdfs)}개")
    print(f"💾 DB 등록: {len(db_filenames)}개")
    print(f"❓ 누락: {len(missing_pdfs)}개")
    print()

    if not missing_pdfs:
        print("✅ 누락된 PDF 없음!")
        return

    if args.limit:
        missing_pdfs = missing_pdfs[: args.limit]
        print(f"⚠️ 제한: {args.limit}개만 처리")

    # 파서 초기화
    meta_parser = MetaParser()
    table_parser = TableParser()
    text_cleaner = TextCleaner()

    # DB 연결
    db = None if args.dry_run else MetadataDB(db_path=str(DB_PATH))

    # 처리
    success = 0
    failed = 0
    start_time = time.time()

    for i, pdf_path in enumerate(missing_pdfs, 1):
        print(f"\n[{i}/{len(missing_pdfs)}] {pdf_path.name}")

        result = process_single_pdf(
            pdf_path, meta_parser, table_parser, text_cleaner, db, args.dry_run
        )

        if result["status"] == "success":
            success += 1
            drafter = result.get("drafter") or "정보 없음"
            print(f"  ✅ 성공 (유형: {result['doctype']}, 기안자: {drafter})")
        else:
            failed += 1
            print(f"  ❌ 실패: {result['reason']}")

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("📊 처리 결과")
    print("=" * 60)
    print(f"✅ 성공: {success}개")
    print(f"❌ 실패: {failed}개")
    print(f"⏱️ 소요 시간: {elapsed:.1f}초")
    print()

    if args.dry_run:
        print("⚠️ Dry-run 모드: 실제 저장되지 않았습니다.")


if __name__ == "__main__":
    main()
