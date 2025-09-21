#!/usr/bin/env python3
"""
AI-CHAT RAG 시스템 종합 테스트 스크립트

주요 기능:
- 다양한 검색 모드 테스트 (document/asset)
- 성능 측정 및 벤치마킹
- 캐시 효율성 검증
- 오류 처리 테스트
- 결과 품질 검증
"""

import sys
import os
import time
import json
import traceback
import psutil
import gc
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import defaultdict

# 디버그 출력 캡처를 위한 설정
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

try:
    from perfect_rag import PerfectRAG
    from log_system import ChatLogger
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# 테스트 설정 상수
TEST_TIMEOUT = 30.0
MEMORY_THRESHOLD_MB = 500
RESPONSE_TIME_THRESHOLD = 5.0  # seconds

# 컬러 출력 지원
class Colors:
    """터미널 컬러 코드"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class TestResult:
    """테스트 결과 저장 클래스"""
    def __init__(self, name: str, passed: bool, duration: float,
                 memory_used: float = 0, error: str = None, details: Dict = None):
        self.name = name
        self.passed = passed
        self.duration = duration
        self.memory_used = memory_used
        self.error = error
        self.details = details or {}
        self.timestamp = datetime.now()

class QuickTestRunner:
    """종합 테스트 러너"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.rag: Optional[PerfectRAG] = None
        self.logger = ChatLogger()
        self.start_memory = 0

    def setup(self) -> bool:
        """테스트 환경 설정"""
        try:
            if self.verbose:
                print(f"{Colors.HEADER}🚀 RAG 시스템 초기화 중...{Colors.ENDC}")

            start_time = time.time()
            self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024

            # RAG 시스템 초기화
            self.rag = PerfectRAG()

            init_time = time.time() - start_time
            memory_after = psutil.Process().memory_info().rss / 1024 / 1024
            memory_used = memory_after - self.start_memory

            if self.verbose:
                print(f"{Colors.OKGREEN}✅ 초기화 완료: {init_time:.2f}초, 메모리: {memory_used:.1f}MB{Colors.ENDC}")

            return True

        except Exception as e:
            print(f"{Colors.FAIL}❌ 초기화 실패: {e}{Colors.ENDC}")
            return False
    
    def test_intent_classification(self) -> TestResult:
        """검색 의도 분류 테스트"""
        test_cases = [
            # (쿼리, 예상 의도)
            ("중계차 장비 목록", "asset"),
            ("2020년 구매 문서", "document"),
            ("신승만 차장 담당 장비", "asset"),
            ("예산 집행 현황 PDF", "document"),
            ("CCU 장비 위치", "asset"),
            ("계약서 조회", "document"),
        ]

        if self.verbose:
            print(f"\n{Colors.HEADER}📝 의도 분류 테스트{Colors.ENDC}")

        start_time = time.time()
        passed_count = 0
        failed_cases = []

        for query, expected_intent in test_cases:
            try:
                actual_intent = self.rag._classify_search_intent(query)
                if actual_intent == expected_intent:
                    passed_count += 1
                    if self.verbose:
                        print(f"  ✅ '{query}' → {actual_intent}")
                else:
                    failed_cases.append((query, expected_intent, actual_intent))
                    if self.verbose:
                        print(f"  ❌ '{query}' → {actual_intent} (예상: {expected_intent})")
            except Exception as e:
                failed_cases.append((query, expected_intent, str(e)))
                if self.verbose:
                    print(f"  ❌ '{query}' → 오류: {e}")

        duration = time.time() - start_time
        passed = passed_count == len(test_cases)

        return TestResult(
            name="의도 분류",
            passed=passed,
            duration=duration,
            details={
                "total": len(test_cases),
                "passed": passed_count,
                "failed": len(failed_cases),
                "failed_cases": failed_cases
            }
        )
    
    def test_asset_search(self) -> TestResult:
        """자산 검색 테스트"""
        test_queries = [
            "중계차 장비 현황",
            "신승만 차장 담당 장비",
            "2020년 이전 구매 장비",
            "1억원 이상 장비",
        ]

        if self.verbose:
            print(f"\n{Colors.HEADER}🔍 자산 검색 테스트{Colors.ENDC}")

        results_info = []
        total_duration = 0
        total_memory = 0

        for query in test_queries:
            if self.verbose:
                print(f"  테스트: {query}")

            start_time = time.time()
            start_mem = psutil.Process().memory_info().rss / 1024 / 1024

            try:
                result = self.rag._answer_internal(query, mode='asset')
                duration = time.time() - start_time
                memory_used = psutil.Process().memory_info().rss / 1024 / 1024 - start_mem

                # 결과 검증
                has_data = bool(result) and len(result) > 100
                has_format = any(marker in result for marker in ["📊", "💰", "📅", "👤"])

                results_info.append({
                    "query": query,
                    "duration": duration,
                    "memory_mb": memory_used,
                    "result_len": len(result) if result else 0,
                    "has_data": has_data,
                    "has_format": has_format,
                    "success": has_data and has_format
                })

                total_duration += duration
                total_memory += abs(memory_used)

                if self.verbose:
                    status = "✅" if (has_data and has_format) else "⚠️"
                    print(f"    {status} {duration:.2f}초, {len(result):,}자")

            except Exception as e:
                results_info.append({
                    "query": query,
                    "error": str(e),
                    "success": False
                })
                if self.verbose:
                    print(f"    ❌ 오류: {e}")

        success_count = sum(1 for r in results_info if r.get("success", False))
        passed = success_count == len(test_queries)

        return TestResult(
            name="자산 검색",
            passed=passed,
            duration=total_duration,
            memory_used=total_memory,
            details={
                "queries_tested": len(test_queries),
                "successful": success_count,
                "avg_duration": total_duration / len(test_queries) if test_queries else 0,
                "results": results_info
            }
        )

    def test_document_search(self) -> TestResult:
        """문서 검색 테스트"""
        test_queries = [
            "2020년 구매 계약서",
            "예산 집행 현황",
            "방송 장비 구매",
        ]

        if self.verbose:
            print(f"\n{Colors.HEADER}📄 문서 검색 테스트{Colors.ENDC}")

        results_info = []
        total_duration = 0

        for query in test_queries:
            if self.verbose:
                print(f"  테스트: {query}")

            start_time = time.time()

            try:
                result = self.rag._answer_internal(query, mode='document')
                duration = time.time() - start_time

                # 결과 검증
                has_content = bool(result) and len(result) > 100
                has_sources = "출처" in result or "문서" in result or ".pdf" in result

                results_info.append({
                    "query": query,
                    "duration": duration,
                    "result_len": len(result) if result else 0,
                    "has_content": has_content,
                    "has_sources": has_sources,
                    "success": has_content
                })

                total_duration += duration

                if self.verbose:
                    status = "✅" if has_content else "⚠️"
                    print(f"    {status} {duration:.2f}초, {len(result):,}자")

            except Exception as e:
                results_info.append({
                    "query": query,
                    "error": str(e),
                    "success": False
                })
                if self.verbose:
                    print(f"    ❌ 오류: {e}")

        success_count = sum(1 for r in results_info if r.get("success", False))
        passed = success_count >= len(test_queries) * 0.7  # 70% 이상 성공

        return TestResult(
            name="문서 검색",
            passed=passed,
            duration=total_duration,
            details={
                "queries_tested": len(test_queries),
                "successful": success_count,
                "avg_duration": total_duration / len(test_queries) if test_queries else 0,
                "results": results_info
            }
        )

    def test_cache_performance(self) -> TestResult:
        """캐시 성능 테스트"""
        if self.verbose:
            print(f"\n{Colors.HEADER}⚡ 캐시 성능 테스트{Colors.ENDC}")

        test_query = "2020년 장비 구매 현황"

        # 첫 번째 실행 (캐시 미스)
        start_time = time.time()
        result1 = self.rag._answer_internal(test_query, mode='document')
        first_duration = time.time() - start_time

        if self.verbose:
            print(f"  첫 실행: {first_duration:.2f}초")

        # 두 번째 실행 (캐시 히트)
        start_time = time.time()
        result2 = self.rag._answer_internal(test_query, mode='document')
        second_duration = time.time() - start_time

        if self.verbose:
            print(f"  캐시 히트: {second_duration:.2f}초")

        # 성능 향상 계산
        speedup = first_duration / second_duration if second_duration > 0 else float('inf')
        cache_effective = second_duration < first_duration * 0.1  # 90% 이상 빨라야 함

        if self.verbose:
            if cache_effective:
                print(f"  {Colors.OKGREEN}✅ 캐시 효과: {speedup:.1f}배 빠름{Colors.ENDC}")
            else:
                print(f"  {Colors.WARNING}⚠️ 캐시 효과 미흡: {speedup:.1f}배{Colors.ENDC}")

        return TestResult(
            name="캐시 성능",
            passed=cache_effective,
            duration=first_duration + second_duration,
            details={
                "first_run": first_duration,
                "cached_run": second_duration,
                "speedup": speedup,
                "cache_effective": cache_effective
            }
        )

    def test_error_handling(self) -> TestResult:
        """오류 처리 테스트"""
        if self.verbose:
            print(f"\n{Colors.HEADER}🛡️ 오류 처리 테스트{Colors.ENDC}")

        error_cases = [
            ("", "빈 쿼리"),
            ("a" * 1000, "너무 긴 쿼리"),
            ("@#$%^&*()", "특수문자 쿼리"),
            (None, "None 쿼리"),
        ]

        handled_count = 0

        for query, description in error_cases:
            if self.verbose:
                print(f"  테스트: {description}")

            try:
                if query is not None:
                    result = self.rag._classify_search_intent(query)
                    handled_count += 1
                    if self.verbose:
                        print(f"    ✅ 처리됨: {result}")
                else:
                    # None 처리
                    try:
                        result = self.rag._classify_search_intent(query)
                    except (TypeError, AttributeError):
                        handled_count += 1
                        if self.verbose:
                            print(f"    ✅ 예외 적절히 처리됨")

            except Exception as e:
                if self.verbose:
                    print(f"    ⚠️ 예외 발생: {e}")

        passed = handled_count >= len(error_cases) * 0.75  # 75% 이상 처리

        return TestResult(
            name="오류 처리",
            passed=passed,
            duration=0,
            details={
                "total_cases": len(error_cases),
                "handled": handled_count,
                "success_rate": handled_count / len(error_cases) if error_cases else 0
            }
        )

    def run_all_tests(self) -> Dict:
        """모든 테스트 실행"""
        if not self.setup():
            return {"error": "Setup failed"}

        print(f"\n{Colors.BOLD}{'='*70}{Colors.ENDC}")
        print(f"{Colors.BOLD}AI-CHAT RAG 시스템 종합 테스트{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}")

        # 테스트 실행
        test_methods = [
            self.test_intent_classification,
            self.test_asset_search,
            self.test_document_search,
            self.test_cache_performance,
            self.test_error_handling,
        ]

        for test_method in test_methods:
            try:
                result = test_method()
                self.results.append(result)

            except Exception as e:
                self.results.append(TestResult(
                    name=test_method.__name__,
                    passed=False,
                    duration=0,
                    error=str(e)
                ))
                if self.verbose:
                    print(f"{Colors.FAIL}❌ 테스트 실패: {e}{Colors.ENDC}")
                    traceback.print_exc()

        # 결과 요약
        return self.generate_summary()

    def generate_summary(self) -> Dict:
        """테스트 결과 요약 생성"""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        total_duration = sum(r.duration for r in self.results)
        total_memory = sum(r.memory_used for r in self.results if r.memory_used > 0)

        # 최종 메모리 사용량
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_increase = final_memory - self.start_memory

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": total_tests - passed_tests,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "total_duration": total_duration,
            "memory_usage": {
                "start_mb": self.start_memory,
                "final_mb": final_memory,
                "increase_mb": memory_increase
            },
            "test_results": [{
                "name": r.name,
                "passed": r.passed,
                "duration": r.duration,
                "details": r.details
            } for r in self.results]
        }

        # 콘솔 출력
        print(f"\n{Colors.BOLD}{'='*70}{Colors.ENDC}")
        print(f"{Colors.BOLD}테스트 결과 요약{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}")

        for result in self.results:
            status = f"{Colors.OKGREEN}✅ PASS{Colors.ENDC}" if result.passed else f"{Colors.FAIL}❌ FAIL{Colors.ENDC}"
            print(f"{result.name:20s}: {status} ({result.duration:.2f}초)")
            if result.error:
                print(f"  오류: {result.error}")

        print(f"\n{Colors.BOLD}총계:{Colors.ENDC}")
        print(f"  테스트: {passed_tests}/{total_tests} 통과 ({summary['pass_rate']:.1f}%)")
        print(f"  실행 시간: {total_duration:.2f}초")
        print(f"  메모리 증가: {memory_increase:.1f}MB")

        # 성능 평가
        if summary['pass_rate'] >= 80:
            print(f"\n{Colors.OKGREEN}🎉 테스트 성공!{Colors.ENDC}")
        elif summary['pass_rate'] >= 60:
            print(f"\n{Colors.WARNING}⚠️ 일부 테스트 실패{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}❌ 테스트 실패{Colors.ENDC}")

        # 결과 파일 저장
        self.save_results(summary)

        return summary

    def save_results(self, summary: Dict):
        """테스트 결과 저장"""
        try:
            results_dir = Path("test_results")
            results_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = results_dir / f"quick_test_{timestamp}.json"

            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            print(f"\n📁 결과 저장: {result_file}")

        except Exception as e:
            print(f"\n⚠️ 결과 저장 실패: {e}")

def quick_test(verbose: bool = True):
    """빠른 테스트 실행 함수 (레거시 호환)"""
    runner = QuickTestRunner(verbose=verbose)
    return runner.run_all_tests()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI-CHAT RAG 시스템 종합 테스트")
    parser.add_argument("--quiet", "-q", action="store_true", help="조용한 모드")
    parser.add_argument("--json", action="store_true", help="JSON 결과만 출력")

    args = parser.parse_args()

    if args.json:
        # JSON 모드: 결과만 출력
        runner = QuickTestRunner(verbose=False)
        summary = runner.run_all_tests()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        # 일반 모드
        quick_test(verbose=not args.quiet)