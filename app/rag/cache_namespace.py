#!/usr/bin/env python3
"""Cache Namespace Generator (enhanced)

인덱스/백엔드/라우터/검색 구성요소의 버전을 안정적으로 반영하여
캐시 네임스페이스를 생성한다.

2025-11-11 개선사항:
- mtime_ns + size로 충돌 방지
- 백엔드 타입 반영
- router 키워드, ExactMatch, FTS 서명 포함
- 환경변수 정규화
- 플랫폼 호환성 개선
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

# ---- 내부 유틸 --------------------------------------------------------------


def _norm_env(name: str, default: str = "") -> str:
    """환경변수 표준화: 앞뒤 공백 제거 + 소문자."""
    return os.getenv(name, default).strip().lower()


def _stat_signature(p: Path) -> str:
    """파일 버전 시그니처: mtime_ns + size (플랫폼 차이를 흡수)."""
    try:
        st = p.stat()
        # 일부 FS는 mtime_ns 미지원 → getattr로 폴백
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        size = st.st_size
        return f"{mtime_ns:x}.{size:x}"
    except Exception:
        return "no_file"


def _sha8(s: str) -> str:
    """문자열의 SHA256 해시 8자리 반환"""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


# ---- 공개 API ---------------------------------------------------------------

def get_index_version() -> str:
    """
    BM25(또는 기타) 인덱스 버전 문자열 반환.
    - 경로: BM25_INDEX_PATH (기본 var/index/bm25_index.pkl)
    - 시그니처: mtime_ns + size

    Returns:
        인덱스 버전 문자열 (예: "bm25_index.pkl:18a3f.1a2b")
    """
    index_path = Path(os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl"))
    if index_path.exists():
        sig = _stat_signature(index_path)
        return f"{index_path.name}:{sig}"
    return "noindex"


def _router_keywords_signature() -> str:
    """
    DOC_ANCHORED 라우터 키워드 파일 서명.
    존재하지 않으면 'nokey' 반환.

    Returns:
        키워드 파일 서명 (8자 해시)
    """
    cfg = Path(os.getenv("ROUTER_KEYWORDS_PATH", "config/router_keywords.yaml"))
    if not cfg.exists():
        return "nokey"
    try:
        data = cfg.read_bytes()
        return _sha8(f"{cfg.name}:{len(data)}:{hashlib.sha256(data).hexdigest()[:16]}")
    except Exception:
        return "nokey"


def _exactmatch_signature() -> str:
    """
    ExactMatch 리소스 버전 표식.
    - 환경변수 ENABLE_EXACT_MATCH=false → 'off'
    - 그렇지 않으면 모델/테이블 버전 힌트(환경변수) 연결

    Returns:
        ExactMatch 버전 표식
    """
    enabled = _norm_env("ENABLE_EXACT_MATCH", "true")
    if enabled not in ("1", "true", "yes"):
        return "off"
    # 사용 중인 테이블/리소스 버전이 있으면 반영 (없으면 'on')
    table_ver = os.getenv("EXACTMATCH_VERSION", "").strip()
    return table_ver or "on"


def _fts_signature() -> str:
    """
    FTS 데이터 소스 버전 표식 (선택).
    환경변수 DOCUMENTS_DB_PATH 지정 시 해당 파일 서명 포함.

    Returns:
        FTS DB 파일 서명
    """
    dbp = os.getenv("DOCUMENTS_DB_PATH", "").strip()
    if not dbp:
        return "notspecified"
    path = Path(dbp)
    return _stat_signature(path)


def get_retriever_config_hash() -> str:
    """
    Retriever 관련 핵심 구성을 정규화하여 8자 해시로 반환.
    - 검색 파라미터 + 백엔드 + 병렬 여부 등 포함
    - 라우터 키워드/ExactMatch/FTS 시그니처까지 포함

    Returns:
        구성 해시 (8자)
    """
    cfg = {
        "retrieve_topk": _norm_env("RETRIEVE_TOPK", "200"),
        "display_limit": _norm_env("DISPLAY_LIMIT", "20"),
        "snippet_max": _norm_env("SNIPPET_MAX_LENGTH", "3600"),
        "backend": _norm_env("RETRIEVER_BACKEND", "bm25"),
        "parallel": _norm_env("ENABLE_PARALLEL_SEARCH", "true"),
        "exact": _norm_env("ENABLE_EXACT_MATCH", "true"),
        "bm25_path": os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl").strip(),
        "router_sig": _router_keywords_signature(),
        "exact_sig": _exactmatch_signature(),
        "fts_sig": _fts_signature(),
    }
    # 안정적 직렬화
    config_str = "|".join(f"{k}={cfg[k]}" for k in sorted(cfg.keys()))
    return _sha8(config_str)


def current_retriever_namespace() -> str:
    """
    백엔드/인덱스 버전/구성 해시를 조합한 네임스페이스.

    Returns:
        네임스페이스 문자열 (예: 'backend:bm25|index:bm25_index.pkl:18a3f...|conf:a1b2c3d4')
    """
    backend = _norm_env("RETRIEVER_BACKEND", "bm25")
    index_ver = get_index_version()
    config_hash = get_retriever_config_hash()
    return f"backend:{backend}|index:{index_ver}|conf:{config_hash}"


def get_namespace_for_mode(mode: Optional[str] = None) -> str:
    """
    모드별 네임스페이스 확장.

    Args:
        mode: 검색 모드 (None, "chat", "doc_anchored" 등)

    Returns:
        모드를 포함한 네임스페이스
    """
    base = current_retriever_namespace()
    if mode:
        return f"{base}|mode:{mode}"
    return base
