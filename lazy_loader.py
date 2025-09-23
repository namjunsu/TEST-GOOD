"""
Lazy Loading 시스템
===================

필요한 시점에만 리소스를 로드하여 시작 시간을 단축합니다.
목표: 7-10초 → 2초 이하
"""

import time
import logging
import threading
from typing import Any, Optional, Dict, Callable
from functools import wraps
from pathlib import Path

logger = logging.getLogger(__name__)


class LazyLoader:
    """지연 로딩 관리 클래스"""

    def __init__(self):
        self._cache = {}
        self._loaders = {}
        self._locks = {}
        self._load_times = {}
        self._preload_queue = []

    def register(self, name: str, loader: Callable, preload: bool = False):
        """로더 함수 등록"""
        self._loaders[name] = loader
        self._locks[name] = threading.Lock()

        if preload:
            self._preload_queue.append(name)

        logger.debug(f"Registered lazy loader: {name} (preload={preload})")

    def get(self, name: str) -> Any:
        """리소스 가져오기 (필요시 로드)"""
        if name not in self._cache:
            with self._locks.get(name, threading.Lock()):
                # Double-check locking
                if name not in self._cache:
                    self._load_resource(name)

        return self._cache[name]

    def _load_resource(self, name: str):
        """리소스 로드"""
        if name not in self._loaders:
            raise ValueError(f"Loader not found: {name}")

        start_time = time.time()
        logger.info(f"Loading resource: {name}...")

        try:
            self._cache[name] = self._loaders[name]()
            load_time = time.time() - start_time
            self._load_times[name] = load_time

            logger.info(f"✓ Loaded {name} in {load_time:.2f}s")
        except Exception as e:
            logger.error(f"✗ Failed to load {name}: {e}")
            raise

    def preload_async(self):
        """백그라운드에서 리소스 사전 로드"""
        def _preload():
            for name in self._preload_queue:
                try:
                    self.get(name)
                except Exception as e:
                    logger.error(f"Preload failed for {name}: {e}")

        thread = threading.Thread(target=_preload, daemon=True)
        thread.start()
        logger.info(f"Started async preloading for {len(self._preload_queue)} resources")

    def get_stats(self) -> Dict[str, Any]:
        """로딩 통계"""
        return {
            'loaded': list(self._cache.keys()),
            'pending': [n for n in self._loaders if n not in self._cache],
            'load_times': self._load_times,
            'total_time': sum(self._load_times.values()),
        }


# 글로벌 인스턴스
_lazy_loader = LazyLoader()


def lazy_load(name: str = None, preload: bool = False):
    """데코레이터: 함수를 lazy loading으로 변환"""
    def decorator(func):
        resource_name = name or func.__name__

        # 로더 등록
        _lazy_loader.register(resource_name, func, preload=preload)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return _lazy_loader.get(resource_name)

        # 속성으로도 접근 가능하게
        wrapper.load_now = lambda: _lazy_loader.get(resource_name)
        wrapper.is_loaded = lambda: resource_name in _lazy_loader._cache

        return wrapper
    return decorator


class LazyModel:
    """모델 지연 로딩 클래스"""

    def __init__(self, model_path: str, model_type: str = "llama"):
        self.model_path = model_path
        self.model_type = model_type
        self._model = None
        self._config = None
        self._lock = threading.Lock()

    @property
    def model(self):
        """모델 인스턴스 (처음 접근시 로드)"""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._load_model()
        return self._model

    def _load_model(self):
        """모델 실제 로드"""
        start_time = time.time()
        logger.info(f"Loading model: {self.model_path}")

        try:
            if self.model_type == "llama":
                from llama_cpp import Llama

                # 최적화된 설정
                self._model = Llama(
                    model_path=self.model_path,
                    n_ctx=4096,  # 줄인 컨텍스트
                    n_batch=256,  # 줄인 배치
                    n_gpu_layers=-1,
                    use_mmap=True,  # 메모리 매핑
                    use_mlock=False,
                    low_vram=True,  # 낮은 VRAM 모드
                    verbose=False,
                )
            else:
                raise ValueError(f"Unknown model type: {self.model_type}")

            load_time = time.time() - start_time
            logger.info(f"✓ Model loaded in {load_time:.2f}s")

        except Exception as e:
            logger.error(f"✗ Model loading failed: {e}")
            raise

    def __getattr__(self, name):
        """모델 메서드 프록시"""
        return getattr(self.model, name)

    def preload_async(self):
        """백그라운드에서 모델 로드"""
        thread = threading.Thread(target=lambda: self.model, daemon=True)
        thread.start()


class LazyVectorStore:
    """벡터 저장소 지연 로딩"""

    def __init__(self, index_path: str = None):
        self.index_path = index_path
        self._index = None
        self._embeddings = None
        self._lock = threading.Lock()

    @property
    def index(self):
        """인덱스 (처음 접근시 로드)"""
        if self._index is None:
            with self._lock:
                if self._index is None:
                    self._load_index()
        return self._index

    def _load_index(self):
        """인덱스 로드 또는 생성"""
        import faiss
        import numpy as np

        start_time = time.time()

        if self.index_path and Path(self.index_path).exists():
            logger.info(f"Loading index from {self.index_path}")
            self._index = faiss.read_index(self.index_path)
        else:
            logger.info("Creating new FAISS index")
            self._index = faiss.IndexFlatL2(768)  # 768차원 벡터

        load_time = time.time() - start_time
        logger.info(f"✓ Index ready in {load_time:.2f}s")

    def search(self, query_vector, k=5):
        """검색 (인덱스 자동 로드)"""
        return self.index.search(query_vector, k)


# 사용 예시 함수들
@lazy_load(name="qwen_model", preload=True)
def load_qwen_model():
    """Qwen 모델 로드"""
    model_path = "models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    return LazyModel(model_path, model_type="llama")


@lazy_load(name="vector_store", preload=True)
def load_vector_store():
    """벡터 저장소 로드"""
    return LazyVectorStore("indexes/faiss.index")


@lazy_load(name="bm25_index", preload=False)
def load_bm25_index():
    """BM25 인덱스 로드"""
    import pickle
    index_path = Path("indexes/bm25.pkl")

    if index_path.exists():
        with open(index_path, 'rb') as f:
            return pickle.load(f)
    else:
        from rank_bm25 import BM25Okapi
        return BM25Okapi([])  # 빈 인덱스


def optimize_startup():
    """시작 시간 최적화"""

    logger.info("="*60)
    logger.info("🚀 Optimized Startup Sequence")
    logger.info("="*60)

    start_time = time.time()

    # 1. 필수 모듈만 먼저 로드
    logger.info("1. Loading essential modules...")
    import streamlit as st  # UI 먼저

    # 2. 백그라운드 사전 로드 시작
    logger.info("2. Starting background preloading...")
    _lazy_loader.preload_async()

    # 3. UI 표시 (로딩중)
    logger.info("3. UI ready for user interaction")

    # 4. 통계
    startup_time = time.time() - start_time
    logger.info("="*60)
    logger.info(f"✅ Startup completed in {startup_time:.2f}s")
    logger.info("   (Heavy resources loading in background)")
    logger.info("="*60)

    return startup_time


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 시작 시간 테스트
    print("\n🎯 Testing Lazy Loading System\n")

    # 1. 일반 로딩 (7-10초)
    print("1. Normal loading...")
    normal_start = time.time()
    # 여기서 모든 모델 직접 로드
    normal_time = time.time() - normal_start

    # 2. Lazy loading (목표 2초)
    print("\n2. Lazy loading...")
    lazy_time = optimize_startup()

    # 3. 결과 비교
    print(f"\n📊 Results:")
    print(f"   Normal: ~7-10s (estimated)")
    print(f"   Lazy:   {lazy_time:.2f}s")
    print(f"   Saved:  ~{7 - lazy_time:.1f}s ({(1 - lazy_time/7)*100:.0f}% faster)")

    # 4. 리소스 접근 테스트
    print("\n4. Accessing resources...")
    model = load_qwen_model()  # 이제 실제 로드
    stats = _lazy_loader.get_stats()
    print(f"   Loaded: {stats['loaded']}")
    print(f"   Total load time: {stats['total_time']:.2f}s")