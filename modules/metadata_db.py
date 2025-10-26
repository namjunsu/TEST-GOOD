#!/usr/bin/env python3
"""
Phase 1.2: 메타데이터 DB 구축
SQLite를 사용한 PDF 메타데이터 관리
"""

from app.core.logging import get_logger
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

logger = get_logger(__name__)

class MetadataDB:
    """PDF 메타데이터 SQLite DB 관리"""

    def __init__(self, db_path: str = "metadata.db"):
        self.db_path = db_path
        self.conn = None
        self.init_database()
        logger.info(f"MetadataDB 초기화: {db_path}")

    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        self.conn = sqlite3.connect(self.db_path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환

        # WAL 모드 설정 (동시 읽기 지원)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        logger.info(f"DB WAL mode enabled: {self.db_path}")

        # 메타데이터 테이블 생성
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                date TEXT,
                year TEXT,
                month TEXT,
                category TEXT,
                drafter TEXT,
                amount INTEGER,
                file_size INTEGER,
                page_count INTEGER,
                text_preview TEXT,
                keywords TEXT,  -- JSON array
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 인덱스 생성 (검색 성능 향상)
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON documents(year)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON documents(category)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON documents(date)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_filename ON documents(filename)')

        # 전문 검색을 위한 FTS 테이블 (Full-Text Search)
        self.conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(
                path UNINDEXED,
                title,
                text_preview,
                keywords,
                content=documents,
                content_rowid=id
            )
        ''')

        # FTS 트리거 설정 (자동 동기화)
        self.conn.execute('''
            CREATE TRIGGER IF NOT EXISTS documents_ai
            AFTER INSERT ON documents
            BEGIN
                INSERT INTO documents_fts(rowid, path, title, text_preview, keywords)
                VALUES (new.id, new.path, new.title, new.text_preview, new.keywords);
            END
        ''')

        self.conn.execute('''
            CREATE TRIGGER IF NOT EXISTS documents_au
            AFTER UPDATE ON documents
            BEGIN
                UPDATE documents_fts
                SET title = new.title,
                    text_preview = new.text_preview,
                    keywords = new.keywords
                WHERE rowid = new.id;
            END
        ''')

        self.conn.execute('''
            CREATE TRIGGER IF NOT EXISTS documents_ad
            AFTER DELETE ON documents
            BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        ''')

        self.conn.commit()

    def add_document(self, metadata: Dict[str, Any]) -> int:
        """문서 메타데이터 추가"""
        try:
            # 키워드를 JSON 문자열로 변환
            keywords = metadata.get('keywords', [])
            if isinstance(keywords, list):
                keywords = json.dumps(keywords, ensure_ascii=False)

            cursor = self.conn.execute('''
                INSERT OR REPLACE INTO documents (
                    path, filename, title, date, year, month, category,
                    drafter, amount, file_size, page_count, text_preview, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(metadata.get('path', '')),
                metadata.get('filename', ''),
                metadata.get('title', ''),
                metadata.get('date', ''),
                metadata.get('year', ''),
                metadata.get('month', ''),
                metadata.get('category', ''),
                metadata.get('drafter', ''),
                metadata.get('amount', 0),
                metadata.get('file_size', 0),
                metadata.get('page_count', 0),
                metadata.get('text_preview', ''),
                keywords
            ))

            self.conn.commit()
            return cursor.lastrowid

        except Exception as e:
            logger.error(f"문서 추가 실패: {e}")
            self.conn.rollback()
            return -1

    def search_by_year(self, year: str) -> List[Dict[str, Any]]:
        """연도별 검색"""
        cursor = self.conn.execute(
            'SELECT * FROM documents WHERE year = ? ORDER BY date DESC',
            (year,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_by_category(self, category: str) -> List[Dict[str, Any]]:
        """카테고리별 검색"""
        cursor = self.conn.execute(
            'SELECT * FROM documents WHERE category LIKE ? ORDER BY date DESC',
            (f'%{category}%',)
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """키워드 검색 (FTS 사용)"""
        cursor = self.conn.execute('''
            SELECT d.* FROM documents d
            JOIN documents_fts f ON d.id = f.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT 20
        ''', (keyword,))
        return [dict(row) for row in cursor.fetchall()]

    def search_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """날짜 범위 검색"""
        cursor = self.conn.execute(
            'SELECT * FROM documents WHERE date BETWEEN ? AND ? ORDER BY date DESC',
            (start_date, end_date)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_document_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """경로로 문서 조회"""
        cursor = self.conn.execute(
            'SELECT * FROM documents WHERE path = ?',
            (str(path),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_document(self, filename: str) -> Optional[Dict[str, Any]]:
        """파일명으로 문서 조회 (perfect_rag.py 호환용)"""
        # 파일명만으로 검색
        cursor = self.conn.execute(
            'SELECT * FROM documents WHERE filename = ? LIMIT 1',
            (filename,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_document(self, filename: str, **kwargs):
        """문서 메타데이터 간편 업데이트 (perfect_rag.py 호환용)"""
        # 먼저 문서 찾기
        doc = self.get_document(filename)

        if not doc:
            # 새 문서면 추가
            metadata = {'filename': filename}
            metadata.update(kwargs)
            return self.add_document(metadata)

        # 기존 문서 업데이트
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['title', 'date', 'year', 'month', 'category', 'drafter',
                      'amount', 'file_size', 'page_count', 'text_preview', 'keywords']:
                fields.append(f"{key} = ?")
                if key == 'keywords' and isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                values.append(value)

        if fields:
            values.append(doc['id'])
            query = f"UPDATE documents SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            self.conn.execute(query, values)
            self.conn.commit()

    def update_text_preview(self, path: str, text_preview: str):
        """텍스트 미리보기 업데이트"""
        self.conn.execute(
            'UPDATE documents SET text_preview = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?',
            (text_preview[:1000], str(path))  # 최대 1000자
        )
        self.conn.commit()

    def get_statistics(self) -> Dict[str, Any]:
        """DB 통계 정보"""
        cursor = self.conn.execute('SELECT COUNT(*) as total FROM documents')
        total = cursor.fetchone()['total']

        cursor = self.conn.execute('''
            SELECT year, COUNT(*) as count
            FROM documents
            GROUP BY year
            ORDER BY year DESC
        ''')
        by_year = {row['year']: row['count'] for row in cursor.fetchall()}

        cursor = self.conn.execute('''
            SELECT category, COUNT(*) as count
            FROM documents
            GROUP BY category
            ORDER BY count DESC
        ''')
        by_category = {row['category']: row['count'] for row in cursor.fetchall()}

        return {
            'total_documents': total,
            'by_year': by_year,
            'by_category': by_category
        }

    def rebuild_fts_index(self):
        """FTS 인덱스 재구축"""
        self.conn.execute('INSERT INTO documents_fts(documents_fts) VALUES("rebuild")')
        self.conn.commit()
        logger.info("FTS 인덱스 재구축 완료")

    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def extract_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """파일명에서 메타데이터 추출"""
    metadata = {
        'filename': filename,
        'title': '',
        'date': '',
        'year': '',
        'month': '',
        'category': '',
        'drafter': ''
    }

    # 날짜 추출 (YYYY-MM-DD or YYYY-MM or YYYY)
    date_match = re.search(r'(\d{4})[-_]?(\d{2})?[-_]?(\d{2})?', filename)
    if date_match:
        year = date_match.group(1)
        month = date_match.group(2) or ''
        day = date_match.group(3) or ''

        metadata['year'] = year
        metadata['month'] = month

        if day:
            metadata['date'] = f"{year}-{month}-{day}"
        elif month:
            metadata['date'] = f"{year}-{month}"
        else:
            metadata['date'] = year

    # 카테고리 추출
    categories = ['구매', '수리', '보수', '교체', '폐기', '검토', '기술', '소모품']
    for cat in categories:
        if cat in filename:
            metadata['category'] = cat
            break

    # 제목 추출 (언더스코어를 공백으로)
    title_part = filename.replace('.pdf', '').replace('.PDF', '')
    # 날짜 부분 제거
    title_part = re.sub(r'\d{4}[-_]?\d{2}[-_]?\d{2}[-_]?', '', title_part)
    title_part = title_part.replace('_', ' ').strip()
    metadata['title'] = title_part

    return metadata