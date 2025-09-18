#!/usr/bin/env python3
"""
문서 메타데이터 캐시 시스템
PDF 파일 메타데이터를 SQLite에 저장하여 빠른 로딩 지원
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
import hashlib
from typing import Dict, List, Optional
import pandas as pd

class DocumentMetadataCache:
    def __init__(self, cache_dir: str = "rag_system/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "document_metadata.db"
        self._init_db()

    def _init_db(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_metadata (
                    filename TEXT PRIMARY KEY,
                    title TEXT,
                    category TEXT,
                    date TEXT,
                    year TEXT,
                    month TEXT,
                    drafter TEXT,
                    file_size INTEGER,
                    file_modified REAL,
                    file_hash TEXT,
                    extracted_at REAL,
                    metadata_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON document_metadata(year)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON document_metadata(category)")
            conn.commit()

    def get_file_hash(self, file_path: Path) -> str:
        """파일의 해시값 계산 (크기와 수정시간 기반)"""
        stat = file_path.stat()
        hash_string = f"{file_path.name}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_string.encode()).hexdigest()

    def is_cached(self, file_path: Path) -> bool:
        """파일이 캐시되어 있고 최신 상태인지 확인"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT file_hash FROM document_metadata WHERE filename = ?",
                (file_path.name,)
            )
            row = cursor.fetchone()
            if row:
                cached_hash = row[0]
                current_hash = self.get_file_hash(file_path)
                return cached_hash == current_hash
        return False

    def get_metadata(self, file_path: Path) -> Optional[Dict]:
        """캐시된 메타데이터 가져오기"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM document_metadata WHERE filename = ?",
                (file_path.name,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'filename': row[0],
                    'title': row[1],
                    'category': row[2],
                    'date': row[3],
                    'year': row[4],
                    'month': row[5],
                    'drafter': row[6],
                    'file_size': row[7],
                    'modified': datetime.fromtimestamp(row[8])
                }
        return None

    def save_metadata(self, file_path: Path, metadata: Dict):
        """메타데이터 캐시에 저장"""
        file_hash = self.get_file_hash(file_path)
        stat = file_path.stat()

        with sqlite3.connect(self.db_path) as conn:
            # datetime 객체를 문자열로 변환
            metadata_copy = metadata.copy()
            if 'modified' in metadata_copy and isinstance(metadata_copy['modified'], datetime):
                metadata_copy['modified'] = metadata_copy['modified'].isoformat()

            conn.execute("""
                INSERT OR REPLACE INTO document_metadata
                (filename, title, category, date, year, month, drafter,
                 file_size, file_modified, file_hash, extracted_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_path.name,
                metadata.get('title', ''),
                metadata.get('category', '기타'),
                metadata.get('date', ''),
                metadata.get('year', ''),
                metadata.get('month', ''),
                metadata.get('drafter', '미상'),
                stat.st_size,
                stat.st_mtime,
                file_hash,
                datetime.now().timestamp(),
                json.dumps(metadata_copy, ensure_ascii=False, default=str)
            ))
            conn.commit()

    def get_all_cached(self) -> pd.DataFrame:
        """모든 캐시된 메타데이터 가져오기"""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query("""
                SELECT filename, title, category, date, year, month, drafter, file_modified
                FROM document_metadata
                ORDER BY date DESC
            """, conn)

            if not df.empty:
                df['modified'] = pd.to_datetime(df['file_modified'], unit='s')
                df = df.drop('file_modified', axis=1)

            return df

    def clear_cache(self):
        """캐시 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM document_metadata")
            conn.commit()

    def get_stats(self) -> Dict:
        """캐시 통계"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM document_metadata")
            total = cursor.fetchone()[0]

            cursor = conn.execute("""
                SELECT category, COUNT(*) FROM document_metadata
                GROUP BY category
            """)
            by_category = dict(cursor.fetchall())

            return {
                'total_cached': total,
                'by_category': by_category
            }