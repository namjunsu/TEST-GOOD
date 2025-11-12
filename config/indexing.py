"""
Indexing Configuration
인덱싱 관련 설정을 중앙 관리하는 모듈
이 모듈은 app.config.settings를 사용합니다 (네임 충돌 방지)
"""

# app.config.settings에서 설정을 가져옵니다
try:
    from app.config.settings import settings
    ALLOWED_EXTS = settings.ALLOWED_EXTS
    DB_PATHS = settings.DB_PATHS
    PROJECT_ROOT = settings.PROJECT_ROOT
except ImportError:
    # 폴백: 기본값 사용
    ALLOWED_EXTS = {".pdf", ".txt"}
    DB_PATHS = {
        "metadata": "metadata.db",
        "everything_index": "everything_index.db",
        "file_index": "file_index.json"
    }
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 인덱싱 상태 플래그
INDEX_FLAGS = {
    "is_active": True,  # 활성 문서만 포함
    "is_indexed": True,  # 인덱싱 완료 문서만 포함
    "is_duplicate": False  # 중복 제외
}

# 파일 스캔 설정
FILE_SCAN_SETTINGS = {
    "exclude_patterns": ["*~", "*.tmp", "*.bak", "._*"],
    "year_folders": True  # year_* 폴더 포함 여부
}

def is_allowed_extension(filename: str) -> bool:
    """파일 확장자가 허용된 것인지 확인"""
    import os
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTS

def get_allowed_extensions_glob():
    """glob 패턴용 확장자 리스트 반환"""
    return [f"*{ext}" for ext in ALLOWED_EXTS]