"""
프로젝트 통합 설정 모듈
네임 충돌 방지를 위해 절대 경로로 임포트: from app.config.settings import ...
"""

from pathlib import Path
import os

# .env 파일 로드 (선택적)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # .env 파일이 환경 변수를 override하도록 설정
except ImportError:
    pass  # dotenv가 없으면 환경변수에서만 읽음

# 프로젝트 루트 추정 (settings.py → config → app → <root>)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 문서 루트: 환경변수 우선, 없으면 기본값
DOCS_DIR = Path(os.getenv("DOCS_DIR", PROJECT_ROOT / "docs"))

# 데이터 디렉토리
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))

# incoming 디렉토리
INCOMING_DIR = Path(os.getenv("INCOMING_DIR", PROJECT_ROOT / "incoming"))

# 허용 확장자 (정책에 따라 ".pdf"만 둘지, ".txt" 포함할지 결정)
ALLOWED_EXTS = set(
    ext.strip().lower()
    for ext in os.getenv("ALLOWED_EXTS", ".pdf,.txt").split(",")
    if ext.strip()
)

# 데이터베이스 경로
DB_PATHS = {
    "metadata": str(PROJECT_ROOT / "metadata.db"),
    "everything_index": str(PROJECT_ROOT / "everything_index.db"),
    "file_index": str(PROJECT_ROOT / "file_index.json")
}

# 로그 디렉토리
LOG_DIR = Path(os.getenv("LOG_DIR", PROJECT_ROOT / "logs"))

# Streamlit 설정
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
STREAMLIT_HOST = os.getenv("STREAMLIT_HOST", "localhost")

# RAG 설정
RAG_MODEL = os.getenv("RAG_MODEL", "Local LLM")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# 디렉토리 자동 생성
for directory in [DOCS_DIR, DATA_DIR, INCOMING_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)