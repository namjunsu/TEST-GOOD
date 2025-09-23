"""
LRU 캐시 모듈
=============

응답 캐싱을 위한 LRU 캐시를 제공합니다.
"""

import hashlib
import json
import logging
import pickle
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from ..config import RAGConfig

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU 캐시 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.max_size = config.cache_max_size
        self.ttl = config.cache_ttl
        self.cache = OrderedDict()
        self.lock = Lock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0
        }

        # 영구 저장 경로
        self.cache_file = config.cache_dir / "response_cache.pkl"

        # 캐시 로드
        self.load_cache()

    def _generate_key(self, data: Any) -> str:
        """
        캐시 키 생성

        Args:
            data: 키 생성용 데이터

        Returns:
            해시 키
        """
        # JSON 직렬화 후 해시
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)

        # 한국어 조사 제거 (캐시 히트율 향상)
        particles = ['은', '는', '이', '가', '을', '를', '의', '에', '에서', '으로', '와', '과']
        for particle in particles:
            json_str = json_str.replace(particle + ' ', ' ')

        # MD5 해시
        return hashlib.md5(json_str.encode()).hexdigest()

    def get(
        self,
        key: Any,
        raw_key: bool = False
    ) -> Optional[Any]:
        """
        캐시에서 값 조회

        Args:
            key: 캐시 키 또는 키 생성용 데이터
            raw_key: True면 key를 그대로 사용

        Returns:
            캐시된 값 또는 None
        """
        with self.lock:
            # 키 생성
            cache_key = key if raw_key else self._generate_key(key)

            # 캐시에 없으면 miss
            if cache_key not in self.cache:
                self.stats['misses'] += 1
                return None

            # 캐시 엔트리 가져오기
            entry = self.cache[cache_key]
            value, timestamp = entry

            # TTL 확인
            if time.time() - timestamp > self.ttl:
                # 만료됨
                del self.cache[cache_key]
                self.stats['expirations'] += 1
                self.stats['misses'] += 1
                return None

            # LRU 업데이트 (가장 최근으로 이동)
            self.cache.move_to_end(cache_key)
            self.stats['hits'] += 1

            return value

    def set(
        self,
        key: Any,
        value: Any,
        raw_key: bool = False
    ) -> None:
        """
        캐시에 값 저장

        Args:
            key: 캐시 키 또는 키 생성용 데이터
            value: 저장할 값
            raw_key: True면 key를 그대로 사용
        """
        with self.lock:
            # 키 생성
            cache_key = key if raw_key else self._generate_key(key)

            # 기존 엔트리가 있으면 업데이트
            if cache_key in self.cache:
                self.cache.move_to_end(cache_key)

            # 새 엔트리 추가
            self.cache[cache_key] = (value, time.time())

            # 크기 제한 확인
            while len(self.cache) > self.max_size:
                # 가장 오래된 엔트리 제거
                evicted_key = next(iter(self.cache))
                del self.cache[evicted_key]
                self.stats['evictions'] += 1

    def clear(self) -> None:
        """캐시 전체 삭제"""
        with self.lock:
            self.cache.clear()
            logger.info("Cache cleared")

    def save_cache(self) -> None:
        """캐시를 파일로 저장"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            with self.lock:
                with open(self.cache_file, 'wb') as f:
                    pickle.dump({
                        'cache': dict(self.cache),
                        'stats': self.stats
                    }, f)

            logger.info(f"Cache saved to {self.cache_file}")

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def load_cache(self) -> bool:
        """저장된 캐시 로드"""
        try:
            if not self.cache_file.exists():
                return False

            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)

            # 만료된 엔트리 필터링
            current_time = time.time()
            valid_entries = OrderedDict()

            for key, (value, timestamp) in data['cache'].items():
                if current_time - timestamp <= self.ttl:
                    valid_entries[key] = (value, timestamp)

            with self.lock:
                self.cache = valid_entries
                self.stats = data.get('stats', self.stats)

            logger.info(f"Loaded {len(valid_entries)} cache entries")
            return True

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return False

    def get_stats(self) -> Dict:
        """
        캐시 통계 반환

        Returns:
            통계 정보
        """
        with self.lock:
            total = self.stats['hits'] + self.stats['misses']
            hit_rate = self.stats['hits'] / total if total > 0 else 0

            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': hit_rate,
                'evictions': self.stats['evictions'],
                'expirations': self.stats['expirations'],
                'ttl': self.ttl
            }

    def reset_stats(self) -> None:
        """통계 초기화"""
        with self.lock:
            self.stats = {
                'hits': 0,
                'misses': 0,
                'evictions': 0,
                'expirations': 0
            }
            logger.info("Cache statistics reset")

    def cleanup_expired(self) -> int:
        """
        만료된 엔트리 정리

        Returns:
            정리된 엔트리 수
        """
        with self.lock:
            current_time = time.time()
            expired_keys = []

            for key, (value, timestamp) in self.cache.items():
                if current_time - timestamp > self.ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                del self.cache[key]

            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)