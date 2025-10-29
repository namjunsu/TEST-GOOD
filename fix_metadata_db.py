#!/usr/bin/env python3
"""
Metadata DB 누락 파일 추가 스크립트
"""

import sqlite3
import os
from datetime import datetime

# 누락된 파일 정보
missing_files = [
    {
        'filename': 'AS_IS_TREE.txt',
        'path': 'docs/AS_IS_TREE.txt',
        'title': 'AS IS TREE',
        'page_count': 1
    },
    {
        'filename': 'IMPORT_GRAPH.txt',
        'path': 'docs/IMPORT_GRAPH.txt',
        'title': 'IMPORT GRAPH',
        'page_count': 1
    },
    {
        'filename': 'ENTRYPOINT_HITS.txt',
        'path': 'docs/ENTRYPOINT_HITS.txt',
        'title': 'ENTRYPOINT HITS',
        'page_count': 1
    },
    {
        'filename': '2024-10-24_2024_채널에이_중계차_노후_보수건.pdf',
        'path': 'docs/year_2024/2024-10-24_2024_채널에이_중계차_노후_보수건.pdf',
        'title': '2024 채널에이 중계차 노후 보수건',
        'page_count': 1  # 실제 페이지 수는 알 수 없으므로 1로 설정
    }
]

# DB 연결
conn = sqlite3.connect('metadata.db')
cursor = conn.cursor()

# 누락된 파일 추가
added = 0
for file_info in missing_files:
    # 이미 존재하는지 확인
    cursor.execute("SELECT COUNT(*) FROM documents WHERE filename = ?", (file_info['filename'],))
    if cursor.fetchone()[0] == 0:
        # 날짜 정보 추출
        date = ""
        year = ""
        month = ""
        if '2024-10-24' in file_info['filename']:
            date = "2024-10-24"
            year = "2024"
            month = "10"

        # 파일 추가
        cursor.execute("""
            INSERT INTO documents (
                path, filename, title, date, year, month, category,
                drafter, amount, file_size, page_count, text_preview,
                keywords, created_at, updated_at, normalized_filename,
                doctype, display_date, claimed_total, sum_match
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_info['path'],
            file_info['filename'],
            file_info['title'],
            date,
            year,
            month,
            "",  # category
            "",  # drafter
            None,  # amount
            0,  # file_size
            file_info['page_count'],
            "",  # text_preview
            "",  # keywords
            datetime.now().isoformat(),  # created_at
            datetime.now().isoformat(),  # updated_at
            file_info['filename'].lower(),  # normalized_filename
            "txt" if file_info['filename'].endswith('.txt') else "pdf",  # doctype
            date if date else "",  # display_date
            None,  # claimed_total
            None   # sum_match
        ))
        added += 1
        print(f"✅ Added: {file_info['filename']}")
    else:
        print(f"⏭️ Already exists: {file_info['filename']}")

# 커밋
conn.commit()
print(f"\n총 {added}개 파일 추가 완료")

# 최종 카운트 확인
cursor.execute("SELECT COUNT(DISTINCT filename) FROM documents")
total_count = cursor.fetchone()[0]
print(f"현재 metadata.db 고유 문서 수: {total_count}개")

conn.close()