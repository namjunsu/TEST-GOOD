"""
성능 벤치마크
=============

시스템 성능을 측정하고 분석합니다.
"""

import time
import psutil
import numpy as np
from pathlib import Path
import json

from rag_core.config import RAGConfig
from rag_core.search import HybridSearch
from rag_core.document.pdf_processor import PDFProcessor
from rag_core.cache.lru_cache import LRUCache


class PerformanceBenchmark:
    """성능 벤치마크 클래스"""

    def __init__(self):
        self.config = RAGConfig()
        self.results = {}

    def measure_pdf_processing(self, num_files=10):
        """PDF 처리 성능 측정"""
        processor = PDFProcessor(self.config)
        pdf_files = list(Path("docs").glob("**/*.pdf"))[:num_files]

        if not pdf_files:
            return None

        times = []
        for pdf_file in pdf_files:
            start = time.time()
            text = processor.extract_text(pdf_file)
            elapsed = time.time() - start
            times.append(elapsed)

        return {
            'avg_time': np.mean(times),
            'min_time': np.min(times),
            'max_time': np.max(times),
            'total_files': len(pdf_files)
        }

    def measure_search_performance(self, num_queries=20):
        """검색 성능 측정"""
        search = HybridSearch(self.config)

        # 테스트 문서 생성
        test_docs = []
        for i in range(100):
            test_docs.append({
                'id': f'doc_{i}',
                'text': f'테스트 문서 {i}. 장비 구매 수리 폐기 검토 내용.',
                'metadata': {'year': str(2020 + i % 5)}
            })

        # 인덱스 구축 시간
        start = time.time()
        search.build_index(test_docs)
        index_time = time.time() - start

        # 검색 시간 측정
        queries = ['장비 구매', '수리 요청', '2023년', '폐기 신청', '검토 보고서']
        search_times = []

        for _ in range(num_queries):
            query = queries[_ % len(queries)]
            start = time.time()
            results = search.search(query, top_k=10)
            elapsed = time.time() - start
            search_times.append(elapsed)

        return {
            'index_time': index_time,
            'avg_search_time': np.mean(search_times),
            'min_search_time': np.min(search_times),
            'max_search_time': np.max(search_times),
            'num_docs': len(test_docs),
            'num_queries': num_queries
        }

    def measure_cache_performance(self, num_operations=1000):
        """캐시 성능 측정"""
        cache = LRUCache(self.config)

        # Write 성능
        write_times = []
        for i in range(num_operations):
            key = f'key_{i}'
            value = {'data': f'value_{i}' * 100}
            start = time.time()
            cache.set(key, value, raw_key=True)
            write_times.append(time.time() - start)

        # Read 성능 (hit)
        read_hit_times = []
        for i in range(num_operations // 2):
            key = f'key_{i}'
            start = time.time()
            result = cache.get(key, raw_key=True)
            read_hit_times.append(time.time() - start)

        # Read 성능 (miss)
        read_miss_times = []
        for i in range(num_operations // 2):
            key = f'nonexistent_{i}'
            start = time.time()
            result = cache.get(key, raw_key=True)
            read_miss_times.append(time.time() - start)

        stats = cache.get_stats()

        return {
            'avg_write_time': np.mean(write_times) * 1000,  # ms
            'avg_read_hit_time': np.mean(read_hit_times) * 1000,
            'avg_read_miss_time': np.mean(read_miss_times) * 1000,
            'cache_stats': stats
        }

    def measure_memory_usage(self):
        """메모리 사용량 측정"""
        process = psutil.Process()
        memory_info = process.memory_info()

        return {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024,
            'percent': process.memory_percent(),
            'available_mb': psutil.virtual_memory().available / 1024 / 1024
        }

    def run_all_benchmarks(self):
        """모든 벤치마크 실행"""
        print("🚀 성능 벤치마크 시작...")
        print("="*50)

        # PDF 처리
        print("\n📄 PDF 처리 성능 측정...")
        pdf_results = self.measure_pdf_processing(5)
        if pdf_results:
            self.results['pdf_processing'] = pdf_results
            print(f"  평균: {pdf_results['avg_time']:.3f}초")

        # 검색 성능
        print("\n🔍 검색 성능 측정...")
        search_results = self.measure_search_performance(20)
        self.results['search'] = search_results
        print(f"  인덱싱: {search_results['index_time']:.3f}초")
        print(f"  평균 검색: {search_results['avg_search_time']:.4f}초")

        # 캐시 성능
        print("\n💾 캐시 성능 측정...")
        cache_results = self.measure_cache_performance(1000)
        self.results['cache'] = cache_results
        print(f"  쓰기: {cache_results['avg_write_time']:.3f}ms")
        print(f"  읽기(hit): {cache_results['avg_read_hit_time']:.3f}ms")

        # 메모리 사용량
        print("\n🧠 메모리 사용량...")
        memory_results = self.measure_memory_usage()
        self.results['memory'] = memory_results
        print(f"  RSS: {memory_results['rss_mb']:.1f}MB")
        print(f"  사용률: {memory_results['percent']:.1f}%")

        # 결과 저장
        self.save_results()

        print("\n"+"="*50)
        print("✅ 벤치마크 완료!")

        return self.results

    def save_results(self):
        """결과 저장"""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f'benchmark_results_{timestamp}.json'

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"\n📊 결과 저장: {filename}")


if __name__ == "__main__":
    benchmark = PerformanceBenchmark()
    results = benchmark.run_all_benchmarks()

    # 성능 기준 체크
    print("\n🎯 성능 기준 평가:")
    if results.get('search', {}).get('avg_search_time', 1) < 0.1:
        print("  ✅ 검색 속도: PASS (< 100ms)")
    else:
        print("  ❌ 검색 속도: FAIL (> 100ms)")

    if results.get('cache', {}).get('avg_read_hit_time', 10) < 1:
        print("  ✅ 캐시 속도: PASS (< 1ms)")
    else:
        print("  ❌ 캐시 속도: FAIL (> 1ms)")

    if results.get('memory', {}).get('rss_mb', 10000) < 8000:
        print("  ✅ 메모리 사용: PASS (< 8GB)")
    else:
        print("  ⚠️  메모리 사용: WARNING (> 8GB)")