"""메타데이터 데이터베이스 모듈

SQLite 기반 메타데이터 관리:
- WAL 모드 (동시 읽기 지원)
- Read/Write 분리
- Connection pool
"""

from app.data.metadata.db import MetadataDB

__all__ = ["MetadataDB"]
