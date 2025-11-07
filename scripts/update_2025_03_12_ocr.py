#!/usr/bin/env python3
"""2025-03-12 문서 OCR 텍스트 DB 업데이트"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf2image import convert_from_path
import pytesseract
from app.modules.metadata_db import MetadataDB

def main():
    pdf_path = "docs/year_2025/2025-03-12_채널에이_중계차_노후_보수_추가_보수건.pdf"

    print(f"OCR 처리 시작: {pdf_path}")

    # PDF를 이미지로 변환
    images = convert_from_path(pdf_path, dpi=300)
    print(f"총 {len(images)} 페이지 변환 완료")

    # 각 페이지를 OCR 처리
    ocr_text = ""
    for i, image in enumerate(images, 1):
        print(f"페이지 {i} OCR 처리 중...")
        page_text = pytesseract.image_to_string(image, lang='kor+eng')
        ocr_text += page_text + "\n"
        print(f"  페이지 {i}: {len(page_text)}자 추출")

    print(f"\n총 OCR 텍스트: {len(ocr_text)}자")

    # 미리보기
    print(f"\nOCR 텍스트 미리보기 (처음 300자):")
    print(ocr_text[:300])

    # MetadataDB 업데이트
    db = MetadataDB()
    filename = Path(pdf_path).name

    # 문서 찾기
    doc = db.get_by_filename(filename)
    if doc:
        print(f"\n문서 ID {doc['id']} 업데이트 중...")
        db.update_ocr_text(doc['id'], ocr_text)
        print("✅ MetadataDB 업데이트 완료")
        print(f"\n📄 문서: {filename}")
        print(f"📊 OCR 텍스트: {len(ocr_text)}자")
        print("\n⚠️ BM25 인덱스 재구축이 필요합니다:")
        print("   .venv/bin/python3 scripts/reindex_atomic.py")
    else:
        print(f"\n⚠️ 문서를 DB에서 찾을 수 없음: {filename}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
