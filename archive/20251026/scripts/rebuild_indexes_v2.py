#!/usr/bin/env python3
"""Rebuild v2 indexes from metadata.db

This script rebuilds both BM25 and FAISS vector indexes from metadata.db.
The key improvement is that indexes use the SAME IDs as the database,
ensuring consistency across the entire RAG system.

ID Format: Always "doc_{int}" matching database ID

Features:
- Filename keyword enhancement (extracts keywords from filename)
- DB-driven indexing (single source of truth)
- Progress reporting
- Verification

Usage:
    python scripts/rebuild_indexes_v2.py

Environment Variables:
    MIN_TEXT_LENGTH: Minimum text_preview length (default 100)
"""

import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import get_logger
from app.rag.db import MetadataDB
from app.rag.index_bm25 import BM25Index
from app.rag.index_vec import VectorIndex

logger = get_logger(__name__)


class IndexRebuilderV2:
    """Rebuild v2 indexes from metadata.db"""

    MIN_TEXT_LENGTH = 100  # Minimum text_preview length

    def __init__(
        self,
        db_path: str = "metadata.db",
        bm25_index_dir: str = "indexes_v2/bm25",
        vec_index_dir: str = "indexes_v2/faiss",
    ):
        """Initialize rebuilder

        Args:
            db_path: Path to metadata.db
            bm25_index_dir: BM25 index output directory
            vec_index_dir: Vector index output directory
        """
        self.db = MetadataDB(db_path)
        self.bm25_index_dir = bm25_index_dir
        self.vec_index_dir = vec_index_dir

        logger.info("IndexRebuilderV2 initialized")

    def _extract_filename_keywords(self, filename: str) -> str:
        """Extract keywords from filename

        Removes dates and extensions, keeps meaningful words.

        Args:
            filename: Original filename

        Returns:
            Cleaned filename keywords

        Example:
            >>> _extract_filename_keywords("2017-12-21_방송_송출_보존용_DVR_교체_검토의_건.pdf")
            "방송 송출 보존용 DVR 교체 검토의 건"
        """
        # Remove date patterns (YYYY-MM-DD, YYYYMMDD)
        clean = re.sub(r'\d{4}-?\d{2}-?\d{2}_?', '', filename)

        # Remove extensions
        clean = re.sub(r'\.(pdf|PDF|docx?|xlsx?|pptx?)$', '', clean)

        # Replace underscores with spaces
        clean = clean.replace('_', ' ').strip()

        return clean

    def collect_documents(self) -> list:
        """Collect documents from metadata.db

        Returns:
            List of dicts with keys:
            - id: "doc_{int}"
            - text: Enhanced text (filename keywords + text_preview)
            - filename: Original filename
        """
        logger.info("Collecting documents from metadata.db...")

        # List all documents
        docs = self.db.list_documents(
            offset=0,
            limit=100000,  # High limit to get all docs
            min_text_length=self.MIN_TEXT_LENGTH
        )

        logger.info(f"Found {len(docs)} documents in database")

        # Enhance documents with metadata + filename keywords
        enhanced_docs = []
        for doc in docs:
            doc_id = doc['id']
            filename = doc['filename']

            # Get text content and metadata
            text_preview = self.db.get_content(doc_id)
            meta = self.db.get_meta(doc_id)

            # Extract filename keywords
            filename_keywords = self._extract_filename_keywords(filename)

            # Create enhanced text with metadata fields
            # This ensures metadata (drafter, category, etc.) are searchable
            meta_lines = []
            meta_lines.append(f"[파일명] {filename_keywords}")

            if meta.get('drafter'):
                meta_lines.append(f"[기안자] {meta['drafter']}")

            if meta.get('category'):
                meta_lines.append(f"[카테고리] {meta['category']}")

            if meta.get('date'):
                meta_lines.append(f"[일자] {meta['date']}")

            if meta.get('title'):
                meta_lines.append(f"[제목] {meta['title']}")

            meta_block = "\n".join(meta_lines)
            enhanced_text = f"{meta_block}\n\n{text_preview}"

            enhanced_docs.append({
                'id': doc_id,
                'text': enhanced_text,
                'filename': filename,
            })

        logger.info(f"Enhanced {len(enhanced_docs)} documents with metadata + filename keywords")
        return enhanced_docs

    def rebuild_bm25(self, documents: list) -> BM25Index:
        """Rebuild BM25 index

        Args:
            documents: List of document dicts

        Returns:
            BM25Index instance
        """
        logger.info("Rebuilding BM25 index...")

        bm25 = BM25Index(self.bm25_index_dir)

        # Add documents
        bm25.add_documents(documents)

        # Save index
        bm25.save()

        stats = bm25.get_stats()
        logger.info(
            f"BM25 index rebuilt: "
            f"{stats['total_documents']} docs, "
            f"{stats['vocab_size']} vocab"
        )

        return bm25

    def rebuild_vector(self, documents: list) -> VectorIndex:
        """Rebuild FAISS vector index

        Args:
            documents: List of document dicts

        Returns:
            VectorIndex instance
        """
        logger.info("Rebuilding FAISS vector index (this may take a while)...")

        vec = VectorIndex(self.vec_index_dir)

        # Add documents (this will load the embedding model and encode all texts)
        vec.add_documents(documents)

        # Save index
        vec.save()

        stats = vec.get_stats()
        logger.info(
            f"FAISS index rebuilt: "
            f"{stats['total_documents']} docs, "
            f"{stats['embedding_dim']}-dim embeddings"
        )

        return vec

    def verify_indexes(self, bm25: BM25Index, vec: VectorIndex, expected_count: int):
        """Verify index counts match expectations

        Args:
            bm25: BM25 index
            vec: Vector index
            expected_count: Expected number of documents
        """
        bm25_count = len(bm25.doc_ids)
        vec_count = len(vec.doc_ids)

        logger.info(
            f"Verification: BM25={bm25_count}, Vec={vec_count}, Expected={expected_count}"
        )

        if bm25_count != expected_count:
            logger.warning(f"BM25 count mismatch: {bm25_count} != {expected_count}")

        if vec_count != expected_count:
            logger.warning(f"Vector count mismatch: {vec_count} != {expected_count}")

        if bm25_count == vec_count == expected_count:
            logger.info("✅ All indexes verified successfully")
        else:
            logger.warning("⚠️  Index counts do not match expectations")

    def run(self):
        """Run full rebuild process"""
        logger.info("=" * 70)
        logger.info("RAG v2 Index Rebuild")
        logger.info("=" * 70)

        # 1. Collect documents
        documents = self.collect_documents()

        if not documents:
            logger.error("No documents found in database!")
            return

        # 2. Rebuild BM25 index
        bm25 = self.rebuild_bm25(documents)

        # 3. Rebuild FAISS vector index
        vec = self.rebuild_vector(documents)

        # 4. Verify
        self.verify_indexes(bm25, vec, len(documents))

        logger.info("=" * 70)
        logger.info("Index rebuild complete!")
        logger.info("=" * 70)
        logger.info(f"BM25 index: {self.bm25_index_dir}")
        logger.info(f"FAISS index: {self.vec_index_dir}")
        logger.info("=" * 70)


def main():
    """Main entry point"""
    rebuilder = IndexRebuilderV2()
    rebuilder.run()


if __name__ == "__main__":
    main()
