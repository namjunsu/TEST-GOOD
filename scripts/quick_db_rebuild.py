#!/usr/bin/env python3
"""
Quick database rebuild from existing text files
"""
import sqlite3
import re
from pathlib import Path

# Create documents table if not exists
conn = sqlite3.connect("metadata.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        year TEXT,
        month TEXT,
        date TEXT,
        path TEXT NOT NULL,
        doctype TEXT,
        category TEXT,
        title TEXT,
        text_preview TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(filename)
    )
""")
conn.commit()

def extract_metadata_from_filename(filename):
    """Extract metadata from filename"""
    result = {
        'year': None,
        'month': None,
        'date': None,
        'title': filename.replace('.pdf', '').replace('_', ' ')
    }

    # Try to extract date
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})_', filename)
    if match:
        result['year'] = match.group(1)
        result['month'] = f"{match.group(1)}-{match.group(2)}"
        result['date'] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        result['title'] = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename).replace('.pdf', '').replace('_', ' ')

    return result

def determine_doctype(filename):
    """Determine document type"""
    if '기안' in filename:
        return 'proposal'
    elif '보고' in filename:
        return 'report'
    elif '구매' in filename or '수리' in filename:
        return 'purchase'
    elif '회의' in filename:
        return 'meeting'
    else:
        return 'document'

def determine_category(filename):
    """Determine category"""
    if '방송' in filename or '송출' in filename:
        return '방송운영'
    elif '기술' in filename or '장비' in filename:
        return '기술관리'
    elif '재난' in filename:
        return '안전관리'
    elif '구매' in filename or '수리' in filename:
        return '구매/수리'
    else:
        return '일반문서'

print("Starting database rebuild...")

# Find all text files
text_files = list(Path("data/extracted").glob("*.txt"))
print(f"Found {len(text_files)} text files")

success = 0
for txt_file in text_files:
    filename = txt_file.name.replace('.txt', '.pdf')

    # Find corresponding PDF
    pdf_files = list(Path("docs").glob(f"year_*/{filename}"))

    if not pdf_files:
        continue

    pdf_path = pdf_files[0]
    relative_path = str(pdf_path.relative_to(Path("docs")))

    # Extract metadata
    meta = extract_metadata_from_filename(filename)
    doctype = determine_doctype(filename)
    category = determine_category(filename)

    # Read text content
    try:
        text_content = txt_file.read_text(encoding='utf-8')
        text_preview = text_content[:200] if text_content else ""
    except:
        text_preview = ""

    # Insert into database
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO documents (
                filename, year, month, date, path,
                doctype, category, title, text_preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename,
            meta['year'] or '정보없음',
            meta['month'] or '정보없음',
            meta['date'] or '정보없음',
            relative_path,
            doctype,
            category,
            meta['title'],
            text_preview
        ))
        conn.commit()
        success += 1

        if '재난방송' in filename:
            print(f"✅ Added 재난방송 document: {filename} (year: {meta['year']})")
    except Exception as e:
        print(f"Error with {filename}: {e}")

print(f"\nAdded {success} documents to database")

# Check total count
cursor.execute("SELECT COUNT(*) FROM documents")
total = cursor.fetchone()[0]
print(f"Total documents in database: {total}")

# Check 재난방송 document
cursor.execute("SELECT * FROM documents WHERE filename LIKE '%재난방송%'")
disaster_docs = cursor.fetchall()
if disaster_docs:
    print(f"\n✅ Found {len(disaster_docs)} 재난방송 document(s)")
    for doc in disaster_docs:
        print(f"  ID: {doc[0]}, File: {doc[1]}, Year: {doc[2]}, Path: {doc[5]}")
else:
    print("\n⚠️ No 재난방송 documents found")

conn.close()
print("\nDatabase rebuild complete!")