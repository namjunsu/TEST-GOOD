"""MetadataDB: Single Source of Truth for document content

This module provides the canonical interface for accessing document
metadata and content from metadata.db. All RAG components should use
this module instead of directly querying the database.

Example:
    >>> db = MetadataDB()
    >>> content = db.get_content("doc_4094")
    >>> meta = db.get_meta("doc_4094")
    >>> print(meta["title"], meta["filename"])
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.core.logging import get_logger
from app.core.errors import SearchError, ErrorCode

logger = get_logger(__name__)


class MetadataDB:
    """SSOT for document metadata and content

    All document content and metadata should be retrieved through this class.
    This ensures consistency across the entire RAG system.

    ID Format: Always "doc_{int}" (e.g., "doc_4094")

    Example:
        >>> db = MetadataDB()
        >>> content = db.get_content("doc_4094")
        >>> meta = db.get_meta("doc_4094")
        >>> docs = db.list_documents(limit=100)
    """

    def __init__(self, db_path: str = "metadata.db"):
        """Initialize MetadataDB

        Args:
            db_path: Path to metadata.db file
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent reads
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")

        logger.info(f"MetadataDB initialized: {db_path}")

    def _doc_id_to_int(self, doc_id: str) -> int:
        """Convert doc_id to integer

        Args:
            doc_id: Document ID in format "doc_{int}"

        Returns:
            Integer ID

        Raises:
            ValueError: If doc_id format is invalid
        """
        if not doc_id.startswith("doc_"):
            raise ValueError(f"Invalid doc_id format: {doc_id} (expected doc_{{int}})")

        try:
            return int(doc_id.replace("doc_", ""))
        except ValueError as e:
            raise ValueError(f"Invalid doc_id format: {doc_id}") from e

    def _int_to_doc_id(self, int_id: int) -> str:
        """Convert integer to doc_id

        Args:
            int_id: Integer ID

        Returns:
            Document ID in format "doc_{int}"
        """
        return f"doc_{int_id}"

    def get_content(self, doc_id: str) -> str:
        """Get document content (text_preview field)

        Args:
            doc_id: Document ID (e.g., "doc_4094")

        Returns:
            Document text content. Returns empty string if not found.
        """
        try:
            int_id = self._doc_id_to_int(doc_id)

            cursor = self.conn.execute("""
                SELECT text_preview
                FROM documents
                WHERE id = ?
            """, (int_id,))

            row = cursor.fetchone()
            if row:
                return row['text_preview'] or ""
            else:
                logger.warning(f"Document not found: {doc_id}")
                return ""

        except Exception as e:
            logger.error(f"Failed to get content for {doc_id}: {e}")
            return ""

    def get_meta(self, doc_id: str) -> Dict[str, Any]:
        """Get document metadata

        Args:
            doc_id: Document ID (e.g., "doc_4094")

        Returns:
            Dictionary with metadata fields:
            - id: "doc_{int}"
            - filename: Original filename
            - title: Document title
            - date: Document date (YYYY-MM-DD or Korean format)
            - year, month: Extracted year/month
            - category: Document category
            - drafter: Document author/drafter
            - amount: Amount (if applicable)
            - page_count: Number of pages
            - path: File path
        """
        try:
            int_id = self._doc_id_to_int(doc_id)

            cursor = self.conn.execute("""
                SELECT
                    id, filename, title, date, year, month,
                    category, drafter, amount, page_count, path
                FROM documents
                WHERE id = ?
            """, (int_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'id': self._int_to_doc_id(row['id']),
                    'filename': row['filename'] or "",
                    'title': row['title'] or "",
                    'date': row['date'] or "",
                    'year': row['year'] or "",
                    'month': row['month'] or "",
                    'category': row['category'] or "",
                    'drafter': row['drafter'] or "",
                    'amount': row['amount'] or 0,
                    'page_count': row['page_count'] or 0,
                    'path': row['path'] or "",
                }
            else:
                logger.warning(f"Document not found: {doc_id}")
                return {'id': doc_id}

        except Exception as e:
            logger.error(f"Failed to get meta for {doc_id}: {e}")
            return {'id': doc_id}

    def list_documents(
        self,
        offset: int = 0,
        limit: int = 1000,
        min_text_length: int = 100
    ) -> List[Dict[str, Any]]:
        """List all documents in database

        Args:
            offset: Offset for pagination
            limit: Maximum number of documents to return
            min_text_length: Minimum text_preview length (filter out empty docs)

        Returns:
            List of document dictionaries with fields:
            - id: "doc_{int}"
            - filename: Original filename
            - path: File path
            - text_length: Length of text_preview
        """
        try:
            cursor = self.conn.execute("""
                SELECT id, filename, path, LENGTH(text_preview) as text_length
                FROM documents
                WHERE text_preview IS NOT NULL
                  AND LENGTH(text_preview) >= ?
                ORDER BY id ASC
                LIMIT ? OFFSET ?
            """, (min_text_length, limit, offset))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': self._int_to_doc_id(row['id']),
                    'filename': row['filename'] or "",
                    'path': row['path'] or "",
                    'text_length': row['text_length'] or 0,
                })

            logger.info(f"Listed {len(results)} documents (offset={offset}, limit={limit})")
            return results

        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    def count_documents(self, min_text_length: int = 100) -> int:
        """Count total documents in database

        Args:
            min_text_length: Minimum text_preview length

        Returns:
            Number of documents
        """
        try:
            cursor = self.conn.execute("""
                SELECT COUNT(*) as count
                FROM documents
                WHERE text_preview IS NOT NULL
                  AND LENGTH(text_preview) >= ?
            """, (min_text_length,))

            row = cursor.fetchone()
            count = row['count'] if row else 0

            logger.info(f"Total documents: {count} (min_text_length={min_text_length})")
            return count

        except Exception as e:
            logger.error(f"Failed to count documents: {e}")
            return 0

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("MetadataDB connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
