#!/usr/bin/env python3
"""
완전한 텍스트 추출 스크립트
- PDF에서 전체 텍스트 추출 (500자 제한 없음)
- 실패시 OCR 적용
- data/extracted/에 전체 텍스트 저장
"""
import sys
from pathlib import Path
import pdfplumber
import subprocess
import sqlite3
from typing import Optional, Dict
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def extract_with_pdfplumber(pdf_path: Path) -> Optional[str]:
    """pdfplumber로 텍스트 추출"""
    try:
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    print(f"    ⚠️ 페이지 {page_num} 추출 실패: {e}")
                    continue

        if text_parts:
            full_text = "\n\n".join(text_parts)
            return full_text
    except Exception as e:
        print(f"    ❌ pdfplumber 실패: {e}")
    return None

def extract_with_ocr(pdf_path: Path) -> Optional[str]:
    """Tesseract OCR로 텍스트 추출"""
    try:
        # Check if tesseract is available
        result = subprocess.run(['which', 'tesseract'], capture_output=True)
        if result.returncode != 0:
            print("    ❌ Tesseract not found")
            return None

        # Convert PDF to images and OCR
        print(f"    🔄 OCR 시작...")

        # Use pdftotext first (might have some text even if pdfplumber failed)
        try:
            result = subprocess.run(
                ['pdftotext', str(pdf_path), '-'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except:
            pass

        # If pdftotext fails, use full OCR (slower but more complete)
        temp_dir = Path('/tmp') / f"ocr_{pdf_path.stem}"
        temp_dir.mkdir(exist_ok=True)

        try:
            # Convert PDF to images
            subprocess.run([
                'pdftoppm', '-png', '-r', '300',
                str(pdf_path), str(temp_dir / 'page')
            ], check=True, timeout=60)

            # OCR each image
            text_parts = []
            for img_path in sorted(temp_dir.glob('*.png')):
                result = subprocess.run([
                    'tesseract', str(img_path), '-', '-l', 'kor+eng'
                ], capture_output=True, text=True, timeout=30)

                if result.returncode == 0 and result.stdout:
                    text_parts.append(result.stdout)

            if text_parts:
                return "\n\n".join(text_parts)

        finally:
            # Clean up temp files
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    except Exception as e:
        print(f"    ❌ OCR 실패: {e}")

    return None

def clean_text(text: str) -> str:
    """텍스트 정제 - 불필요한 URL 및 노이즈 제거"""
    if not text:
        return ""

    # Remove URLs and noise
    patterns_to_remove = [
        r'.*gw\.channela-mt\.com/groupware/approval/.*\n?',
        r'.*http://gw\.channela-mt\.com.*\n?',
        r'.*http://www\.elmarket\.co\.kr.*\n?',
        r'^\s*\d+/\d+\s*$',  # Page numbers like "1/3"
    ]

    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE)

    # Remove excessive whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = re.sub(r' {2,}', ' ', cleaned)

    return cleaned.strip()

def main():
    print("=" * 70)
    print("📋 전체 텍스트 추출 시작")
    print("  - 500자 제한 없이 PDF 전체 내용 추출")
    print("  - 실패시 OCR 자동 적용")
    print("=" * 70)

    # Get all PDFs from database
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT filename, path
        FROM documents
        WHERE filename LIKE '%.pdf'
        ORDER BY filename
    """)
    all_pdfs = cursor.fetchall()

    print(f"\n📊 총 {len(all_pdfs)}개 PDF 처리")

    # Create output directory
    extracted_dir = Path('data/extracted')
    extracted_dir.mkdir(parents=True, exist_ok=True)

    # Statistics
    stats = {
        'success_pdfplumber': 0,
        'success_ocr': 0,
        'failed': 0,
        'total_chars_before': 0,
        'total_chars_after': 0
    }

    for i, (filename, filepath) in enumerate(all_pdfs, 1):
        pdf_path = Path(filepath)
        txt_filename = filename.replace('.pdf', '.txt')
        txt_path = extracted_dir / txt_filename

        print(f"\n[{i}/{len(all_pdfs)}] {filename}")

        # Check existing text file
        if txt_path.exists():
            with open(txt_path, 'r', encoding='utf-8') as f:
                existing_text = f.read()
                stats['total_chars_before'] += len(existing_text)
                print(f"  📄 기존: {len(existing_text):,}자")

        if not pdf_path.exists():
            print(f"  ❌ PDF 파일 없음: {pdf_path}")
            stats['failed'] += 1
            continue

        # Extract text
        full_text = None

        # Try pdfplumber first
        full_text = extract_with_pdfplumber(pdf_path)
        if full_text and len(full_text) > 100:
            print(f"  ✅ pdfplumber 성공: {len(full_text):,}자")
            stats['success_pdfplumber'] += 1
        else:
            # Try OCR
            print(f"  ⚠️ pdfplumber 실패 또는 부족 ({len(full_text) if full_text else 0}자)")
            ocr_text = extract_with_ocr(pdf_path)
            if ocr_text:
                full_text = ocr_text
                print(f"  ✅ OCR 성공: {len(full_text):,}자")
                stats['success_ocr'] += 1
            else:
                print(f"  ❌ 추출 완전 실패")
                stats['failed'] += 1
                continue

        # Clean text
        cleaned_text = clean_text(full_text)

        # Save to file
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)

        stats['total_chars_after'] += len(cleaned_text)
        print(f"  💾 저장: {txt_path.name} ({len(cleaned_text):,}자)")

        # Update database with full text
        try:
            cursor.execute("""
                UPDATE documents
                SET text_preview = ?
                WHERE filename = ?
            """, (cleaned_text[:500], filename))  # Still keep preview as 500 chars

            # If we have a full_text column, update that too
            cursor.execute("""
                UPDATE documents
                SET full_text = ?
                WHERE filename = ?
            """, (cleaned_text, filename))
        except sqlite3.OperationalError:
            # full_text column might not exist
            pass

        if i % 10 == 0:
            conn.commit()
            print(f"\n진행률: {i}/{len(all_pdfs)} ({i/len(all_pdfs)*100:.1f}%)")

    conn.commit()
    conn.close()

    # Print statistics
    print("\n" + "=" * 70)
    print("📊 추출 완료 통계")
    print(f"  ✅ pdfplumber 성공: {stats['success_pdfplumber']}개")
    print(f"  🔄 OCR 성공: {stats['success_ocr']}개")
    print(f"  ❌ 실패: {stats['failed']}개")
    print(f"  📝 총 문자수:")
    print(f"     - 이전: {stats['total_chars_before']:,}자")
    print(f"     - 이후: {stats['total_chars_after']:,}자")
    print(f"     - 증가: {stats['total_chars_after'] - stats['total_chars_before']:,}자")

    # Verify specific file
    target_file = extracted_dir / "2023-01-31_방송_프로그램_제작용_건전지_소모품_구매의_건.txt"
    if target_file.exists():
        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"\n🔍 검증 - 2023-01-31 문서:")
            print(f"   - 크기: {len(content):,}자")
            print(f"   - 내용 미리보기: {content[:200]}...")

    print("\n✅ 전체 텍스트 추출 완료!")
    print("   다음 단계: scripts/reindex_atomic.py 실행하여 인덱스 재구축")

if __name__ == "__main__":
    main()