#!/usr/bin/env python3
"""
고급 검색 최적화 시스템
========================
FAISS 기반 초고속 벡터 검색 및 하이브리드 검색 최적화
"""

import numpy as np
import pickle
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import faiss
import hashlib
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
from collections import OrderedDict
import json

class FAISSSearchOptimizer:
    """FAISS 기반 초고속 벡터 검색"""

    def __init__(self, dimension: int = 768, index_type: str = "IVF"):
        self.dimension = dimension
        self.index_type = index_type
        self.index = None
        self.document_store = {}
        self.id_to_doc = {}
        self.embedding_model = None
        self.index_path = Path(".cache/faiss_index")
        self.index_path.mkdir(parents=True, exist_ok=True)

        # GPU 지원 확인
        self.use_gpu = faiss.get_num_gpus() > 0
        if self.use_gpu:
            print("🎮 GPU 가속 활성화")

        self._initialize_index()
        self._load_embedding_model()

    def _initialize_index(self):
        """FAISS 인덱스 초기화"""
        if self.index_type == "IVF":
            # IVF (Inverted File) 인덱스 - 대규모 데이터셋에 효율적
            quantizer = faiss.IndexFlatL2(self.dimension)
            self.index = faiss.IndexIVFFlat(quantizer, self.dimension, 100)
        elif self.index_type == "HNSW":
            # HNSW (Hierarchical Navigable Small World) - 높은 정확도
            self.index = faiss.IndexHNSWFlat(self.dimension, 32)
        else:
            # 기본: Flat 인덱스
            self.index = faiss.IndexFlatL2(self.dimension)

        # GPU로 이동 (가능한 경우)
        if self.use_gpu:
            res = faiss.StandardGpuResources()
            self.index = faiss.index_cpu_to_gpu(res, 0, self.index)

    def _load_embedding_model(self):
        """임베딩 모델 로드"""
        try:
            self.embedding_model = SentenceTransformer(
                'sentence-transformers/paraphrase-multilingual-mpnet-base-v2'
            )
            print("✅ 임베딩 모델 로드 완료")
        except:
            # 폴백: 간단한 해시 기반 임베딩
            print("⚠️  임베딩 모델 로드 실패, 해시 기반 폴백")
            self.embedding_model = None

    def add_documents(self, documents: List[Dict[str, Any]], batch_size: int = 100):
        """문서 일괄 추가"""
        print(f"📚 {len(documents)}개 문서 인덱싱 시작...")

        # 배치 처리
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            embeddings = self._batch_encode(batch)

            # FAISS 인덱스에 추가
            if self.index_type == "IVF" and not self.index.is_trained:
                # IVF 인덱스는 학습 필요
                self.index.train(embeddings)

            start_id = len(self.id_to_doc)
            ids = np.arange(start_id, start_id + len(batch))

            self.index.add_with_ids(embeddings, ids)

            # 문서 저장
            for j, doc in enumerate(batch):
                doc_id = start_id + j
                self.id_to_doc[doc_id] = doc
                self.document_store[doc.get('id', str(doc_id))] = doc

        print(f"✅ 인덱싱 완료: {self.index.ntotal}개 벡터")
        self._save_index()

    def _batch_encode(self, documents: List[Dict]) -> np.ndarray:
        """배치 인코딩"""
        texts = [doc.get('content', '') for doc in documents]

        if self.embedding_model:
            embeddings = self.embedding_model.encode(texts, batch_size=32, show_progress_bar=False)
        else:
            # 폴백: 해시 기반 임베딩
            embeddings = []
            for text in texts:
                hash_obj = hashlib.sha256(text.encode()).digest()
                embedding = np.frombuffer(hash_obj * 24, dtype=np.float32)[:self.dimension]
                embeddings.append(embedding)
            embeddings = np.array(embeddings)

        return embeddings.astype('float32')

    def search(self, query: str, k: int = 10, threshold: float = 0.7) -> List[Dict]:
        """초고속 벡터 검색"""
        if self.index.ntotal == 0:
            return []

        # 쿼리 임베딩
        if self.embedding_model:
            query_embedding = self.embedding_model.encode([query])
        else:
            hash_obj = hashlib.sha256(query.encode()).digest()
            query_embedding = np.frombuffer(hash_obj * 24, dtype=np.float32)[:self.dimension].reshape(1, -1)

        query_embedding = query_embedding.astype('float32')

        # FAISS 검색
        distances, indices = self.index.search(query_embedding, k)

        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx >= 0 and idx in self.id_to_doc:
                doc = self.id_to_doc[idx]
                score = 1 / (1 + dist)  # 거리를 유사도로 변환

                if score >= threshold:
                    results.append({
                        **doc,
                        'score': float(score),
                        'rank': i + 1
                    })

        return results

    def _save_index(self):
        """인덱스 저장"""
        try:
            # FAISS 인덱스 저장
            faiss.write_index(self.index, str(self.index_path / "faiss.index"))

            # 문서 매핑 저장
            with open(self.index_path / "doc_mapping.pkl", 'wb') as f:
                pickle.dump({
                    'id_to_doc': self.id_to_doc,
                    'document_store': self.document_store
                }, f)

            print("💾 인덱스 저장 완료")
        except Exception as e:
            print(f"❌ 인덱스 저장 실패: {e}")

    def load_index(self) -> bool:
        """인덱스 로드"""
        try:
            index_file = self.index_path / "faiss.index"
            mapping_file = self.index_path / "doc_mapping.pkl"

            if index_file.exists() and mapping_file.exists():
                # FAISS 인덱스 로드
                self.index = faiss.read_index(str(index_file))

                # GPU로 이동 (가능한 경우)
                if self.use_gpu:
                    res = faiss.StandardGpuResources()
                    self.index = faiss.index_cpu_to_gpu(res, 0, self.index)

                # 문서 매핑 로드
                with open(mapping_file, 'rb') as f:
                    data = pickle.load(f)
                    self.id_to_doc = data['id_to_doc']
                    self.document_store = data['document_store']

                print(f"✅ 인덱스 로드 완료: {self.index.ntotal}개 벡터")
                return True
        except Exception as e:
            print(f"⚠️  인덱스 로드 실패: {e}")

        return False


class HybridSearchOptimizer:
    """하이브리드 검색 최적화 (BM25 + FAISS)"""

    def __init__(self):
        self.faiss_search = FAISSSearchOptimizer()
        self.bm25_cache = OrderedDict(maxsize=1000)
        self.result_cache = OrderedDict(maxsize=500)
        self.cache_lock = threading.Lock()

        # 성능 메트릭
        self.search_times = []
        self.cache_hits = 0
        self.total_searches = 0

    def index_documents(self, documents: List[Dict]):
        """문서 인덱싱"""
        start_time = time.time()

        # 병렬 처리
        with ThreadPoolExecutor(max_workers=4) as executor:
            # FAISS 인덱싱
            future_faiss = executor.submit(self.faiss_search.add_documents, documents)

            # BM25 준비 (추후 구현)
            # future_bm25 = executor.submit(self._prepare_bm25, documents)

            future_faiss.result()
            # future_bm25.result()

        index_time = time.time() - start_time
        print(f"⚡ 인덱싱 완료: {index_time:.2f}초")

    def search(self, query: str, mode: str = "hybrid", k: int = 10) -> List[Dict]:
        """하이브리드 검색"""
        self.total_searches += 1

        # 캐시 확인
        cache_key = f"{query}:{mode}:{k}"
        with self.cache_lock:
            if cache_key in self.result_cache:
                self.cache_hits += 1
                print(f"💨 캐시 히트! ({self.cache_hits}/{self.total_searches})")
                return self.result_cache[cache_key]

        start_time = time.time()

        if mode == "vector":
            results = self.faiss_search.search(query, k)
        elif mode == "keyword":
            results = self._bm25_search(query, k)
        else:  # hybrid
            # 벡터 검색
            vector_results = self.faiss_search.search(query, k * 2)

            # 키워드 검색
            keyword_results = self._bm25_search(query, k * 2)

            # 결과 병합
            results = self._merge_results(vector_results, keyword_results, k)

        search_time = time.time() - start_time
        self.search_times.append(search_time)

        # 캐시 저장
        with self.cache_lock:
            self.result_cache[cache_key] = results
            # 캐시 크기 제한
            if len(self.result_cache) > 500:
                self.result_cache.popitem(last=False)

        print(f"🔍 검색 완료: {search_time:.3f}초")
        return results

    def _bm25_search(self, query: str, k: int) -> List[Dict]:
        """BM25 키워드 검색 (플레이스홀더)"""
        # 실제 BM25 구현은 기존 시스템 활용
        return []

    def _merge_results(self, vector_results: List[Dict], keyword_results: List[Dict], k: int) -> List[Dict]:
        """검색 결과 병합"""
        # 점수 기반 병합
        all_results = {}

        # 벡터 결과 추가 (가중치 0.6)
        for result in vector_results:
            doc_id = result.get('id', str(result))
            if doc_id not in all_results:
                all_results[doc_id] = result
                all_results[doc_id]['final_score'] = result.get('score', 0) * 0.6
            else:
                all_results[doc_id]['final_score'] += result.get('score', 0) * 0.6

        # 키워드 결과 추가 (가중치 0.4)
        for result in keyword_results:
            doc_id = result.get('id', str(result))
            if doc_id not in all_results:
                all_results[doc_id] = result
                all_results[doc_id]['final_score'] = result.get('score', 0) * 0.4
            else:
                all_results[doc_id]['final_score'] += result.get('score', 0) * 0.4

        # 정렬 및 상위 k개 반환
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x['final_score'],
            reverse=True
        )

        return sorted_results[:k]

    def get_performance_stats(self) -> Dict:
        """성능 통계"""
        if not self.search_times:
            return {}

        return {
            'avg_search_time': np.mean(self.search_times),
            'min_search_time': np.min(self.search_times),
            'max_search_time': np.max(self.search_times),
            'cache_hit_rate': (self.cache_hits / self.total_searches * 100) if self.total_searches > 0 else 0,
            'total_searches': self.total_searches,
            'index_size': self.faiss_search.index.ntotal if self.faiss_search.index else 0
        }


class SearchAccelerator:
    """검색 가속기 - 프리페칭 및 예측"""

    def __init__(self, optimizer: HybridSearchOptimizer):
        self.optimizer = optimizer
        self.query_history = []
        self.prefetch_cache = {}
        self.prediction_model = None

    def predictive_search(self, partial_query: str) -> List[str]:
        """예측 검색 - 타이핑 중 자동완성"""
        predictions = []

        # 쿼리 히스토리에서 유사한 쿼리 찾기
        for hist_query in self.query_history:
            if partial_query.lower() in hist_query.lower():
                predictions.append(hist_query)

        # 자주 사용되는 패턴
        common_patterns = [
            f"{partial_query} 문서",
            f"{partial_query} 구매",
            f"{partial_query} 년도",
            f"{partial_query} 장비",
            f"2024년 {partial_query}",
            f"{partial_query} 현황"
        ]

        predictions.extend(common_patterns)
        return predictions[:5]  # 상위 5개

    def prefetch_results(self, query: str):
        """결과 프리페칭 - 백그라운드 로딩"""
        # 예상 쿼리 생성
        related_queries = [
            query,
            f"{query} 상세",
            f"{query} 요약",
            f"{query} 최근"
        ]

        # 백그라운드에서 프리페치
        def _prefetch():
            for q in related_queries:
                if q not in self.prefetch_cache:
                    results = self.optimizer.search(q, k=5)
                    self.prefetch_cache[q] = results

        thread = threading.Thread(target=_prefetch)
        thread.daemon = True
        thread.start()

    def get_instant_results(self, query: str) -> Optional[List[Dict]]:
        """즉시 결과 반환 (프리페치된 경우)"""
        return self.prefetch_cache.get(query)


# 전역 인스턴스
search_optimizer = HybridSearchOptimizer()
search_accelerator = SearchAccelerator(search_optimizer)


# 사용 예제
if __name__ == "__main__":
    print("🚀 고급 검색 최적화 시스템 테스트")

    # 테스트 문서 생성
    test_docs = [
        {'id': f'doc_{i}', 'content': f'테스트 문서 {i}번입니다. 내용: {i*100}'}
        for i in range(100)
    ]

    # 인덱싱
    search_optimizer.index_documents(test_docs)

    # 검색 테스트
    results = search_optimizer.search("테스트 문서 50", k=5)
    print(f"\n검색 결과: {len(results)}개")
    for result in results[:3]:
        print(f"  - {result.get('id')}: {result.get('final_score', result.get('score', 0)):.3f}")

    # 성능 통계
    stats = search_optimizer.get_performance_stats()
    print(f"\n📊 성능 통계:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # 예측 검색
    predictions = search_accelerator.predictive_search("테스트")
    print(f"\n🔮 예측 검색:")
    for pred in predictions:
        print(f"  - {pred}")