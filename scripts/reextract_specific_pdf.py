#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""특정 PDF 재추출 스크립트"""

import sys
from pathlib import Path
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

def extract_with_pdfplumber(pdf_path: Path) -> str:
    """PDFPlumber로 텍스트 추출"""
    print("🔧 PDFPlumber로 시도...")
    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                    print(f"  - 페이지 {i+1}: {len(page_text)} 문자")

        full_text = "\n\n".join(text_parts)
        print(f"  → 총 {len(full_text)} 문자 추출")
        return full_text
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return ""

def extract_with_ocr(pdf_path: Path) -> str:
    """OCR로 텍스트 추출"""
    print("\n🔍 OCR로 시도...")
    try:
        # PDF를 이미지로 변환
        images = convert_from_path(pdf_path, dpi=200)

        text_parts = []
        for i, image in enumerate(images):
            # OCR 수행
            text = pytesseract.image_to_string(image, lang='kor')
            if text:
                text_parts.append(text)
                print(f"  - 페이지 {i+1}: {len(text)} 문자")

        full_text = "\n\n".join(text_parts)
        print(f"  → 총 {len(full_text)} 문자 추출")
        return full_text
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return ""

def main():
    if len(sys.argv) < 2:
        print("Usage: python reextract_specific_pdf.py <pdf_file>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])

    if not pdf_path.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    print(f"📄 처리 대상: {pdf_path.name}")
    print("=" * 60)

    # 1. PDFPlumber 시도
    text = extract_with_pdfplumber(pdf_path)

    # 2. 텍스트가 너무 짧으면 OCR 시도
    if len(text) < 100:
        print("\n⚠️ PDFPlumber 추출 부족, OCR 시도...")
        ocr_text = extract_with_ocr(pdf_path)
        if len(ocr_text) > len(text):
            text = ocr_text

    # 3. 결과 저장
    if text:
        output_path = Path('data/extracted') / pdf_path.name.replace('.pdf', '.txt')
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)

        print("\n" + "=" * 60)
        print(f"✅ 추출 완료!")
        print(f"  - 저장: {output_path}")
        print(f"  - 크기: {len(text)} 문자")

        # 샘플 출력
        print("\n📝 첫 500자:")
        print(text[:500])

        # 키워드 확인
        keywords = ['DVR', 'SPG9000', 'APTN', '교체', '검토']
        print("\n🔍 키워드 확인:")
        for kw in keywords:
            if kw in text:
                print(f"  ✅ '{kw}' 발견")
            else:
                print(f"  ❌ '{kw}' 없음")
    else:
        print("\n❌ 텍스트 추출 완전 실패")

if __name__ == "__main__":
    main()