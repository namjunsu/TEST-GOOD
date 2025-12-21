"""FAISS 벡터 스토어 v1.1

청크 임베딩을 저장하고 유사도 검색을 수행합니다.

특징:
- FAISS IndexFlatIP (내적 기반, 정규화 벡터용)
- 청크 메타데이터 관리
- 인덱스 저장/로드
- 증분 추가 지원

2025-12-21 v1.1 변경사항:
- 배치/검색 설정을 EmbeddingsConfig로 외부화
- H100 GPU 환경 최적화
"""

import os
import pickle
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np

from app.core.logging import get_logger
from app.rag.chunking import Chunk
from app.rag.embeddings.embedding_model import EmbeddingModel, get_embedding_model
from config.constants import EmbeddingsConfig

logger = get_logger(__name__)


class VectorStore:
    """FAISS 벡터 스토어

    청크 임베딩을 저장하고 유사도 검색을 수행합니다.

    Args:
        embedding_model: 임베딩 모델 인스턴스
        index_path: 인덱스 저장 경로 (기본: data/vector_index)
    """

    DEFAULT_INDEX_PATH = "data/vector_index"

    def __init__(
        self,
        embedding_model: Optional[EmbeddingModel] = None,
        index_path: Optional[str] = None,
    ):
        self.embedding_model = embedding_model or get_embedding_model()
        self.index_path = Path(
            index_path or os.getenv("VECTOR_INDEX_PATH", self.DEFAULT_INDEX_PATH)
        )

        self._index = None
        self._chunks: list[dict] = []  # 청크 메타데이터
        self._doc_id_to_indices: dict[str, list[int]] = {}  # doc_id → 인덱스 매핑
        self._lock = threading.RLock()

        # 기존 인덱스 로드 시도
        self._try_load_index()

        logger.info(
            f"✅ VectorStore 초기화: "
            f"path={self.index_path}, chunks={len(self._chunks)}"
        )

    def _try_load_index(self) -> bool:
        """기존 인덱스 로드 시도"""
        index_file = self.index_path / "faiss.index"
        meta_file = self.index_path / "chunks.pkl"

        if index_file.exists() and meta_file.exists():
            try:
                import faiss

                self._index = faiss.read_index(str(index_file))
                with open(meta_file, "rb") as f:
                    self._chunks = pickle.load(f)

                # doc_id → indices 매핑 재구성
                self._rebuild_doc_index()

                logger.info(
                    f"✅ 인덱스 로드 완료: {self._index.ntotal}개 벡터"
                )
                return True
            except Exception as e:
                logger.warning(f"⚠️ 인덱스 로드 실패: {e}")
                self._index = None
                self._chunks = []

        return False

    def _rebuild_doc_index(self):
        """doc_id → indices 매핑 재구성"""
        self._doc_id_to_indices.clear()
        for idx, chunk in enumerate(self._chunks):
            doc_id = chunk.get("doc_id", "")
            if doc_id not in self._doc_id_to_indices:
                self._doc_id_to_indices[doc_id] = []
            self._doc_id_to_indices[doc_id].append(idx)

    def _ensure_index(self):
        """인덱스가 없으면 생성"""
        if self._index is None:
            import faiss

            dim = self.embedding_model.dimension
            # 정규화된 벡터용 내적 인덱스
            self._index = faiss.IndexFlatIP(dim)
            logger.info(f"✅ FAISS 인덱스 생성: dim={dim}")

    def add_chunks(
        self,
        chunks: list[Chunk],
        batch_size: int = EmbeddingsConfig.VECTOR_ADD_BATCH_SIZE,
        show_progress: bool = True,
    ) -> int:
        """청크 추가

        Args:
            chunks: Chunk 객체 리스트
            batch_size: 임베딩 배치 크기
            show_progress: 진행률 표시

        Returns:
            추가된 청크 수
        """
        if not chunks:
            return 0

        with self._lock:
            self._ensure_index()

            # 텍스트 추출 및 임베딩
            texts = [c.text for c in chunks]
            embeddings = self.embedding_model.encode_documents(
                texts,
                batch_size=batch_size,
                show_progress=show_progress,
            )

            # FAISS에 추가
            self._index.add(embeddings.astype(np.float32))

            # 메타데이터 저장
            start_idx = len(self._chunks)
            for i, chunk in enumerate(chunks):
                chunk_meta = chunk.to_dict()
                self._chunks.append(chunk_meta)

                # doc_id → indices 매핑
                doc_id = chunk.doc_id
                if doc_id not in self._doc_id_to_indices:
                    self._doc_id_to_indices[doc_id] = []
                self._doc_id_to_indices[doc_id].append(start_idx + i)

            logger.info(
                f"✅ {len(chunks)}개 청크 추가 완료 (총 {self._index.ntotal}개)"
            )
            return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = EmbeddingsConfig.DEFAULT_SEARCH_TOP_K,
        filter_doc_ids: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """유사도 검색

        Args:
            query: 검색 쿼리
            top_k: 상위 K개 결과
            filter_doc_ids: 특정 문서만 검색 (선택적)

        Returns:
            검색 결과 리스트 [{
                "doc_id": str,
                "chunk_id": str,
                "text": str,
                "score": float,
                "chunk_index": int,
                "metadata": dict,
            }, ...]
        """
        if self._index is None or self._index.ntotal == 0:
            logger.warning("⚠️ 벡터 인덱스가 비어있습니다")
            return []

        with self._lock:
            # 쿼리 임베딩
            query_embedding = self.embedding_model.encode_query(query)
            query_vector = query_embedding.reshape(1, -1).astype(np.float32)

            # 검색 (필터 없으면 전체 검색)
            if filter_doc_ids:
                return self._filtered_search(query_vector, top_k, filter_doc_ids)

            # 전체 검색
            scores, indices = self._index.search(query_vector, top_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._chunks):
                    continue

                chunk = self._chunks[idx]
                results.append({
                    "doc_id": chunk["doc_id"],
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "snippet": chunk["text"][:EmbeddingsConfig.SNIPPET_MAX_LENGTH],
                    "score": float(score),
                    "chunk_index": chunk["chunk_index"],
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "metadata": chunk.get("metadata", {}),
                    "source": "dense",  # 검색 소스 표시
                })

            return results

    def _filtered_search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        doc_ids: list[str],
    ) -> list[dict[str, Any]]:
        """특정 문서만 필터링하여 검색"""
        # 해당 문서들의 인덱스 수집
        target_indices = []
        for doc_id in doc_ids:
            indices = self._doc_id_to_indices.get(doc_id, [])
            target_indices.extend(indices)

        if not target_indices:
            return []

        # 해당 인덱스들만 추출하여 검색
        import faiss

        target_indices = np.array(target_indices, dtype=np.int64)

        # 서브셋 생성
        subset_vectors = np.zeros(
            (len(target_indices), self.embedding_model.dimension),
            dtype=np.float32,
        )
        for i, idx in enumerate(target_indices):
            self._index.reconstruct(int(idx), subset_vectors[i])

        # 임시 인덱스로 검색
        temp_index = faiss.IndexFlatIP(self.embedding_model.dimension)
        temp_index.add(subset_vectors)

        k = min(top_k, len(target_indices))
        scores, local_indices = temp_index.search(query_vector, k)

        results = []
        for score, local_idx in zip(scores[0], local_indices[0]):
            if local_idx < 0:
                continue

            global_idx = target_indices[local_idx]
            chunk = self._chunks[global_idx]

            results.append({
                "doc_id": chunk["doc_id"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "snippet": chunk["text"][:EmbeddingsConfig.SNIPPET_MAX_LENGTH],
                "score": float(score),
                "chunk_index": chunk["chunk_index"],
                "start_char": chunk["start_char"],
                "end_char": chunk["end_char"],
                "metadata": chunk.get("metadata", {}),
                "source": "dense",
            })

        return results

    def save(self):
        """인덱스 저장"""
        if self._index is None:
            logger.warning("⚠️ 저장할 인덱스가 없습니다")
            return

        with self._lock:
            self.index_path.mkdir(parents=True, exist_ok=True)

            import faiss

            index_file = self.index_path / "faiss.index"
            meta_file = self.index_path / "chunks.pkl"

            faiss.write_index(self._index, str(index_file))
            with open(meta_file, "wb") as f:
                pickle.dump(self._chunks, f)

            logger.info(
                f"✅ 인덱스 저장 완료: {index_file} ({self._index.ntotal}개 벡터)"
            )

    def clear(self):
        """인덱스 초기화"""
        with self._lock:
            self._index = None
            self._chunks = []
            self._doc_id_to_indices = {}
            logger.info("✅ 벡터 스토어 초기화됨")

    def get_stats(self) -> dict:
        """통계 정보 반환"""
        return {
            "total_vectors": self._index.ntotal if self._index else 0,
            "total_chunks": len(self._chunks),
            "total_documents": len(self._doc_id_to_indices),
            "dimension": self.embedding_model.dimension,
            "index_path": str(self.index_path),
        }

    @property
    def is_empty(self) -> bool:
        """인덱스가 비어있는지 확인"""
        return self._index is None or self._index.ntotal == 0


# 싱글톤 인스턴스
_vector_store: Optional[VectorStore] = None
_store_lock = threading.Lock()


def get_vector_store(
    index_path: Optional[str] = None,
    force_reload: bool = False,
) -> VectorStore:
    """VectorStore 싱글톤 인스턴스 반환

    Args:
        index_path: 인덱스 경로 (첫 호출 시에만 적용)
        force_reload: 강제 재로드

    Returns:
        VectorStore 인스턴스
    """
    global _vector_store

    with _store_lock:
        if _vector_store is None or force_reload:
            _vector_store = VectorStore(index_path=index_path)

    return _vector_store
