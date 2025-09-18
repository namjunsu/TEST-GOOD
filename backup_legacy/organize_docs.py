#!/usr/bin/env python3
"""
문서 폴더 체계적으로 정리
"""
import os
import shutil
from pathlib import Path
import re
from collections import defaultdict

def organize_documents():
    docs_dir = Path("docs")
    
    # 통계
    stats = defaultdict(int)
    moved_files = []
    
    # 1. 연도별 폴더 생성
    for year in range(2014, 2025):
        (docs_dir / f"year_{year}").mkdir(exist_ok=True)
    
    # 2. 카테고리별 폴더 생성
    categories = {
        '구매': 'purchase',
        '수리': 'repair',
        '검토': 'review',
        '폐기': 'disposal',
        '소모품': 'consumables'
    }
    
    for ko, en in categories.items():
        (docs_dir / f"category_{en}").mkdir(exist_ok=True)
    
    # 3. 특별 폴더
    (docs_dir / "assets").mkdir(exist_ok=True)  # 자산 데이터
    (docs_dir / "recent").mkdir(exist_ok=True)  # 최근 문서 (2023-2024)
    (docs_dir / "archive").mkdir(exist_ok=True)  # 오래된 문서 (2014-2016)
    
    # 4. PDF 파일 정리
    pdf_files = list(docs_dir.glob("*.pdf"))
    
    for pdf_file in pdf_files:
        filename = pdf_file.name
        
        # 연도 추출
        year_match = re.match(r'(\d{4})', filename)
        if year_match:
            year = int(year_match.group(1))
            
            # 연도별 폴더로 이동
            year_folder = docs_dir / f"year_{year}"
            
            # 추가로 카테고리별 분류
            category_folder = None
            for ko, en in categories.items():
                if ko in filename:
                    category_folder = docs_dir / f"category_{en}"
                    break
            
            # 최근/아카이브 분류
            if year >= 2023:
                # 최근 문서 폴더에도 복사
                shutil.copy2(pdf_file, docs_dir / "recent" / filename)
                stats['recent'] += 1
            elif year <= 2016:
                # 오래된 문서는 아카이브로
                shutil.copy2(pdf_file, docs_dir / "archive" / filename)
                stats['archive'] += 1
            
            # 연도별 폴더로 이동
            new_path = year_folder / filename
            shutil.move(str(pdf_file), str(new_path))
            moved_files.append(f"{filename} -> year_{year}/")
            stats[f'year_{year}'] += 1
            
            # 카테고리별 폴더에도 심볼릭 링크 생성 (중복 방지)
            if category_folder:
                link_path = category_folder / filename
                if not link_path.exists():
                    try:
                        link_path.symlink_to(new_path)
                        stats[f'category_{category_folder.name}'] += 1
                    except:
                        pass
    
    # 5. TXT 파일 (자산 데이터) 정리
    txt_files = list(docs_dir.glob("*.txt"))
    for txt_file in txt_files:
        if '자산' in txt_file.name or '7904' in txt_file.name:
            shutil.move(str(txt_file), str(docs_dir / "assets" / txt_file.name))
            moved_files.append(f"{txt_file.name} -> assets/")
            stats['assets'] += 1
    
    # 6. 결과 출력
    print("📁 문서 폴더 정리 완료!")
    print("="*50)
    
    print("\n📊 정리 통계:")
    for key, value in sorted(stats.items()):
        if value > 0:
            print(f"  {key}: {value}개")
    
    print(f"\n총 {len(moved_files)}개 파일 이동")
    
    # 폴더 구조 표시
    print("\n📂 새로운 폴더 구조:")
    print("docs/")
    print("├── year_2014/ ~ year_2024/  (연도별)")
    print("├── category_purchase/        (구매)")
    print("├── category_repair/          (수리)")
    print("├── category_review/          (검토)")
    print("├── category_disposal/        (폐기)")
    print("├── category_consumables/     (소모품)")
    print("├── recent/                   (2023-2024 최근문서)")
    print("├── archive/                  (2014-2016 오래된문서)")
    print("└── assets/                   (자산 데이터)")
    
    return stats

if __name__ == "__main__":
    organize_documents()
