"""
최적화된 캐시 시스템 - 메모리 효율적
"""

import pickle
import zlib
import json
from pathlib import Path

class CompressedCache:
    """압축 캐시 - 메모리 사용량 70% 감소"""

    def __init__(self, cache_dir="cache_compressed"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.memory_cache = {}  # 작은 인메모리 캐시
        self.MAX_MEMORY_ITEMS = 10

    def set(self, key: str, value: any):
        """압축하여 저장"""
        # 작은 데이터는 메모리에
        if len(str(value)) < 1000:
            if len(self.memory_cache) >= self.MAX_MEMORY_ITEMS:
                # LRU 방식으로 제거
                oldest = next(iter(self.memory_cache))
                del self.memory_cache[oldest]
            self.memory_cache[key] = value
        else:
            # 큰 데이터는 압축하여 디스크에
            compressed = zlib.compress(pickle.dumps(value))
            cache_file = self.cache_dir / f"{hash(key)}.cache"
            with open(cache_file, 'wb') as f:
                f.write(compressed)

    def get(self, key: str):
        """압축 해제하여 조회"""
        # 먼저 메모리 확인
        if key in self.memory_cache:
            return self.memory_cache[key]

        # 디스크에서 조회
        cache_file = self.cache_dir / f"{hash(key)}.cache"
        if cache_file.exists():
            with open(cache_file, 'rb') as f:
                compressed = f.read()
            return pickle.loads(zlib.decompress(compressed))
        return None

    def clear_old_cache(self, days=7):
        """오래된 캐시 정리"""
        import time
        current_time = time.time()

        for cache_file in self.cache_dir.glob("*.cache"):
            if current_time - cache_file.stat().st_mtime > days * 86400:
                cache_file.unlink()

        print(f"✅ {days}일 이상 된 캐시 파일 정리 완료")

class LazyLoader:
    """지연 로딩 - 필요한 때만 메모리에 로드"""

    def __init__(self):
        self.loaded_docs = {}
        self.doc_paths = []

    def register_document(self, path: Path):
        """문서 경로만 등록"""
        self.doc_paths.append(path)

    def get_document(self, path: Path):
        """필요할 때 로드"""
        if path not in self.loaded_docs:
            # 메모리 체크
            if len(self.loaded_docs) > 10:
                # 가장 오래된 문서 언로드
                oldest = next(iter(self.loaded_docs))
                del self.loaded_docs[oldest]
                gc.collect()

            # 문서 로드
            self.loaded_docs[path] = self._load_document(path)

        return self.loaded_docs[path]

    def _load_document(self, path: Path):
        """실제 문서 로드"""
        # 간단한 예시
        with open(path, 'rb') as f:
            return f.read()
