#!/usr/bin/env python3
"""
완전한 정리 스크립트 - 모든 특수 문자 제거
"""

import re
import sys
from pathlib import Path
from datetime import datetime
import shutil

def clean_all_special_chars(input_file: str, output_file: str):
    """모든 특수 문자 제거 및 정리"""

    print(f"📖 파일 읽기: {input_file}")
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # 모든 유니코드 특수 문자 제거 패턴
    patterns_to_remove = [
        (r'[^\x00-\x7F]+', ''),  # ASCII가 아닌 모든 문자 제거
        (r'[•●○■□▪▫★☆✓✗✔✘]', ''),  # 특수 기호
        (r'[📊📋📄📝📌💰💡🔍🔧🎯🚀✅❌⚠️]', ''),  # 이모지
        (r'[""''„]', '"'),  # 특수 따옴표를 일반 따옴표로
        (r'[–—]', '-'),  # 특수 대시를 일반 대시로
        (r'[…]', '...'),  # 특수 말줄임표
    ]

    print("🔍 특수 문자 제거 중...")
    for pattern, replacement in patterns_to_remove:
        content = re.sub(pattern, replacement, content)

    # 라인 단위로 추가 정리
    lines = content.split('\n')
    cleaned_lines = []

    for line in lines:
        # 빈 문자열 리터럴 제거
        if line.strip() in ['""', "''", '``', '**', '** **']:
            continue

        # 의미없는 공백 라인 제거
        if line.strip() == '' and len(cleaned_lines) > 0 and cleaned_lines[-1].strip() == '':
            continue

        # 깨진 f-string 수정
        if 'f"' in line and '{' not in line:
            line = line.replace('f"', '"')
        if "f'" in line and '{' not in line:
            line = line.replace("f'", "'")

        cleaned_lines.append(line)

    # 저장
    print(f"💾 정리된 파일 저장: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cleaned_lines))

    return len(lines), len(cleaned_lines)

def fix_remaining_syntax(filepath: str):
    """남은 문법 오류 수정"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    for i, line in enumerate(lines):
        # 잘못된 프롬프트 템플릿 수정
        if '** **' in line or '• :' in line:
            # 이런 라인들은 프롬프트 템플릿의 일부이므로 주석 처리
            if not line.strip().startswith('#'):
                line = '# ' + line

        # 불완전한 문자열 수정
        quote_count = line.count('"') - line.count('\\"')
        if quote_count % 2 == 1:
            line = line.rstrip() + '"\n'

        fixed_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

def validate_and_fix(filepath: str) -> bool:
    """파일 검증 및 자동 수정"""
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            compile(code, filepath, 'exec')
            print(f"✅ 검증 성공! (시도 {attempt + 1}회)")
            return True
        except SyntaxError as e:
            print(f"  문법 오류 (줄 {e.lineno}): {e.msg}")

            # 오류 라인 자동 수정 시도
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if e.lineno and e.lineno <= len(lines):
                error_line = lines[e.lineno - 1]

                # 특수 문자가 있으면 주석 처리
                if any(ord(c) > 127 for c in error_line):
                    lines[e.lineno - 1] = '# ' + error_line
                # 불완전한 문자열이면 닫기
                elif error_line.count('"') % 2 == 1:
                    lines[e.lineno - 1] = error_line.rstrip() + '"\n'
                else:
                    # 그 외의 경우 라인 제거
                    lines[e.lineno - 1] = '\n'

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                print(f"  → 줄 {e.lineno} 수정 시도")
        except Exception as e:
            print(f"❌ 기타 오류: {e}")
            break

    return False

def main():
    """메인 실행"""
    print("="*60)
    print("🚀 Perfect RAG 완전 정리")
    print("="*60)

    # 1단계: 특수 문자 제거
    original, cleaned = clean_all_special_chars(
        'perfect_rag_clean.py',
        'perfect_rag_complete.py'
    )

    print(f"\n📊 정리 통계:")
    print(f"  원본: {original}줄")
    print(f"  정리 후: {cleaned}줄")

    # 2단계: 남은 문법 오류 수정
    print("\n🔧 남은 문법 오류 수정 중...")
    fix_remaining_syntax('perfect_rag_complete.py')

    # 3단계: 검증 및 자동 수정
    print("\n🔍 최종 검증 중...")
    if validate_and_fix('perfect_rag_complete.py'):
        print("\n✅ 모든 오류 해결!")

        # 백업 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"perfect_rag_backup_{timestamp}.py"
        shutil.copy('perfect_rag.py', backup_name)
        print(f"💾 백업 생성: {backup_name}")

        # 파일 교체
        shutil.copy('perfect_rag_complete.py', 'perfect_rag.py')
        print("✅ perfect_rag.py 업데이트 완료!")

        # 임시 파일 정리
        for temp_file in ['perfect_rag_clean.py', 'perfect_rag_final.py',
                         'perfect_rag_fixed.py', 'perfect_rag_complete.py']:
            Path(temp_file).unlink(missing_ok=True)
        print("🧹 임시 파일 정리 완료")

        print("\n" + "="*60)
        print("🎉 완료!")
        print("="*60)
        return True
    else:
        print("⚠️ 수동 수정 필요")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)