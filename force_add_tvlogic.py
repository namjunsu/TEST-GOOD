#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

from modules_legacy.metadata_db import MetadataDB

db = MetadataDB("metadata.db")

# Force add TVLogic document
metadata = {
    "path": "processed/2025-08-13_TVLogic_모니터_구매_검토서.pdf",
    "filename": "2025-08-13_TVLogic_모니터_구매_검토서.pdf",
    "title": "TVLogic 모니터 구매 검토서",
    "date": "2025-08-13",
    "year": "2025",
    "month": "08",
    "category": "구매",
    "drafter": "",
    "amount": 0,
    "file_size": 100000,
    "page_count": 2,
    "text_preview": "TVLogic 모니터 구매 검토서...",
    "keywords": ["TVLogic", "모니터", "구매"],
    "doctype": "disposal",
    "display_date": "2025-08-13"
}

result = db.add_document(metadata)
print(f"✅ TVLogic 문서 DB에 추가 완료 (ID: {result})")
