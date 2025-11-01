#!/usr/bin/env python3
"""DVR 교체 검토 문서 2개 OCR 추출 전용 스크립트"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import pdfplumber
from PIL import Image
import pytesseract
import io

# 대상 문서 2개
DVR_DOCS = [
    "docs/year_2017/2017-12-21_방송_송출_보존용_DVR_교체_검토의_건.pdf",
    "docs/year_2025/2025-03-04_방송_영상_보존용_DVR_교체_검토의_건.pdf",
]

def extract_with_ocr(pdf_path):
    """PDF에서 텍스트+OCR 추출"""
    all_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # 1. 일반 텍스트 추출 시도
            text = page.extract_text() or ""

            # 2. 텍스트가 짧으면 OCR 수행
            if len(text.strip()) < 50:
                print(f"   페이지 {page_num}: OCR 수행 중...")
                try:
                    # 페이지를 이미지로 변환 (해상도 300 DPI)
                    img = page.to_image(resolution=300)
                    pil_img = img.original

                    # Tesseract OCR (한글+영문)
                    ocr_text = pytesseract.image_to_string(pil_img, lang='kor+eng')
                    text = ocr_text
                except Exception as e:
                    print(f"   ⚠️ OCR 실패: {e}")

            all_text.append(text)

    return "\n\n".join(all_text)

def main():
    print("=" * 80)
    print("DVR 문서 OCR 추출 시작")
    print("=" * 80)

    for pdf_path in DVR_DOCS:
        pdf = Path(pdf_path)
        if not pdf.exists():
            print(f"❌ 파일 없음: {pdf_path}")
            continue

        print(f"\n📄 처리 중: {pdf.name}")

        # OCR 추출
        try:
            text = extract_with_ocr(str(pdf))

            # data/extracted에 저장
            output_dir = Path("data/extracted")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{pdf.stem}.txt"

            output_file.write_text(text, encoding="utf-8")
            print(f"✅ 추출 완료: {output_file} ({len(text)} chars)")

            # HRD-442 확인
            if "HRD" in text or "Hanwha" in text:
                print(f"🎯 HRD/Hanwha 키워드 감지!")
                # 미리보기 (HRD 포함 라인)
                for line in text.split('\n'):
                    if "HRD" in line or "Hanwha" in line or "10.120" in line:
                        print(f"   → {line.strip()[:100]}")

        except Exception as e:
            print(f"❌ OCR 실패: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("완료")
    print("=" * 80)

if __name__ == "__main__":
    main()
