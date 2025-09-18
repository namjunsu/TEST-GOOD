#!/usr/bin/env python3
"""
경량 문서 관리자
문서가 많아져도 빠른 로딩을 위한 최적화된 관리자
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import sqlite3

class LightweightDocumentManager:
    """문서 메타데이터만 관리하는 경량 매니저"""

    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = Path(docs_dir)
        self.db_path = Path("rag_system/cache/documents.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # DB 연결
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_database()

        # 파일 인덱스만 메모리에 (가벼움)
        self.file_index = {}
        self._build_index()

    def _init_database(self):
        """데이터베이스 초기화"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                filename TEXT PRIMARY KEY,
                path TEXT,
                year INTEGER,
                month INTEGER,
                doc_type TEXT,
                size INTEGER,
                modified REAL,
                indexed_at REAL,
                full_text TEXT
            )
        ''')

        # 인덱스 생성 (빠른 검색용)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_year ON documents(year)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type ON documents(doc_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON documents(filename)')

        self.conn.commit()

    def _build_index(self):
        """빠른 파일 인덱스 구축 (내용 X, 목록만)"""
        start = time.time()

        pdf_count = 0
        txt_count = 0

        for pdf_file in self.docs_dir.glob("*.pdf"):
            self.file_index[pdf_file.name] = {
                'path': str(pdf_file),
                'size': pdf_file.stat().st_size,
                'modified': pdf_file.stat().st_mtime
            }
            pdf_count += 1

        for txt_file in self.docs_dir.glob("*.txt"):
            self.file_index[txt_file.name] = {
                'path': str(txt_file),
                'size': txt_file.stat().st_size,
                'modified': txt_file.stat().st_mtime
            }
            txt_count += 1

        elapsed = time.time() - start
        print(f"⚡ 인덱스 구축: {pdf_count} PDF, {txt_count} TXT ({elapsed:.3f}초)")

    def get_document_list(self, page: int = 1, per_page: int = 20,
                         filter_year: Optional[int] = None,
                         filter_type: Optional[str] = None) -> Dict:
        """페이지네이션된 문서 목록 반환"""

        # SQL 쿼리 구성
        query = "SELECT filename, year, doc_type FROM documents WHERE 1=1"
        params = []

        if filter_year:
            query += " AND year = ?"
            params.append(filter_year)

        if filter_type:
            query += " AND doc_type = ?"
            params.append(filter_type)

        query += " ORDER BY filename"
        query += f" LIMIT {per_page} OFFSET {(page-1) * per_page}"

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        documents = []
        for row in cursor.fetchall():
            documents.append({
                'filename': row[0],
                'year': row[1],
                'type': row[2]
            })

        # 전체 개수 (페이지네이션용)
        count_query = "SELECT COUNT(*) FROM documents WHERE 1=1"
        if filter_year:
            count_query += f" AND year = {filter_year}"
        if filter_type:
            count_query += f" AND doc_type = '{filter_type}'"

        cursor.execute(count_query)
        total_count = cursor.fetchone()[0]

        return {
            'documents': documents,
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': (total_count + per_page - 1) // per_page
        }

    def search_documents(self, query: str, limit: int = 20) -> List[Dict]:
        """빠른 문서 검색 (인덱스 기반)"""
        cursor = self.conn.cursor()

        # 파일명 검색
        cursor.execute(
            "SELECT filename, year, doc_type FROM documents WHERE filename LIKE ? LIMIT ?",
            (f'%{query}%', limit)
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                'filename': row[0],
                'year': row[1],
                'type': row[2]
            })

        return results

    def add_document_async(self, filepath: Path):
        """비동기로 문서 추가 (백그라운드 처리)"""
        # 백그라운드 처리를 위한 스레드 풀 사용 (추후 구현 가능)
        filename = filepath.name

        # 간단한 메타데이터만 즉시 추가
        year = int(filename[:4]) if filename[:4].isdigit() else 0
        doc_type = self._detect_type(filename)

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO documents (filename, path, year, doc_type, size, modified, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (filename, str(filepath), year, doc_type,
             filepath.stat().st_size, filepath.stat().st_mtime, time.time())
        )
        self.conn.commit()

        return True

    def _detect_type(self, filename: str) -> str:
        """문서 타입 자동 감지"""
        if '구매' in filename:
            return '구매'
        elif '수리' in filename:
            return '수리'
        elif '검토' in filename:
            return '검토'
        elif '소모품' in filename:
            return '소모품'
        else:
            return '기타'

    def get_statistics(self) -> Dict:
        """빠른 통계 반환"""
        cursor = self.conn.cursor()

        # 연도별 통계
        cursor.execute("SELECT year, COUNT(*) FROM documents GROUP BY year ORDER BY year")
        year_stats = dict(cursor.fetchall())

        # 타입별 통계
        cursor.execute("SELECT doc_type, COUNT(*) FROM documents GROUP BY doc_type")
        type_stats = dict(cursor.fetchall())

        # 전체 통계
        cursor.execute("SELECT COUNT(*), SUM(size) FROM documents")
        total_count, total_size = cursor.fetchone()

        return {
            'total_documents': total_count or 0,
            'total_size_mb': (total_size or 0) / 1024 / 1024,
            'by_year': year_stats,
            'by_type': type_stats
        }


if __name__ == "__main__":
    # 테스트
    manager = LightweightDocumentManager()

    print("\n📊 문서 통계:")
    stats = manager.get_statistics()
    print(f"  총 문서: {stats['total_documents']}개")
    print(f"  총 크기: {stats['total_size_mb']:.1f} MB")

    print("\n📄 첫 페이지 문서 목록:")
    page_data = manager.get_document_list(page=1, per_page=10)
    for doc in page_data['documents'][:5]:
        print(f"  - {doc['filename'][:50]}...")

    print(f"\n  (전체 {page_data['total']}개 중 {len(page_data['documents'])}개 표시)")