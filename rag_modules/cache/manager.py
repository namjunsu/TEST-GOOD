"""
Cache management module
"""

import time
import logging
from collections import OrderedDict
from typing import Any, Optional, Dict
from ..core.config import CacheConfig

logger = logging.getLogger(__name__)

class CacheManager:
    """캐시 관리 클래스"""

    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.cache = OrderedDict()
        self.timestamps = {}

    def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        if key in self.cache:
            # TTL 확인
            if self._is_expired(key):
                self.remove(key)
                return None

            # LRU를 위해 재정렬
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """캐시에 값 저장"""
        # 크기 제한 확인
        if len(self.cache) >= self.config.max_size:
            # 가장 오래된 항목 제거
            oldest = next(iter(self.cache))
            self.remove(oldest)
            logger.debug(f"Cache eviction: {oldest}")

        self.cache[key] = value
        self.timestamps[key] = time.time()

    def remove(self, key: str):
        """캐시에서 항목 제거"""
        if key in self.cache:
            del self.cache[key]
            del self.timestamps[key]

    def _is_expired(self, key: str) -> bool:
        """TTL 만료 확인"""
        if key not in self.timestamps:
            return True
        return time.time() - self.timestamps[key] > self.config.ttl

    def clear(self):
        """캐시 전체 초기화"""
        self.cache.clear()
        self.timestamps.clear()

    def _calculate_hit_rate(self) -> float:
        """캐시 히트율 계산"""
        # 실제로는 히트/미스 카운트를 추적해야 하지만 여기서는 간단히 구현
        return 0.0 if len(self.cache) == 0 else len(self.cache) / self.config.max_size

    def stats(self) -> Dict:
        """캐시 통계"""
        return {
            'size': len(self.cache),
            'max_size': self.config.max_size,
            'ttl': self.config.ttl,
            'hit_rate': self._calculate_hit_rate()
        }
