"""
로그 로테이션 및 보존 정책 설정
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime

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

def setup_rotating_logger(name: str, log_file: str, level=logging.INFO):
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
    
    return logger

def backup_manifest():
    """매니페스트 일자별 백업"""
    manifest_path = Path(os.getenv("DB_DIR", DEFAULT_DB_DIR)) / MANIFEST_FILENAME
    
    if manifest_path.exists():
        today = datetime.now().strftime(BACKUP_DATE_FORMAT)
        backup_dir = manifest_path.parent / BACKUP_DIR_NAME
        backup_dir.mkdir(exist_ok=True)
        
        backup_path = backup_dir / f"index_manifest_{today}.json"
        
        # 오늘 백업이 없으면 생성
        if not backup_path.exists():
            import shutil
            shutil.copy2(manifest_path, backup_path)
            
            # 보존 기간 이전 백업 정리
            import glob
            import time
            cutoff_time = time.time() - (LOG_RETENTION_DAYS * SECONDS_PER_DAY)
            
            for old_backup in glob.glob(str(backup_dir / "index_manifest_*.json")):
                if os.path.getmtime(old_backup) < cutoff_time:
                    os.remove(old_backup)