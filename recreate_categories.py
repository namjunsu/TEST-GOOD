#!/usr/bin/env python3
"""
카테고리 폴더 재생성 스크립트
올바른 경로로 심볼릭 링크 생성
"""

import os
from pathlib import Path
import re

def categorize_file(filename):
    """파일명을 분석해서 카테고리 결정"""
    categories = []

    # 파일명 소문자 변환
    name_lower = filename.lower()

    # 구매/구입 관련
    if any(keyword in name_lower for keyword in ['구매', '구입', '구매기안', '기안서', '구입품의']):
        categories.append('purchase')

    # 수리 관련
    if any(keyword in name_lower for keyword in ['수리', '보수', '정비', '수선', 'as']):
        categories.append('repair')

    # 검토/리뷰 관련
    if any(keyword in name_lower for keyword in ['검토', '보고', '평가', '분석', '리뷰']):
        categories.append('review')

    # 폐기 관련
    if any(keyword in name_lower for keyword in ['폐기', '처분', '매각', '불용']):
        categories.append('disposal')

    # 소모품 관련
    if any(keyword in name_lower for keyword in ['소모품', '용품', '비품', '재료']):
        categories.append('consumables')

    return categories

def create_category_folders():
    """카테고리 폴더 생성 및 심볼릭 링크 생성"""

    docs_dir = Path("/home/wnstn4647/AI-CHAT/docs")

    # 카테고리 폴더 목록
    category_folders = {
        'purchase': docs_dir / 'category_purchase',
        'repair': docs_dir / 'category_repair',
        'review': docs_dir / 'category_review',
        'disposal': docs_dir / 'category_disposal',
        'consumables': docs_dir / 'category_consumables'
    }

    # 카테고리 폴더 생성
    for category, folder in category_folders.items():
        folder.mkdir(exist_ok=True)
        print(f"📁 Created folder: {folder.name}")

    # 통계
    stats = {category: 0 for category in category_folders}
    total_links = 0

    # 연도별 폴더 탐색
    year_folders = [d for d in docs_dir.iterdir() if d.is_dir() and d.name.startswith('year_')]

    for year_folder in sorted(year_folders):
        print(f"\n📅 Processing {year_folder.name}...")

        for pdf_file in year_folder.glob("*.pdf"):
            # 파일 카테고리 결정
            categories = categorize_file(pdf_file.name)

            for category in categories:
                if category in category_folders:
                    # 심볼릭 링크 대상 (절대 경로 사용)
                    link_path = category_folders[category] / pdf_file.name

                    # 이미 존재하면 스킵
                    if link_path.exists():
                        continue

                    try:
                        # 심볼릭 링크 생성 (절대 경로로)
                        link_path.symlink_to(pdf_file.absolute())
                        stats[category] += 1
                        total_links += 1
                        print(f"  ✅ {category}: {pdf_file.name}")
                    except Exception as e:
                        print(f"  ❌ Failed to create link for {pdf_file.name}: {e}")

    # 결과 출력
    print("\n" + "="*50)
    print("📊 카테고리 폴더 생성 완료:")
    print("="*50)
    for category, count in stats.items():
        folder_name = f"category_{category}"
        print(f"  📁 {folder_name}: {count}개 링크")
    print(f"\n  📎 총 {total_links}개 심볼릭 링크 생성됨")

    # 각 카테고리 폴더 확인
    print("\n" + "="*50)
    print("📁 카테고리 폴더 검증:")
    print("="*50)
    for category, folder in category_folders.items():
        if folder.exists():
            links = list(folder.glob("*.pdf"))
            valid_links = [l for l in links if l.exists()]
            broken_links = [l for l in links if not l.exists()]
            print(f"  {folder.name}:")
            print(f"    - 전체 링크: {len(links)}개")
            print(f"    - 유효 링크: {len(valid_links)}개")
            if broken_links:
                print(f"    - 깨진 링크: {len(broken_links)}개 ⚠️")

    return stats

if __name__ == "__main__":
    print("="*50)
    print("🔧 카테고리 폴더 재생성 시작")
    print("="*50)

    stats = create_category_folders()

    print("\n✅ 카테고리 폴더 재생성 완료!")
    print("이제 perfect_rag.py가 정상적으로 작동할 것입니다.")