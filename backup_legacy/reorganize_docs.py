#!/usr/bin/env python3
"""
문서 폴더 완전 재정리
"""
import os
import shutil
from pathlib import Path
import re
from collections import defaultdict

def reorganize_documents():
    docs_dir = Path("docs")

    # 통계
    stats = defaultdict(int)

    # 1. 2025년 폴더 생성 (누락됨)
    (docs_dir / "year_2025").mkdir(exist_ok=True)

    # 2. 루트에 있는 모든 PDF 파일 정리
    pdf_files = list(docs_dir.glob("*.pdf"))
    print(f"📁 {len(pdf_files)}개 PDF 파일 정리 시작...")

    for pdf_file in pdf_files:
        filename = pdf_file.name

        # 연도 추출
        year_match = re.match(r'(\d{4})', filename)
        if year_match:
            year = int(year_match.group(1))

            # 연도별 폴더로 이동
            year_folder = docs_dir / f"year_{year}"
            year_folder.mkdir(exist_ok=True)

            new_path = year_folder / filename
            shutil.move(str(pdf_file), str(new_path))
            stats[f'year_{year}'] += 1
            print(f"  ✅ {filename} → year_{year}/")

            # 추가 분류
            # 1. 최근 문서 (2023-2025)
            if year >= 2023:
                recent_path = docs_dir / "recent" / filename
                if not recent_path.exists():
                    shutil.copy2(new_path, recent_path)
                    stats['recent'] += 1

            # 2. 아카이브 (2014-2016)
            elif year <= 2016:
                archive_path = docs_dir / "archive" / filename
                if not archive_path.exists():
                    shutil.copy2(new_path, archive_path)
                    stats['archive_copy'] += 1

            # 3. 카테고리별 심볼릭 링크
            category = None
            if '구매' in filename:
                category = 'purchase'
            elif '수리' in filename or '보수' in filename:
                category = 'repair'
            elif '검토' in filename:
                category = 'review'
            elif '폐기' in filename:
                category = 'disposal'
            elif '소모품' in filename:
                category = 'consumables'

            if category:
                cat_folder = docs_dir / f"category_{category}"
                cat_folder.mkdir(exist_ok=True)
                link_path = cat_folder / filename
                if not link_path.exists():
                    try:
                        # Windows는 심볼릭 링크 대신 복사
                        shutil.copy2(new_path, link_path)
                        stats[f'category_{category}'] += 1
                    except:
                        pass

    # 3. 결과 출력
    print("\n📊 정리 완료!")
    print("="*50)

    # 연도별 통계
    print("\n📅 연도별 문서:")
    for year in range(2014, 2026):
        year_key = f'year_{year}'
        if stats[year_key] > 0:
            print(f"  {year}년: {stats[year_key]}개")

    print(f"\n📁 특별 폴더:")
    print(f"  recent (2023-2025): {stats['recent']}개")
    print(f"  archive 추가: {stats['archive_copy']}개")

    print(f"\n📂 카테고리별:")
    for cat in ['purchase', 'repair', 'review', 'disposal', 'consumables']:
        if stats[f'category_{cat}'] > 0:
            print(f"  {cat}: {stats[f'category_{cat}']}개")

    # 최종 구조 확인
    print("\n📋 최종 폴더 구조:")
    for folder in sorted(docs_dir.iterdir()):
        if folder.is_dir():
            pdf_count = len(list(folder.glob("*.pdf")))
            if pdf_count > 0:
                print(f"  {folder.name}/: {pdf_count}개 PDF")

if __name__ == "__main__":
    reorganize_documents()