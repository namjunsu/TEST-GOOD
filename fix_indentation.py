#!/usr/bin/env python3
"""
perfect_rag.py의 들여쓰기 오류를 자동으로 수정
"""

import re
import ast
import sys

def fix_indentation_errors():
    """들여쓰기 오류 수정"""
    
    with open('perfect_rag.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 여러 번 시도하면서 오류 수정
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            # 컴파일 시도
            code = ''.join(lines)
            compile(code, 'perfect_rag.py', 'exec')
            print(f"✅ 문법 오류 없음! (시도 {attempt + 1}회)")
            return lines
            
        except IndentationError as e:
            print(f"들여쓰기 오류 발견 (줄 {e.lineno}): {e.msg}")
            
            # 오류가 있는 줄
            error_line = e.lineno - 1
            if error_line < len(lines):
                line = lines[error_line]
                
                # 이전 줄의 들여쓰기 레벨 확인
                prev_indent = 0
                if error_line > 0:
                    prev_line = lines[error_line - 1]
                    prev_indent = len(prev_line) - len(prev_line.lstrip())
                
                # 현재 줄의 들여쓰기 레벨
                current_indent = len(line) - len(line.lstrip())
                
                # 주석 처리된 if문 다음 줄인지 확인
                if error_line > 0 and '#' in lines[error_line - 1] and 'if' in lines[error_line - 1]:
                    # 들여쓰기 제거 또는 감소
                    if current_indent > prev_indent:
                        lines[error_line] = line.lstrip() + '\n'
                        print(f"  수정: 줄 {e.lineno}의 불필요한 들여쓰기 제거")
                        continue
                
                # 예상치 못한 들여쓰기
                if 'unexpected indent' in e.msg:
                    # 이전 줄과 같은 레벨로 조정
                    lines[error_line] = ' ' * prev_indent + line.lstrip()
                    print(f"  수정: 줄 {e.lineno}을 이전 줄과 같은 레벨로 조정")
                    continue
                    
        except SyntaxError as e:
            print(f"문법 오류 발견 (줄 {e.lineno}): {e.msg}")
            
            # 잘못된 주석 처리 수정
            if e.lineno and e.lineno <= len(lines):
                error_line = e.lineno - 1
                line = lines[error_line]
                
                # 백슬래시 뒤에 주석이 있는 경우
                if '\\' in line and '#' in line:
                    # 주석을 다음 줄로 이동
                    parts = line.split('#', 1)
                    if len(parts) == 2:
                        lines[error_line] = parts[0].rstrip() + ' \\\n'
                        lines.insert(error_line + 1, ' ' * len(parts[0].rstrip()) + '# ' + parts[1])
                        print(f"  수정: 줄 {e.lineno}의 주석을 다음 줄로 이동")
                        continue
                        
        except Exception as e:
            print(f"기타 오류: {e}")
            break
    
    return lines

if __name__ == "__main__":
    fixed_lines = fix_indentation_errors()
    
    # 수정된 내용 저장
    with open('perfect_rag.py', 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("\n✅ perfect_rag.py 수정 완료")
    
    # 최종 검증
    try:
        compile(open('perfect_rag.py').read(), 'perfect_rag.py', 'exec')
        print("✅ 최종 검증: 문법 오류 없음!")
    except Exception as e:
        print(f"⚠️ 최종 검증 실패: {e}")