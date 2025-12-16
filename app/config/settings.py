"""
프로젝트 통합 설정 모듈
절대 경로 임포트 권장: from app.config.settings import settings, ensure_dirs
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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


def _parse_exts(env_key: str, default: str = ".pdf,.txt") -> set[str]:
    raw = os.getenv(env_key, default)
    out: set[str] = set()
    for token in raw.split(","):
        t = token.strip().lower()
        if not t:
            continue
        if not t.startswith("."):
            t = "." + t
        out.add(t)
    return out


def _validate_api_key(env_key: str = "API_KEY", default: str = "") -> str:
    """API 키 검증 (보안 강화).

    Returns:
        검증된 API 키 문자열

    Warning:
        - 32자 미만이면 경고 로그 출력
        - 기본값('CHANGE-ME' 포함)이면 경고 로그 출력
    """
    import logging
    logger = logging.getLogger(__name__)

    key = os.getenv(env_key, default)

    if not key:
        logger.warning(f"[SECURITY] {env_key} 환경변수가 설정되지 않았습니다.")
        return key

    if "CHANGE-ME" in key or key == "broadcast-tech-rag-2025":
        logger.warning(f"[SECURITY] {env_key}가 기본값입니다. 프로덕션에서는 강력한 키로 변경하세요.")

    if len(key) < 32:
        logger.warning(f"[SECURITY] {env_key} 길이가 {len(key)}자입니다. 32자 이상을 권장합니다.")

    return key


# ---------- 설정 데이터클래스 ----------
@dataclass(frozen=True)
class Settings:
    PROJECT_ROOT: Path
    DOCS_DIR: Path
    DATA_DIR: Path
    INCOMING_DIR: Path
    LOG_DIR: Path

    DB_PATHS: dict[str, str]

    ALLOWED_EXTS: set[str]

    STREAMLIT_HOST: str
    STREAMLIT_PORT: int

    RAG_MODEL: str
    EMBEDDING_MODEL: str

    # RAG 인덱스 경로 (다중 후보)
    BM25_CANDIDATES: list[Path]
    FAISS_CANDIDATES: list[Path]

    # RAG 검색/스코어 설정
    RAG_MIN_SCORE: float
    RAG_MIN_SCORE_POLICY: str  # "normalized" or "absolute"
    BM25_MIN_ABS: float
    VEC_MIN_ABS: float
    MIN_KEYWORD_COVERAGE: int

    # LLM 토큰 설정
    LLM_MAX_TOKENS_DETAILED: int
    LLM_MAX_TOKENS_SECTION: int
    LLM_MAX_TOKENS_SUMMARY: int
    LLM_MAX_TOKENS_QA: int

    # 문서 처리 설정
    EXTRACTED_DIR: Path
    DOC_ANCHOR_MIN_SNIPPET: int

    # 디버그/진단
    DIAG_RAG: bool
    DIAG_LOG_LEVEL: str

    # 런타임 모드 설정
    MODE: str  # "AUTO", "SEARCH", "DOCUMENT" 등
    USE_V2_RETRIEVER: bool
    MODEL_PATH: str

    # 보안 설정
    API_KEY: str

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
_BM25_CANDIDATES: list[Path] = []
if os.getenv("BM25_INDEX_PATH"):
    _BM25_CANDIDATES.append(_as_path("BM25_INDEX_PATH", _PROJECT_ROOT / "var/index/bm25_index.pkl"))
else:
    _BM25_CANDIDATES.append(_PROJECT_ROOT / "var/index/bm25_index.pkl")
# rag_system/db/ 경로는 제거됨 (var/index/가 기본)

_FAISS_CANDIDATES: list[Path] = []
if os.getenv("FAISS_INDEX_PATH"):
    _FAISS_CANDIDATES.append(_as_path("FAISS_INDEX_PATH", _PROJECT_ROOT / "var/index/faiss.index"))
else:
    _FAISS_CANDIDATES.append(_PROJECT_ROOT / "var/index/faiss.index")
# rag_system/db/ 경로는 제거됨 (var/index/가 기본)

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
    # RAG 검색/스코어 설정
    RAG_MIN_SCORE=float(os.getenv("RAG_MIN_SCORE", "0.35")),
    RAG_MIN_SCORE_POLICY=os.getenv("RAG_MIN_SCORE_POLICY", "normalized"),
    BM25_MIN_ABS=float(os.getenv("BM25_MIN_ABS", "5.0")),
    VEC_MIN_ABS=float(os.getenv("VEC_MIN_ABS", "0.25")),
    MIN_KEYWORD_COVERAGE=int(os.getenv("MIN_KEYWORD_COVERAGE", "2")),
    # LLM 토큰 설정
    LLM_MAX_TOKENS_DETAILED=int(os.getenv("LLM_MAX_TOKENS_DETAILED", "3072")),  # 1500→3072: 상세 모드 확장
    LLM_MAX_TOKENS_SECTION=int(os.getenv("LLM_MAX_TOKENS_SECTION", "900")),
    LLM_MAX_TOKENS_SUMMARY=int(os.getenv("LLM_MAX_TOKENS_SUMMARY", "2048")),  # 600→2048: JSON 요약 출력용
    LLM_MAX_TOKENS_QA=int(os.getenv("LLM_MAX_TOKENS_QA", "800")),
    # 문서 처리 설정
    EXTRACTED_DIR=_as_path("EXTRACTED_DIR", _DATA_DIR / "extracted"),
    DOC_ANCHOR_MIN_SNIPPET=int(os.getenv("DOC_ANCHOR_MIN_SNIPPET", "1200")),
    # 디버그/진단
    DIAG_RAG=os.getenv("DIAG_RAG", "false").lower() == "true",
    DIAG_LOG_LEVEL=os.getenv("DIAG_LOG_LEVEL", "INFO").upper(),
    # 런타임 모드 설정
    MODE=os.getenv("MODE", "AUTO").upper(),
    USE_V2_RETRIEVER=os.getenv("USE_V2_RETRIEVER", "false").lower() == "true",
    MODEL_PATH=os.getenv("MODEL_PATH", "./models/ggml-model-Q4_K_M.gguf"),
    # 보안 설정
    API_KEY=_validate_api_key("API_KEY"),
)

__all__ = ["ensure_dirs", "settings"]


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
