#!/usr/bin/env python3
"""DVR 문서 강제 인덱싱"""

import sys
sys.path.append('/home/wnstn4647/AI-CHAT')

import os
os.environ['PYTHONPATH'] = '/home/wnstn4647/AI-CHAT'

from pathlib import Path
import pickle
import sqlite3

TARGET_FILE = "2017-12-21_방송_송출_보존용_DVR_교체_검토의_건.pdf"
TARGET_STEM = TARGET_FILE[:-4]

print("=" * 70)
print("🔧 DVR 문서 강제 인덱싱")
print("=" * 70)

# 1. 현재 인덱스 로드
print("\n1️⃣ 현재 인덱스 로드...")
with open('var/index/bm25_index.pkl', 'rb') as f:
    bm25_data = pickle.load(f)

print(f"  - 현재 문서 수: {len(bm25_data.get('metadata', []))}")

# 2. 텍스트 파일 읽기
txt_path = Path(f"data/extracted/{TARGET_STEM}.txt")
print(f"\n2️⃣ 텍스트 파일 읽기: {txt_path}")

if txt_path.exists():
    text = txt_path.read_text(encoding='utf-8', errors='ignore')
    print(f"  ✅ 텍스트 로드: {len(text)} 문자")
    print(f"  - DVR 포함: {text.count('DVR')}회")
else:
    print(f"  ❌ 파일 없음!")
    sys.exit(1)

# 3. 기존 문서 제거 (중복 방지)
print(f"\n3️⃣ 기존 항목 제거...")
old_count = len(bm25_data.get('metadata', []))

if 'metadata' in bm25_data and 'corpus' in bm25_data:
    # 제거할 인덱스 찾기
    indices_to_remove = []
    for i, meta in enumerate(bm25_data['metadata']):
        if meta.get('filename') == TARGET_FILE:
            indices_to_remove.append(i)

    # 역순으로 제거 (인덱스 꼬임 방지)
    for i in sorted(indices_to_remove, reverse=True):
        del bm25_data['metadata'][i]
        del bm25_data['corpus'][i]
        if 'doc_lengths' in bm25_data:
            del bm25_data['doc_lengths'][i]

    print(f"  - {len(indices_to_remove)}개 항목 제거")

# 4. 새 항목 추가
print(f"\n4️⃣ 새 항목 추가...")

# 메타데이터 가져오기
conn = sqlite3.connect('metadata.db')
cursor = conn.execute("""
    SELECT filename, drafter, category, date
    FROM documents
    WHERE filename = ?
""", (TARGET_FILE,))

row = cursor.fetchone()
if row:
    filename, drafter, category, date = row
    metadata = {
        'filename': filename,
        'drafter': drafter or '',
        'category': category or '',
        'date': date or ''
    }
else:
    metadata = {
        'filename': TARGET_FILE,
        'drafter': '신규호',
        'category': 'broadcast',
        'date': '2017-12-21'
    }

# 추가
if 'metadata' not in bm25_data:
    bm25_data['metadata'] = []
if 'corpus' not in bm25_data:
    bm25_data['corpus'] = []

bm25_data['metadata'].append(metadata)
bm25_data['corpus'].append(text)

print(f"  ✅ 추가 완료")
print(f"  - 메타데이터: {metadata}")
print(f"  - 텍스트: {len(text)} 문자")

# 5. 저장
print(f"\n5️⃣ 인덱스 저장...")
with open('var/index/bm25_index.pkl', 'wb') as f:
    pickle.dump(bm25_data, f)

print(f"  ✅ 저장 완료")
print(f"  - 이전 문서 수: {old_count}")
print(f"  - 현재 문서 수: {len(bm25_data['metadata'])}")

# 6. 검증
print(f"\n6️⃣ 검증...")
with open('var/index/bm25_index.pkl', 'rb') as f:
    verify_data = pickle.load(f)

found = False
for i, meta in enumerate(verify_data['metadata']):
    if meta.get('filename') == TARGET_FILE:
        corpus_text = verify_data['corpus'][i]
        dvr_count = corpus_text.count('DVR')
        print(f"  ✅ 인덱스에서 발견!")
        print(f"  - 위치: {i}")
        print(f"  - DVR 포함: {dvr_count}회")
        found = True
        break

if not found:
    print(f"  ❌ 인덱스에 없음 (뭔가 잘못됨)")

conn.close()

print("\n" + "=" * 70)
print("✅ 강제 인덱싱 완료!")
print("=" * 70)