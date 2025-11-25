#!/usr/bin/env python3
"""
Rebuild database from all PDF files in docs/year_* folders
"""

import os
import sys
import sqlite3
import re
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.metadata_db import MetadataDB
from app.rag.ocr.pipeline import ocr_extract_pdf

def extract_year_from_filename(filename):
    """Extract year from filename pattern: YYYY-MM-DD_*"""
    match = re.match(r'^(\d{4})-\d{2}-\d{2}_', filename)
    if match:
        return match.group(1)
    return None

def extract_month_from_filename(filename):
    """Extract month from filename pattern: YYYY-MM-DD_*"""
    match = re.match(r'^(\d{4}-\d{2})-\d{2}_', filename)
    if match:
        return match.group(1)
    return None

def extract_date_from_filename(filename):
    """Extract date from filename pattern: YYYY-MM-DD_*"""
    match = re.match(r'^(\d{4}-\d{2}-\d{2})_', filename)
    if match:
        return match.group(1)
    return None

def determine_doctype(filename, path):
    """Determine document type from filename or path"""
    filename_lower = filename.lower()

    # Common document type patterns
    if '기안' in filename or '기안서' in filename:
        return 'proposal'
    elif '보고' in filename or '보고서' in filename:
        return 'report'
    elif '계약' in filename:
        return 'contract'
    elif '회의' in filename or '회의록' in filename:
        return 'meeting'
    elif '구매' in filename or '수리' in filename:
        return 'purchase'
    elif '검토' in filename:
        return 'review'
    else:
        return 'document'

def determine_category(filename, doctype):
    """Determine category from filename and doctype"""
    filename_lower = filename.lower()

    if '방송' in filename or '송출' in filename or '스튜디오' in filename:
        return '방송운영'
    elif '기술' in filename or '장비' in filename or '시스템' in filename:
        return '기술관리'
    elif '구매' in filename or '수리' in filename:
        return '구매/수리'
    elif '재난' in filename or '안전' in filename:
        return '안전관리'
    elif '영상' in filename or '취재' in filename:
        return '제작지원'
    else:
        return '일반문서'

def extract_title_from_filename(filename):
    """Extract title from filename by removing date prefix and extension"""
    # Remove date prefix (YYYY-MM-DD_)
    title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
    # Remove .pdf extension
    title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
    # Replace underscores with spaces
    title = title.replace('_', ' ')
    return title

def main():
    print("=" * 80)
    print("Database Rebuild from PDFs")
    print("=" * 80)

    # Initialize database
    db = MetadataDB("metadata.db")

    # Find all PDF files
    docs_root = Path("docs")
    pdf_files = list(docs_root.glob("year_*/**.pdf"))

    print(f"Found {len(pdf_files)} PDF files")

    success_count = 0
    fail_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        filename = pdf_path.name
        relative_path = str(pdf_path.relative_to(docs_root))

        print(f"\n[{i}/{len(pdf_files)}] Processing: {filename}")

        try:
            # Extract metadata from filename
            year = extract_year_from_filename(filename)
            month = extract_month_from_filename(filename)
            date = extract_date_from_filename(filename)

            # Skip if year extraction failed
            if not year:
                print(f"  ⚠️ Cannot extract year from: {filename}")
                year = "정보없음"
                month = "정보없음"
                date = "정보없음"

            # Determine document type and category
            doctype = determine_doctype(filename, relative_path)
            category = determine_category(filename, doctype)
            title = extract_title_from_filename(filename)

            # Check if text file exists
            text_file = Path(f"data/extracted/{filename.replace('.pdf', '.txt')}")

            if text_file.exists():
                # Read existing text
                text_content = text_file.read_text(encoding='utf-8')
                print(f"  ✓ Using existing text: {len(text_content)} chars")
            else:
                # Extract text using OCR
                print(f"  ⏳ Extracting text with OCR...")
                text_content = ocr_extract_pdf(pdf_path, dpi=150, engine="tesseract")

                # Save extracted text
                text_file.parent.mkdir(parents=True, exist_ok=True)
                text_file.write_text(text_content, encoding='utf-8')
                print(f"  ✓ Extracted: {len(text_content)} chars")

            # Create preview (first 200 chars)
            text_preview = text_content[:200] if text_content else ""

            # Insert into database
            conn = sqlite3.connect("metadata.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO documents (
                    filename, year, month, date, path,
                    doctype, category, title, text_preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename, year, month, date, relative_path,
                doctype, category, title, text_preview
            ))

            conn.commit()
            conn.close()

            success_count += 1
            print(f"  ✅ Added to database: {title}")

        except Exception as e:
            fail_count += 1
            print(f"  ❌ Error: {e}")

    print("\n" + "=" * 80)
    print(f"Rebuild complete: {success_count} success, {fail_count} failed")

    # Show final database count
    conn = sqlite3.connect("metadata.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    total_docs = cursor.fetchone()[0]
    conn.close()

    print(f"Total documents in database: {total_docs}")

    # Check if 재난방송 document is present
    conn = sqlite3.connect("metadata.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filename, year, path
        FROM documents
        WHERE filename LIKE '%재난방송%'
    """)
    disaster_docs = cursor.fetchall()
    conn.close()

    if disaster_docs:
        print(f"\n✅ 재난방송 documents found: {len(disaster_docs)}")
        for doc in disaster_docs:
            print(f"  - {doc[0]} (year: {doc[1]}, path: {doc[2]})")
    else:
        print("\n⚠️ No 재난방송 documents found!")

if __name__ == "__main__":
    main()