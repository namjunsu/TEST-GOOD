#!/usr/bin/env python3
"""
Lazy Loading System - 고급 지연 로딩 시스템

주요 기능:
- 필요한 문서만 온디맨드 로드
- LRU 캐싱으로 메모리 효율화
- 파일 변경 자동 감지
- 메타데이터 인덱싱
- 스레드 안전 보장
- 배치 로딩 지원
- 비동기 프리페칭
"""
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, Future
import threading
import hashlib
import json
import time
import logging
import re
import weakref
import gc

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logging.warning("pdfplumber not installed - PDF support disabled")

try:
    from functools import lru_cache
except ImportError:
    # Python 2 fallback (shouldn't happen but just in case)
    def lru_cache(maxsize=128):
        def decorator(func):
            cache = OrderedDict()
            def wrapper(*args, **kwargs):
                key = str(args) + str(kwargs)
                if key in cache:
                    cache.move_to_end(key)
                    return cache[key]
                result = func(*args, **kwargs)
                cache[key] = result
                if len(cache) > maxsize:
                    cache.popitem(last=False)
                return result
            return wrapper
        return decorator

@dataclass
class DocumentInfo:
    """문서 정보 데이터클래스"""
    path: Path
    name: str
    size: int
    modified: float
    hash: Optional[str] = None
    metadata: Optional[Dict] = None
    content: Optional[str] = None
    loaded: bool = False
    load_time: Optional[float] = None

class LRUCache:
    """Thread-safe LRU Cache implementation"""

    def __init__(self, maxsize: int = 100):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self.lock:
            self.cache.pop(key, None)

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            total = self.hits + self.misses
            return {
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': self.hits / total if total > 0 else 0,
                'size': len(self.cache),
                'maxsize': self.maxsize
            }

class LazyDocumentLoader:
    """고급 지연 문서 로더"""

    def __init__(self, docs_dir: Path, cache_size: int = 100,
                 prefetch_size: int = 10, max_workers: int = 4):
        self.docs_dir = Path(docs_dir)
        self.cache_size = cache_size
        self.prefetch_size = prefetch_size
        self.max_workers = max_workers

        # 데이터 구조
        self.file_index = {}  # filename -> DocumentInfo
        self.path_index = {}  # full_path -> DocumentInfo
        self.metadata_index = defaultdict(lambda: defaultdict(set))  # field -> value -> filenames

        # 캐싱
        self.content_cache = LRUCache(cache_size)
        self.hash_cache = {}  # path -> (hash, mtime)

        # 스레드 관리
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.prefetch_queue = set()
        self.prefetch_futures = {}

        # 통계
        self.stats = {
            'files_scanned': 0,
            'files_loaded': 0,
            'total_load_time': 0.0,
            'cache_invalidations': 0,
            'prefetch_hits': 0
        }

        # 로거
        self.logger = logging.getLogger(__name__)

    def quick_scan(self, pattern: Optional[str] = None) -> int:
        """빠른 파일 스캔 (내용 로드 없이)

        Args:
            pattern: 파일명 패턴 필터 (정규식)

        Returns:
            스캔된 파일 개수
        """
        start_time = time.time()

        with self.lock:
            # 기존 인덱스 초기화
            self.file_index.clear()
            self.path_index.clear()
            self.metadata_index.clear()

            # 검색 경로 구성
            search_paths = self._get_search_paths()
            pattern_re = re.compile(pattern) if pattern else None

            # 병렬 스캔
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for path in search_paths:
                    if path.exists():
                        future = executor.submit(self._scan_directory, path, pattern_re)
                        futures.append(future)

                # 결과 수집
                for future in futures:
                    docs = future.result()
                    for doc in docs:
                        self.file_index[doc.name] = doc
                        self.path_index[str(doc.path)] = doc
                        self.stats['files_scanned'] += 1

            # 메타데이터 인덱스 구축
            self._build_metadata_index()

        elapsed = time.time() - start_time
        count = len(self.file_index)
        self.logger.info(f"⚡ {count}개 파일 스캔 완료 ({elapsed:.2f}초)")
        return count

    def _get_search_paths(self) -> List[Path]:
        """검색 경로 목록 생성"""
        paths = [self.docs_dir]

        # 연도별 폴더
        for year in range(2014, 2026):
            paths.append(self.docs_dir / f"year_{year}")

        # 카테고리 폴더
        categories = ['category_purchase', 'category_repair', 'category_review',
                     'category_disposal', 'category_consumables', 'recent', 'archive', 'assets']
        for cat in categories:
            paths.append(self.docs_dir / cat)

        return paths

    def _scan_directory(self, path: Path, pattern_re: Optional[re.Pattern]) -> List[DocumentInfo]:
        """디렉토리 스캔 (스레드 안전)"""
        docs = []

        for ext in ['*.pdf', '*.txt']:
            for file_path in path.glob(ext):
                if pattern_re and not pattern_re.search(file_path.name):
                    continue

                try:
                    stat = file_path.stat()
                    doc = DocumentInfo(
                        path=file_path,
                        name=file_path.name,
                        size=stat.st_size,
                        modified=stat.st_mtime
                    )

                    # 간단한 메타데이터 추출 (파일명 기반)
                    doc.metadata = self._extract_quick_metadata(file_path)
                    docs.append(doc)

                except Exception as e:
                    self.logger.warning(f"Failed to scan {file_path}: {e}")

        return docs

    def _extract_quick_metadata(self, file_path: Path) -> Dict[str, Any]:
        """파일명에서 빠른 메타데이터 추출"""
        metadata = {
            'extension': file_path.suffix.lower(),
            'folder': file_path.parent.name
        }

        # 연도 추출
        year_match = re.search(r'(20\d{2})', file_path.name)
        if year_match:
            metadata['year'] = int(year_match.group(1))

        # 카테고리 추출
        if '구매' in file_path.name or 'purchase' in file_path.parent.name:
            metadata['category'] = 'purchase'
        elif '수리' in file_path.name or 'repair' in file_path.parent.name:
            metadata['category'] = 'repair'
        elif '폐기' in file_path.name or 'disposal' in file_path.parent.name:
            metadata['category'] = 'disposal'

        return metadata

    def _build_metadata_index(self) -> None:
        """메타데이터 인덱스 구축"""
        for filename, doc in self.file_index.items():
            if doc.metadata:
                for field, value in doc.metadata.items():
                    self.metadata_index[field][str(value)].add(filename)

    def load_document(self, filename: str, prefetch_related: bool = True) -> Optional[Dict]:
        """필요할 때만 문서 로드

        Args:
            filename: 로드할 파일명
            prefetch_related: 관련 문서 프리페칭 여부

        Returns:
            문서 데이터 또는 None
        """
        # 캐시 확인
        cached = self.content_cache.get(filename)
        if cached:
            # 파일 변경 확인
            doc = self.file_index.get(filename)
            if doc and not self._is_file_changed(doc):
                return cached
            else:
                self.content_cache.invalidate(filename)
                self.stats['cache_invalidations'] += 1

        # 프리페치 큐에 있는지 확인
        if filename in self.prefetch_futures:
            future = self.prefetch_futures.pop(filename)
            try:
                result = future.result(timeout=5.0)
                self.stats['prefetch_hits'] += 1
                return result
            except Exception as e:
                self.logger.warning(f"Prefetch failed for {filename}: {e}")

        # 문서 로드
        with self.lock:
            doc = self.file_index.get(filename)
            if not doc:
                return None

            start_time = time.time()
            result = self._load_single_document(doc)
            load_time = time.time() - start_time

            if result:
                doc.loaded = True
                doc.load_time = load_time
                self.stats['files_loaded'] += 1
                self.stats['total_load_time'] += load_time

                # 캐시에 저장
                self.content_cache.put(filename, result)

                # 관련 문서 프리페칭
                if prefetch_related:
                    self._prefetch_related(doc)

                return result

        return None

    def load_batch(self, filenames: List[str], parallel: bool = True) -> Dict[str, Dict]:
        """여러 문서 배치 로드

        Args:
            filenames: 로드할 파일명 리스트
            parallel: 병렬 처리 여부

        Returns:
            filename -> 문서 데이터 딕셔너리
        """
        results = {}

        if parallel:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for filename in filenames:
                    # 캐시에 있으면 스킵
                    cached = self.content_cache.get(filename)
                    if cached:
                        results[filename] = cached
                    else:
                        future = executor.submit(self.load_document, filename, False)
                        futures[filename] = future

                # 결과 수집
                for filename, future in futures.items():
                    try:
                        result = future.result(timeout=10.0)
                        if result:
                            results[filename] = result
                    except Exception as e:
                        self.logger.error(f"Failed to load {filename}: {e}")
        else:
            for filename in filenames:
                result = self.load_document(filename, False)
                if result:
                    results[filename] = result

        return results

    def _load_single_document(self, doc: DocumentInfo) -> Optional[Dict]:
        """단일 문서 로드 (실제 내용 추출)"""
        try:
            file_path = doc.path

            # 파일 해시 계산 (변경 감지용)
            doc.hash = self._calculate_file_hash(file_path)

            # 확장자별 처리
            if file_path.suffix.lower() == '.pdf':
                content = self._extract_pdf_content(file_path)
            elif file_path.suffix.lower() == '.txt':
                content = self._extract_text_content(file_path)
            else:
                self.logger.warning(f"Unsupported file type: {file_path.suffix}")
                return None

            # 결과 구성
            result = {
                'filename': doc.name,
                'path': str(doc.path),
                'content': content,
                'size': doc.size,
                'modified': doc.modified,
                'hash': doc.hash,
                'metadata': doc.metadata or {},
                'loaded_at': time.time()
            }

            # 전체 메타데이터 추출 (내용 기반)
            if content:
                result['metadata'].update(self._extract_content_metadata(content))
                doc.content = content[:1000]  # 미리보기용 일부만 저장

            return result

        except Exception as e:
            self.logger.error(f"Failed to load document {doc.path}: {e}")
            return None

    def _extract_pdf_content(self, file_path: Path) -> str:
        """PDF 내용 추출"""
        if not PDF_SUPPORT:
            return "[PDF support not available]"

        try:
            content = []
            with pdfplumber.open(file_path) as pdf:
                # 처음 10페이지만 추출 (성능 고려)
                max_pages = min(10, len(pdf.pages))
                for i in range(max_pages):
                    page = pdf.pages[i]
                    text = page.extract_text()
                    if text:
                        content.append(text)

            return '\n'.join(content)

        except Exception as e:
            self.logger.warning(f"PDF extraction failed for {file_path}: {e}")
            return ""

    def _extract_text_content(self, file_path: Path) -> str:
        """텍스트 파일 내용 추출"""
        try:
            # 인코딩 자동 감지
            encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue

            # 모든 인코딩 실패시 바이너리로 읽기
            with open(file_path, 'rb') as f:
                return f.read().decode('utf-8', errors='ignore')

        except Exception as e:
            self.logger.warning(f"Text extraction failed for {file_path}: {e}")
            return ""

    def _extract_content_metadata(self, content: str) -> Dict[str, Any]:
        """내용에서 메타데이터 추출"""
        metadata = {}

        # 금액 추출
        amounts = re.findall(r'([\d,]+)\s*(?:원|천원|만원|억원)', content)
        if amounts:
            metadata['amounts'] = amounts[:5]  # 처음 5개만

        # 날짜 추출
        dates = re.findall(r'(20\d{2}[-./]\d{1,2}[-./]\d{1,2})', content)
        if dates:
            metadata['dates'] = list(set(dates))[:5]

        # 키워드 추출 (간단한 빈도 기반)
        words = re.findall(r'[가-힣]{2,}', content)
        if words:
            from collections import Counter
            word_freq = Counter(words)
            metadata['keywords'] = [w for w, _ in word_freq.most_common(10)]

        return metadata

    def _calculate_file_hash(self, file_path: Path) -> str:
        """파일 해시 계산 (캐싱 포함)"""
        cache_key = str(file_path)
        current_mtime = file_path.stat().st_mtime

        # 캐시 확인
        if cache_key in self.hash_cache:
            cached_hash, cached_mtime = self.hash_cache[cache_key]
            if cached_mtime == current_mtime:
                return cached_hash

        # 해시 계산
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            # 큰 파일은 샘플링
            if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                f.read(1024 * 1024)  # 처음 1MB
                hash_md5.update(f.read(1024 * 1024))
                f.seek(-1024 * 1024, 2)  # 마지막 1MB
                hash_md5.update(f.read())
            else:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)

        file_hash = hash_md5.hexdigest()
        self.hash_cache[cache_key] = (file_hash, current_mtime)
        return file_hash

    def _is_file_changed(self, doc: DocumentInfo) -> bool:
        """파일 변경 여부 확인"""
        try:
            current_mtime = doc.path.stat().st_mtime
            return current_mtime != doc.modified
        except:
            return True

    def _prefetch_related(self, doc: DocumentInfo) -> None:
        """관련 문서 프리페칭"""
        if not doc.metadata:
            return

        related_files = set()

        # 같은 연도 문서
        if 'year' in doc.metadata:
            year_files = self.metadata_index['year'].get(str(doc.metadata['year']), set())
            related_files.update(list(year_files)[:self.prefetch_size // 2])

        # 같은 카테고리 문서
        if 'category' in doc.metadata:
            cat_files = self.metadata_index['category'].get(doc.metadata['category'], set())
            related_files.update(list(cat_files)[:self.prefetch_size // 2])

        # 현재 파일과 이미 큐에 있는 파일 제외
        related_files.discard(doc.name)
        related_files -= self.prefetch_queue

        # 프리페칭 시작
        for filename in list(related_files)[:self.prefetch_size]:
            if filename not in self.content_cache.cache:
                self.prefetch_queue.add(filename)
                future = self.executor.submit(self.load_document, filename, False)
                self.prefetch_futures[filename] = future

    def get_file_list(self, filter_func: Optional[Callable] = None) -> List[str]:
        """파일명 목록 반환

        Args:
            filter_func: 필터 함수 (DocumentInfo -> bool)

        Returns:
            파일명 리스트
        """
        with self.lock:
            if filter_func:
                return [name for name, doc in self.file_index.items()
                       if filter_func(doc)]
            return list(self.file_index.keys())

    def search_by_metadata(self, field: str, value: str) -> List[str]:
        """메타데이터로 검색

        Args:
            field: 메타데이터 필드명
            value: 검색할 값

        Returns:
            매칭되는 파일명 리스트
        """
        with self.lock:
            return list(self.metadata_index.get(field, {}).get(str(value), set()))

    def get_document_info(self, filename: str) -> Optional[DocumentInfo]:
        """문서 정보 반환 (내용 로드 없이)"""
        with self.lock:
            return self.file_index.get(filename)

    def invalidate_cache(self, filename: Optional[str] = None) -> None:
        """캐시 무효화

        Args:
            filename: 특정 파일만 무효화, None이면 전체 무효화
        """
        if filename:
            self.content_cache.invalidate(filename)
            self.logger.info(f"Cache invalidated for {filename}")
        else:
            self.content_cache.clear()
            self.logger.info("All cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        with self.lock:
            cache_stats = self.content_cache.get_stats()

            return {
                'files_scanned': self.stats['files_scanned'],
                'files_loaded': self.stats['files_loaded'],
                'avg_load_time': (self.stats['total_load_time'] / self.stats['files_loaded']
                                 if self.stats['files_loaded'] > 0 else 0),
                'cache_stats': cache_stats,
                'cache_invalidations': self.stats['cache_invalidations'],
                'prefetch_hits': self.stats['prefetch_hits'],
                'memory_usage': self._estimate_memory_usage()
            }

    def _estimate_memory_usage(self) -> int:
        """메모리 사용량 추정 (bytes)"""
        total = 0

        # 인덱스 메모리
        for doc in self.file_index.values():
            total += 1024  # DocumentInfo 기본 크기
            if doc.content:
                total += len(doc.content.encode('utf-8'))

        # 캐시 메모리
        for key, value in self.content_cache.cache.items():
            total += len(str(key).encode('utf-8'))
            if isinstance(value, dict) and 'content' in value:
                total += len(str(value['content']).encode('utf-8'))

        return total

    def cleanup(self) -> None:
        """리소스 정리"""
        self.executor.shutdown(wait=False)
        self.content_cache.clear()
        self.hash_cache.clear()
        self.prefetch_futures.clear()
        gc.collect()
        self.logger.info("LazyDocumentLoader cleanup completed")

if __name__ == "__main__":
    import argparse

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Lazy Document Loader Test")
    parser.add_argument('--docs-dir', default='docs', help='Documents directory')
    parser.add_argument('--cache-size', type=int, default=100, help='Cache size')
    parser.add_argument('--test-load', action='store_true', help='Test document loading')
    parser.add_argument('--test-batch', action='store_true', help='Test batch loading')
    parser.add_argument('--test-search', action='store_true', help='Test metadata search')
    args = parser.parse_args()

    # 테스트
    loader = LazyDocumentLoader(
        Path(args.docs_dir),
        cache_size=args.cache_size
    )

    print("🚀 LazyDocumentLoader Test")
    print("=" * 50)

    # 1. 빠른 스캔 테스트
    print("\n📂 Quick Scan Test:")
    start = time.time()
    count = loader.quick_scan()
    scan_time = time.time() - start
    print(f"✅ Scanned {count} files in {scan_time:.2f}s")
    print(f"   Average: {scan_time/count*1000:.2f}ms per file")

    # 2. 파일 목록
    print(f"\n📋 File List (first 10):")
    for name in loader.get_file_list()[:10]:
        info = loader.get_document_info(name)
        if info:
            size_kb = info.size / 1024
            print(f"   - {name} ({size_kb:.1f}KB)")

    # 3. 문서 로딩 테스트
    if args.test_load:
        print("\n📖 Document Loading Test:")
        files = loader.get_file_list()[:5]

        for filename in files:
            start = time.time()
            doc = loader.load_document(filename)
            load_time = time.time() - start

            if doc:
                content_len = len(doc['content'])
                print(f"   ✓ {filename}: {load_time:.3f}s ({content_len} chars)")
            else:
                print(f"   ✗ {filename}: Failed")

        # 캐시 히트 테스트
        print("\n🔄 Cache Hit Test:")
        for filename in files[:2]:
            start = time.time()
            doc = loader.load_document(filename)
            cache_time = time.time() - start
            print(f"   ✓ {filename}: {cache_time*1000:.3f}ms (cached)")

    # 4. 배치 로딩 테스트
    if args.test_batch:
        print("\n📦 Batch Loading Test:")
        batch_files = loader.get_file_list()[:10]

        start = time.time()
        results = loader.load_batch(batch_files, parallel=True)
        batch_time = time.time() - start

        print(f"   Loaded {len(results)}/{len(batch_files)} files in {batch_time:.2f}s")
        print(f"   Average: {batch_time/len(results):.3f}s per file")

    # 5. 메타데이터 검색 테스트
    if args.test_search:
        print("\n🔍 Metadata Search Test:")

        # 연도별 검색
        for year in [2020, 2021, 2022]:
            files = loader.search_by_metadata('year', str(year))
            if files:
                print(f"   Year {year}: {len(files)} files")

        # 카테고리별 검색
        for category in ['purchase', 'repair', 'disposal']:
            files = loader.search_by_metadata('category', category)
            if files:
                print(f"   Category '{category}': {len(files)} files")

    # 6. 통계 출력
    print("\n📊 Statistics:")
    stats = loader.get_stats()
    print(f"   Files scanned: {stats['files_scanned']}")
    print(f"   Files loaded: {stats['files_loaded']}")
    print(f"   Avg load time: {stats['avg_load_time']:.3f}s")
    print(f"   Cache hit rate: {stats['cache_stats']['hit_rate']*100:.1f}%")
    print(f"   Memory usage: {stats['memory_usage']/1024/1024:.1f}MB")

    # 정리
    loader.cleanup()
    print("\n✅ Test completed and cleaned up")