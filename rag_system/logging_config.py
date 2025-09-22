"""
로그 로테이션 및 보존 정책 설정
"""

import logging
import logging.handlers
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 로깅 설정 상수
LOG_RETENTION_DAYS = 90  # 로그 보존 기간 (일)
LOG_ROTATION_TIME = 'midnight'  # 로그 로테이션 시간
LOG_ROTATION_INTERVAL = 1  # 로테이션 간격
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_ENCODING = 'utf-8'

# 백업 설정 상수
DEFAULT_DB_DIR = "db"
MANIFEST_FILENAME = "index_manifest.json"
BACKUP_DIR_NAME = "backups"
BACKUP_DATE_FORMAT = "%Y%m%d"
SECONDS_PER_DAY = 24 * 60 * 60

# 로깅 통계
_logger_stats: Dict[str, Dict[str, Any]] = {}

def setup_rotating_logger(name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
    """일자별 로테이션 로거 설정"""
    
    # 로그 디렉터리 생성
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 일자별 로테이션 핸들러
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when=LOG_ROTATION_TIME,
        interval=LOG_ROTATION_INTERVAL,
        backupCount=LOG_RETENTION_DAYS,
        encoding=LOG_ENCODING
    )
    
    # 로그 포맷
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)
    
    # 핸들러 추가
    logger.addHandler(handler)

    # 콘솔 핸들러도 추가
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 통계 초기화
    _logger_stats[name] = {
        'created_at': datetime.now(),
        'log_file': str(log_file),
        'level': logging.getLevelName(level),
        'rotation_count': 0,
        'last_rotation': None
    }

    return logger

def get_logger_stats() -> Dict[str, Dict[str, Any]]:
    """로거 통계 반환

    Returns:
        각 로거의 통계 정보 딕셔너리
    """
    stats = {}
    for name, logger_stat in _logger_stats.items():
        stats[name] = {
            **logger_stat,
            'uptime_seconds': (datetime.now() - logger_stat['created_at']).total_seconds() if logger_stat.get('created_at') else 0
        }
    return stats

def update_rotation_stats(name: str) -> None:
    """로테이션 통계 업데이트

    Args:
        name: 로거 이름
    """
    if name in _logger_stats:
        _logger_stats[name]['rotation_count'] += 1
        _logger_stats[name]['last_rotation'] = datetime.now()

def backup_manifest() -> bool:
    """매니페스트 일자별 백업

    Returns:
        백업 성공 여부
    """
    try:
        manifest_path = Path(os.getenv("DB_DIR", DEFAULT_DB_DIR)) / MANIFEST_FILENAME

        if not manifest_path.exists():
            return False

        today = datetime.now().strftime(BACKUP_DATE_FORMAT)
        backup_dir = manifest_path.parent / BACKUP_DIR_NAME
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_dir / f"index_manifest_{today}.json"

        # 오늘 백업이 없으면 생성
        if not backup_path.exists():
            import shutil
            shutil.copy2(manifest_path, backup_path)

            # 로그에 백업 기록
            logger = logging.getLogger(__name__)
            logger.info(f"매니페스트 백업 생성: {backup_path}")

            # 보존 기간 이전 백업 정리
            cleanup_old_backups(backup_dir)

        return True

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"매니페스트 백업 실패: {e}")
        return False

def cleanup_old_backups(backup_dir: Path) -> int:
    """오래된 백업 파일 정리

    Args:
        backup_dir: 백업 디렉토리 경로

    Returns:
        삭제된 파일 개수
    """
    import glob

    deleted_count = 0
    cutoff_time = time.time() - (LOG_RETENTION_DAYS * SECONDS_PER_DAY)

    try:
        for old_backup in glob.glob(str(backup_dir / "index_manifest_*.json")):
            if os.path.getmtime(old_backup) < cutoff_time:
                os.remove(old_backup)
                deleted_count += 1

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"백업 파일 정리 중 오류: {e}")

    return deleted_count