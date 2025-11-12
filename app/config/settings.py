"""
프로젝트 통합 설정 모듈
절대 경로 임포트 권장: from app.config.settings import settings, ensure_dirs
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
from typing import Set, Dict, List

# .env 로드 (선택)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass


# ---------- 내부 유틸 ----------
def _find_project_root(candidates: tuple[str, ...] = ("pyproject.toml", ".git", "setup.cfg")) -> Path:
    """상위로 올라가며 루트 마커를 탐색. 실패 시 현재 파일 기준 2단계 상위 → CWD 순 폴백."""
    p = Path(__file__).resolve()
    for parent in [*p.parents]:
        if any((parent / m).exists() for m in candidates):
            return parent
    # 기존 로직 폴백
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd().resolve()


def _as_path(env_key: str, default: Path) -> Path:
    v = os.getenv(env_key)
    return Path(v).expanduser().resolve() if v else default.expanduser().resolve()


def _parse_port(env_key: str, default: int = 8501) -> int:
    v = os.getenv(env_key)
    if not v:
        return default
    try:
        port = int(v)
        if 1 <= port <= 65535:
            return port
    except ValueError:
        pass
    return default


def _parse_host(env_key: str, default: str = "localhost") -> str:
    v = os.getenv(env_key, default).strip()
    return v or default


def _parse_exts(env_key: str, default: str = ".pdf,.txt") -> Set[str]:
    raw = os.getenv(env_key, default)
    out: Set[str] = set()
    for token in raw.split(","):
        t = token.strip().lower()
        if not t:
            continue
        if not t.startswith("."):
            t = "." + t
        out.add(t)
    return out


# ---------- 설정 데이터클래스 ----------
@dataclass(frozen=True)
class Settings:
    PROJECT_ROOT: Path
    DOCS_DIR: Path
    DATA_DIR: Path
    INCOMING_DIR: Path
    LOG_DIR: Path

    DB_PATHS: Dict[str, str]

    ALLOWED_EXTS: Set[str]

    STREAMLIT_HOST: str
    STREAMLIT_PORT: int

    RAG_MODEL: str
    EMBEDDING_MODEL: str

    # RAG 인덱스 경로 (다중 후보)
    BM25_CANDIDATES: List[Path]
    FAISS_CANDIDATES: List[Path]

    def is_allowed_file(self, path: Path) -> bool:
        """허용 확장자 정책 검사 (대소문자 무시)."""
        return path.suffix.lower() in self.ALLOWED_EXTS


# ---------- 인스턴스 생성 ----------
_PROJECT_ROOT = _find_project_root()

_DOCS_DIR = _as_path("DOCS_DIR", _PROJECT_ROOT / "docs")
_DATA_DIR = _as_path("DATA_DIR", _PROJECT_ROOT / "data")
_INCOMING_DIR = _as_path("INCOMING_DIR", _PROJECT_ROOT / "incoming")
_LOG_DIR = _as_path("LOG_DIR", _PROJECT_ROOT / "logs")

_DB_METADATA = str(_as_path("DB_METADATA_PATH", _PROJECT_ROOT / "metadata.db"))
_DB_EVERYTHING = str(_as_path("DB_EVERYTHING_PATH", _PROJECT_ROOT / "everything_index.db"))
_DB_FILE_INDEX = str(_as_path("DB_FILE_INDEX_PATH", _PROJECT_ROOT / "file_index.json"))

# RAG 인덱스 경로 (다중 후보, 중복 제거)
_BM25_CANDIDATES: List[Path] = []
if os.getenv("BM25_INDEX_PATH"):
    _BM25_CANDIDATES.append(_as_path("BM25_INDEX_PATH", _PROJECT_ROOT / "var/index/bm25_index.pkl"))
else:
    _BM25_CANDIDATES.append(_PROJECT_ROOT / "var/index/bm25_index.pkl")
_BM25_CANDIDATES.append(_PROJECT_ROOT / "rag_system/db/bm25_index.pkl")

_FAISS_CANDIDATES: List[Path] = []
if os.getenv("FAISS_INDEX_PATH"):
    _FAISS_CANDIDATES.append(_as_path("FAISS_INDEX_PATH", _PROJECT_ROOT / "var/index/faiss.index"))
else:
    _FAISS_CANDIDATES.append(_PROJECT_ROOT / "var/index/faiss.index")
_FAISS_CANDIDATES.append(_PROJECT_ROOT / "rag_system/db/faiss.index")

settings = Settings(
    PROJECT_ROOT=_PROJECT_ROOT,
    DOCS_DIR=_DOCS_DIR,
    DATA_DIR=_DATA_DIR,
    INCOMING_DIR=_INCOMING_DIR,
    LOG_DIR=_LOG_DIR,
    DB_PATHS={
        "metadata": _DB_METADATA,
        "everything_index": _DB_EVERYTHING,
        "file_index": _DB_FILE_INDEX,
    },
    ALLOWED_EXTS=_parse_exts("ALLOWED_EXTS", ".pdf,.txt"),
    STREAMLIT_HOST=_parse_host("STREAMLIT_HOST", "localhost"),
    STREAMLIT_PORT=_parse_port("STREAMLIT_PORT", 8501),
    RAG_MODEL=os.getenv("RAG_MODEL", "Local LLM"),
    EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    BM25_CANDIDATES=_BM25_CANDIDATES,
    FAISS_CANDIDATES=_FAISS_CANDIDATES,
)

__all__ = ["settings", "ensure_dirs"]


# ---------- 부작용 없는 디렉터리 준비 함수 ----------
def ensure_dirs(create_missing: bool = True) -> None:
    """
    필요한 디렉터리를 명시적으로 생성.
    임포트 시 부작용을 방지하기 위해 호출식으로 제공.
    """
    dirs = [settings.DOCS_DIR, settings.DATA_DIR, settings.INCOMING_DIR, settings.LOG_DIR]
    if create_missing:
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
