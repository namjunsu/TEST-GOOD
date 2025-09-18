#!/usr/bin/env python3
"""
심볼릭 링크 수정 스크립트
category 폴더의 잘못된 심볼릭 링크를 수정
"""

import os
from pathlib import Path

def fix_category_symlinks():
    """category 폴더의 심볼릭 링크 수정"""
    
    docs_dir = Path("/home/wnstn4647/AI-CHAT/docs")
    category_folders = [
        "category_purchase",
        "category_repair", 
        "category_review",
        "category_disposal",
        "category_consumables"
    ]
    
    fixed_count = 0
    error_count = 0
    
    for category in category_folders:
        category_path = docs_dir / category
        if not category_path.exists():
            continue
            
        print(f"\n📁 {category} 폴더 확인 중...")
        
        for item in category_path.iterdir():
            if item.is_symlink():
                target = Path(os.readlink(item))
                
                # 잘못된 링크인지 확인
                if not (docs_dir / target).exists():
                    # 공백을 언더스코어로 변경
                    new_target_str = str(target).replace(" ", "_")
                    new_target = Path(new_target_str)
                    
                    # 새 타겟이 존재하는지 확인
                    if (docs_dir / new_target).exists():
                        try:
                            # 기존 심볼릭 링크 삭제
                            item.unlink()
                            # 새 심볼릭 링크 생성
                            item.symlink_to(docs_dir / new_target)
                            print(f"  ✅ 수정: {item.name}")
                            fixed_count += 1
                        except Exception as e:
                            print(f"  ❌ 실패: {item.name} - {e}")
                            error_count += 1
    
    print(f"\n📊 결과:")
    print(f"  - 수정된 링크: {fixed_count}개")
    print(f"  - 실패: {error_count}개")
    
    return fixed_count, error_count

if __name__ == "__main__":
    print("="*50)
    print("🔧 심볼릭 링크 수정 시작")
    print("="*50)
    
    fixed, errors = fix_category_symlinks()
    
    if fixed > 0:
        print(f"\n✅ {fixed}개의 심볼릭 링크가 수정되었습니다!")
    else:
        print("\n⚠️ 수정할 심볼릭 링크가 없습니다.")
