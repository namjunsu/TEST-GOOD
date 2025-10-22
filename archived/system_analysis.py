#!/usr/bin/env python3
"""현 시스템 냉정 분석"""
import sqlite3
from pathlib import Path
import os

print("="*60)
print("🔍 시스템 냉정 분석 (실측 기반)")
print("="*60)
print()

# 1. 데이터 상태
print("1️⃣ 데이터 상태")
print("-"*60)

conn = sqlite3.connect('everything_index.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM files')
db_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(DISTINCT filename) FROM files')
unique_count = cursor.fetchone()[0]
conn.close()

pdf_files = [f for f in Path('docs').rglob('*.pdf') if not f.is_symlink()]
real_files = len(pdf_files)

print(f"DB 레코드: {db_count}개")
print(f"고유 파일명: {unique_count}개")
print(f"실제 PDF: {real_files}개")
print(f"데이터 일치: {'✅' if db_count == unique_count == real_files else '❌ 불일치!'}")
if db_count != real_files:
    print(f"  ⚠️  차이: {abs(db_count - real_files)}개")
print()

# 2. 코드 복잡도
print("2️⃣ 코드 복잡도")
print("-"*60)

files_to_check = [
    ('perfect_rag.py', '메인 RAG'),
    ('hybrid_chat_rag_v2.py', '통합 RAG'),
    ('quick_fix_rag.py', '빠른 검색'),
    ('web_interface.py', '웹 UI'),
    ('everything_like_search.py', '검색 엔진'),
]

total_lines = 0
for file, desc in files_to_check:
    if os.path.exists(file):
        lines = sum(1 for _ in open(file, 'r', encoding='utf-8'))
        size_kb = os.path.getsize(file) / 1024
        total_lines += lines
        complexity = "🔴" if lines > 1500 else ("🟡" if lines > 800 else "🟢")
        print(f"{complexity} {file:30s} {lines:5d} 줄 ({desc})")

print(f"\n총 코드: {total_lines:,}줄")
print()

# 3. 사용되지 않는 파일
print("3️⃣ 사용되지 않는 파일/폴더 (정리 가능)")
print("-"*60)

unused_dirs = []
for p in Path('.').iterdir():
    if p.is_dir():
        name = p.name
        if name in ['unused_files', 'docs_archive', 'do']:
            try:
                size_mb = sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) / (1024*1024)
                file_count = sum(1 for f in p.rglob('*') if f.is_file())
                unused_dirs.append((name, size_mb, file_count))
            except:
                pass

for name, size, count in unused_dirs:
    print(f"📁 {name:20s} {size:8.1f} MB ({count}개 파일)")

if unused_dirs:
    total_waste = sum(s for _, s, _ in unused_dirs)
    print(f"\n정리 가능 공간: {total_waste:.1f} MB")
print()

# 4. 테스트 파일
print("4️⃣ 테스트 파일")
print("-"*60)

test_files = list(Path('.').glob('test_*.py'))
print(f"테스트 파일: {len(test_files)}개")
for f in test_files[:10]:
    lines = sum(1 for _ in open(f, 'r', encoding='utf-8'))
    print(f"  📝 {f.name:35s} {lines:4d} 줄")
print()

# 5. 캐시 파일
print("5️⃣ 캐시 파일")
print("-"*60)

caches = [
    ('everything_index.db', 'SQLite 인덱스'),
    ('docs/.ocr_cache.json', 'OCR 캐시'),
    ('config/metadata.db', '메타데이터 DB'),
]

for file, desc in caches:
    p = Path(file)
    if p.exists():
        size_mb = p.stat().st_size / (1024*1024)
        print(f"💾 {desc:20s} {size_mb:6.1f} MB")
    else:
        print(f"❌ {desc:20s} 없음")
print()

# 6. 핵심 문제
print("6️⃣ 발견된 문제")
print("-"*60)

issues = []

# 데이터 불일치
if db_count != real_files:
    issues.append(f"⚠️  DB와 실제 파일 수 불일치 ({db_count} vs {real_files})")

# 복잡한 코드
if total_lines > 5000:
    issues.append(f"⚠️  코드 복잡도 높음 ({total_lines:,}줄)")

# perfect_rag.py 크기
if os.path.exists('perfect_rag.py'):
    lines = sum(1 for _ in open('perfect_rag.py', 'r', encoding='utf-8'))
    if lines > 1500:
        issues.append(f"⚠️  perfect_rag.py 너무 큼 ({lines}줄)")

# 불필요한 파일
if unused_dirs:
    issues.append(f"⚠️  정리 안된 폴더 ({len(unused_dirs)}개)")

if issues:
    for issue in issues:
        print(issue)
else:
    print("✅ 주요 문제 없음!")

print()
print("="*60)
