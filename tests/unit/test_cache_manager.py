"""
Unit tests for Cache Manager
"""

import pytest
import time
from unittest.mock import Mock, patch
from rag_modules.cache.manager import CacheManager
from rag_modules.core.config import CacheConfig

class TestCacheManager:
    """CacheManager 단위 테스트"""

    @pytest.fixture
    def cache_manager(self):
        """캐시 매니저 fixture"""
        config = CacheConfig(max_size=3, ttl=1)
        return CacheManager(config)

    def test_cache_set_and_get(self, cache_manager):
        """캐시 저장 및 조회 테스트"""
        # Given
        key = "test_key"
        value = "test_value"

        # When
        cache_manager.set(key, value)
        result = cache_manager.get(key)

        # Then
        assert result == value

    def test_cache_lru_eviction(self, cache_manager):
        """LRU 캐시 제거 테스트"""
        # Given
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")
        cache_manager.set("key3", "value3")

        # When - 캐시 크기 초과
        cache_manager.set("key4", "value4")

        # Then - 가장 오래된 항목 제거됨
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key4") == "value4"

    def test_cache_ttl_expiration(self, cache_manager):
        """TTL 만료 테스트"""
        # Given
        cache_manager.set("key", "value")

        # When - TTL 만료 대기
        time.sleep(1.1)

        # Then
        assert cache_manager.get("key") is None

    def test_cache_stats(self, cache_manager):
        """캐시 통계 테스트"""
        # Given
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        # When
        stats = cache_manager.stats()

        # Then
        assert stats['size'] == 2
        assert stats['max_size'] == 3
        assert stats['ttl'] == 1
        assert 0 <= stats['hit_rate'] <= 1

    @pytest.mark.parametrize("key,value", [
        ("string_key", "string_value"),
        ("int_key", 12345),
        ("dict_key", {"nested": "value"}),
        ("list_key", [1, 2, 3])
    ])
    def test_cache_various_types(self, cache_manager, key, value):
        """다양한 타입 캐싱 테스트"""
        cache_manager.set(key, value)
        assert cache_manager.get(key) == value
