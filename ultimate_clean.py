#!/usr/bin/env python3
"""
Perfect RAG 궁극의 정리 스크립트
모든 자산 코드 완전 제거 및 문법 오류 수정
"""

import re
import ast
import sys
from pathlib import Path
from datetime import datetime
import shutil

def ultimate_cleanup():
    """궁극의 정리 작업"""

    print("="*60)
    print("🚀 Perfect RAG 궁극의 정리")
    print("="*60)

    # 1. 백업 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"perfect_rag_backup_{timestamp}.py"
    shutil.copy('perfect_rag.py', backup_name)
    print(f"💾 백업 생성: {backup_name}")

    # 2. 파일 읽기
    with open('perfect_rag.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"📄 원본 파일: {len(lines)}줄")

    # 3. 자산 관련 코드 제거
    new_lines = []
    i = 0
    removed_count = 0

    while i < len(lines):
        line = lines[i]
        skip_block = False

        # 자산 관련 키워드
        asset_keywords = ['자산', 'asset', 'Asset', '7904', 'S/N', '시리얼', '담당자별', '위치별']

        # 자산 관련 함수 정의 제거
        if 'def ' in line and any(kw in line for kw in ['_search_asset', '_parse_asset', '_load_asset', '_enhance_asset', '_format_asset']):
            # 함수 끝까지 스킵
            indent = len(line) - len(line.lstrip())
            removed_count += 1
            i += 1

            while i < len(lines):
                next_line = lines[i]
                if next_line.strip() and not next_line.startswith(' ' * (indent + 1)):
                    if next_line.strip().startswith('def '):
                        break
                i += 1
                removed_count += 1
            continue

        # 자산 관련 if/elif 블록 제거
        if ('if ' in line or 'elif ' in line) and any(kw in line for kw in asset_keywords):
            # 블록 끝까지 스킵
            indent = len(line) - len(line.lstrip())
            removed_count += 1
            i += 1

            while i < len(lines):
                next_line = lines[i]
                if next_line.strip() and not next_line.startswith(' ' * (indent + 1)):
                    # elif나 else도 제거
                    if next_line.strip().startswith(('elif ', 'else:')):
                        indent = len(next_line) - len(next_line.lstrip())
                        i += 1
                        removed_count += 1
                        continue
                    break
                i += 1
                removed_count += 1
            continue

        # 자산 관련 변수/호출 제거
        if any(kw in line for kw in ['asset_data', 'asset_cache', '_load_asset', 'asset_paths', '자산_파일', '방송장비_자산']):
            removed_count += 1
            i += 1
            continue

        # 주석된 자산 관련 라인과 그 아래 블록 제거
        if '#' in line and 'if' in line and any(kw in line for kw in asset_keywords):
            # 다음 줄들이 들여쓰기 되어있으면 제거
            current_indent = len(line) - len(line.lstrip())
            removed_count += 1
            i += 1

            while i < len(lines) and lines[i].strip():
                next_indent = len(lines[i]) - len(lines[i].lstrip())
                if next_indent > current_indent:
                    removed_count += 1
                    i += 1
                else:
                    break
            continue

        # 정상 라인 유지
        new_lines.append(line)
        i += 1

    print(f"🗑️ 자산 관련 코드 {removed_count}줄 제거")

    # 4. 문법 오류 수정
    print("\n🔧 문법 오류 수정 중...")

    # bare except 수정
    for i, line in enumerate(new_lines):
        if re.match(r'^\\s*except\\s*:\\s*$', line):
            indent = len(line) - len(line.lstrip())
            new_lines[i] = ' ' * indent + 'except Exception as e:\\n'

    # 고아 elif 수정 (else 블록 다음에 오는 elif)
    for i in range(1, len(new_lines)):
        if 'elif ' in new_lines[i]:
            # 이전 블록이 else인지 확인
            j = i - 1
            while j >= 0 and new_lines[j].strip() == '':
                j -= 1

            if j >= 0:
                # 현재 elif의 들여쓰기
                elif_indent = len(new_lines[i]) - len(new_lines[i].lstrip())

                # 이전 non-empty 라인 확인
                prev_line = new_lines[j]
                prev_indent = len(prev_line) - len(prev_line.lstrip())

                # elif가 더 들여쓰기 되어있고 이전이 else가 아니면 if로 변경
                if elif_indent > 0 and 'else:' not in prev_line and 'elif ' not in prev_line and 'if ' not in prev_line:
                    new_lines[i] = new_lines[i].replace('elif ', 'if ')

    # 5. 이모지 제거
    print("🔍 이모지 제거 중...")
    emoji_pattern = re.compile(
        "[\\U0001F300-\\U0001F9FF\\U00002600-\\U000027BF\\U0001F900-\\U0001F9FF]+",
        flags=re.UNICODE
    )

    for i, line in enumerate(new_lines):
        new_lines[i] = emoji_pattern.sub('', line)

    # 6. 저장
    output_file = 'perfect_rag.py'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"\n💾 정리 완료: {len(new_lines)}줄")
    print(f"📉 총 {len(lines) - len(new_lines)}줄 감소")

    # 7. 검증
    print("\n🔍 최종 검증 중...")
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, output_file, 'exec')
        print("✅ 문법 오류 없음!")
        return True
    except SyntaxError as e:
        print(f"⚠️ 문법 오류 발견 (줄 {e.lineno}): {e.msg}")

        # 오류 부분 보기
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if e.lineno:
            start = max(0, e.lineno - 3)
            end = min(len(lines), e.lineno + 2)

            print("\n문제 부분:")
            for i in range(start, end):
                marker = " >>> " if i == e.lineno - 1 else "     "
                print(f"{marker}{i+1}: {lines[i].rstrip()}")

        return False

if __name__ == "__main__":
    success = ultimate_cleanup()

    if success:
        print("\n" + "="*60)
        print("🎉 모든 작업 완료!")
        print("="*60)
        print("\n✅ 완료된 작업:")
        print("  • 자산 관련 코드 완전 제거")
        print("  • Bare except 수정")
        print("  • 문법 오류 해결")
        print("  • 이모지 제거")
        print("  • 코드 정리 및 최적화")

    sys.exit(0 if success else 1)