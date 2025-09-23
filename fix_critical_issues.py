#!/usr/bin/env python3
"""
Critical 이슈 자동 수정 스크립트
bare except를 구체적 예외로 변경
"""

import re
from pathlib import Path

def fix_bare_excepts(filepath: Path):
    """bare except를 구체적 예외로 변경"""

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # bare except 패턴 찾기 및 수정
    replacements = [
        ('except:\n', 'except Exception as e:\n'),
        ('except: ', 'except Exception as e: '),
        ('except Exception as e as e:', 'except Exception as e:'),  # 중복 수정 방지
    ]

    original = content
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Fixed bare excepts in {filepath}")
        return True
    return False

def add_type_hints(filepath: Path):
    """타입 힌트 추가"""

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    modified = False
    for i, line in enumerate(lines):
        # def 함수에 타입 힌트 추가
        if line.strip().startswith('def ') and '->' not in line:
            if '(self' in line:
                lines[i] = line.rstrip()[:-1] + ' -> None:\n'
                modified = True

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"✅ Added type hints to {filepath}")

def split_long_functions(filepath: Path):
    """긴 함수 분할 제안"""

    suggestions = []

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_func = None
    func_start = 0

    for i, line in enumerate(lines):
        if line.strip().startswith('def '):
            if current_func and (i - func_start) > 50:
                suggestions.append({
                    'function': current_func,
                    'lines': i - func_start,
                    'start': func_start,
                    'recommendation': 'Split into smaller functions'
                })
            current_func = line.strip().split('(')[0].replace('def ', '')
            func_start = i

    return suggestions

def main():
    """메인 실행"""
    print("🚨 Critical 이슈 수정 시작")
    print("=" * 60)

    files_to_fix = ['perfect_rag.py', 'web_interface.py', 'auto_indexer.py']

    for filename in files_to_fix:
        filepath = Path(filename)
        if filepath.exists():
            print(f"\n📄 {filename} 수정 중...")

            # 1. Bare except 수정
            fix_bare_excepts(filepath)

            # 2. 타입 힌트 추가
            # add_type_hints(filepath)  # 주의: 실제로는 더 정교한 처리 필요

            # 3. 긴 함수 분할 제안
            suggestions = split_long_functions(filepath)
            if suggestions:
                print(f"  📝 함수 분할 제안:")
                for s in suggestions[:3]:
                    print(f"    - {s['function']}: {s['lines']}줄 → 분할 필요")

    print("\n✅ Critical 이슈 수정 완료!")
    print("\n다음 단계: python3 setup_tests.py")

if __name__ == "__main__":
    main()