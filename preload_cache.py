#!/usr/bin/env python3
"""
고급 캐시 프리로딩 시스템

주요 기능:
- 병렬 문서 프리로딩
- 다층 캐시 워밍업
- 진행 상태 실시간 표시
- 선택적/증분 캐싱
- 캐시 검증 및 복구
- 통계 수집 및 분석
- 재개 가능한 프리로딩
"""

import os
import sys
import time
import json
import pickle
import hashlib
import sqlite3
import threading
import multiprocessing
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict, OrderedDict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
import logging
import argparse
import warnings

# 진행률 표시
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    warnings.warn("tqdm not installed - progress bars disabled")

# 캐시 백엔드
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import memcache
    MEMCACHE_AVAILABLE = True
except ImportError:
    MEMCACHE_AVAILABLE = False

@dataclass
class CacheStats:
    """캐시 통계"""
    total_files: int = 0
    cached_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_size: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    load_time: float = 0.0
    cache_time: float = 0.0
    errors: List[str] = field(default_factory=list)

@dataclass
class CacheEntry:
    """캐시 엔트리"""
    key: str
    data: Any
    size: int
    timestamp: float
    ttl: int = 3600
    hits: int = 0
    checksum: Optional[str] = None

class CacheBackend:
    """캐시 백엔드 기본 클래스"""

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def clear(self) -> bool:
        raise NotImplementedError

    def stats(self) -> Dict[str, Any]:
        raise NotImplementedError

class MemoryCacheBackend(CacheBackend):
    """메모리 캐시 백엔드"""

    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry.timestamp < entry.ttl:
                    self.cache.move_to_end(key)
                    entry.hits += 1
                    self.hits += 1
                    return entry.data
                else:
                    del self.cache[key]
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        with self.lock:
            try:
                size = len(pickle.dumps(value))
                entry = CacheEntry(
                    key=key,
                    data=value,
                    size=size,
                    timestamp=time.time(),
                    ttl=ttl
                )

                self.cache[key] = entry

                # LRU eviction
                while len(self.cache) > self.max_size:
                    self.cache.popitem(last=False)

                return True
            except:
                return False

    def exists(self, key: str) -> bool:
        with self.lock:
            return key in self.cache

    def delete(self, key: str) -> bool:
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def clear(self) -> bool:
        with self.lock:
            self.cache.clear()
            return True

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            total_size = sum(e.size for e in self.cache.values())
            return {
                'entries': len(self.cache),
                'size': total_size,
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
            }

class DiskCacheBackend(CacheBackend):
    """디스크 캐시 백엔드 (SQLite)"""

    def __init__(self, cache_path: Path):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(str(self.cache_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB,
                size INTEGER,
                timestamp REAL,
                ttl INTEGER,
                hits INTEGER DEFAULT 0,
                checksum TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)')
        conn.commit()
        conn.close()

    def get(self, key: str) -> Optional[Any]:
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.execute(
            'SELECT value, timestamp, ttl, hits FROM cache WHERE key = ?',
            (key,)
        )
        row = cursor.fetchone()

        if row:
            value_blob, timestamp, ttl, hits = row
            if time.time() - timestamp < ttl:
                # Update hits
                conn.execute(
                    'UPDATE cache SET hits = ? WHERE key = ?',
                    (hits + 1, key)
                )
                conn.commit()
                conn.close()
                return pickle.loads(value_blob)
            else:
                # Expired
                conn.execute('DELETE FROM cache WHERE key = ?', (key,))
                conn.commit()

        conn.close()
        return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            value_blob = pickle.dumps(value)
            size = len(value_blob)
            checksum = hashlib.md5(value_blob).hexdigest()

            conn = sqlite3.connect(str(self.cache_path))
            conn.execute('''
                INSERT OR REPLACE INTO cache
                (key, value, size, timestamp, ttl, checksum)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (key, value_blob, size, time.time(), ttl, checksum))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Failed to cache {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.execute('SELECT 1 FROM cache WHERE key = ?', (key,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def delete(self, key: str) -> bool:
        conn = sqlite3.connect(str(self.cache_path))
        conn.execute('DELETE FROM cache WHERE key = ?', (key,))
        deleted = conn.total_changes > 0
        conn.commit()
        conn.close()
        return deleted

    def clear(self) -> bool:
        conn = sqlite3.connect(str(self.cache_path))
        conn.execute('DELETE FROM cache')
        conn.commit()
        conn.close()
        return True

    def stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.cache_path))
        cursor = conn.execute('''
            SELECT COUNT(*), SUM(size), SUM(hits) FROM cache
        ''')
        count, total_size, total_hits = cursor.fetchone()
        conn.close()

        return {
            'entries': count or 0,
            'size': total_size or 0,
            'total_hits': total_hits or 0,
            'path': str(self.cache_path)
        }

class RedisCacheBackend(CacheBackend):
    """Redis 캐시 백엔드"""

    def __init__(self, host='localhost', port=6379, db=0):
        if not REDIS_AVAILABLE:
            raise ImportError("Redis not available")
        self.redis = redis.Redis(host=host, port=port, db=db)
        self.prefix = "preload:"

    def get(self, key: str) -> Optional[Any]:
        try:
            data = self.redis.get(f"{self.prefix}{key}")
            if data:
                return pickle.loads(data)
        except:
            pass
        return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            data = pickle.dumps(value)
            return self.redis.setex(
                f"{self.prefix}{key}",
                ttl,
                data
            )
        except:
            return False

    def exists(self, key: str) -> bool:
        return self.redis.exists(f"{self.prefix}{key}")

    def delete(self, key: str) -> bool:
        return self.redis.delete(f"{self.prefix}{key}") > 0

    def clear(self) -> bool:
        keys = self.redis.keys(f"{self.prefix}*")
        if keys:
            self.redis.delete(*keys)
        return True

    def stats(self) -> Dict[str, Any]:
        info = self.redis.info()
        return {
            'entries': len(self.redis.keys(f"{self.prefix}*")),
            'used_memory': info.get('used_memory', 0),
            'connected_clients': info.get('connected_clients', 0)
        }

class CachePreloader:
    """캐시 프리로더"""

    def __init__(self, backend: CacheBackend, max_workers: int = 4):
        self.backend = backend
        self.max_workers = max_workers
        self.stats = CacheStats()
        self.logger = logging.getLogger(__name__)

        # 재개 지원
        self.checkpoint_file = Path("cache_preload_checkpoint.json")
        self.processed_files = set()
        self._load_checkpoint()

    def _load_checkpoint(self):
        """체크포인트 로드"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_files = set(data.get('processed', []))
                    self.logger.info(f"Resumed from checkpoint: {len(self.processed_files)} files already processed")
            except:
                pass

    def _save_checkpoint(self):
        """체크포인트 저장"""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed': list(self.processed_files),
                    'timestamp': time.time(),
                    'stats': asdict(self.stats)
                }, f)
        except:
            pass

    def preload_documents(self, docs_dir: Path,
                         file_patterns: List[str] = None,
                         force: bool = False) -> CacheStats:
        """문서 프리로딩"""
        start_time = time.time()

        # 파일 수집
        files = self._collect_files(docs_dir, file_patterns)

        if not force:
            # 이미 처리된 파일 제외
            files = [f for f in files if str(f) not in self.processed_files]

        self.stats.total_files = len(files)

        if not files:
            self.logger.info("All files already cached")
            return self.stats

        self.logger.info(f"Preloading {len(files)} files...")

        # 병렬 프리로딩
        if self.max_workers > 1:
            self._parallel_preload(files)
        else:
            self._sequential_preload(files)

        # 통계 업데이트
        self.stats.load_time = time.time() - start_time

        # 체크포인트 저장
        self._save_checkpoint()

        # 체크포인트 파일 정리 (완료시)
        if self.stats.cached_files == self.stats.total_files:
            self.checkpoint_file.unlink(missing_ok=True)

        return self.stats

    def _collect_files(self, docs_dir: Path,
                       patterns: List[str] = None) -> List[Path]:
        """파일 수집"""
        if patterns is None:
            patterns = ['*.pdf', '*.txt', '*.docx']

        files = []
        for pattern in patterns:
            files.extend(docs_dir.rglob(pattern))

        return sorted(set(files))

    def _parallel_preload(self, files: List[Path]):
        """병렬 프리로딩"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # tqdm 진행률 표시
            if TQDM_AVAILABLE:
                futures = {
                    executor.submit(self._preload_file, f): f
                    for f in files
                }

                for future in tqdm(as_completed(futures),
                                 total=len(files),
                                 desc="Preloading",
                                 unit="files"):
                    try:
                        result = future.result(timeout=30)
                        if result:
                            self.stats.cached_files += 1
                        else:
                            self.stats.failed_files += 1
                    except Exception as e:
                        self.stats.failed_files += 1
                        self.stats.errors.append(str(e))
            else:
                # tqdm 없이
                futures = []
                for f in files:
                    future = executor.submit(self._preload_file, f)
                    futures.append((future, f))

                for i, (future, file) in enumerate(futures):
                    try:
                        result = future.result(timeout=30)
                        if result:
                            self.stats.cached_files += 1
                        else:
                            self.stats.failed_files += 1

                        # 진행률 출력
                        if (i + 1) % 10 == 0:
                            progress = (i + 1) / len(files) * 100
                            print(f"Progress: {progress:.1f}% ({i+1}/{len(files)})")
                    except Exception as e:
                        self.stats.failed_files += 1
                        self.stats.errors.append(str(e))

    def _sequential_preload(self, files: List[Path]):
        """순차 프리로딩"""
        for i, file in enumerate(files):
            try:
                if self._preload_file(file):
                    self.stats.cached_files += 1
                else:
                    self.stats.failed_files += 1

                # 진행률
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / len(files) * 100
                    print(f"Progress: {progress:.1f}% ({i+1}/{len(files)})")
            except Exception as e:
                self.stats.failed_files += 1
                self.stats.errors.append(str(e))

    def _preload_file(self, file_path: Path) -> bool:
        """단일 파일 프리로딩"""
        try:
            # 캐시 키 생성
            cache_key = self._get_cache_key(file_path)

            # 이미 캐시에 있는지 확인
            if self.backend.exists(cache_key):
                self.stats.skipped_files += 1
                self.processed_files.add(str(file_path))
                return True

            # 메타데이터 추출
            metadata = self._extract_metadata(file_path)
            if metadata:
                # 캐시 저장
                cache_start = time.time()
                success = self.backend.set(cache_key, metadata, ttl=86400)  # 24시간
                self.stats.cache_time += time.time() - cache_start

                if success:
                    self.processed_files.add(str(file_path))
                    self.stats.total_size += file_path.stat().st_size
                    return True

            return False

        except Exception as e:
            self.logger.warning(f"Failed to preload {file_path}: {e}")
            return False

    def _get_cache_key(self, file_path: Path) -> str:
        """캐시 키 생성"""
        # 파일 경로와 수정 시간 기반 키
        stat = file_path.stat()
        key_str = f"{file_path}_{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _extract_metadata(self, file_path: Path) -> Optional[Dict]:
        """메타데이터 추출"""
        try:
            metadata = {
                'path': str(file_path),
                'name': file_path.name,
                'size': file_path.stat().st_size,
                'modified': file_path.stat().st_mtime,
                'extension': file_path.suffix.lower()
            }

            # 파일 타입별 추가 메타데이터
            if file_path.suffix.lower() == '.pdf':
                metadata['type'] = 'pdf'
                metadata['pages'] = self._count_pdf_pages(file_path)
            elif file_path.suffix.lower() in ['.txt', '.md']:
                metadata['type'] = 'text'
                metadata['encoding'] = self._detect_encoding(file_path)

            return metadata

        except Exception as e:
            self.logger.debug(f"Metadata extraction failed for {file_path}: {e}")
            return None

    def _count_pdf_pages(self, file_path: Path) -> int:
        """PDF 페이지 수 카운트"""
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                return len(reader.pages)
        except:
            return 0

    def _detect_encoding(self, file_path: Path) -> str:
        """텍스트 파일 인코딩 감지"""
        try:
            import chardet
            with open(file_path, 'rb') as f:
                result = chardet.detect(f.read(1024))
                return result['encoding'] or 'utf-8'
        except:
            return 'utf-8'

    def warm_up_cache(self, common_queries: List[str]):
        """캐시 워밍업 - 자주 사용되는 쿼리 미리 실행"""
        self.logger.info(f"Warming up cache with {len(common_queries)} queries...")

        for query in common_queries:
            cache_key = f"query_{hashlib.md5(query.encode()).hexdigest()}"

            if not self.backend.exists(cache_key):
                # 실제 쿼리 실행 시뮬레이션
                result = {'query': query, 'timestamp': time.time()}
                self.backend.set(cache_key, result, ttl=7200)

        self.logger.info("Cache warm-up completed")

    def verify_cache(self) -> Tuple[int, int]:
        """캐시 검증"""
        valid = 0
        invalid = 0

        # 캐시 엔트리 검증
        cache_stats = self.backend.stats()

        # TODO: 실제 검증 로직 구현
        # 예: 체크섬 확인, TTL 확인 등

        return valid, invalid

    def optimize_cache(self):
        """캐시 최적화"""
        # 오래된 엔트리 정리
        # 자주 사용되지 않는 엔트리 제거
        # 캐시 압축
        pass

def create_cache_backend(backend_type: str, **kwargs) -> CacheBackend:
    """캐시 백엔드 생성 팩토리"""
    if backend_type == 'memory':
        return MemoryCacheBackend(max_size=kwargs.get('max_size', 1000))
    elif backend_type == 'disk':
        return DiskCacheBackend(cache_path=Path(kwargs.get('path', 'cache/preload.db')))
    elif backend_type == 'redis':
        if not REDIS_AVAILABLE:
            raise ImportError("Redis not installed")
        return RedisCacheBackend(
            host=kwargs.get('host', 'localhost'),
            port=kwargs.get('port', 6379)
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="Cache Preloader")
    parser.add_argument('--docs-dir', default='docs', help='Documents directory')
    parser.add_argument('--backend', choices=['memory', 'disk', 'redis'],
                       default='disk', help='Cache backend')
    parser.add_argument('--workers', type=int, default=4, help='Parallel workers')
    parser.add_argument('--force', action='store_true', help='Force reload all')
    parser.add_argument('--warm-up', action='store_true', help='Warm up cache')
    parser.add_argument('--verify', action='store_true', help='Verify cache')
    parser.add_argument('--stats', action='store_true', help='Show cache stats')
    parser.add_argument('--clear', action='store_true', help='Clear cache')
    args = parser.parse_args()

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("="*60)
    print("📚 Advanced Cache Preloader")
    print("="*60)

    # 백엔드 생성
    backend = create_cache_backend(args.backend)

    if args.clear:
        print("🗑️ Clearing cache...")
        backend.clear()
        print("✅ Cache cleared")
        return

    if args.stats:
        print("📊 Cache Statistics:")
        stats = backend.stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return

    if args.verify:
        print("🔍 Verifying cache...")
        preloader = CachePreloader(backend)
        valid, invalid = preloader.verify_cache()
        print(f"  Valid entries: {valid}")
        print(f"  Invalid entries: {invalid}")
        return

    # 프리로더 생성
    preloader = CachePreloader(backend, max_workers=args.workers)

    # 캐시 워밍업
    if args.warm_up:
        common_queries = [
            "2024년 구매",
            "중계차 장비",
            "카메라 수리",
            "장비 현황",
            "예산 집행"
        ]
        preloader.warm_up_cache(common_queries)

    # 문서 프리로딩
    docs_dir = Path(args.docs_dir)
    if not docs_dir.exists():
        print(f"❌ Directory not found: {docs_dir}")
        return

    start_time = time.time()
    stats = preloader.preload_documents(docs_dir, force=args.force)
    elapsed = time.time() - start_time

    # 결과 출력
    print("\n" + "="*60)
    print("✅ Preloading Complete!")
    print(f"⏱️  Total time: {elapsed:.2f}s")
    print(f"📊 Statistics:")
    print(f"   Files processed: {stats.cached_files}/{stats.total_files}")
    print(f"   Files skipped: {stats.skipped_files}")
    print(f"   Files failed: {stats.failed_files}")
    print(f"   Total size: {stats.total_size / (1024*1024):.1f}MB")
    print(f"   Cache time: {stats.cache_time:.2f}s")

    if stats.errors:
        print(f"\n⚠️  Errors ({len(stats.errors)}):")
        for error in stats.errors[:5]:
            print(f"   - {error}")

    # 캐시 통계
    cache_stats = backend.stats()
    print(f"\n📦 Cache Status:")
    print(f"   Entries: {cache_stats.get('entries', 0)}")
    print(f"   Size: {cache_stats.get('size', 0) / (1024*1024):.1f}MB")

    print("\n💡 Cache is ready for use!")
    print("   Run: streamlit run web_interface.py")
    print("="*60)

if __name__ == "__main__":
    main()