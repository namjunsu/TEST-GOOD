"""BM25 Index for v2 RAG system

Simplified BM25 implementation with:
- Korean tokenization (basic whitespace-based)
- Filename keyword enhancement
- Standardized return format with 'id' key
- Stored in indexes_v2/bm25/

Example:
    >>> bm25 = BM25Index()
    >>> bm25.add_documents([
    ...     {"id": "doc_4094", "text": "DVR 구매 문서 내용..."}
    ... ])
    >>> bm25.save()
    >>> results = bm25.search("DVR 구매", top_k=10)
    >>> print(results[0]["id"], results[0]["score"])
"""

from __future__ import annotations

import re
import math
import pickle
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

from app.core.logging import get_logger

logger = get_logger(__name__)


class KoreanTokenizer:
    """Simple Korean tokenizer

    Basic whitespace-based tokenization that works for Korean, English, and numbers.
    Removes special characters and normalizes to lowercase.
    """

    TOKEN_PATTERN = r'[^\w\s가-힣]'
    MIN_TOKEN_LENGTH = 1

    def __init__(self):
        self._compiled_pattern = re.compile(self.TOKEN_PATTERN)

    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into words

        Args:
            text: Input text

        Returns:
            List of tokens (lowercase)
        """
        if not text or not text.strip():
            return []

        # Remove special characters, keep Korean/English/Numbers
        text = self._compiled_pattern.sub(' ', text)

        # Split by whitespace and filter
        tokens = [
            t.lower()
            for t in text.split()
            if len(t) > self.MIN_TOKEN_LENGTH
        ]

        return tokens


class BM25Index:
    """BM25 keyword search index

    Okapi BM25 algorithm with Korean tokenization.
    Optimized for precision over recall (good for keyword matching).

    Parameters:
        k1: Term frequency saturation (default 1.2)
        b: Document length normalization (default 0.75)
    """

    DEFAULT_K1 = 1.2
    DEFAULT_B = 0.75
    DEFAULT_INDEX_DIR = "indexes_v2/bm25"

    def __init__(
        self,
        index_dir: str = None,
        k1: float = None,
        b: float = None,
    ):
        """Initialize BM25 index

        Args:
            index_dir: Directory to store index files
            k1: BM25 k1 parameter
            b: BM25 b parameter
        """
        self.index_dir = Path(index_dir) if index_dir else Path(self.DEFAULT_INDEX_DIR)
        self.k1 = k1 if k1 is not None else self.DEFAULT_K1
        self.b = b if b is not None else self.DEFAULT_B

        self.tokenizer = KoreanTokenizer()

        # BM25 data structures
        self.doc_ids: List[str] = []  # Document IDs (e.g., "doc_4094")
        self.doc_texts: List[str] = []  # Original texts
        self.term_freqs: List[Dict[str, int]] = []  # Term frequencies per doc
        self.doc_freqs: Dict[str, int] = defaultdict(int)  # Document frequencies
        self.doc_lens: List[int] = []  # Document lengths
        self.avg_doc_len: float = 0.0  # Average document length
        self.vocab: set = set()  # Vocabulary

        # Try to load existing index
        self._load_if_exists()

        logger.info(f"BM25Index initialized: {len(self.doc_ids)} documents (k1={self.k1}, b={self.b})")

    def _load_if_exists(self):
        """Load index from disk if it exists"""
        index_file = self.index_dir / "bm25.pkl"
        if index_file.exists():
            try:
                with open(index_file, 'rb') as f:
                    data = pickle.load(f)

                self.doc_ids = data['doc_ids']
                self.doc_texts = data['doc_texts']
                self.term_freqs = data['term_freqs']
                self.doc_freqs = data['doc_freqs']
                self.doc_lens = data['doc_lens']
                self.avg_doc_len = data['avg_doc_len']
                self.vocab = data['vocab']
                self.k1 = data.get('k1', self.k1)
                self.b = data.get('b', self.b)

                logger.info(f"Loaded BM25 index: {len(self.doc_ids)} docs from {index_file}")

            except Exception as e:
                logger.warning(f"Failed to load BM25 index: {e}, starting fresh")

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Add documents to index

        Args:
            documents: List of dicts with keys:
                - id: Document ID (e.g., "doc_4094")
                - text: Document text (should include filename keywords)
        """
        if not documents:
            logger.warning("No documents to add")
            return

        for doc in documents:
            doc_id = doc['id']
            text = doc['text']

            # Tokenize
            tokens = self.tokenizer.tokenize(text)

            # Add to index
            self.doc_ids.append(doc_id)
            self.doc_texts.append(text)

            # Calculate term frequencies
            term_freq = defaultdict(int)
            for token in tokens:
                term_freq[token] += 1
                self.vocab.add(token)

            self.term_freqs.append(dict(term_freq))
            self.doc_lens.append(len(tokens))

            # Update document frequencies
            for token in set(tokens):
                self.doc_freqs[token] += 1

        # Recalculate average document length
        if self.doc_lens:
            self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens)

        logger.info(f"Added {len(documents)} documents to BM25 index (total: {len(self.doc_ids)})")

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search documents using BM25

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dicts with keys:
            - id: Document ID (e.g., "doc_4094")
            - score: BM25 score
            - rank: Rank (1-indexed)
        """
        if not self.doc_ids:
            logger.warning("BM25 index is empty")
            return []

        # Tokenize query
        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens:
            logger.warning("Query tokenized to empty")
            return []

        # Calculate BM25 scores
        scores = []
        N = len(self.doc_ids)

        for doc_idx in range(N):
            score = 0.0
            doc_len = self.doc_lens[doc_idx]

            for token in query_tokens:
                if token in self.term_freqs[doc_idx]:
                    # Term frequency
                    tf = self.term_freqs[doc_idx][token]

                    # Document frequency
                    df = self.doc_freqs.get(token, 0)
                    if df == 0:
                        continue

                    # IDF calculation
                    idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

                    # BM25 score
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))

                    score += idf * (numerator / denominator)

            scores.append((score, doc_idx))

        # Sort by score
        scores.sort(key=lambda x: x[0], reverse=True)

        # Build results
        results = []
        for rank, (score, doc_idx) in enumerate(scores[:top_k], 1):
            if score > 0:
                results.append({
                    'id': self.doc_ids[doc_idx],
                    'score': float(score),
                    'rank': rank,
                })

        logger.info(f"BM25 search: '{query}' → {len(results)} results")
        return results

    def save(self) -> None:
        """Save index to disk"""
        try:
            self.index_dir.mkdir(parents=True, exist_ok=True)

            index_file = self.index_dir / "bm25.pkl"

            data = {
                'doc_ids': self.doc_ids,
                'doc_texts': self.doc_texts,
                'term_freqs': self.term_freqs,
                'doc_freqs': dict(self.doc_freqs),
                'doc_lens': self.doc_lens,
                'avg_doc_len': self.avg_doc_len,
                'vocab': self.vocab,
                'k1': self.k1,
                'b': self.b,
            }

            with open(index_file, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(f"Saved BM25 index: {len(self.doc_ids)} docs to {index_file}")

        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}", exc_info=True)
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'total_documents': len(self.doc_ids),
            'vocab_size': len(self.vocab),
            'avg_doc_length': self.avg_doc_len,
            'index_dir': str(self.index_dir),
            'parameters': {
                'k1': self.k1,
                'b': self.b,
            },
        }
