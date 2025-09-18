#!/usr/bin/env python3
"""
고급 캐싱 시스템
- 문서 내용 캐싱
- 검색 결과 캐싱
- 자동 갱신
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import pickle
import sqlite3
from datetime import datetime, timedelta

class AdvancedCacheSystem:
    def __init__(self, cache_dir: str = "rag_system/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 여러 레벨의 캐시
        self.memory_cache = {}  # 메모리 캐시 (가장 빠름)
        self.disk_cache_path = self.cache_dir / "advanced_cache.db"
        self.vector_cache_path = self.cache_dir / "vector_cache.pkl"

        # TTL 설정
        self.default_ttl = 3600  # 1시간
        self.max_memory_items = 100

        # DB 초기화
        self._init_db()

        # 통계
        self.stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'disk_hits': 0
        }

    def _init_db(self):
        """SQLite 캐시 DB 초기화"""
        with sqlite3.connect(self.disk_cache_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at REAL,
                    expires_at REAL,
                    hit_count INTEGER DEFAULT 0,
                    last_hit REAL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_cache (
                    filepath TEXT PRIMARY KEY,
                    content TEXT,
                    metadata TEXT,
                    embeddings BLOB,
                    file_hash TEXT,
                    indexed_at REAL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    query TEXT,
                    results TEXT,
                    search_type TEXT,
                    created_at REAL,
                    expires_at REAL
                )
            """)
            conn.commit()

    def get_cache_key(self, *args) -> str:
        """캐시 키 생성"""
        combined = "_".join(str(arg) for arg in args)
        return hashlib.md5(combined.encode()).hexdigest()

    def get(self, key: str, cache_type: str = "general") -> Optional[Any]:
        """캐시에서 데이터 가져오기"""
        # 1. 메모리 캐시 확인
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if time.time() < entry['expires_at']:
                self.stats['memory_hits'] += 1
                self.stats['hits'] += 1
                return entry['value']
            else:
                del self.memory_cache[key]

        # 2. 디스크 캐시 확인
        with sqlite3.connect(self.disk_cache_path) as conn:
            if cache_type == "document":
                cursor = conn.execute(
                    "SELECT content, metadata FROM document_cache WHERE filepath = ?",
                    (key,)
                )
            elif cache_type == "search":
                cursor = conn.execute(
                    "SELECT results FROM search_cache WHERE query_hash = ? AND expires_at > ?",
                    (key, time.time())
                )
            else:
                cursor = conn.execute(
                    "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
                    (key, time.time())
                )

            row = cursor.fetchone()
            if row:
                self.stats['disk_hits'] += 1
                self.stats['hits'] += 1

                # 메모리 캐시에도 저장
                if len(self.memory_cache) < self.max_memory_items:
                    self.memory_cache[key] = {
                        'value': json.loads(row[0]) if cache_type != "document" else row[0],
                        'expires_at': time.time() + 300  # 5분간 메모리 캐시
                    }

                return json.loads(row[0]) if cache_type != "document" else {'content': row[0], 'metadata': json.loads(row[1]) if row[1] else {}}

        self.stats['misses'] += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None, cache_type: str = "general"):
        """캐시에 데이터 저장"""
        if ttl is None:
            ttl = self.default_ttl

        expires_at = time.time() + ttl

        # 1. 메모리 캐시 저장
        if len(self.memory_cache) >= self.max_memory_items:
            # LRU 방식으로 오래된 항목 제거
            oldest_key = min(self.memory_cache.keys(),
                           key=lambda k: self.memory_cache[k].get('last_access', 0))
            del self.memory_cache[oldest_key]

        self.memory_cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'last_access': time.time()
        }

        # 2. 디스크 캐시 저장
        with sqlite3.connect(self.disk_cache_path) as conn:
            if cache_type == "document":
                conn.execute("""
                    INSERT OR REPLACE INTO document_cache
                    (filepath, content, metadata, file_hash, indexed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    key,
                    value.get('content', ''),
                    json.dumps(value.get('metadata', {}), ensure_ascii=False),
                    value.get('file_hash', ''),
                    time.time()
                ))
            elif cache_type == "search":
                conn.execute("""
                    INSERT OR REPLACE INTO search_cache
                    (query_hash, query, results, search_type, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    key,
                    value.get('query', ''),
                    json.dumps(value.get('results', []), ensure_ascii=False),
                    value.get('search_type', 'general'),
                    time.time(),
                    expires_at
                ))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO cache
                    (key, value, created_at, expires_at, hit_count)
                    VALUES (?, ?, ?, ?, 0)
                """, (
                    key,
                    json.dumps(value, ensure_ascii=False),
                    time.time(),
                    expires_at
                ))
            conn.commit()

    def cache_document(self, filepath: Path, content: str, metadata: Dict):
        """문서 캐싱"""
        file_hash = hashlib.md5(f"{filepath.stat().st_size}_{filepath.stat().st_mtime}".encode()).hexdigest()

        self.set(
            str(filepath),
            {
                'content': content,
                'metadata': metadata,
                'file_hash': file_hash
            },
            ttl=86400,  # 24시간
            cache_type="document"
        )

    def cache_search_result(self, query: str, results: List, search_type: str = "general"):
        """검색 결과 캐싱"""
        query_hash = self.get_cache_key(query, search_type)

        self.set(
            query_hash,
            {
                'query': query,
                'results': results,
                'search_type': search_type
            },
            ttl=1800,  # 30분
            cache_type="search"
        )

    def get_search_result(self, query: str, search_type: str = "general") -> Optional[List]:
        """캐시된 검색 결과 가져오기"""
        query_hash = self.get_cache_key(query, search_type)
        result = self.get(query_hash, cache_type="search")
        return result.get('results') if result else None

    def clear_expired(self):
        """만료된 캐시 정리"""
        current_time = time.time()

        # 메모리 캐시 정리
        expired_keys = [k for k, v in self.memory_cache.items()
                       if v['expires_at'] < current_time]
        for key in expired_keys:
            del self.memory_cache[key]

        # 디스크 캐시 정리
        with sqlite3.connect(self.disk_cache_path) as conn:
            conn.execute("DELETE FROM cache WHERE expires_at < ?", (current_time,))
            conn.execute("DELETE FROM search_cache WHERE expires_at < ?", (current_time,))
            conn.commit()

    def get_stats(self) -> Dict:
        """캐시 통계 반환"""
        hit_rate = (self.stats['hits'] / (self.stats['hits'] + self.stats['misses']) * 100) if (self.stats['hits'] + self.stats['misses']) > 0 else 0

        with sqlite3.connect(self.disk_cache_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache")
            general_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM document_cache")
            doc_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM search_cache")
            search_count = cursor.fetchone()[0]

        return {
            'hit_rate': f"{hit_rate:.1f}%",
            'total_hits': self.stats['hits'],
            'total_misses': self.stats['misses'],
            'memory_hits': self.stats['memory_hits'],
            'disk_hits': self.stats['disk_hits'],
            'memory_cache_size': len(self.memory_cache),
            'disk_cache_items': {
                'general': general_count,
                'documents': doc_count,
                'searches': search_count
            }
        }

    def warm_up_cache(self, docs_dir: Path):
        """캐시 예열 (자주 사용하는 문서 미리 로드)"""
        print("🔥 캐시 예열 시작...")

        # 최근 수정된 문서 우선
        pdf_files = sorted(docs_dir.glob("*.pdf"),
                          key=lambda x: x.stat().st_mtime,
                          reverse=True)[:20]

        for pdf_file in pdf_files:
            # 여기서 실제 PDF 처리 로직 호출
            print(f"  - {pdf_file.name} 캐싱...")

        print("✅ 캐시 예열 완료")

if __name__ == "__main__":
    # 테스트
    cache = AdvancedCacheSystem()

    # 캐시 저장
    cache.set("test_key", {"data": "test_value"}, ttl=60)

    # 캐시 조회
    result = cache.get("test_key")
    print(f"캐시 결과: {result}")

    # 통계
    print(f"캐시 통계: {cache.get_stats()}")