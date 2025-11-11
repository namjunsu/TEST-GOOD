# QueryCache v2.0 사용 가이드

**버전**: v2.0
**작성일**: 2025-11-11

---

## 개요

QueryCache v2.0은 스레드 안전, 네임스페이스 분리, 캐시 스탬피드 방지를 제공하는
프로덕션 급 인메모리 캐시입니다.

### 주요 기능

- ✅ **스레드 안전성**: threading.RLock 사용
- ✅ **네임스페이스**: 인덱스 버전/설정 자동 반영
- ✅ **캐시 스탬피드 방지**: in-flight de-duplication
- ✅ **TTL + LRU**: 만료 + 용량 기반 축출
- ✅ **Monotonic Clock**: 시계 변동 영향 제거

---

## 기본 사용법

### 1. 단순 캐시 사용

```python
from app.rag.cache_manager import get_cache
from app.rag.cache_namespace import current_retriever_namespace

cache = get_cache()
namespace = current_retriever_namespace()

# 캐시 조회
result = cache.get(query, mode="chat", namespace=namespace)

if result is None:
    # 캐시 미스 - 검색 수행
    result = expensive_search(query, mode="chat")
    cache.set(query, result, mode="chat", namespace=namespace)

return result
```

---

## 캐시 스탬피드 방지

동일 질의 동시 요청 시 중복 계산을 방지합니다.

### 권장 패턴

```python
from app.rag.cache_manager import get_cache
from app.rag.cache_namespace import current_retriever_namespace

def search_with_cache(query: str, mode: str = "chat"):
    cache = get_cache()
    namespace = current_retriever_namespace()

    # 1. 캐시 조회
    result = cache.get(query, mode, namespace)
    if result is not None:
        return result

    # 2. 계산 시작 신호
    is_leader = cache.begin_inflight(query, mode, namespace)

    if is_leader:
        # 리더: 실제 검색 수행
        try:
            result = expensive_search(query, mode)
            cache.set(query, result, mode, namespace)
            return result
        finally:
            # 계산 완료 신호 (항상 호출)
            cache.end_inflight(query, mode, namespace)
    else:
        # 팔로워: 리더의 계산 완료 대기
        cache.wait_inflight(query, mode, namespace, timeout=10.0)

        # 재조회 (리더가 캐시에 저장했을 것)
        result = cache.get(query, mode, namespace)
        if result is None:
            # 타임아웃 또는 리더 실패 - 직접 계산
            result = expensive_search(query, mode)
            cache.set(query, result, mode, namespace)

        return result
```

---

## 네임스페이스 사용

### 자동 네임스페이스

```python
from app.rag.cache_namespace import current_retriever_namespace

# 인덱스 버전 + 설정 해시 자동 조합
namespace = current_retriever_namespace()
# 예: "bm25:v1699876543|conf:a1b2c3d4"

cache.get(query, mode="chat", namespace=namespace)
```

### 수동 네임스페이스

```python
# 특정 실험용 네임스페이스
namespace = "experiment:v1"

cache.get(query, mode="chat", namespace=namespace)
```

### 네임스페이스 효과

**인덱스 로테이션 시**:
```python
# Before: namespace = "bm25:v1699876543|conf:a1b2c3d4"
# After:  namespace = "bm25:v1699999999|conf:a1b2c3d4"
# → 자동으로 새로운 캐시 키 사용 (오래된 캐시는 TTL로 자연 만료)
```

**설정 변경 시**:
```python
# Before: RETRIEVE_TOPK=200 → conf:a1b2c3d4
# After:  RETRIEVE_TOPK=120 → conf:9z8y7x6w
# → 설정 변경 시 자동 캐시 무효화
```

---

## 통계 조회

```python
from app.rag.cache_manager import get_cache_stats

stats = get_cache_stats()
print(stats)

# 출력 예시:
# {
#     "size": 45,
#     "max_size": 100,
#     "hits": 523,
#     "misses": 177,
#     "evictions": 3,
#     "expired": 12,
#     "hit_rate": "74.71%",
#     "inflight_count": 0
# }
```

---

## API 레퍼런스

### QueryCache 메서드

#### `get(query, mode=None, namespace=None)`
캐시 조회 (thread-safe)

**반환값**: 캐시된 결과 또는 None

---

#### `set(query, result, mode=None, namespace=None)`
캐시 저장 (thread-safe)

**주의**: LRU 축출 발생 가능

---

#### `begin_inflight(query, mode=None, namespace=None)`
스탬피드 방지: 계산 시작 신호

**반환값**: True (리더), False (팔로워)

---

#### `end_inflight(query, mode=None, namespace=None)`
계산 완료 신호 (리더만 호출)

---

#### `wait_inflight(query, mode=None, namespace=None, timeout=10.0)`
다른 스레드의 계산 완료 대기 (팔로워만 호출)

---

#### `clear()`
전체 캐시 삭제 (thread-safe)

---

#### `get_stats()`
캐시 통계 조회

---

## 헬퍼 함수

### `get_cached_result(query, mode=None, namespace=None)`
단순 캐시 조회 헬퍼

```python
from app.rag.cache_manager import get_cached_result

result = get_cached_result("질의", mode="chat", namespace=ns)
```

---

### `cache_query_result(query, result, mode=None, namespace=None)`
단순 캐시 저장 헬퍼

```python
from app.rag.cache_manager import cache_query_result

cache_query_result("질의", result, mode="chat", namespace=ns)
```

---

## 환경 설정

```bash
# .env
CACHE_MAX_SIZE=100   # 최대 캐시 항목 수
CACHE_TTL=7200       # TTL (초, 기본 2시간)
```

---

## 성능 고려사항

### 메모리 사용량

- **1개 항목**: ~10KB (평균 검색 결과 크기)
- **100개 항목**: ~1MB

대형 결과 캐싱 시 max_size 조정 권장.

---

### 스탬피드 빈도

고빈도 반복 질의가 많은 환경에서 효과 극대화:

```python
# 동시 요청 100개 → 실제 검색 1회
# 나머지 99개는 대기 후 캐시 히트
```

---

### TTL 전략

| 용도 | 권장 TTL |
|------|---------|
| **일반 검색** | 2시간 (7200초) |
| **DOC_ANCHORED** | 10분 (600초) |
| **실험/개발** | 5분 (300초) |

---

## 트러블슈팅

### Q: 캐시 히트율이 낮아요 (< 30%)

**원인**:
- 질의 다양성이 높음
- 네임스페이스가 자주 변경됨 (인덱스 로테이션)

**해결**:
- max_size 증가 (100 → 200)
- TTL 증가 (2h → 4h)

---

### Q: 메모리 사용량이 과다해요

**원인**:
- 대형 결과 캐싱
- max_size가 너무 큼

**해결**:
- max_size 감소 (100 → 50)
- TTL 감소 (2h → 1h)
- 결과 크기 제한 (snippet 길이 축소)

---

### Q: 캐시 스탬피드가 여전히 발생해요

**원인**:
- begin_inflight/end_inflight 미사용
- 비동기 환경에서 동기 캐시 사용

**해결**:
- 권장 패턴 적용 (위 예시 참조)
- asyncio 환경이면 별도 async 캐시 고려

---

## 마이그레이션 (v1 → v2)

### Before (v1)

```python
from app.rag.cache_manager import get_cache

cache = get_cache()
result = cache.get(query, mode="chat")
if result is None:
    result = search(query)
    cache.set(query, result, mode="chat")
```

### After (v2)

```python
from app.rag.cache_manager import get_cache
from app.rag.cache_namespace import current_retriever_namespace

cache = get_cache()
namespace = current_retriever_namespace()

result = cache.get(query, mode="chat", namespace=namespace)
if result is None:
    result = search(query)
    cache.set(query, result, mode="chat", namespace=namespace)
```

**변경 사항**: `namespace` 파라미터 추가 (선택사항, 기본값 "default")

---

## 참고 자료

- **소스 코드**: `app/rag/cache_manager.py`
- **네임스페이스 헬퍼**: `app/rag/cache_namespace.py`
- **스마트 키 생성**: `app/rag/smart_cache_key.py`

---

**최종 수정**: 2025-11-11
**문서 버전**: 2.0
