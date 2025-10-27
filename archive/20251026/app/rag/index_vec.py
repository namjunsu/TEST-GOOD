"""FAISS Vector Index for v2 RAG system

Dense vector search using:
- Korean sentence embeddings (jhgan/ko-sroberta-multitask)
- FAISS IndexFlatL2 (exact L2 search, no quantization)
- Stored in indexes_v2/faiss/

For larger datasets (>100k docs), consider using IndexIVFFlat with
nlist=sqrt(N) clusters for faster search.

Example:
    >>> vec = VectorIndex()
    >>> vec.add_documents([
    ...     {"id": "doc_4094", "text": "문서 내용..."}
    ... ])
    >>> vec.save()
    >>> results = vec.search("검색 질의", top_k=20)
    >>> print(results[0]["id"], results[0]["score"])
"""

from __future__ import annotations

import os
import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy imports for heavy dependencies
_sentence_transformers = None
_faiss = None


def _get_sentence_transformers():
    """Lazy import sentence_transformers"""
    global _sentence_transformers
    if _sentence_transformers is None:
        import sentence_transformers
        _sentence_transformers = sentence_transformers
    return _sentence_transformers


def _get_faiss():
    """Lazy import faiss"""
    global _faiss
    if _faiss is None:
        import faiss
        _faiss = faiss
    return _faiss


class VectorIndex:
    """FAISS-based dense vector search

    Uses Korean sentence embeddings for semantic search.
    Good for capturing meaning and synonyms.

    Default model: jhgan/ko-sroberta-multitask (768-dim)
    """

    DEFAULT_MODEL_NAME = "jhgan/ko-sroberta-multitask"
    DEFAULT_INDEX_DIR = "indexes_v2/faiss"
    DEFAULT_EMBEDDING_DIM = 768

    def __init__(
        self,
        index_dir: str = None,
        model_name: str = None,
    ):
        """Initialize vector index

        Args:
            index_dir: Directory to store index files
            model_name: HuggingFace model name for embeddings
        """
        self.index_dir = Path(index_dir) if index_dir else Path(self.DEFAULT_INDEX_DIR)
        self.model_name = model_name or os.getenv('EMBEDDING_MODEL', self.DEFAULT_MODEL_NAME)

        # Embedding model (lazy loaded)
        self._model = None

        # FAISS index
        self.index = None  # Will be initialized on first add
        self.doc_ids: List[str] = []  # Document IDs
        self.embedding_dim = self.DEFAULT_EMBEDDING_DIM

        # Try to load existing index
        self._load_if_exists()

        logger.info(f"VectorIndex initialized: {len(self.doc_ids)} documents (model={self.model_name})")

    def _get_model(self):
        """Lazy load embedding model"""
        if self._model is None:
            st = _get_sentence_transformers()
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = st.SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded: {self.model_name}")

        return self._model

    def _load_if_exists(self):
        """Load index from disk if it exists"""
        index_file = self.index_dir / "faiss.index"
        meta_file = self.index_dir / "meta.pkl"

        if index_file.exists() and meta_file.exists():
            try:
                faiss = _get_faiss()

                # Load FAISS index
                self.index = faiss.read_index(str(index_file))

                # Load metadata
                with open(meta_file, 'rb') as f:
                    meta = pickle.load(f)

                self.doc_ids = meta['doc_ids']
                self.embedding_dim = meta['embedding_dim']
                self.model_name = meta.get('model_name', self.model_name)

                logger.info(f"Loaded FAISS index: {len(self.doc_ids)} docs from {index_file}")

            except Exception as e:
                logger.warning(f"Failed to load FAISS index: {e}, starting fresh")

    def _encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings

        Args:
            texts: List of text strings

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        model = self._get_model()

        # Encode with normalization
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
            show_progress_bar=False,
        )

        return embeddings.astype('float32')

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Add documents to index

        Args:
            documents: List of dicts with keys:
                - id: Document ID (e.g., "doc_4094")
                - text: Document text
        """
        if not documents:
            logger.warning("No documents to add")
            return

        faiss = _get_faiss()

        # Extract texts and IDs
        texts = [doc['text'] for doc in documents]
        doc_ids = [doc['id'] for doc in documents]

        # Encode texts
        logger.info(f"Encoding {len(texts)} documents...")
        embeddings = self._encode(texts)

        # Initialize index if needed
        if self.index is None:
            self.embedding_dim = embeddings.shape[1]
            # Use IndexFlatL2 for exact search (no quantization)
            # For large datasets, consider IndexIVFFlat with nlist=sqrt(N)
            self.index = faiss.IndexFlatL2(self.embedding_dim)
            logger.info(f"Created FAISS IndexFlatL2 (dim={self.embedding_dim})")

        # Add to index
        self.index.add(embeddings)
        self.doc_ids.extend(doc_ids)

        logger.info(f"Added {len(documents)} documents to FAISS index (total: {len(self.doc_ids)})")

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """Search documents using vector similarity

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dicts with keys:
            - id: Document ID (e.g., "doc_4094")
            - score: L2 distance (lower is better)
            - rank: Rank (1-indexed)

        Note:
            Scores are L2 distances. For cosine similarity, use:
            cosine_sim = 1 - (L2_distance^2 / 2)
        """
        if self.index is None or len(self.doc_ids) == 0:
            logger.warning("FAISS index is empty")
            return []

        # Encode query
        query_embedding = self._encode([query])

        # Search
        distances, indices = self.index.search(query_embedding, min(top_k, len(self.doc_ids)))

        # Build results
        results = []
        for rank, (dist, idx) in enumerate(zip(distances[0], indices[0]), 1):
            if idx >= 0 and idx < len(self.doc_ids):
                results.append({
                    'id': self.doc_ids[idx],
                    'score': float(dist),
                    'rank': rank,
                })

        logger.info(f"FAISS search: '{query}' → {len(results)} results")
        return results

    def save(self) -> None:
        """Save index to disk"""
        if self.index is None or len(self.doc_ids) == 0:
            logger.warning("No index to save")
            return

        try:
            faiss = _get_faiss()

            self.index_dir.mkdir(parents=True, exist_ok=True)

            # Save FAISS index
            index_file = self.index_dir / "faiss.index"
            faiss.write_index(self.index, str(index_file))

            # Save metadata
            meta_file = self.index_dir / "meta.pkl"
            meta = {
                'doc_ids': self.doc_ids,
                'embedding_dim': self.embedding_dim,
                'model_name': self.model_name,
            }

            with open(meta_file, 'wb') as f:
                pickle.dump(meta, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(f"Saved FAISS index: {len(self.doc_ids)} docs to {self.index_dir}")

        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}", exc_info=True)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'total_documents': len(self.doc_ids),
            'embedding_dim': self.embedding_dim,
            'model_name': self.model_name,
            'index_dir': str(self.index_dir),
            'index_trained': self.index.is_trained if self.index else False,
        }
