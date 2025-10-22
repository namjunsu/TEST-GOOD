#!/usr/bin/env python3
"""
메타데이터 DB 재구축 스크립트
PDF 파일에서 기안자 정보를 추출하여 metadata.db에 저장
"""

import sqlite3
from pathlib import Path
from pypdf import PdfReader
import logging
from modules.metadata_extractor import MetadataExtractor
from modules.metadata_db import MetadataDB
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: Path, max_pages: int = 3) -> str:
    """PDF 파일에서 텍스트 추출 (처음 몇 페이지만)"""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            text = ""

            # 처음 max_pages 페이지만 읽기 (보통 기안자는 첫 페이지에 있음)
            for i in range(min(max_pages, len(reader.pages))):
                page = reader.pages[i]
                text += page.extract_text() or ""

            return text
    except Exception as e:
        logger.error(f"PDF 텍스트 추출 실패 {pdf_path}: {e}")
        return ""

def rebuild_metadata_db():
    """메타데이터 DB 재구축"""

    # 초기화
    extractor = MetadataExtractor()
    db = MetadataDB()

    # PDF 파일 찾기
    docs_dir = Path("docs")
    pdf_files = list(docs_dir.rglob("*.pdf")) + list(docs_dir.rglob("*.PDF"))

    logger.info(f"총 {len(pdf_files)}개 PDF 파일 발견")

    # 통계
    stats = {
        'total': len(pdf_files),
        'success': 0,
        'with_drafter': 0,
        'failed': 0
    }

    # 각 PDF 파일 처리
    for pdf_path in tqdm(pdf_files, desc="메타데이터 추출 중"):
        try:
            # 파일 정보
            filename = pdf_path.name
            relative_path = str(pdf_path.relative_to(docs_dir))

            # 카테고리 추출
            category = ""
            if "category_purchase" in str(pdf_path):
                category = "구매"
            elif "category_repair" in str(pdf_path):
                category = "수리"
            elif "category_consumables" in str(pdf_path):
                category = "소모품"
            elif "category_disposal" in str(pdf_path):
                category = "폐기"

            # PDF 텍스트 추출
            text = extract_text_from_pdf(pdf_path, max_pages=3)

            # 메타데이터 추출
            metadata_extracted = extractor.extract_all(text, filename)

            # 메타데이터 딕셔너리 생성
            metadata = {
                'path': str(pdf_path),
                'filename': filename,
                'title': filename.replace('.pdf', '').replace('.PDF', ''),
                'category': category,
                'drafter': metadata_extracted.get('drafter', ''),
                'date': metadata_extracted['dates'].get('main_date', ''),
                'year': str(metadata_extracted['dates'].get('year', '')),
                'month': '',
                'amount': metadata_extracted['amounts'].get('total', 0),
                'file_size': pdf_path.stat().st_size,
                'page_count': 0,
                'text_preview': text[:500] if text else '',
                'keywords': []
            }

            # 날짜에서 월 추출
            if metadata['date']:
                parts = metadata['date'].split('-')
                if len(parts) >= 2:
                    metadata['month'] = parts[1]

            # DB에 저장
            db.add_document(metadata)

            stats['success'] += 1
            if metadata['drafter']:
                stats['with_drafter'] += 1
                logger.debug(f"✅ {filename}: 기안자={metadata['drafter']}")

        except Exception as e:
            logger.error(f"처리 실패 {pdf_path}: {e}")
            stats['failed'] += 1

    # 결과 출력
    print("\n" + "="*60)
    print("메타데이터 DB 재구축 완료")
    print("="*60)
    print(f"총 파일 수: {stats['total']}")
    print(f"성공: {stats['success']}")
    print(f"기안자 추출 성공: {stats['with_drafter']}")
    print(f"실패: {stats['failed']}")
    print("="*60)

    # DB 통계
    db_stats = db.get_statistics()
    print(f"\nDB 총 문서 수: {db_stats['total_documents']}")

    db.close()

if __name__ == "__main__":
    rebuild_metadata_db()
