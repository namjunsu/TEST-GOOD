#!/usr/bin/env python3
"""
Perfect RAG 시스템 완전 정리 스크립트
자산 관련 코드 완전 제거 및 문법 오류 수정
"""

import re
import ast
import sys
from pathlib import Path
from typing import List, Tuple

class DeepCleaner:
    """심층 코드 정리 클래스"""

    def __init__(self, filename: str):
        self.filename = filename
        self.lines = []
        self.removed_lines = []
        self.load_file()

    def load_file(self):
        """파일 로드"""
        with open(self.filename, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        print(f"📄 파일 로드: {len(self.lines)}줄")

    def save_file(self, output_name: str = None):
        """정리된 파일 저장"""
        output = output_name or self.filename.replace('.py', '_clean.py')
        with open(output, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)
        print(f"💾 파일 저장: {output} ({len(self.lines)}줄)")
        return output

    def remove_asset_blocks(self):
        """자산 관련 코드 블록 완전 제거"""
        print("\n🔍 자산 관련 코드 제거 시작...")

        # 제거할 패턴들
        asset_patterns = [
            r'자산', r'asset', r'Asset', r'ASSET',
            r'7904', r'S/N', r'시리얼', r'담당자별',
            r'위치별', r'장비별', r'제조사별'
        ]

        new_lines = []
        i = 0
        removed_count = 0

        while i < len(self.lines):
            line = self.lines[i]
            skip_block = False

            # 1. 자산 관련 함수 정의 제거
            if 'def ' in line and any(p in line for p in ['_search_asset', '_process_asset', '_load_asset', '_parse_asset', '_enhance_asset']):
                print(f"  🗑️ 함수 제거: {line.strip()[:50]}")
                # 함수 전체 제거
                indent = len(line) - len(line.lstrip())
                i += 1
                removed_count += 1

                # 함수 끝까지 스킵
                while i < len(self.lines):
                    next_line = self.lines[i]
                    if next_line.strip() and not next_line.startswith(' ' * (indent + 1)):
                        break
                    i += 1
                    removed_count += 1
                continue

            # 2. 자산 관련 조건문 제거
            if any(pattern in line for pattern in asset_patterns):
                # if/elif 문인 경우
                if re.match(r'^\s*(if |elif )', line):
                    print(f"  🗑️ 조건문 제거: {line.strip()[:50]}")
                    # 해당 블록 전체 제거
                    indent = len(line) - len(line.lstrip())
                    i += 1
                    removed_count += 1

                    # 블록 끝까지 스킵
                    while i < len(self.lines):
                        next_line = self.lines[i]
                        if next_line.strip() and not next_line.startswith(' ' * (indent + 1)):
                            # elif나 else인 경우 계속 제거
                            if re.match(r'^\s*(elif |else:)', next_line):
                                i += 1
                                removed_count += 1
                                continue
                            break
                        i += 1
                        removed_count += 1
                    continue

                # 주석 처리된 자산 관련 라인
                elif '#' in line and any(pattern in line for pattern in asset_patterns):
                    # 주석된 if문 다음의 블록도 제거
                    if 'if' in line or 'elif' in line:
                        print(f"  🗑️ 주석된 조건문과 블록 제거: {line.strip()[:50]}")
                        i += 1
                        removed_count += 1

                        # 다음 줄이 들여쓰기된 블록이면 제거
                        if i < len(self.lines):
                            next_line = self.lines[i]
                            current_indent = len(line) - len(line.lstrip())
                            next_indent = len(next_line) - len(next_line.lstrip())

                            while i < len(self.lines) and next_indent > current_indent:
                                i += 1
                                removed_count += 1
                                if i < len(self.lines):
                                    next_line = self.lines[i]
                                    next_indent = len(next_line) - len(next_line.lstrip())
                        continue
                    else:
                        # 일반 주석은 제거
                        i += 1
                        removed_count += 1
                        continue

                # 변수 할당이나 기타 자산 관련 라인
                else:
                    print(f"  🗑️ 라인 제거: {line.strip()[:50]}")
                    i += 1
                    removed_count += 1
                    continue

            # 3. 빈 블록 정리 (자산 코드 제거 후 남은 빈 블록)
            if line.strip() == 'pass' and i > 0:
                prev_line = new_lines[-1] if new_lines else ''
                if 'def ' in prev_line or 'if ' in prev_line or 'elif ' in prev_line:
                    # pass만 있는 빈 함수/조건문은 제거
                    new_lines.pop()  # 이전 줄(def/if) 제거
                    i += 1
                    removed_count += 2
                    continue

            # 정상 라인 유지
            new_lines.append(line)
            i += 1

        self.lines = new_lines
        print(f"✅ 자산 관련 코드 {removed_count}줄 제거 완료")

    def fix_syntax_errors(self):
        """문법 오류 수정"""
        print("\n🔧 문법 오류 수정 시작...")

        max_attempts = 10
        fixed_count = 0

        for attempt in range(max_attempts):
            try:
                code = ''.join(self.lines)
                compile(code, self.filename, 'exec')
                print(f"✅ 문법 오류 없음! (시도 {attempt + 1}회)")
                return True

            except IndentationError as e:
                print(f"  들여쓰기 오류 (줄 {e.lineno}): {e.msg}")
                if not self._fix_indentation_at_line(e.lineno - 1):
                    break
                fixed_count += 1

            except SyntaxError as e:
                print(f"  구문 오류 (줄 {e.lineno}): {e.msg}")
                if not self._fix_syntax_at_line(e.lineno - 1):
                    break
                fixed_count += 1

        print(f"🔧 {fixed_count}개 오류 수정")
        return False

    def _fix_indentation_at_line(self, line_num: int) -> bool:
        """특정 줄의 들여쓰기 수정"""
        if line_num >= len(self.lines):
            return False

        line = self.lines[line_num]

        # 이전 줄 확인
        if line_num > 0:
            prev_line = self.lines[line_num - 1]
            prev_indent = len(prev_line) - len(prev_line.lstrip())

            # 현재 줄 들여쓰기 조정
            self.lines[line_num] = ' ' * prev_indent + line.lstrip()
            return True

        # 첫 줄이면 들여쓰기 제거
        self.lines[line_num] = line.lstrip()
        return True

    def _fix_syntax_at_line(self, line_num: int) -> bool:
        """특정 줄의 구문 오류 수정"""
        if line_num >= len(self.lines):
            return False

        line = self.lines[line_num]

        # 잘못된 백슬래시 제거
        if line.rstrip().endswith('\\'):
            self.lines[line_num] = line.rstrip()[:-1] + '\n'
            return True

        # 불완전한 문자열 수정
        if line.count('"') % 2 == 1:
            self.lines[line_num] = line.rstrip() + '"\n'
            return True

        if line.count("'") % 2 == 1:
            self.lines[line_num] = line.rstrip() + "'\n"
            return True

        return False

    def fix_bare_except(self):
        """bare except 수정"""
        print("\n🔧 Bare except 수정...")

        fixed_count = 0
        for i, line in enumerate(self.lines):
            if re.match(r'^\s*except\s*:\s*$', line):
                indent = len(line) - len(line.lstrip())
                self.lines[i] = ' ' * indent + 'except Exception as e:\n'
                fixed_count += 1

        print(f"✅ {fixed_count}개 bare except 수정 완료")

    def optimize_imports(self):
        """import 문 정리"""
        print("\n📦 Import 문 정리...")

        # import 문 추출
        imports = []
        other_lines = []
        in_imports = True

        for line in self.lines:
            if in_imports and (line.startswith('import ') or line.startswith('from ')):
                imports.append(line)
            elif in_imports and line.strip() and not line.startswith('#'):
                in_imports = False
                other_lines.append(line)
            else:
                other_lines.append(line)

        # 중복 제거 및 정렬
        imports = sorted(list(set(imports)))

        # 파일 재구성
        self.lines = imports + ['\n'] + other_lines
        print(f"✅ {len(imports)}개 import 문 정리 완료")

    def run_complete_cleanup(self):
        """완전한 정리 실행"""
        print("="*60)
        print("🚀 Perfect RAG 심층 정리 시작")
        print("="*60)

        # 1. 자산 관련 코드 완전 제거
        self.remove_asset_blocks()

        # 2. 문법 오류 수정
        self.fix_syntax_errors()

        # 3. Bare except 수정
        self.fix_bare_except()

        # 4. Import 문 정리
        self.optimize_imports()

        print("\n" + "="*60)
        print("✅ 정리 완료!")
        print("="*60)

def main():
    """메인 함수"""
    # 백업 생성
    import shutil
    from datetime import datetime

    backup_name = f"perfect_rag_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    shutil.copy('perfect_rag.py', backup_name)
    print(f"💾 백업 생성: {backup_name}")

    # 정리 실행
    cleaner = DeepCleaner('perfect_rag.py')
    cleaner.run_complete_cleanup()

    # 저장
    output_file = cleaner.save_file('perfect_rag_clean.py')

    # 검증
    try:
        with open(output_file, 'r') as f:
            compile(f.read(), output_file, 'exec')
        print("\n✅ 최종 검증: 문법 오류 없음!")

        # 원본 파일 교체
        shutil.copy(output_file, 'perfect_rag.py')
        print("✅ perfect_rag.py 업데이트 완료!")

    except Exception as e:
        print(f"\n⚠️ 최종 검증 실패: {e}")
        print(f"정리된 파일은 {output_file}에 저장되었습니다.")

if __name__ == "__main__":
    main()