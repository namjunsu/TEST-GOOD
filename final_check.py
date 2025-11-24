#!/usr/bin/env python3
"""최종 검증"""

import pickle

with open('var/index/bm25_index.pkl', 'rb') as f:
    data = pickle.load(f)

# DVR 검색
print("🔍 DVR 포함 문서 검색:")
print("-" * 60)

dvr_docs = []
for i, text in enumerate(data['corpus']):
    if 'DVR' in text:
        meta = data['metadata'][i]
        filename = meta.get('filename', 'unknown')
        count = text.count('DVR')
        dvr_docs.append((filename, count))

for i, (filename, count) in enumerate(dvr_docs, 1):
    marker = "🎯" if "2017-12-21" in filename else "  "
    print(f"{marker} {i}. {filename} (DVR {count}회)")

print(f"\n총 {len(dvr_docs)}개 문서에서 DVR 발견")

# 타겟 문서 직접 확인
print("\n" + "-" * 60)
print("🎯 타겟 문서 확인:")
target = "2017-12-21_방송_송출_보존용_DVR_교체_검토의_건.pdf"

for i, meta in enumerate(data['metadata']):
    if meta.get('filename') == target:
        text = data['corpus'][i]
        print(f"✅ 인덱스 {i}번에서 발견!")
        print(f"  - 텍스트 길이: {len(text)}")
        print(f"  - DVR 포함: {text.count('DVR')}회")
        print(f"  - 첫 300자: {text[:300]}")
        break
else:
    print(f"❌ 타겟 문서가 인덱스에 없음")