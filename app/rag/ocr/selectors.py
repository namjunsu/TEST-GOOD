#!/usr/bin/env python3
"""
OCR 대상 문서 선택기
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def select_by_text_length(
    db_path: str,
    threshold: int = 100,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """텍스트 길이 기준 선택 (force_ocr_update.py 로직)

    Args:
        db_path: DB 파일 경로
        threshold: 텍스트 길이 임계값 (기본 100자)
        limit: 최대 개수 제한

    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            id,
            path,
            filename,
            page_count,
            LENGTH(text_preview) as text_len
        FROM documents
        WHERE LENGTH(text_preview) < ?
        ORDER BY text_len ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query, (threshold,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    logger.info(f"선택 (text_length < {threshold}): {len(results)}개 문서")
    return results


def select_by_avg_per_page(
    db_path: str,
    threshold: int = 300,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """페이지당 평균 글자수 기준 선택 (reprocess_with_ocr.py 로직)

    Args:
        db_path: DB 파일 경로
        threshold: 페이지당 평균 글자수 임계값 (기본 300자)
        limit: 최대 개수 제한

    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            id,
            path,
            filename,
            page_count,
            LENGTH(text_preview) as text_len,
            CAST(LENGTH(text_preview) AS FLOAT) / NULLIF(page_count, 0) as avg_per_page
        FROM documents
        WHERE page_count > 0
          AND text_preview IS NOT NULL
          AND LENGTH(text_preview) > 0
          AND (CAST(LENGTH(text_preview) AS FLOAT) / page_count) < ?
        ORDER BY avg_per_page ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query, (threshold,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    logger.info(f"선택 (avg_per_page < {threshold}): {len(results)}개 문서")
    return results


def select_zero_text(
    db_path: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """0자 문서 선택 (batch_ocr_zero_chars.py 로직)

    Args:
        db_path: DB 파일 경로
        limit: 최대 개수 제한

    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT
            id,
            path,
            filename,
            page_count
        FROM documents
        WHERE filename LIKE '%.pdf'
          AND (text_preview IS NULL OR LENGTH(text_preview) = 0)
        ORDER BY filename
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    logger.info(f"선택 (zero_text): {len(results)}개 문서")
    return results


def select_from_file_list(
    file_list_path: str,
    db_path: str = "metadata.db"
) -> List[Dict[str, Any]]:
    """파일 목록에서 읽기 (batch_ocr_from_report.py 로직)

    Args:
        file_list_path: 파일 목록 경로 (한 줄에 하나씩)
        db_path: DB 파일 경로

    Returns:
        선택된 문서 목록
    """
    file_list = Path(file_list_path).read_text().strip().split("\n")
    file_list = [f.strip() for f in file_list if f.strip()]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    results = []
    for filename in file_list:
        cursor = conn.execute(
            "SELECT id, path, filename, page_count FROM documents WHERE filename = ?",
            (filename,)
        )
        row = cursor.fetchone()
        if row:
            results.append(dict(row))
        else:
            logger.warning(f"DB에 없는 파일: {filename}")

    conn.close()
    logger.info(f"선택 (file_list): {len(results)}개 문서")
    return results
