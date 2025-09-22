#!/usr/bin/env python3
"""
에러 처리 및 로깅 시스템 개선
"""

import re
from pathlib import Path

def improve_error_handling():
    """에러 처리 및 로깅 개선"""

    print("="*60)
    print("🛡️ 에러 처리 및 로깅 개선")
    print("="*60)

    # perfect_rag.py 읽기
    with open('perfect_rag.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 1. 로깅 설정 개선
    logging_setup = '''import logging
from typing import Optional, Dict, Any, List, Tuple
import traceback

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('perfect_rag.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

'''

    # 파일 시작 부분에 로깅 설정 추가
    import_end = 0
    for i, line in enumerate(lines):
        if line.startswith('class '):
            import_end = i
            break

    lines.insert(import_end, logging_setup)
    print("  ✅ 로깅 설정 추가")

    # 2. 에러 처리 클래스 추가
    error_classes = '''
class RAGException(Exception):
    """RAG 시스템 기본 예외"""
    pass

class DocumentNotFoundException(RAGException):
    """문서를 찾을 수 없을 때"""
    pass

class PDFExtractionException(RAGException):
    """PDF 추출 실패"""
    pass

class LLMException(RAGException):
    """LLM 관련 오류"""
    pass

class CacheException(RAGException):
    """캐시 관련 오류"""
    pass

'''

    lines.insert(import_end + 1, error_classes)
    print("  ✅ 커스텀 예외 클래스 추가")

    # 3. 에러 처리 데코레이터 추가
    error_decorator = '''
def handle_errors(default_return=None):
    """에러 처리 데코레이터"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RAGException as e:
                logger.error(f"{func.__name__} - RAG 오류: {str(e)}")
                if default_return is not None:
                    return default_return
                raise
            except Exception as e:
                logger.error(f"{func.__name__} - 예상치 못한 오류: {str(e)}", exc_info=True)
                if default_return is not None:
                    return default_return
                raise RAGException(f"처리 중 오류 발생: {str(e)}")
        return wrapper
    return decorator

'''

    lines.insert(import_end + 2, error_decorator)
    print("  ✅ 에러 처리 데코레이터 추가")

    # 4. Exception as e를 구체적인 예외로 변경
    print("\n  🔄 구체적인 예외 처리로 변경 중...")

    replacements = [
        # PDF 관련
        (r'except Exception as e:(\s*#.*PDF)', 'except (FileNotFoundError, PDFExtractionException) as e:\\1'),
        (r'pdfplumber.*\nexcept Exception as e:', 'except PDFExtractionException as e:'),

        # LLM 관련
        (r'llm.*\nexcept Exception as e:', 'except LLMException as e:'),

        # 파일 관련
        (r'open\(.*\nexcept Exception as e:', 'except (FileNotFoundError, IOError, PermissionError) as e:'),

        # 캐시 관련
        (r'cache.*\nexcept Exception as e:', 'except CacheException as e:'),
    ]

    modified_count = 0
    for i, line in enumerate(lines):
        if 'except Exception as e:' in line:
            # 이전 줄 확인해서 컨텍스트 파악
            if i > 0:
                prev_line = lines[i-1]
                if 'pdf' in prev_line.lower():
                    lines[i] = line.replace('Exception', 'PDFExtractionException')
                    modified_count += 1
                elif 'llm' in prev_line.lower():
                    lines[i] = line.replace('Exception', 'LLMException')
                    modified_count += 1
                elif 'open(' in prev_line:
                    lines[i] = line.replace('Exception', '(FileNotFoundError, IOError)')
                    modified_count += 1
                elif 'cache' in prev_line.lower():
                    lines[i] = line.replace('Exception', 'CacheException')
                    modified_count += 1

    print(f"  ✅ {modified_count}개 예외 처리 개선")

    # 5. 주요 함수에 로깅 추가
    print("\n  🔄 주요 함수에 로깅 추가 중...")

    log_points = [
        ('def search(', 'logger.info(f"검색 시작: {query[:50]}...")'),
        ('def _extract_metadata(', 'logger.debug("메타데이터 추출 시작")'),
        ('def _generate_llm_summary(', 'logger.info("LLM 요약 생성 시작")'),
        ('def _build_metadata_cache(', 'logger.info("메타데이터 캐시 구축 시작")'),
    ]

    for func_signature, log_message in log_points:
        for i, line in enumerate(lines):
            if func_signature in line:
                # 함수 시작 다음 줄에 로깅 추가
                indent = len(lines[i+1]) - len(lines[i+1].lstrip())
                lines.insert(i+2, ' ' * indent + log_message + '\\n')
                break

    print("  ✅ 로깅 포인트 추가 완료")

    # 6. 에러 복구 로직 추가
    recovery_logic = '''
    def _safe_pdf_extract(self, pdf_path, max_retries=3):
        """안전한 PDF 추출 with 재시도"""
        for attempt in range(max_retries):
            try:
                return self._extract_full_pdf_content(pdf_path)
            except PDFExtractionException as e:
                logger.warning(f"PDF 추출 실패 (시도 {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"PDF 추출 최종 실패: {pdf_path}")
                    return None
                time.sleep(1)  # 재시도 전 대기

    def _validate_input(self, query):
        """입력 검증"""
        if not query:
            raise ValueError("쿼리가 비어있습니다")

        if len(query) > 1000:
            logger.warning(f"쿼리가 너무 깁니다: {len(query)}자")
            query = query[:1000]

        # SQL 인젝션 방지
        dangerous_patterns = ['DROP', 'DELETE', 'INSERT', 'UPDATE', '--', ';']
        for pattern in dangerous_patterns:
            if pattern in query.upper():
                raise ValueError(f"허용되지 않은 패턴: {pattern}")

        return query.strip()
'''

    # PerfectRAG 클래스 내에 추가
    for i, line in enumerate(lines):
        if 'class PerfectRAG:' in line:
            # 클래스 끝 부분 찾기
            class_end = len(lines)
            for j in range(i+1, len(lines)):
                if lines[j].startswith('class ') or (lines[j].strip() and not lines[j].startswith(' ')):
                    class_end = j
                    break

            lines.insert(class_end - 1, recovery_logic)
            print("  ✅ 에러 복구 로직 추가")
            break

    # 파일 저장
    with open('perfect_rag.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print("\n✅ 에러 처리 및 로깅 개선 완료!")
    print("  - 구조화된 로깅 시스템")
    print("  - 커스텀 예외 클래스")
    print("  - 에러 처리 데코레이터")
    print("  - 입력 검증 로직")
    print("  - 에러 복구 메커니즘")

if __name__ == "__main__":
    improve_error_handling()