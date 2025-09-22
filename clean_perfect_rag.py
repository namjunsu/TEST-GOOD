#!/usr/bin/env python3
"""
perfect_rag.py에서 자산 관련 코드를 제거하는 스크립트
"""

import re

# perfect_rag.py 읽기
with open('perfect_rag.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"원본 파일: {len(lines)}줄")

# 제거할 메서드들의 시작 줄 찾기
remove_methods = [
    '_search_asset_detail',
    '_search_asset_complex', 
    '_search_asset_by_equipment_type',
    '_search_asset_by_manager',
    '_search_asset_by_price_range',
    '_search_asset_by_year_range',
    '_search_asset_by_year',
    '_search_asset_by_location',
    '_search_asset_with_llm',
    '_search_asset_by_manufacturer',
    '_search_asset_by_model',
    '_load_asset_data',
    '_enhance_asset_response',
    '_format_asset_results',
]

# 새로운 라인 리스트
new_lines = []
i = 0
removed_count = 0

while i < len(lines):
    line = lines[i]
    
    # 자산 관련 메서드 시작인지 확인
    method_found = False
    for method_name in remove_methods:
        if f'def {method_name}' in line:
            method_found = True
            print(f"제거: {method_name} (줄 {i+1})")
            
            # 메서드 끝까지 스킵
            indent_level = len(line) - len(line.lstrip())
            i += 1
            
            while i < len(lines):
                next_line = lines[i]
                
                # 다음 메서드나 클래스 정의를 만나면 종료
                if next_line.strip() and not next_line.startswith(' ' * (indent_level + 1)):
                    if next_line.strip().startswith('def ') or next_line.strip().startswith('class '):
                        i -= 1  # 다음 메서드는 유지
                        break
                i += 1
            removed_count += 1
            break
    
    if not method_found:
        # 자산 관련 변수 초기화 제거
        if 'asset_data' in line or 'asset_cache' in line:
            if 'self.asset' in line:
                print(f"제거: 자산 변수 (줄 {i+1})")
                i += 1
                continue
        
        # _load_asset_data 호출 제거
        if '_load_asset_data()' in line:
            print(f"제거: _load_asset_data 호출 (줄 {i+1})")
            i += 1
            continue
            
        # 자산 관련 조건문 제거/수정
        if "'자산' in" in line or "'7904' in" in line:
            # 주석으로 처리
            new_lines.append(f"        # {line.strip()} # 자산 관련 코드 제거\n")
            i += 1
            continue
            
        new_lines.append(line)
    
    i += 1

print(f"\n제거된 메서드: {removed_count}개")
print(f"수정 후: {len(new_lines)}줄")

# 파일 저장
with open('perfect_rag_cleaned.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("\n✅ perfect_rag_cleaned.py 생성 완료")