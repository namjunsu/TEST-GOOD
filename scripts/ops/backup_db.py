#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
SQLite 메타데이터 DB 백업 스크립트

- metadata.db를 안전하게 백업 디렉터리로 복사
- SQLite backup API 사용 (파일 단순 cp보다 안전)
- 기본 보존 정책: 최신 7개만 유지
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# === 설정 영역 ===
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # /home/wnstn4647/AI-CHAT
DB_PATH = PROJECT_ROOT / "metadata.db"              # DB 위치
BACKUP_DIR = PROJECT_ROOT / "backups" / "db"        # 백업 저장 위치
RETENTION_COUNT = 7                                 # 보존 개수

def ensure_dirs() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def backup_db() -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없음: {DB_PATH}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"metadata.db.{timestamp}.bak"

    # SQLite 백업 API 사용
    src_conn = sqlite3.connect(str(DB_PATH))
    dst_conn = sqlite3.connect(str(backup_path))

    try:
        # WAL 모드 등 설정은 원본 DB에 이미 적용되어 있다고 가정
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    return backup_path

def cleanup_old_backups() -> None:
    backups = sorted(BACKUP_DIR.glob("metadata.db.*.bak"))
    if len(backups) <= RETENTION_COUNT:
        return

    # 오래된 것부터 삭제
    to_delete = backups[:-RETENTION_COUNT]
    for path in to_delete:
        try:
            path.unlink()
            print(f"[INFO] 오래된 백업 삭제: {path.name}")
        except Exception as e:
            print(f"[WARN] 백업 삭제 실패: {path} ({e})")

def main() -> None:
    ensure_dirs()
    backup_path = backup_db()
    print(f"[INFO] DB 백업 완료: {backup_path}")
    cleanup_old_backups()

if __name__ == "__main__":
    main()
