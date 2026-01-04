"""CacheService - 2-tier 캐시 관리 서비스

Phase 3 리팩토링: pipeline.py의 캐시 로직을 별도 서비스로 추출

Tier 1: 메모리 캐시 (가장 빠름)
Tier 2: 영구 캐시 (서버 재시작 후에도 유지)
"""

from typing import Any, Optional

from app.core.logging import get_logger
from app.rag.cache_manager import cache_query_result, get_cached_result
from app.rag.persistent_cache import (
    cache_query_result_persistent,
    get_cached_result_persistent,
)

logger = get_logger(__name__)


class CacheService:
    """2-tier 캐시 관리 서비스

    책임:
    - 메모리 캐시 조회/저장
    - 영구 캐시 조회/저장
    - 캐시 히트 로깅
    - 메타데이터 태깅 (from_cache)
    """

    def __init__(self) -> None:
        """초기화"""
        # 캐시 함수 참조
        self._memory_get = get_cached_result
        self._memory_set = cache_query_result
        self._persistent_get = get_cached_result_persistent
        self._persistent_set = cache_query_result_persistent

    def get(
        self,
        cache_key: str,
        mode: str,
        query_preview: str
    ) -> Optional[dict[str, Any]]:
        """2-tier 캐시 조회

        Args:
            cache_key: 캐시 키
            mode: 모드 (로깅용)
            query_preview: 쿼리 미리보기 (로깅용)

        Returns:
            캐시된 결과 또는 None
        """
        # Tier 1: 메모리 캐시
        result = self._memory_get(cache_key)
        if result:
            logger.info(f"🎯 Memory Cache HIT! mode={mode}, query: {query_preview[:50]}...")
            if "status" in result:
                result["status"]["from_cache"] = "memory"
            return result

        # Tier 2: 영구 캐시
        result = self._persistent_get(cache_key)
        if result:
            logger.info(f"💾 Persistent Cache HIT! mode={mode}, query: {query_preview[:50]}...")
            # 영구 캐시에서 가져온 결과를 메모리 캐시에 재저장 (다음 접근 최적화)
            self._memory_set(cache_key, result)
            if "status" in result:
                result["status"]["from_cache"] = "persistent"
            return result

        return None

    def set(self, cache_key: str, result: dict[str, Any]) -> None:
        """2-tier 캐시 저장

        Args:
            cache_key: 캐시 키
            result: 저장할 결과
        """
        self._memory_set(cache_key, result)
        self._persistent_set(cache_key, result)

    def invalidate(self, cache_key: str) -> None:
        """캐시 무효화 (미래 확장용)

        Args:
            cache_key: 무효화할 캐시 키

        Note:
            현재는 구현되지 않음. Phase 4에서 필요 시 구현.
        """
        # TODO: 구현 필요
        pass


__all__ = ["CacheService"]
