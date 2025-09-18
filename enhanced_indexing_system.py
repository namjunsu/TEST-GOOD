#!/usr/bin/env python3
"""
향상된 인덱싱 시스템
- 증분 인덱싱
- 병렬 처리
- 실시간 업데이트
"""

import asyncio
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any
import hashlib
import json
import time
from datetime import datetime
import sqlite3
import numpy as np
from collections import defaultdict

class EnhancedIndexingSystem:
    def __init__(self, docs_dir: str = "docs", max_workers: int = 4):
        self.docs_dir = Path(docs_dir)
        self.max_workers = max_workers
        self.index_db = Path("rag_system/cache/enhanced_index.db")
        self.index_db.parent.mkdir(parents=True, exist_ok=True)

        # 인덱스 타입
        self.index_types = {
            'text': {},      # 텍스트 인덱스
            'metadata': {},  # 메타데이터 인덱스
            'vector': {},    # 벡터 인덱스
            'asset': {}      # 자산 전용 인덱스
        }

        self._init_db()
        self.load_indexes()

    def _init_db(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.index_db) as conn:
            # 문서 인덱스
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_index (
                    filepath TEXT PRIMARY KEY,
                    file_hash TEXT,
                    file_type TEXT,
                    file_size INTEGER,
                    last_modified REAL,
                    indexed_at REAL,
                    title TEXT,
                    content_hash TEXT,
                    metadata TEXT,
                    keywords TEXT,
                    category TEXT
                )
            """)

            # 자산 인덱스
            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_index (
                    equipment_id TEXT PRIMARY KEY,
                    equipment_name TEXT,
                    manufacturer TEXT,
                    model TEXT,
                    serial_number TEXT,
                    location TEXT,
                    manager TEXT,
                    purchase_date TEXT,
                    price REAL,
                    status TEXT,
                    metadata TEXT
                )
            """)

            # 검색 인덱스
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath TEXT,
                    chunk_id INTEGER,
                    content TEXT,
                    embedding BLOB,
                    FOREIGN KEY (filepath) REFERENCES document_index(filepath)
                )
            """)

            # 인덱스 생성
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON document_index(file_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON document_index(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_equipment_location ON asset_index(location)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_equipment_manager ON asset_index(manager)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_search_content ON search_index(content)")

            conn.commit()

    def calculate_file_hash(self, filepath: Path) -> str:
        """파일 해시 계산"""
        stat = filepath.stat()
        return hashlib.md5(f"{filepath.name}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()

    def needs_reindex(self, filepath: Path) -> bool:
        """재인덱싱 필요 여부 확인"""
        current_hash = self.calculate_file_hash(filepath)

        with sqlite3.connect(self.index_db) as conn:
            cursor = conn.execute(
                "SELECT file_hash FROM document_index WHERE filepath = ?",
                (str(filepath),)
            )
            row = cursor.fetchone()

            if row and row[0] == current_hash:
                return False

        return True

    def index_document(self, filepath: Path) -> Dict[str, Any]:
        """단일 문서 인덱싱"""
        print(f"  📄 인덱싱: {filepath.name}")

        file_hash = self.calculate_file_hash(filepath)
        file_type = filepath.suffix.lower()
        metadata = {}

        # 파일 타입별 처리
        if file_type == '.pdf':
            metadata = self._index_pdf(filepath)
        elif file_type == '.txt':
            metadata = self._index_txt(filepath)
        elif file_type in ['.xlsx', '.xls']:
            metadata = self._index_excel(filepath)

        # DB에 저장
        with sqlite3.connect(self.index_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO document_index
                (filepath, file_hash, file_type, file_size, last_modified, indexed_at,
                 title, category, metadata, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(filepath),
                file_hash,
                file_type,
                filepath.stat().st_size,
                filepath.stat().st_mtime,
                time.time(),
                metadata.get('title', filepath.stem),
                metadata.get('category', '기타'),
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(metadata.get('keywords', []), ensure_ascii=False)
            ))
            conn.commit()

        return metadata

    def _index_pdf(self, filepath: Path) -> Dict:
        """PDF 문서 인덱싱"""
        metadata = {
            'title': filepath.stem,
            'type': 'pdf',
            'category': self._detect_category(filepath.name)
        }

        # 날짜 추출
        if '_' in filepath.stem:
            parts = filepath.stem.split('_', 1)
            if len(parts[0]) >= 8:
                metadata['date'] = parts[0][:10]
                metadata['year'] = parts[0][:4]

        # 키워드 추출
        keywords = []
        if '구매' in filepath.name:
            keywords.append('구매')
        if '수리' in filepath.name:
            keywords.append('수리')
        if '검토' in filepath.name:
            keywords.append('검토')

        metadata['keywords'] = keywords

        return metadata

    def _index_txt(self, filepath: Path) -> Dict:
        """텍스트 파일 인덱싱 (주로 자산 데이터)"""
        metadata = {
            'title': filepath.stem,
            'type': 'txt',
            'category': '자산'
        }

        # 자산 파일인 경우 특별 처리
        if '자산' in filepath.name or '7904' in filepath.name:
            metadata['is_asset'] = True
            metadata['asset_type'] = 'equipment_list'

            # 빠른 통계 생성
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    metadata['total_items'] = content.count('[')
                    metadata['locations'] = []

                    # 주요 위치 추출
                    for location in ['중계차', '광화문', '대형스튜디오', '소형부조정실']:
                        if location in content:
                            metadata['locations'].append(location)

            except Exception as e:
                print(f"  ⚠️ 자산 파일 인덱싱 오류: {e}")

        return metadata

    def _index_excel(self, filepath: Path) -> Dict:
        """엑셀 파일 인덱싱"""
        metadata = {
            'title': filepath.stem,
            'type': 'excel',
            'category': '데이터'
        }

        if 'equipment' in filepath.name.lower():
            metadata['is_asset'] = True
            metadata['asset_type'] = 'equipment_database'

        return metadata

    def _detect_category(self, filename: str) -> str:
        """파일명에서 카테고리 자동 감지"""
        filename_lower = filename.lower()

        if '구매' in filename_lower:
            return '구매'
        elif '수리' in filename_lower or '보수' in filename_lower:
            return '수리'
        elif '검토' in filename_lower:
            return '검토'
        elif '폐기' in filename_lower:
            return '폐기'
        elif '자산' in filename_lower:
            return '자산'
        else:
            return '기타'

    def parallel_index_documents(self, filepaths: List[Path]) -> Dict[str, Any]:
        """병렬로 여러 문서 인덱싱"""
        results = {
            'success': [],
            'failed': [],
            'skipped': []
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_filepath = {}

            for filepath in filepaths:
                if not self.needs_reindex(filepath):
                    results['skipped'].append(filepath.name)
                    continue

                future = executor.submit(self.index_document, filepath)
                future_to_filepath[future] = filepath

            for future in concurrent.futures.as_completed(future_to_filepath):
                filepath = future_to_filepath[future]
                try:
                    metadata = future.result()
                    results['success'].append(filepath.name)
                except Exception as e:
                    print(f"  ❌ {filepath.name}: {e}")
                    results['failed'].append(filepath.name)

        return results

    def build_full_index(self):
        """전체 인덱스 구축"""
        print("🚀 전체 인덱스 구축 시작...")
        start_time = time.time()

        # 모든 파일 수집
        all_files = []
        all_files.extend(self.docs_dir.glob("*.pdf"))
        all_files.extend(self.docs_dir.glob("*.txt"))
        all_files.extend(self.docs_dir.glob("*.xlsx"))
        all_files.extend(self.docs_dir.glob("**/*.pdf"))  # 하위 폴더도 포함

        print(f"📁 총 {len(all_files)}개 파일 발견")

        # 병렬 인덱싱
        results = self.parallel_index_documents(all_files)

        elapsed = time.time() - start_time
        print(f"\n✅ 인덱싱 완료!")
        print(f"  - 소요 시간: {elapsed:.2f}초")
        print(f"  - 성공: {len(results['success'])}개")
        print(f"  - 스킵: {len(results['skipped'])}개")
        print(f"  - 실패: {len(results['failed'])}개")

        return results

    def search_by_category(self, category: str) -> List[Dict]:
        """카테고리별 검색"""
        with sqlite3.connect(self.index_db) as conn:
            cursor = conn.execute(
                """SELECT filepath, title, metadata
                   FROM document_index
                   WHERE category = ?
                   ORDER BY last_modified DESC""",
                (category,)
            )
            results = []
            for row in cursor:
                results.append({
                    'filepath': row[0],
                    'title': row[1],
                    'metadata': json.loads(row[2])
                })
            return results

    def search_assets(self, location: str = None, manager: str = None) -> List[Dict]:
        """자산 검색"""
        query = "SELECT * FROM asset_index WHERE 1=1"
        params = []

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")

        if manager:
            query += " AND manager LIKE ?"
            params.append(f"%{manager}%")

        with sqlite3.connect(self.index_db) as conn:
            cursor = conn.execute(query, params)
            columns = [description[0] for description in cursor.description]
            results = []
            for row in cursor:
                results.append(dict(zip(columns, row)))
            return results

    def load_indexes(self):
        """인덱스 메모리에 로드"""
        with sqlite3.connect(self.index_db) as conn:
            cursor = conn.execute("SELECT filepath, title, category FROM document_index")
            for row in cursor:
                self.index_types['metadata'][row[0]] = {
                    'title': row[1],
                    'category': row[2]
                }

    def get_statistics(self) -> Dict:
        """인덱스 통계"""
        with sqlite3.connect(self.index_db) as conn:
            stats = {}

            # 전체 문서 수
            cursor = conn.execute("SELECT COUNT(*) FROM document_index")
            stats['total_documents'] = cursor.fetchone()[0]

            # 카테고리별 문서 수
            cursor = conn.execute("""
                SELECT category, COUNT(*) FROM document_index
                GROUP BY category
            """)
            stats['by_category'] = dict(cursor.fetchall())

            # 파일 타입별
            cursor = conn.execute("""
                SELECT file_type, COUNT(*) FROM document_index
                GROUP BY file_type
            """)
            stats['by_type'] = dict(cursor.fetchall())

            # 자산 데이터
            cursor = conn.execute("SELECT COUNT(*) FROM asset_index")
            stats['total_assets'] = cursor.fetchone()[0]

            return stats

if __name__ == "__main__":
    # 테스트
    indexer = EnhancedIndexingSystem()
    indexer.build_full_index()
    stats = indexer.get_statistics()
    print(f"\n📊 인덱스 통계: {json.dumps(stats, indent=2, ensure_ascii=False)}")