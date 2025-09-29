#!/usr/bin/env python3
"""
성능 테스트 및 비교 분석
"""

import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any
import logging
from datetime import datetime

# 시스템 컴포넌트 임포트
try:
    from improved_search import ImprovedSearch
    NEW_SYSTEM = True
except ImportError:
    NEW_SYSTEM = False

try:
    from everything_like_search import EverythingLikeSearch
    OLD_SYSTEM = True
except ImportError:
    OLD_SYSTEM = False

try:
    from perfect_rag import PerfectRAG
    PERFECT_RAG = True
except ImportError:
    PERFECT_RAG = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceTester:
    """성능 테스트 도구"""

    def __init__(self, pdf_directory: str = "./pdf_documents"):
        self.pdf_directory = Path(pdf_directory)
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': [],
            'summary': {}
        }

        # 시스템 초기화
        self.systems = {}

        if NEW_SYSTEM:
            logger.info("새 시스템 초기화...")
            self.systems['improved'] = ImprovedSearch(pdf_directory)

        if OLD_SYSTEM:
            logger.info("기존 Everything 시스템 초기화...")
            self.systems['everything'] = EverythingLikeSearch()
            self.systems['everything'].index_directory(pdf_directory)

        if PERFECT_RAG:
            logger.info("PerfectRAG 시스템 초기화...")
            try:
                self.systems['perfect_rag'] = PerfectRAG()
            except:
                logger.warning("PerfectRAG 초기화 실패")

    def run_all_tests(self) -> Dict:
        """모든 테스트 실행"""
        logger.info("=" * 60)
        logger.info("성능 테스트 시작")
        logger.info("=" * 60)

        # 테스트 쿼리
        test_queries = [
            # 단순 검색
            {"query": "DVR", "description": "단순 키워드"},
            {"query": "카메라", "description": "일반적인 용어"},
            {"query": "2024년", "description": "연도 검색"},

            # 복합 검색
            {"query": "DVR 관련 문서 찾아줘", "description": "자연어 쿼리"},
            {"query": "2024년 카메라부 구매", "description": "복합 조건"},
            {"query": "중계차 수리 내역", "description": "특정 주제"},

            # 한국어 처리
            {"query": "조명 장비 구매했던 문서", "description": "과거형 표현"},
            {"query": "스튜디오에서 사용하는 장비", "description": "관계절"},
        ]

        # 각 쿼리로 테스트
        for test_case in test_queries:
            self._run_single_test(test_case)

        # 요약 생성
        self._generate_summary()

        # 결과 저장
        self._save_results()

        return self.results

    def _run_single_test(self, test_case: Dict):
        """단일 테스트 실행"""
        query = test_case['query']
        description = test_case['description']

        logger.info(f"\n테스트: {description} - '{query}'")
        logger.info("-" * 40)

        test_result = {
            'query': query,
            'description': description,
            'systems': {}
        }

        # 각 시스템에서 테스트
        for system_name, system in self.systems.items():
            result = self._test_system(system_name, system, query)
            test_result['systems'][system_name] = result

            # 결과 출력
            logger.info(f"{system_name:15} - "
                       f"시간: {result['search_time']:.3f}s, "
                       f"결과: {result['result_count']}개")

        self.results['tests'].append(test_result)

    def _test_system(self, name: str, system: Any, query: str) -> Dict:
        """시스템별 테스트"""
        result = {
            'system': name,
            'search_time': 0,
            'result_count': 0,
            'results': [],
            'error': None
        }

        try:
            start_time = time.time()

            if name == 'improved':
                # 새 시스템
                response = system.search(query, limit=5)
                result['result_count'] = len(response['documents'])
                result['results'] = [
                    {
                        'file': doc['file_name'],
                        'score': doc.get('final_score', 0)
                    }
                    for doc in response['documents']
                ]

            elif name == 'everything':
                # Everything 시스템
                keywords = self._extract_keywords(query)
                docs = system.search_documents(keywords, limit=5)
                result['result_count'] = len(docs)
                result['results'] = [
                    {
                        'file': doc['name'],
                        'score': doc.get('score', 0)
                    }
                    for doc in docs
                ]

            elif name == 'perfect_rag':
                # PerfectRAG
                response = system.search(query, top_k=5)
                if response and 'documents' in response:
                    result['result_count'] = len(response['documents'])
                    result['results'] = [
                        {
                            'file': Path(doc.get('file', '')).name,
                            'score': doc.get('score', 0)
                        }
                        for doc in response['documents']
                    ]

            result['search_time'] = time.time() - start_time

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"테스트 실패 {name}: {e}")

        return result

    def _extract_keywords(self, query: str) -> List[str]:
        """키워드 추출"""
        stopwords = ['관련', '문서', '찾아', '찾아줘', '검색', '알려', '보여']
        words = query.split()
        return [w for w in words if w not in stopwords and len(w) > 1]

    def _generate_summary(self):
        """요약 통계 생성"""
        summary = {
            'total_tests': len(self.results['tests']),
            'systems_tested': list(self.systems.keys()),
            'average_times': {},
            'average_results': {},
            'success_rate': {}
        }

        # 시스템별 통계
        for system_name in self.systems.keys():
            times = []
            counts = []
            errors = 0

            for test in self.results['tests']:
                if system_name in test['systems']:
                    sys_result = test['systems'][system_name]
                    if not sys_result['error']:
                        times.append(sys_result['search_time'])
                        counts.append(sys_result['result_count'])
                    else:
                        errors += 1

            if times:
                summary['average_times'][system_name] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times)
                }

            if counts:
                summary['average_results'][system_name] = {
                    'mean': statistics.mean(counts),
                    'median': statistics.median(counts),
                    'min': min(counts),
                    'max': max(counts)
                }

            total = len(self.results['tests'])
            summary['success_rate'][system_name] = (total - errors) / total * 100

        self.results['summary'] = summary

    def _save_results(self):
        """결과 저장"""
        # JSON으로 저장
        output_file = f"performance_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        logger.info(f"\n결과 저장: {output_file}")

    def print_comparison_table(self):
        """비교 테이블 출력"""
        print("\n" + "=" * 80)
        print("성능 비교 요약")
        print("=" * 80)

        # 헤더
        print(f"{'시스템':<15} {'평균 시간':<12} {'평균 결과':<12} {'성공률':<10}")
        print("-" * 80)

        summary = self.results['summary']

        for system in summary['systems_tested']:
            avg_time = summary['average_times'].get(system, {}).get('mean', 0)
            avg_results = summary['average_results'].get(system, {}).get('mean', 0)
            success_rate = summary['success_rate'].get(system, 0)

            print(f"{system:<15} {avg_time:<12.3f} {avg_results:<12.1f} {success_rate:<10.1f}%")

        print("=" * 80)

    def benchmark_indexing(self) -> Dict:
        """인덱싱 성능 테스트"""
        logger.info("\n인덱싱 성능 테스트")
        logger.info("-" * 40)

        results = {}

        # 새 시스템 인덱싱
        if 'improved' in self.systems:
            logger.info("새 시스템 인덱싱...")
            start = time.time()
            stats = self.systems['improved'].index_all_documents()
            results['improved'] = {
                'time': time.time() - start,
                'stats': stats
            }

        # Everything 인덱싱
        if 'everything' in self.systems:
            logger.info("Everything 인덱싱...")
            start = time.time()
            self.systems['everything'].index_directory(str(self.pdf_directory))
            results['everything'] = {
                'time': time.time() - start
            }

        return results


class SystemComparator:
    """시스템 비교 도구"""

    def __init__(self):
        self.old_results = []
        self.new_results = []

    def compare_accuracy(self, query: str, expected_files: List[str]) -> Dict:
        """정확도 비교"""
        accuracy = {}

        # 각 시스템 테스트
        # ... (정확도 측정 로직)

        return accuracy

    def compare_features(self) -> Dict:
        """기능 비교"""
        features = {
            'old_system': {
                'OCR': False,
                'metadata_extraction': False,
                'content_search': False,
                'caching': False,
                'year_filter': True,
                'dept_filter': False
            },
            'new_system': {
                'OCR': True,
                'metadata_extraction': True,
                'content_search': True,
                'caching': True,
                'year_filter': True,
                'dept_filter': True
            }
        }

        return features


def main():
    """메인 테스트 실행"""
    print("\n🚀 AI-CHAT 시스템 성능 테스트")
    print("=" * 60)

    # 성능 테스터 생성
    tester = PerformanceTester("./pdf_documents")

    # 모든 테스트 실행
    results = tester.run_all_tests()

    # 비교 테이블 출력
    tester.print_comparison_table()

    # 상세 결과
    print("\n📊 상세 테스트 결과")
    print("-" * 60)

    for test in results['tests']:
        print(f"\n쿼리: '{test['query']}'")

        for system, result in test['systems'].items():
            if result['error']:
                print(f"  {system}: ❌ 오류 - {result['error']}")
            else:
                print(f"  {system}: ✅ {result['result_count']}개 결과, "
                     f"{result['search_time']:.3f}초")

    # 개선 효과
    print("\n📈 개선 효과")
    print("-" * 60)

    if 'improved' in results['summary']['average_times'] and \
       'everything' in results['summary']['average_times']:

        old_time = results['summary']['average_times']['everything']['mean']
        new_time = results['summary']['average_times']['improved']['mean']
        improvement = (old_time - new_time) / old_time * 100

        print(f"검색 속도: {improvement:.1f}% 개선")

        old_results = results['summary']['average_results']['everything']['mean']
        new_results = results['summary']['average_results']['improved']['mean']
        result_improvement = (new_results - old_results) / old_results * 100

        print(f"검색 결과: {result_improvement:.1f}% 더 많은 결과")

    # 인덱싱 성능
    print("\n⚡ 인덱싱 성능 테스트")
    indexing_results = tester.benchmark_indexing()

    for system, result in indexing_results.items():
        print(f"{system}: {result['time']:.2f}초")

    print("\n✅ 테스트 완료!")


if __name__ == "__main__":
    main()