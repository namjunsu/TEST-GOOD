#!/usr/bin/env python3
"""
Redis 기반 고성능 캐싱 시스템
================================
초고속 분산 캐싱 및 실시간 데이터 처리
"""

import redis
import json
import pickle
import hashlib
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from functools import wraps
import threading
from collections import OrderedDict
import msgpack
import asyncio
import aioredis

class RedisCache:
    """Redis 캐시 시스템"""

    def __init__(self, host='localhost', port=6379, db=0, password=None):
        """Redis 연결 초기화"""
        self.config = {
            'host': host,
            'port': port,
            'db': db,
            'password': password,
            'decode_responses': False,
            'socket_keepalive': True,
            'socket_keepalive_options': {
                1: 1,  # TCP_KEEPIDLE
                2: 2,  # TCP_KEEPINTVL
                3: 3,  # TCP_KEEPCNT
            }
        }

        # Redis 연결 풀
        self.pool = redis.ConnectionPool(**self.config)
        self.redis_client = redis.Redis(connection_pool=self.pool)

        # 파이프라인 (배치 처리용)
        self.pipeline = None

        # 통계
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0
        }

        # Pub/Sub용 별도 연결
        self.pubsub = self.redis_client.pubsub()

        self._test_connection()

    def _test_connection(self):
        """연결 테스트"""
        try:
            self.redis_client.ping()
            print("✅ Redis 연결 성공")
        except redis.ConnectionError:
            print("⚠️  Redis 연결 실패 - 로컬 캐시 모드로 전환")
            self._fallback_to_local()

    def _fallback_to_local(self):
        """로컬 캐시로 폴백"""
        self.local_cache = OrderedDict()
        self.max_local_size = 1000

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """값 저장"""
        try:
            # 직렬화
            if isinstance(value, (dict, list)):
                serialized = msgpack.packb(value)
            else:
                serialized = pickle.dumps(value)

            # Redis 저장
            result = self.redis_client.setex(
                key,
                ttl,
                serialized
            )

            self.stats['sets'] += 1
            return result

        except Exception as e:
            print(f"❌ Redis set 오류: {e}")
            self.stats['errors'] += 1
            return False

    def get(self, key: str) -> Optional[Any]:
        """값 조회"""
        try:
            value = self.redis_client.get(key)

            if value is None:
                self.stats['misses'] += 1
                return None

            # 역직렬화
            try:
                deserialized = msgpack.unpackb(value, raw=False)
            except:
                deserialized = pickle.loads(value)

            self.stats['hits'] += 1

            # TTL 연장 (LRU 효과)
            self.redis_client.expire(key, 3600)

            return deserialized

        except Exception as e:
            print(f"❌ Redis get 오류: {e}")
            self.stats['errors'] += 1
            return None

    def mset(self, mapping: Dict[str, Any], ttl: int = 3600) -> bool:
        """여러 값 동시 저장"""
        try:
            pipe = self.redis_client.pipeline()

            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    serialized = msgpack.packb(value)
                else:
                    serialized = pickle.dumps(value)

                pipe.setex(key, ttl, serialized)

            results = pipe.execute()
            self.stats['sets'] += len(mapping)

            return all(results)

        except Exception as e:
            print(f"❌ Redis mset 오류: {e}")
            self.stats['errors'] += 1
            return False

    def delete(self, *keys: str) -> int:
        """키 삭제"""
        try:
            deleted = self.redis_client.delete(*keys)
            self.stats['deletes'] += deleted
            return deleted

        except Exception as e:
            print(f"❌ Redis delete 오류: {e}")
            self.stats['errors'] += 1
            return 0

    def exists(self, key: str) -> bool:
        """키 존재 확인"""
        return self.redis_client.exists(key) > 0

    def expire(self, key: str, ttl: int) -> bool:
        """TTL 설정"""
        return self.redis_client.expire(key, ttl)

    def get_stats(self) -> Dict:
        """캐시 통계"""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total * 100) if total > 0 else 0

        return {
            **self.stats,
            'hit_rate': f"{hit_rate:.2f}%",
            'total_requests': total,
            'memory_usage': self._get_memory_usage()
        }

    def _get_memory_usage(self) -> str:
        """메모리 사용량"""
        try:
            info = self.redis_client.info('memory')
            used_memory = info.get('used_memory_human', 'N/A')
            return used_memory
        except:
            return "N/A"

    def flush(self):
        """캐시 전체 삭제"""
        self.redis_client.flushdb()
        print("🗑️  캐시 전체 삭제됨")


class CacheDecorator:
    """캐시 데코레이터"""

    def __init__(self, cache: RedisCache):
        self.cache = cache

    def cached(self, ttl: int = 3600, key_prefix: str = ""):
        """함수 결과 캐싱"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 캐시 키 생성
                cache_key = self._generate_key(func.__name__, args, kwargs, key_prefix)

                # 캐시 확인
                cached_result = self.cache.get(cache_key)
                if cached_result is not None:
                    print(f"💨 캐시 히트: {func.__name__}")
                    return cached_result

                # 함수 실행
                result = func(*args, **kwargs)

                # 결과 캐싱
                self.cache.set(cache_key, result, ttl)

                return result

            return wrapper
        return decorator

    def invalidate(self, pattern: str):
        """캐시 무효화"""
        keys = self.cache.redis_client.keys(pattern)
        if keys:
            self.cache.delete(*keys)
            print(f"🗑️  {len(keys)}개 캐시 키 무효화")

    def _generate_key(self, func_name: str, args: tuple, kwargs: dict, prefix: str) -> str:
        """캐시 키 생성"""
        key_data = {
            'func': func_name,
            'args': str(args),
            'kwargs': str(sorted(kwargs.items()))
        }

        key_str = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.md5(key_str.encode()).hexdigest()

        if prefix:
            return f"{prefix}:{key_hash}"
        return key_hash


class AsyncRedisCache:
    """비동기 Redis 캐시"""

    def __init__(self, url: str = "redis://localhost"):
        self.url = url
        self.redis = None

    async def connect(self):
        """비동기 연결"""
        self.redis = await aioredis.from_url(
            self.url,
            encoding="utf-8",
            decode_responses=True
        )
        print("✅ 비동기 Redis 연결 성공")

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """비동기 저장"""
        serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        await self.redis.setex(key, ttl, serialized)

    async def get(self, key: str) -> Optional[Any]:
        """비동기 조회"""
        value = await self.redis.get(key)
        if value:
            try:
                return json.loads(value)
            except:
                return value
        return None

    async def close(self):
        """연결 종료"""
        if self.redis:
            await self.redis.close()


class RedisPubSub:
    """Redis Pub/Sub 시스템"""

    def __init__(self, cache: RedisCache):
        self.cache = cache
        self.subscribers = {}
        self.running = False

    def subscribe(self, channel: str, callback):
        """채널 구독"""
        if channel not in self.subscribers:
            self.subscribers[channel] = []

        self.subscribers[channel].append(callback)
        self.cache.pubsub.subscribe(channel)

        if not self.running:
            self._start_listener()

    def publish(self, channel: str, message: Any):
        """메시지 발행"""
        serialized = json.dumps(message) if isinstance(message, dict) else str(message)
        self.cache.redis_client.publish(channel, serialized)

    def _start_listener(self):
        """리스너 시작"""
        self.running = True
        thread = threading.Thread(target=self._listen, daemon=True)
        thread.start()

    def _listen(self):
        """메시지 수신"""
        for message in self.cache.pubsub.listen():
            if message['type'] == 'message':
                channel = message['channel'].decode() if isinstance(message['channel'], bytes) else message['channel']
                data = message['data'].decode() if isinstance(message['data'], bytes) else message['data']

                # 콜백 실행
                if channel in self.subscribers:
                    for callback in self.subscribers[channel]:
                        try:
                            callback(channel, data)
                        except Exception as e:
                            print(f"❌ Pub/Sub 콜백 오류: {e}")


class RateLimiter:
    """레이트 리미터"""

    def __init__(self, cache: RedisCache):
        self.cache = cache

    def is_allowed(self, key: str, max_requests: int = 100, window: int = 60) -> bool:
        """요청 허용 여부"""
        current = self.cache.redis_client.incr(key)

        if current == 1:
            self.cache.expire(key, window)

        return current <= max_requests

    def get_remaining(self, key: str, max_requests: int = 100) -> int:
        """남은 요청 수"""
        current = self.cache.redis_client.get(key)
        if current:
            return max(0, max_requests - int(current))
        return max_requests


# 전역 인스턴스
try:
    redis_cache = RedisCache()
    cache_decorator = CacheDecorator(redis_cache)
    pubsub = RedisPubSub(redis_cache)
    rate_limiter = RateLimiter(redis_cache)
    print("🚀 Redis 캐시 시스템 초기화 완료")
except:
    print("⚠️  Redis 연결 실패 - 기본 캐시 사용")
    redis_cache = None


# 사용 예제
if __name__ == "__main__":
    print("🧪 Redis 캐시 테스트")

    if redis_cache:
        # 기본 캐시 테스트
        redis_cache.set("test_key", {"name": "AI-CHAT", "version": "2.0"})
        value = redis_cache.get("test_key")
        print(f"캐시 값: {value}")

        # 데코레이터 테스트
        @cache_decorator.cached(ttl=60)
        def expensive_function(x, y):
            print(f"계산 실행: {x} + {y}")
            time.sleep(1)
            return x + y

        # 첫 호출 (캐시 미스)
        result1 = expensive_function(10, 20)
        print(f"결과1: {result1}")

        # 두 번째 호출 (캐시 히트)
        result2 = expensive_function(10, 20)
        print(f"결과2: {result2}")

        # 통계 출력
        stats = redis_cache.get_stats()
        print(f"\n📊 캐시 통계:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))

        # Pub/Sub 테스트
        def message_handler(channel, message):
            print(f"📨 메시지 수신 [{channel}]: {message}")

        pubsub.subscribe("test_channel", message_handler)
        pubsub.publish("test_channel", {"event": "test", "data": "hello"})

        # Rate Limiter 테스트
        for i in range(5):
            if rate_limiter.is_allowed("api_key_123", max_requests=3, window=10):
                print(f"✅ 요청 {i+1} 허용")
            else:
                print(f"❌ 요청 {i+1} 차단 (레이트 리밋)")

        time.sleep(2)

        print("\n✅ Redis 캐시 테스트 완료")
    else:
        print("❌ Redis 사용 불가")