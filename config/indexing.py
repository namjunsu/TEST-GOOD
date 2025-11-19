"""
Indexing Configuration (Revised)
인덱싱 관련 설정을 중앙 관리하는 모듈
이 모듈은 app.config.settings를 사용합니다 (네임 충돌 방지)
"""

import logging
import os
from pathlib import Path
from typing import Dict, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1) settings 로드 + 폴백
# ---------------------------------------------------------
try:
    from app.config.settings import settings
    # 확장자 정규화: 소문자로 변환 + 공백 제거
    ALLOWED_EXTS: Set[str] = {ext.lower().strip() for ext in settings.ALLOWED_EXTS}
    DB_PATHS: Dict[str, str] = settings.DB_PATHS
    PROJECT_ROOT = Path(settings.PROJECT_ROOT)
    logger.info(f"[IndexConfig] settings 모듈 로드 완료 - ALLOWED_EXTS: {ALLOWED_EXTS}")
except Exception as e:
    logger.warning(f"[IndexConfig] settings 모듈 로드 실패, 폴백 사용: {e}")
    # 폴백: 기본값 사용
    ALLOWED_EXTS = {".pdf", ".txt"}
    DB_PATHS = {
        "metadata": "metadata.db",
        "everything_index": "everything_index.db",
        "file_index": "file_index.json"
    }
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    logger.info(f"[IndexConfig] 폴백 설정 사용 - PROJECT_ROOT: {PROJECT_ROOT}")

# ---------------------------------------------------------
# 2) 인덱싱 상태 플래그
# ---------------------------------------------------------
INDEX_FLAGS = {
    "is_active": True,  # 활성 문서만 포함
    "is_indexed": True,  # 인덱싱 완료 문서만 포함
    "is_duplicate": False,  # 중복 제외
    # 향후 확장 가능: is_ocr_done, is_text_extracted 등
}

# ---------------------------------------------------------
# 3) 파일 스캔 설정 (운영 환경 최적화)
# ---------------------------------------------------------
FILE_SCAN_SETTINGS = {
    "exclude_patterns": [
        # 임시 파일
        "*~", "*.tmp", "*.bak", "._*",
        # 시스템/개발 폴더
        "__pycache__", ".git", ".venv", ".pytest_cache",
        # 운영 폴더 제외
        "logs/*", "tmp/*", "var/index/*", "var/run/*",
        # 백업/아카이브
        "archive/*", "backups/*",
    ],
    "year_folders": True,  # year_* 폴더 포함 여부
    "max_depth": 5,  # 최대 디렉토리 깊이 제한
}


# ---------------------------------------------------------
# 4) 확장자 유효성 검사 (강화 버전)
# ---------------------------------------------------------
def is_allowed_extension(filename: str) -> bool:
    """
    파일 확장자가 허용된 것인지 확인
    - 파일명 끝 공백 제거
    - 대소문자 정규화
    - 다중 확장자 대응 (.backup.pdf → .pdf)
    """
    # 파일명 공백 제거
    filename = filename.strip()

    # 확장자 추출 및 소문자 변환
    ext = os.path.splitext(filename)[1].lower()

    # 단일 확장자가 이미 허용된 경우 즉시 반환
    if ext in ALLOWED_EXTS:
        return True

    # 다중 확장자 처리 (예: .backup.pdf → 마지막 유효 확장자 찾기)
    # 최대 3개까지만 체크하여 무한 루프 방지
    parts = filename.split('.')
    for i in range(len(parts) - 1, max(0, len(parts) - 4), -1):
        ext = f".{parts[i].lower()}"
        if ext in ALLOWED_EXTS:
            return True

    return False


def get_allowed_extensions_glob():
    """glob 패턴용 확장자 리스트 반환"""
    return [f"*{ext}" for ext in ALLOWED_EXTS]
