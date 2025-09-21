#!/usr/bin/env python3
"""
고급 병렬 검색 최적화 시스템

주요 기능:
- 멀티스레드/멀티프로세스/비동기 병렬 처리
- 동적 워커 풀 관리
- 우선순위 기반 작업 스케줄링
- 메모리 효율적인 스트리밍 처리
- 실시간 성능 모니터링
- 장애 복구 및 재시도
- 결과 집계 및 랭킹
"""

import os
import sys
import time
import asyncio
import hashlib
import threading
import multiprocessing
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Generator, Union
from dataclasses import dataclass, field
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed, Future
from queue import Queue, PriorityQueue, Empty
from functools import partial, lru_cache
import logging
import pickle
import psutil
import warnings

# PDF 처리
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    warnings.warn("pdfplumber not installed - PDF support disabled")

# 텍스트 검색
try:
    from rapidfuzz import fuzz
    FUZZY_SUPPORT = True
except ImportError:
    FUZZY_SUPPORT = False
    warnings.warn("rapidfuzz not installed - fuzzy search disabled")

@dataclass
class SearchTask:
    """검색 작업 정의"""
    id: str
    file_path: Path
    query: str
    priority: int = 0
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        return self.priority > other.priority  # 높은 우선순위가 먼저

@dataclass
class SearchResult:
    """검색 결과"""
    task_id: str
    file_path: Path
    relevance: float
    snippets: List[str]
    metadata: Dict[str, Any]
    processing_time: float
    success: bool = True
    error: Optional[str] = None

class WorkerPool:
    """동적 워커 풀 관리"""

    def __init__(self, min_workers: int = 2, max_workers: int = 8,
                 pool_type: str = 'thread'):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.pool_type = pool_type

        # CPU 코어 수에 따라 조정
        cpu_count = psutil.cpu_count()
        self.max_workers = min(self.max_workers, cpu_count * 2)

        # 현재 워커 수
        self.current_workers = min_workers

        # 풀 생성
        self._create_pool()

        # 성능 메트릭
        self.tasks_submitted = 0
        self.tasks_completed = 0
        self.total_wait_time = 0

        self.logger = logging.getLogger(__name__)

    def _create_pool(self):
        """워커 풀 생성"""
        if self.pool_type == 'thread':
            self.executor = ThreadPoolExecutor(max_workers=self.current_workers)
        elif self.pool_type == 'process':
            self.executor = ProcessPoolExecutor(max_workers=self.current_workers)
        else:
            raise ValueError(f"Unknown pool type: {self.pool_type}")

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """작업 제출"""
        self.tasks_submitted += 1
        future = self.executor.submit(fn, *args, **kwargs)

        # 동적 스케일링 체크
        self._check_scaling()

        return future

    def _check_scaling(self):
        """동적 스케일링 체크"""
        # 대기 중인 작업 수
        pending = self.tasks_submitted - self.tasks_completed

        # 스케일 업
        if pending > self.current_workers * 2 and self.current_workers < self.max_workers:
            self._scale_up()

        # 스케일 다운
        elif pending < self.current_workers // 2 and self.current_workers > self.min_workers:
            self._scale_down()

    def _scale_up(self):
        """워커 증가"""
        new_workers = min(self.current_workers + 2, self.max_workers)
        if new_workers > self.current_workers:
            self.logger.info(f"Scaling up workers: {self.current_workers} -> {new_workers}")
            self.current_workers = new_workers
            # 새 풀로 교체
            old_executor = self.executor
            self._create_pool()
            old_executor.shutdown(wait=False)

    def _scale_down(self):
        """워커 감소"""
        new_workers = max(self.current_workers - 1, self.min_workers)
        if new_workers < self.current_workers:
            self.logger.info(f"Scaling down workers: {self.current_workers} -> {new_workers}")
            self.current_workers = new_workers

    def shutdown(self, wait: bool = True):
        """풀 종료"""
        self.executor.shutdown(wait=wait)

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            'current_workers': self.current_workers,
            'tasks_submitted': self.tasks_submitted,
            'tasks_completed': self.tasks_completed,
            'pending_tasks': self.tasks_submitted - self.tasks_completed,
            'pool_type': self.pool_type
        }

class ParallelSearchEngine:
    """병렬 검색 엔진"""

    def __init__(self, max_workers: int = 4, pool_type: str = 'thread'):
        self.worker_pool = WorkerPool(
            min_workers=2,
            max_workers=max_workers,
            pool_type=pool_type
        )

        # 작업 큐
        self.task_queue = PriorityQueue()
        self.result_queue = Queue()

        # 활성 작업 추적
        self.active_tasks = {}
        self.completed_tasks = {}

        # 캐시
        self.search_cache = {}

        # 통계
        self.stats = {
            'total_searches': 0,
            'successful_searches': 0,
            'failed_searches': 0,
            'cache_hits': 0,
            'total_time': 0
        }

        self.logger = logging.getLogger(__name__)

    def search_files(self, file_paths: List[Path], query: str,
                    max_results: int = 10,
                    timeout: float = 30.0) -> List[SearchResult]:
        """파일 목록 병렬 검색"""
        start_time = time.time()

        # 작업 생성
        tasks = []
        for i, file_path in enumerate(file_paths):
            task = SearchTask(
                id=f"task_{i}_{time.time()}",
                file_path=file_path,
                query=query,
                priority=self._calculate_priority(file_path),
                timeout=timeout
            )
            tasks.append(task)

        # 병렬 검색 실행
        results = self._execute_parallel_search(tasks, max_results)

        # 통계 업데이트
        self.stats['total_searches'] += len(tasks)
        self.stats['total_time'] += time.time() - start_time

        return results

    def _calculate_priority(self, file_path: Path) -> int:
        """파일 우선순위 계산"""
        priority = 0

        # 최근 수정된 파일 우선
        stat = file_path.stat()
        days_old = (time.time() - stat.st_mtime) / 86400
        if days_old < 30:
            priority += 10
        elif days_old < 90:
            priority += 5

        # 작은 파일 우선 (빠른 처리)
        size_mb = stat.st_size / (1024 * 1024)
        if size_mb < 1:
            priority += 5
        elif size_mb < 5:
            priority += 3

        return priority

    def _execute_parallel_search(self, tasks: List[SearchTask],
                                max_results: int) -> List[SearchResult]:
        """병렬 검색 실행"""
        results = []
        futures = {}

        # 모든 작업 제출
        for task in tasks:
            # 캐시 확인
            cache_key = self._get_cache_key(task)
            if cache_key in self.search_cache:
                self.stats['cache_hits'] += 1
                cached_result = self.search_cache[cache_key]
                results.append(cached_result)
                continue

            # 병렬 실행
            future = self.worker_pool.submit(self._search_single_file, task)
            futures[future] = task

        # 결과 수집 (완료되는 대로)
        for future in as_completed(futures, timeout=30):
            task = futures[future]

            try:
                result = future.result(timeout=1)

                if result.success:
                    self.stats['successful_searches'] += 1
                    results.append(result)

                    # 캐시 저장
                    cache_key = self._get_cache_key(task)
                    self.search_cache[cache_key] = result

                    # 조기 종료 (충분한 결과)
                    if len(results) >= max_results * 2:
                        break
                else:
                    self.stats['failed_searches'] += 1

                    # 재시도
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        retry_future = self.worker_pool.submit(
                            self._search_single_file, task
                        )
                        futures[retry_future] = task

            except Exception as e:
                self.logger.error(f"Search failed for {task.file_path}: {e}")
                self.stats['failed_searches'] += 1

        # 관련성 순으로 정렬
        results.sort(key=lambda r: r.relevance, reverse=True)

        return results[:max_results]

    def _search_single_file(self, task: SearchTask) -> SearchResult:
        """단일 파일 검색"""
        start_time = time.time()

        try:
            # 파일 타입별 처리
            if task.file_path.suffix.lower() == '.pdf':
                content = self._extract_pdf_content(task.file_path)
            elif task.file_path.suffix.lower() in ['.txt', '.md']:
                content = self._extract_text_content(task.file_path)
            else:
                raise ValueError(f"Unsupported file type: {task.file_path.suffix}")

            # 텍스트 검색
            relevance, snippets = self._search_content(content, task.query)

            # 메타데이터 추가
            metadata = {
                'file_size': task.file_path.stat().st_size,
                'modified': task.file_path.stat().st_mtime,
                'extension': task.file_path.suffix
            }
            metadata.update(task.metadata)

            return SearchResult(
                task_id=task.id,
                file_path=task.file_path,
                relevance=relevance,
                snippets=snippets,
                metadata=metadata,
                processing_time=time.time() - start_time,
                success=True
            )

        except Exception as e:
            return SearchResult(
                task_id=task.id,
                file_path=task.file_path,
                relevance=0.0,
                snippets=[],
                metadata={},
                processing_time=time.time() - start_time,
                success=False,
                error=str(e)
            )

    def _extract_pdf_content(self, file_path: Path) -> str:
        """PDF 내용 추출"""
        if not PDF_SUPPORT:
            raise ImportError("PDF support not available")

        content = []
        with pdfplumber.open(file_path) as pdf:
            # 처음 10페이지만
            for i, page in enumerate(pdf.pages[:10]):
                text = page.extract_text()
                if text:
                    content.append(text)

        return '\n'.join(content)

    def _extract_text_content(self, file_path: Path) -> str:
        """텍스트 파일 내용 추출"""
        encodings = ['utf-8', 'cp949', 'euc-kr']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        # 실패시 바이너리로 읽고 디코드
        with open(file_path, 'rb') as f:
            return f.read().decode('utf-8', errors='ignore')

    def _search_content(self, content: str, query: str) -> Tuple[float, List[str]]:
        """내용에서 쿼리 검색"""
        if not content:
            return 0.0, []

        content_lower = content.lower()
        query_lower = query.lower()

        # 정확한 매칭
        exact_matches = content_lower.count(query_lower)

        # 퍼지 매칭
        if FUZZY_SUPPORT:
            fuzzy_score = fuzz.partial_ratio(query_lower, content_lower) / 100.0
        else:
            fuzzy_score = 0.5 if query_lower in content_lower else 0.0

        # 관련성 점수 계산
        relevance = min(1.0, (exact_matches * 0.2) + (fuzzy_score * 0.8))

        # 스니펫 추출
        snippets = self._extract_snippets(content, query, max_snippets=3)

        return relevance, snippets

    def _extract_snippets(self, content: str, query: str,
                         max_snippets: int = 3,
                         context_size: int = 100) -> List[str]:
        """쿼리 주변 텍스트 스니펫 추출"""
        snippets = []
        query_lower = query.lower()
        content_lower = content.lower()

        # 쿼리 위치 찾기
        start = 0
        while len(snippets) < max_snippets:
            pos = content_lower.find(query_lower, start)
            if pos == -1:
                break

            # 컨텍스트 추출
            snippet_start = max(0, pos - context_size)
            snippet_end = min(len(content), pos + len(query) + context_size)

            snippet = content[snippet_start:snippet_end]
            snippet = f"...{snippet}..."

            snippets.append(snippet)
            start = pos + len(query)

        return snippets

    def _get_cache_key(self, task: SearchTask) -> str:
        """캐시 키 생성"""
        key_str = f"{task.file_path}_{task.query}_{task.file_path.stat().st_mtime}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        stats = dict(self.stats)
        stats['worker_pool'] = self.worker_pool.get_stats()
        stats['cache_size'] = len(self.search_cache)

        if self.stats['total_searches'] > 0:
            stats['success_rate'] = self.stats['successful_searches'] / self.stats['total_searches']
            stats['cache_hit_rate'] = self.stats['cache_hits'] / self.stats['total_searches']
            stats['avg_time'] = self.stats['total_time'] / self.stats['total_searches']

        return stats

    def shutdown(self):
        """엔진 종료"""
        self.worker_pool.shutdown()
        self.logger.info("Parallel search engine shutdown")

class AsyncSearchEngine:
    """비동기 검색 엔진"""

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.results = []
        self.logger = logging.getLogger(__name__)

    async def search_async(self, file_paths: List[Path], query: str,
                          max_results: int = 10) -> List[SearchResult]:
        """비동기 파일 검색"""
        tasks = []

        for i, file_path in enumerate(file_paths):
            task = self._search_file_async(file_path, query, f"async_{i}")
            tasks.append(task)

        # 동시 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 성공한 결과만 필터링
        valid_results = [r for r in results if isinstance(r, SearchResult) and r.success]

        # 관련성 순 정렬
        valid_results.sort(key=lambda r: r.relevance, reverse=True)

        return valid_results[:max_results]

    async def _search_file_async(self, file_path: Path, query: str,
                                task_id: str) -> SearchResult:
        """비동기 단일 파일 검색"""
        async with self.semaphore:  # 동시 실행 제한
            start_time = time.time()

            try:
                # I/O 작업을 비동기로 실행
                content = await self._read_file_async(file_path)

                # CPU 집약적 작업은 executor로
                loop = asyncio.get_event_loop()
                relevance, snippets = await loop.run_in_executor(
                    None,
                    self._search_content_sync,
                    content,
                    query
                )

                return SearchResult(
                    task_id=task_id,
                    file_path=file_path,
                    relevance=relevance,
                    snippets=snippets,
                    metadata={},
                    processing_time=time.time() - start_time,
                    success=True
                )

            except Exception as e:
                return SearchResult(
                    task_id=task_id,
                    file_path=file_path,
                    relevance=0.0,
                    snippets=[],
                    metadata={},
                    processing_time=time.time() - start_time,
                    success=False,
                    error=str(e)
                )

    async def _read_file_async(self, file_path: Path) -> str:
        """비동기 파일 읽기"""
        loop = asyncio.get_event_loop()

        def read_file():
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        return await loop.run_in_executor(None, read_file)

    def _search_content_sync(self, content: str, query: str) -> Tuple[float, List[str]]:
        """동기 방식 내용 검색"""
        if not content:
            return 0.0, []

        # 간단한 검색 로직
        query_lower = query.lower()
        content_lower = content.lower()

        count = content_lower.count(query_lower)
        relevance = min(1.0, count * 0.1)

        # 스니펫 추출
        snippets = []
        pos = content_lower.find(query_lower)
        if pos != -1:
            start = max(0, pos - 50)
            end = min(len(content), pos + len(query) + 50)
            snippets.append(f"...{content[start:end]}...")

        return relevance, snippets

class StreamingSearchEngine:
    """스트리밍 검색 엔진 - 메모리 효율적"""

    def __init__(self, chunk_size: int = 1024 * 1024):  # 1MB chunks
        self.chunk_size = chunk_size
        self.logger = logging.getLogger(__name__)

    def search_stream(self, file_paths: List[Path], query: str,
                      callback: Optional[Callable] = None) -> Generator[SearchResult, None, None]:
        """결과를 스트리밍으로 반환"""

        for i, file_path in enumerate(file_paths):
            try:
                # 파일을 청크 단위로 읽으면서 검색
                relevance = 0.0
                snippets = []

                with open(file_path, 'rb') as f:
                    chunk_num = 0

                    while True:
                        chunk = f.read(self.chunk_size)
                        if not chunk:
                            break

                        # 텍스트로 디코드
                        try:
                            text = chunk.decode('utf-8', errors='ignore')
                        except:
                            continue

                        # 청크에서 검색
                        if query.lower() in text.lower():
                            relevance += 0.1

                            # 스니펫 추출
                            pos = text.lower().find(query.lower())
                            if pos != -1 and len(snippets) < 3:
                                start = max(0, pos - 50)
                                end = min(len(text), pos + len(query) + 50)
                                snippets.append(f"...{text[start:end]}...")

                        chunk_num += 1

                # 결과 생성
                if relevance > 0:
                    result = SearchResult(
                        task_id=f"stream_{i}",
                        file_path=file_path,
                        relevance=min(1.0, relevance),
                        snippets=snippets,
                        metadata={'chunks_processed': chunk_num},
                        processing_time=0,
                        success=True
                    )

                    # 콜백 호출
                    if callback:
                        callback(result)

                    yield result

            except Exception as e:
                self.logger.error(f"Stream search failed for {file_path}: {e}")

# 편의 함수들
def parallel_search(file_paths: List[Path], query: str,
                   max_workers: int = 4,
                   max_results: int = 10) -> List[SearchResult]:
    """간단한 병렬 검색"""
    engine = ParallelSearchEngine(max_workers=max_workers)
    try:
        results = engine.search_files(file_paths, query, max_results)
        return results
    finally:
        engine.shutdown()

async def async_search(file_paths: List[Path], query: str,
                      max_results: int = 10) -> List[SearchResult]:
    """간단한 비동기 검색"""
    engine = AsyncSearchEngine()
    return await engine.search_async(file_paths, query, max_results)

def stream_search(file_paths: List[Path], query: str) -> Generator[SearchResult, None, None]:
    """간단한 스트리밍 검색"""
    engine = StreamingSearchEngine()
    yield from engine.search_stream(file_paths, query)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parallel Search Optimizer")
    parser.add_argument('--mode', choices=['parallel', 'async', 'stream'],
                       default='parallel', help='Search mode')
    parser.add_argument('--query', default='구매', help='Search query')
    parser.add_argument('--workers', type=int, default=4, help='Number of workers')
    parser.add_argument('--max-results', type=int, default=10, help='Max results')
    parser.add_argument('--test', action='store_true', help='Run tests')
    args = parser.parse_args()

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.test:
        print("=" * 60)
        print("🧪 Parallel Search Optimizer Test")
        print("=" * 60)

        # 테스트 파일 생성
        test_dir = Path("test_docs")
        test_dir.mkdir(exist_ok=True)

        test_files = []
        for i in range(20):
            file_path = test_dir / f"test_{i}.txt"
            content = f"테스트 문서 {i}\n구매 관련 내용\n" * 10
            if i % 3 == 0:
                content += f"\n{args.query} 관련 상세 내용\n" * 5

            file_path.write_text(content)
            test_files.append(file_path)

        # 1. 병렬 검색 테스트
        print("\n📊 Parallel Search Test:")
        print("-" * 40)

        engine = ParallelSearchEngine(max_workers=args.workers)

        start = time.time()
        results = engine.search_files(test_files, args.query, args.max_results)
        elapsed = time.time() - start

        print(f"Found {len(results)} results in {elapsed:.2f}s")
        for i, result in enumerate(results[:3], 1):
            print(f"  {i}. {result.file_path.name} (relevance: {result.relevance:.2f})")

        print("\n📈 Statistics:")
        stats = engine.get_stats()
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

        engine.shutdown()

        # 2. 비동기 검색 테스트
        if args.mode == 'async':
            print("\n📊 Async Search Test:")
            print("-" * 40)

            async def test_async():
                start = time.time()
                results = await async_search(test_files, args.query, args.max_results)
                elapsed = time.time() - start

                print(f"Found {len(results)} results in {elapsed:.2f}s")
                for i, result in enumerate(results[:3], 1):
                    print(f"  {i}. {result.file_path.name} (relevance: {result.relevance:.2f})")

            asyncio.run(test_async())

        # 3. 스트리밍 검색 테스트
        if args.mode == 'stream':
            print("\n📊 Streaming Search Test:")
            print("-" * 40)

            start = time.time()
            results = list(stream_search(test_files, args.query))
            elapsed = time.time() - start

            print(f"Streamed {len(results)} results in {elapsed:.2f}s")
            for i, result in enumerate(results[:3], 1):
                print(f"  {i}. {result.file_path.name} (relevance: {result.relevance:.2f})")

        # 테스트 파일 정리
        import shutil
        shutil.rmtree(test_dir)

        print("\n✅ Test completed")

    else:
        # 실제 검색 실행
        docs_dir = Path("docs")
        if not docs_dir.exists():
            print(f"❌ Directory not found: {docs_dir}")
            sys.exit(1)

        # PDF 파일 수집
        pdf_files = list(docs_dir.rglob("*.pdf"))[:50]  # 최대 50개

        if not pdf_files:
            print("❌ No PDF files found")
            sys.exit(1)

        print(f"🔍 Searching {len(pdf_files)} files for '{args.query}'...")

        if args.mode == 'parallel':
            results = parallel_search(pdf_files, args.query, args.workers, args.max_results)
        elif args.mode == 'async':
            results = asyncio.run(async_search(pdf_files, args.query, args.max_results))
        else:  # stream
            results = list(stream_search(pdf_files, args.query))[:args.max_results]

        print(f"\n📊 Search Results ({len(results)} found):")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.file_path.name}")
            print(f"   Relevance: {result.relevance:.2f}")
            if result.snippets:
                print(f"   Snippet: {result.snippets[0][:100]}...")