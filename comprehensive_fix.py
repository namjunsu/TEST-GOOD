#!/usr/bin/env python3
"""
전문 개발자 수준의 코드 품질 개선 스크립트
Perfect RAG 시스템을 체계적으로 수정
"""

import re
import ast
import sys
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class CodeFixer:
    """전문적인 코드 수정 클래스"""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.lines = []
        self.fixes_applied = []
        self.load_file()
        
    def load_file(self):
        """파일 로드"""
        with open(self.filename, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        logger.info(f"파일 로드 완료: {len(self.lines)}줄")
    
    def save_file(self, output_name: str = None):
        """수정된 파일 저장"""
        output = output_name or self.filename
        with open(output, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)
        logger.info(f"파일 저장 완료: {output}")
    
    def fix_syntax_errors(self) -> bool:
        """문법 오류 수정"""
        max_attempts = 20
        
        for attempt in range(max_attempts):
            try:
                code = ''.join(self.lines)
                compile(code, self.filename, 'exec')
                logger.info(f"✅ 문법 오류 없음 (시도 {attempt + 1}회)")
                return True
                
            except IndentationError as e:
                self._fix_indentation_error(e)
                
            except SyntaxError as e:
                self._fix_syntax_error(e)
                
            except Exception as e:
                logger.error(f"예상치 못한 오류: {e}")
                break
                
        return False
    
    def _fix_indentation_error(self, error: IndentationError):
        """들여쓰기 오류 수정"""
        line_num = error.lineno - 1
        if line_num >= len(self.lines):
            return
            
        logger.info(f"들여쓰기 오류 수정 (줄 {error.lineno}): {error.msg}")
        
        # 문제 라인
        problem_line = self.lines[line_num]
        
        # 이전 줄 확인
        if line_num > 0:
            prev_line = self.lines[line_num - 1]
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            
            # 주석 처리된 if/for/while 다음 줄 처리
            if '#' in prev_line and any(keyword in prev_line for keyword in ['if ', 'for ', 'while ', 'elif ']):
                # 블록 내용을 같은 레벨로 조정
                self.lines[line_num] = ' ' * (prev_indent - 4) + problem_line.lstrip()
                self.fixes_applied.append(f"줄 {error.lineno}: 주석 처리된 제어문 다음 들여쓰기 수정")
                return
        
        # 일반적인 들여쓰기 수정
        if 'unexpected indent' in error.msg:
            # 이전 줄과 같은 레벨로
            if line_num > 0:
                self.lines[line_num] = ' ' * prev_indent + problem_line.lstrip()
                self.fixes_applied.append(f"줄 {error.lineno}: 예상치 못한 들여쓰기 제거")
    
    def _fix_syntax_error(self, error: SyntaxError):
        """구문 오류 수정"""
        line_num = error.lineno - 1
        if line_num >= len(self.lines):
            return
            
        logger.info(f"구문 오류 수정 (줄 {error.lineno}): {error.msg}")
        
        problem_line = self.lines[line_num]
        
        # elif/else가 잘못된 위치에 있는 경우
        if 'invalid syntax' in error.msg and ('elif' in problem_line or 'else' in problem_line):
            # 제거 또는 if로 변경
            if 'elif' in problem_line:
                self.lines[line_num] = problem_line.replace('elif', 'if')
                self.fixes_applied.append(f"줄 {error.lineno}: elif를 if로 변경")
            elif 'else:' in problem_line:
                # else를 제거하거나 주석 처리
                self.lines[line_num] = '#' + problem_line
                self.fixes_applied.append(f"줄 {error.lineno}: 잘못된 else 주석 처리")
    
    def remove_asset_code(self):
        """자산 관련 코드 제거"""
        asset_keywords = ['자산', '7904', 'asset', 'Asset', 'S/N', '시리얼', '담당자별', '위치별']
        removed_count = 0
        
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            
            # 자산 관련 함수 정의 찾기
            if 'def ' in line and any(kw in line for kw in ['_search_asset', '_process_asset', 'asset_']):
                # 함수 전체 제거
                indent = len(line) - len(line.lstrip())
                start = i
                i += 1
                
                # 함수 끝까지 찾기
                while i < len(self.lines):
                    next_line = self.lines[i]
                    if next_line.strip() and not next_line.startswith(' ' * (indent + 1)):
                        break
                    i += 1
                
                # 함수 제거
                del self.lines[start:i]
                removed_count += (i - start)
                logger.info(f"자산 관련 함수 제거: 줄 {start+1}-{i}")
                continue
                
            # 자산 관련 조건문 제거
            if any(kw in line for kw in asset_keywords) and ('if ' in line or 'elif ' in line):
                self.lines[i] = '#' + line
                removed_count += 1
                
            i += 1
        
        logger.info(f"자산 관련 코드 {removed_count}줄 제거/주석 처리")
        self.fixes_applied.append(f"자산 관련 코드 {removed_count}줄 정리")
    
    def fix_bare_except(self):
        """bare except 수정"""
        fixed_count = 0
        
        for i, line in enumerate(self.lines):
            if re.match(r'^\s*except\s*:\s*$', line):
                # bare except를 구체적인 예외로 변경
                indent = len(line) - len(line.lstrip())
                self.lines[i] = ' ' * indent + 'except Exception as e:\n'
                fixed_count += 1
                logger.info(f"줄 {i+1}: bare except 수정")
        
        if fixed_count:
            self.fixes_applied.append(f"bare except {fixed_count}개 수정")
    
    def add_cache_limits(self):
        """캐시 크기 제한 추가"""
        cache_patterns = [
            (r'self\.(\w*cache\w*) = OrderedDict\(\)', r'self.\1 = OrderedDict()  # TODO: maxsize 제한 필요'),
            (r'self\.(\w*cache\w*) = \{\}', r'self.\1 = {}  # TODO: LRU 캐시로 변경 필요')
        ]
        
        fixed_count = 0
        for i, line in enumerate(self.lines):
            for pattern, replacement in cache_patterns:
                if re.search(pattern, line):
                    self.lines[i] = re.sub(pattern, replacement, line)
                    fixed_count += 1
                    logger.info(f"줄 {i+1}: 캐시 제한 TODO 추가")
        
        if fixed_count:
            self.fixes_applied.append(f"캐시 제한 필요 위치 {fixed_count}개 표시")
    
    def add_type_hints_comments(self):
        """타입 힌트 필요 위치 표시"""
        function_pattern = r'^\s*def\s+(\w+)\s*\(([^)]*)\)\s*:'
        
        fixed_count = 0
        for i, line in enumerate(self.lines):
            match = re.match(function_pattern, line)
            if match and '->' not in line:
                # 타입 힌트가 없는 함수
                self.lines[i] = line.rstrip() + '  # TODO: 타입 힌트 추가\n'
                fixed_count += 1
        
        if fixed_count:
            self.fixes_applied.append(f"타입 힌트 필요 함수 {fixed_count}개 표시")
    
    def run_all_fixes(self):
        """모든 수정 작업 실행"""
        logger.info("="*60)
        logger.info("전문적인 코드 수정 시작")
        logger.info("="*60)
        
        # 1. 자산 코드 제거
        logger.info("\n[1/5] 자산 관련 코드 제거...")
        self.remove_asset_code()
        
        # 2. 문법 오류 수정
        logger.info("\n[2/5] 문법 오류 수정...")
        syntax_fixed = self.fix_syntax_errors()
        
        # 3. bare except 수정
        logger.info("\n[3/5] Bare except 수정...")
        self.fix_bare_except()
        
        # 4. 캐시 제한 추가
        logger.info("\n[4/5] 캐시 제한 표시...")
        self.add_cache_limits()
        
        # 5. 타입 힌트 필요 위치 표시
        logger.info("\n[5/5] 타입 힌트 필요 위치 표시...")
        self.add_type_hints_comments()
        
        # 결과 요약
        logger.info("\n" + "="*60)
        logger.info("수정 작업 완료")
        logger.info("="*60)
        for fix in self.fixes_applied:
            logger.info(f"✅ {fix}")
        
        return syntax_fixed

def main():
    """메인 함수"""
    fixer = CodeFixer('perfect_rag.py')
    
    # 모든 수정 작업 실행
    success = fixer.run_all_fixes()
    
    # 파일 저장
    fixer.save_file('perfect_rag_fixed.py')
    
    # 최종 검증
    if success:
        logger.info("\n✅ 모든 문법 오류가 수정되었습니다!")
    else:
        logger.warning("\n⚠️ 일부 문법 오류가 남아있을 수 있습니다.")
    
    return success

if __name__ == "__main__":
    sys.exit(0 if main() else 1)