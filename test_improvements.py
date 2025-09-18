#!/usr/bin/env python3
"""
개선사항 테스트 스크립트
- config.yaml 로드 테스트
- PDF 병렬처리 테스트
- 에러 핸들링 테스트
"""

import time
import sys
from pathlib import Path
from typing import Dict, List
import traceback

# 색상 코드
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_test_header(test_name: str):
    """테스트 헤더 출력"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}테스트: {test_name}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")


def print_result(success: bool, message: str):
    """테스트 결과 출력"""
    if success:
        print(f"{GREEN}✅ {message}{RESET}")
    else:
        print(f"{RED}❌ {message}{RESET}")


def test_config_manager():
    """ConfigManager 테스트"""
    print_test_header("ConfigManager 및 config.yaml 로드")

    try:
        from config_manager import config_manager

        # 설정 로드 테스트
        print("\n1. 설정 파일 로드 테스트:")
        all_config = config_manager.get_all()
        print_result(bool(all_config), f"설정 항목 수: {len(all_config)}")

        # 주요 설정 값 확인
        print("\n2. 주요 설정 값 확인:")
        tests = [
            ('system.name', 'AI-CHAT RAG System'),
            ('cache.response.max_size', 100),
            ('models.qwen.context_window', 8192),
            ('parallel_processing.pdf.max_workers', 4),
            ('limits.max_text_length', 10000)
        ]

        for key, expected in tests:
            value = config_manager.get(key)
            success = value == expected
            print_result(success, f"{key}: {value} (예상값: {expected})")

        # 호환성 속성 테스트
        print("\n3. 기존 config.py 호환성 테스트:")
        compat_tests = [
            ('DOCS_DIR', './docs'),
            ('N_CTX', 8192),
            ('CACHE_TTL', 3600)
        ]

        for attr, expected in compat_tests:
            value = getattr(config_manager, attr, None)
            success = value == expected
            print_result(success, f"{attr}: {value} (예상값: {expected})")

        return True

    except Exception as e:
        print_result(False, f"ConfigManager 테스트 실패: {e}")
        traceback.print_exc()
        return False


def test_pdf_parallel_processor():
    """PDF 병렬처리 테스트"""
    print_test_header("PDF 병렬처리 모듈")

    try:
        from pdf_parallel_processor import PDFParallelProcessor
        from config_manager import config_manager

        processor = PDFParallelProcessor(config_manager)

        # 테스트용 PDF 찾기
        docs_dir = Path('./docs')
        pdf_files = list(docs_dir.glob('*.pdf'))[:3]  # 최대 3개만 테스트

        if not pdf_files:
            print(f"{YELLOW}⚠️ 테스트할 PDF 파일이 없습니다{RESET}")
            return True

        print(f"\n1. 병렬 처리 테스트 ({len(pdf_files)}개 파일):")

        # 순차 처리 시간 측정
        start_time = time.time()
        sequential_results = {}
        for pdf in pdf_files:
            result = processor._process_single_pdf_safe(pdf)
            sequential_results[str(pdf)] = result
        sequential_time = time.time() - start_time

        # 병렬 처리 시간 측정
        start_time = time.time()
        parallel_results = processor.process_multiple_pdfs(pdf_files)
        parallel_time = time.time() - start_time

        # 결과 비교
        speedup = sequential_time / parallel_time if parallel_time > 0 else 1
        print_result(True, f"순차 처리: {sequential_time:.2f}초")
        print_result(True, f"병렬 처리: {parallel_time:.2f}초")
        print_result(speedup > 1, f"속도 향상: {speedup:.2f}배")

        # 결과 검증
        print("\n2. 처리 결과 검증:")
        for pdf_path, result in parallel_results.items():
            filename = Path(pdf_path).name
            has_text = bool(result.get('text'))
            has_error = 'error' in result

            if has_error:
                print_result(False, f"{filename}: 에러 발생 - {result['error']}")
            else:
                text_len = len(result.get('text', ''))
                page_count = result.get('page_count', 0)
                print_result(has_text, f"{filename}: {text_len}자, {page_count}페이지")

        # 캐시 테스트
        print("\n3. 캐시 테스트:")
        cache_stats = processor.get_cache_stats()
        print_result(True, f"캐시 크기: {cache_stats['cache_size']}")

        return True

    except Exception as e:
        print_result(False, f"PDF 병렬처리 테스트 실패: {e}")
        traceback.print_exc()
        return False


def test_error_handler():
    """에러 핸들러 테스트"""
    print_test_header("에러 핸들러 모듈")

    try:
        from error_handler import RAGErrorHandler, ErrorRecovery, DetailedError, safe_execute

        # 1. 파일 읽기 테스트
        print("\n1. 안전한 파일 읽기 테스트:")
        test_files = [
            ('test_file.txt', 'utf-8'),
            ('존재하지않는파일.txt', None),
        ]

        # 테스트 파일 생성
        test_file = Path('test_file.txt')
        test_file.write_text('테스트 내용입니다', encoding='utf-8')

        for filename, encoding in test_files:
            file_path = Path(filename)
            content = RAGErrorHandler.safe_file_read(file_path)

            if file_path.exists():
                print_result(content is not None, f"{filename}: 읽기 성공")
            else:
                print_result(content is None, f"{filename}: 예상대로 실패")

        # 테스트 파일 삭제
        test_file.unlink()

        # 2. 재시도 데코레이터 테스트
        print("\n2. 재시도 데코레이터 테스트:")
        attempt_count = 0

        @RAGErrorHandler.retry_with_backoff(max_retries=3, backoff_factor=0.1)
        def failing_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("의도적 실패")
            return "성공"

        try:
            result = failing_function()
            print_result(result == "성공", f"3번째 시도에서 성공 (총 {attempt_count}회 시도)")
        except:
            print_result(False, "재시도 실패")

        # 3. DetailedError 테스트
        print("\n3. DetailedError 테스트:")
        try:
            raise DetailedError(
                "테스트 에러",
                details={"key": "value"},
                error_code="TEST_ERROR",
                suggestions=["제안1", "제안2"]
            )
        except DetailedError as e:
            error_dict = e.to_dict()
            print_result('error_code' in error_dict, f"에러 코드: {error_dict.get('error_code')}")
            print_result('suggestions' in error_dict, f"제안 수: {len(error_dict.get('suggestions', []))}")

        # 4. Progressive Degradation 테스트
        print("\n4. Progressive Degradation 테스트:")

        def method1():
            raise ValueError("Method 1 실패")

        def method2():
            raise ValueError("Method 2 실패")

        def method3():
            return "Method 3 성공"

        recovery = ErrorRecovery()
        result = recovery.progressive_degradation([method1, method2, method3])
        print_result(result == "Method 3 성공", "3번째 메서드에서 성공")

        return True

    except Exception as e:
        print_result(False, f"에러 핸들러 테스트 실패: {e}")
        traceback.print_exc()
        return False


def test_integration():
    """통합 테스트"""
    print_test_header("통합 테스트 (perfect_rag.py)")

    try:
        # perfect_rag import 시도
        from perfect_rag import PerfectRAG

        print("\n1. PerfectRAG 초기화 테스트:")
        start_time = time.time()
        rag = PerfectRAG(preload_llm=False)
        init_time = time.time() - start_time

        print_result(True, f"초기화 시간: {init_time:.2f}초")
        print_result(len(rag.pdf_files) > 0, f"PDF 파일: {len(rag.pdf_files)}개")
        print_result(len(rag.metadata_cache) > 0, f"메타데이터 캐시: {len(rag.metadata_cache)}개")

        # 2. 설정값 확인
        print("\n2. 설정값 적용 확인:")
        config_tests = [
            ('max_cache_size', 100),
            ('cache_ttl', 3600),
            ('max_text_length', 10000),
            ('max_pdf_pages', 10)
        ]

        for attr, expected in config_tests:
            value = getattr(rag, attr, None)
            print_result(value == expected, f"{attr}: {value}")

        # 3. PDF 프로세서 확인
        print("\n3. PDF 병렬처리기 확인:")
        has_processor = hasattr(rag, 'pdf_processor')
        print_result(has_processor, "PDF 병렬처리기 초기화됨")

        # 4. 에러 핸들러 확인
        print("\n4. 에러 핸들러 확인:")
        has_handler = hasattr(rag, 'error_handler')
        has_recovery = hasattr(rag, 'error_recovery')
        print_result(has_handler, "에러 핸들러 초기화됨")
        print_result(has_recovery, "에러 복구 모듈 초기화됨")

        return True

    except Exception as e:
        print_result(False, f"통합 테스트 실패: {e}")
        traceback.print_exc()
        return False


def main():
    """메인 테스트 실행"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}AI-CHAT 개선사항 테스트 시작{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    tests = [
        ("ConfigManager", test_config_manager),
        ("PDF 병렬처리", test_pdf_parallel_processor),
        ("에러 핸들러", test_error_handler),
        ("통합 테스트", test_integration)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"{RED}테스트 실행 오류: {e}{RESET}")
            results.append((test_name, False))

    # 최종 결과
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}테스트 결과 요약{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    success_count = sum(1 for _, success in results if success)
    total_count = len(results)

    for test_name, success in results:
        status = f"{GREEN}✅ 성공{RESET}" if success else f"{RED}❌ 실패{RESET}"
        print(f"{test_name}: {status}")

    print(f"\n전체 결과: {success_count}/{total_count} 테스트 통과")

    if success_count == total_count:
        print(f"{GREEN}🎉 모든 테스트를 통과했습니다!{RESET}")
    else:
        print(f"{YELLOW}⚠️ 일부 테스트가 실패했습니다{RESET}")

    return success_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)