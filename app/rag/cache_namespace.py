#!/usr/bin/env python3
"""Cache Namespace Generator

인덱스 버전과 retriever 설정을 조합하여 캐시 네임스페이스 생성.
인덱스 로테이션이나 설정 변경 시 자동으로 캐시 무효화.
"""
import hashlib
import os
from pathlib import Path
from typing import Optional


def get_index_version() -> str:
    """BM25 인덱스 버전 가져오기

    Returns:
        인덱스 버전 문자열 (예: "v20251111_6550db")
    """
    try:
        # BM25 인덱스 파일 경로
        index_path = Path("var/index/bm25_index.pkl")
        if index_path.exists():
            # mtime을 버전으로 사용
            mtime = index_path.stat().st_mtime
            return f"v{int(mtime)}"
        else:
            return "v_noindex"
    except Exception:
        return "v_unknown"


def get_retriever_config_hash() -> str:
    """Retriever 설정 해시 생성

    주요 설정값들을 조합하여 해시 생성.
    설정 변경 시 자동으로 캐시 무효화.

    Returns:
        설정 해시 (8자)
    """
    # 주요 설정값들
    config_tuple = (
        os.getenv("RETRIEVE_TOPK", "200"),
        os.getenv("DISPLAY_LIMIT", "20"),
        os.getenv("SNIPPET_MAX_LENGTH", "3600"),
        os.getenv("ENABLE_EXACT_MATCH", "true"),
        os.getenv("RETRIEVER_BACKEND", "bm25"),
    )

    config_str = "|".join(str(v) for v in config_tuple)
    return hashlib.sha256(config_str.encode()).hexdigest()[:8]


def current_retriever_namespace() -> str:
    """현재 retriever 네임스페이스 생성

    인덱스 버전과 설정 해시를 조합.

    Returns:
        네임스페이스 문자열 (예: "bm25:v1699876543|conf:a1b2c3d4")
    """
    index_ver = get_index_version()
    config_hash = get_retriever_config_hash()
    return f"bm25:{index_ver}|conf:{config_hash}"


def get_namespace_for_mode(mode: Optional[str] = None) -> str:
    """모드별 네임스페이스 생성

    Args:
        mode: 검색 모드 (None, "chat", "doc_anchored" 등)

    Returns:
        모드를 포함한 네임스페이스
    """
    base = current_retriever_namespace()
    if mode:
        return f"{base}|mode:{mode}"
    return base
