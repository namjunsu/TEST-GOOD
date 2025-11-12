#!/usr/bin/env python3
"""
검색 모듈 - Perfect RAG에서 분리된 검색 기능
2025-09-29 리팩토링

이 모듈은 perfect_rag.py에서 검색 관련 기능을 분리하여
유지보수성과 가독성을 높이기 위해 생성되었습니다.
"""

from app.core.logging import get_logger
import os
import re
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

# 검색 관련 모듈들
from everything_like_search import EverythingLikeSearch
from modules.metadata_extractor import MetadataExtractor
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


class SearchModule:
    """검색 기능 통합 모듈"""

    def __init__(self, docs_dir: str = "docs", config: Dict = None):
        """
        Args:
            docs_dir: 문서 디렉토리 경로
            config: 설정 딕셔너리
        """
        self.docs_dir = Path(docs_dir)
        self.config = config or {}

        # Everything-like 검색 초기화
        self.everything_search = None
        try:
            self.everything_search = EverythingLikeSearch()
            logger.info("Everything-like search initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Everything search: {e}")

        # 메타데이터 추출기 초기화
        self.metadata_extractor = None
        try:
            self.metadata_extractor = MetadataExtractor()
            logger.info("✅ MetadataExtractor 초기화 성공")
        except Exception as e:
            logger.error(f"❌ MetadataExtractor 초기화 실패: {e}")

        # 메타데이터 DB 초기화
        self.metadata_db = None
        try:
            self.metadata_db = MetadataDB()
            logger.info("✅ MetadataDB 초기화 성공")
        except Exception as e:
            logger.error(f"❌ MetadataDB 초기화 실패: {e}")

        # 캐시
        self.search_cache = {}
        self.cache_ttl = 3600  # 1시간

        # OCR 캐시 로드
        self.ocr_cache = {}
        self._load_ocr_cache()

    def search_by_drafter(self, drafter_name: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        기안자별 문서 검색 - 정확 컬럼: metadata.db.documents.drafter

        Args:
            drafter_name: 기안자 이름
            top_k: 반환할 최대 문서 수

        Returns:
            기안자가 작성한 문서 리스트
        """
        # 1순위: 메타DB FTS/정렬 기반
        if self.metadata_db:
            try:
                # 메타DB 직접 조회 (COALESCE로 최신순)
                import sqlite3
                conn = sqlite3.connect("metadata.db")
                conn.row_factory = sqlite3.Row
                cur = conn.execute("""
                    SELECT *
                    FROM documents
                    WHERE drafter LIKE ?
                    ORDER BY COALESCE(display_date, date) DESC
                    LIMIT ?
                """, (f"%{drafter_name}%", top_k))
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()

                return [{
                    'id': r['id'],  # doc_id for deduplication
                    'filename': r['filename'],
                    'path': r['path'],
                    'score': 2.0,  # 필드 일치 가중
                    'date': r.get('display_date') or r.get('date') or '',
                    'category': r.get('category') or '',
                    'drafter': r.get('drafter') or '',
                    'keywords': r.get('keywords') or ''
                } for r in rows]
            except Exception as e:
                logger.error(f"Drafter search via metadata.db failed: {e}")

        # 2순위(옵션): everything_index에 drafter 컬럼이 존재할 때만 사용
        if self.everything_search:
            try:
                import sqlite3
                conn = sqlite3.connect('everything_index.db')
                cur = conn.cursor()
                # 드롭인 호환: 존재 컬럼 확인
                cols = [c[1] for c in cur.execute("PRAGMA table_info(files)")]
                if 'drafter' in cols:
                    cur.execute("""
                        SELECT id, filename, path, date, category, drafter, keywords
                        FROM files
                        WHERE drafter LIKE ?
                        ORDER BY date DESC
                        LIMIT ?
                    """, (f"%{drafter_name}%", top_k))
                    results = [{
                        'id': r[0], 'filename': r[1], 'path': r[2], 'score': 1.5,
                        'date': r[3] or '', 'category': r[4] or '',
                        'drafter': r[5] or '', 'keywords': r[6] or ''
                    } for r in cur.fetchall()]
                    conn.close()
                    return results
                conn.close()
            except Exception as e:
                logger.error(f"Drafter search via everything_index failed: {e}")

        return []

    def search_by_drafter_and_year(self, drafter_name: str, year: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        기안자 + 연도 조합 검색 - 메타데이터 기반

        Args:
            drafter_name: 기안자 이름
            year: 연도 (예: '2021', '2022')
            top_k: 반환할 최대 문서 수

        Returns:
            해당 기안자의 해당 연도 문서 리스트
        """
        if not self.metadata_db:
            return []

        try:
            import sqlite3
            conn = sqlite3.connect("metadata.db")
            conn.row_factory = sqlite3.Row

            # 연도 조건: year 컬럼 또는 date 컬럼에서 추출
            cur = conn.execute("""
                SELECT *
                FROM documents
                WHERE drafter LIKE ?
                  AND (year = ? OR year = CAST(? AS INTEGER) OR date LIKE ?)
                ORDER BY COALESCE(display_date, date) DESC
                LIMIT ?
            """, (f"%{drafter_name}%", year, year, f"{year}%", top_k))

            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            return [{
                'id': r['id'],
                'filename': r['filename'],
                'path': r['path'],
                'score': 3.0,  # 메타데이터 2개 일치 (높은 가중치)
                'date': r.get('display_date') or r.get('date') or '',
                'category': r.get('category') or '',
                'drafter': r.get('drafter') or '',
                'keywords': r.get('keywords') or '',
                'year': r.get('year') or ''
            } for r in rows]

        except Exception as e:
            logger.error(f"Drafter+Year search failed: {e}")
            return []

    def search_by_content(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        내용 기반 문서 검색 - Everything-like 초고속 검색 사용

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 문서 수

        Returns:
            검색 결과 리스트
        """
        # 0) 쿼리 정규화
        q = (query or '').strip()
        if not q:
            return []

        # 1) Everything 우선
        if self.everything_search:
            try:
                raw = self.everything_search.search(q, limit=top_k)
                return self._enrich_results(raw, preview_mode='lite', limit=top_k)
            except Exception as e:
                logger.error(f"Everything search failed: {e}")

        # 2) 폴백: 메타DB FTS5 (bm25)
        if self.metadata_db:
            try:
                fts_hits = self.metadata_db.search_by_keyword(q)
                raw = [{
                    'id': r.get('id', 0),  # doc_id for deduplication
                    'filename': r.get('filename',''),
                    'path': r.get('path',''),
                    'score': r.get('score', 1.0) if 'score' in r else 1.0,
                    'date': r.get('display_date') or r.get('date') or '',
                    'category': r.get('category') or '',
                    'keywords': r.get('keywords') or '',
                    'department': r.get('drafter') or ''
                } for r in fts_hits][:top_k]
                return self._enrich_results(raw, preview_mode='lite', limit=top_k)
            except Exception as e:
                logger.error(f"FTS fallback failed: {e}")

        # 3) 최후 폴백: 파일명 병렬 매칭
        return self._legacy_search(q, top_k)

    def _legacy_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """레거시 검색 (Everything 사용 불가시 폴백)"""
        pdf_files = list(self.docs_dir.rglob("*.pdf"))
        if not pdf_files:
            logger.warning("No PDF files found in docs directory")
            return []

        # 병렬 검색
        results = self._parallel_search_pdfs(pdf_files, query, top_k)
        return results[:top_k]

    def _parallel_search_pdfs(self, pdf_files: List[Path], query: str, top_k: int = 5) -> List[Dict]:
        """PDF 파일들을 병렬로 검색"""
        results = []

        def search_single_pdf(pdf_path):
            try:
                # 간단한 파일명 매칭
                filename_lower = pdf_path.name.lower()
                query_lower = query.lower()

                # 파일명에서 키워드 매칭
                score = 0
                for keyword in query_lower.split():
                    if keyword in filename_lower:
                        score += 1

                if score > 0:
                    return {
                        'filename': pdf_path.name,
                        'path': str(pdf_path),
                        'score': score,
                        'date': self._extract_date_from_filename(pdf_path.name),
                        'category': self._extract_category_from_path(pdf_path)
                    }
            except Exception as e:
                logger.debug(f"Error searching {pdf_path}: {e}")

            return None

        # 병렬 처리
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(search_single_pdf, pdf): pdf for pdf in pdf_files}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # 점수 기준 정렬
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def find_best_document(self, query: str) -> Optional[Path]:
        """쿼리에 가장 적합한 단일 문서 찾기"""
        results = self.search_by_content(query, top_k=1)
        if results:
            return Path(results[0]['path'])
        return None

    def search_multiple_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """여러 문서 동시 검색 및 통합 결과 반환"""
        results = self.search_by_content(query, top_k=top_k)

        # 각 문서에서 관련 내용 추출
        for result in results:
            try:
                pdf_path = Path(result['path'])
                if pdf_path.exists():
                    with pdfplumber.open(pdf_path) as pdf:
                        # 첫 페이지 내용 추가
                        if pdf.pages:
                            text = pdf.pages[0].extract_text() or ""
                            result['preview'] = text[:500]  # 미리보기
            except Exception as e:
                logger.debug(f"Error extracting preview: {e}")
                result['preview'] = ""

        return results

    def search_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """날짜 범위로 문서 검색"""
        all_files = list(self.docs_dir.rglob("*.pdf"))
        results = []

        for pdf_path in all_files:
            date = self._extract_date_from_filename(pdf_path.name)
            if date and start_date <= date <= end_date:
                results.append({
                    'filename': pdf_path.name,
                    'path': str(pdf_path),
                    'date': date
                })

        results.sort(key=lambda x: x['date'])
        return results

    def search_by_category(self, category: str) -> List[Dict[str, Any]]:
        """카테고리별 문서 검색"""
        category_path = self.docs_dir / f"category_{category.lower()}"
        if not category_path.exists():
            return []

        pdf_files = list(category_path.rglob("*.pdf"))
        return [
            {
                'filename': pdf.name,
                'path': str(pdf),
                'category': category
            }
            for pdf in pdf_files
        ]

    def get_search_statistics(self) -> Dict[str, Any]:
        """검색 통계 반환"""
        stats = {'total_documents': 0, 'categories': 0, 'years': 0, 'cache_size': len(self.search_cache)}
        try:
            if self.docs_dir.exists():
                stats['total_documents'] = len(list(self.docs_dir.rglob("*.pdf")))
                stats['categories'] = sum(1 for d in self.docs_dir.iterdir() if d.is_dir() and d.name.startswith('category_'))
                stats['years'] = sum(1 for d in self.docs_dir.iterdir() if d.is_dir() and d.name.startswith('year_'))
        except Exception as e:
            logger.debug(f"Stats dir scan skipped: {e}")

        if self.metadata_db:
            try:
                # 우선순위 1: 메타DB의 총 문서 수
                stats_db = self.metadata_db.get_statistics()
                stats['indexed_documents'] = stats_db.get('total_documents', 0)
            except Exception:
                # 대체: 고유 문서 카운트
                stats['indexed_documents'] = getattr(self.metadata_db, 'count_unique_documents', lambda: 0)()

        return stats

    def _enrich_results(self, docs: List[Dict[str, Any]], preview_mode: str = 'lite', limit: int = 20) -> List[Dict[str, Any]]:
        """
        결과 후처리:
          - preview_mode='lite' : 첫 페이지 800~1200자만, 표 파싱/ OCR 미수행
          - preview_mode='full' : 표→MD 변환 + OCR 캐시(느림)
        """
        out = []
        for doc in docs[:limit]:
            res = dict(doc)
            pdf_path = Path(doc.get('path',''))
            # 안전 가드
            if not (pdf_path.suffix.lower() == '.pdf' and pdf_path.exists()):
                res['content'] = ''
                out.append(res)
                continue

            try:
                with pdfplumber.open(pdf_path) as pdf:
                    if not pdf.pages:
                        res['content'] = ''
                        out.append(res)
                        continue

                    if preview_mode == 'lite':
                        txt = (pdf.pages[0].extract_text() or '')[:1200]
                        res['content'] = txt
                    else:
                        full_text = ''
                        for page in pdf.pages[:5]:
                            page_txt = page.extract_text() or ''
                            full_text += page_txt + '\n\n'

                            # 표 추출 및 마크다운 형식 변환
                            tables = page.extract_tables()
                            if tables:
                                for table in tables:
                                    table_md = self._format_table_as_markdown(table)
                                    if table_md:
                                        full_text += "\n📊 **표 데이터**\n" + table_md + "\n\n"

                            if len(full_text) > 15000:
                                break

                        # OCR 폴백 (full 모드에서만)
                        text_lines = [line for line in full_text.split('\n') if line.strip()]
                        is_mostly_headers = len(text_lines) < 10 or full_text.count('gw.channela-mt.com') > 2

                        if len(full_text.strip()) < 500 or is_mostly_headers:
                            ocr_text = self._get_ocr_text(pdf_path)
                            if ocr_text and len(ocr_text) > len(full_text):
                                full_text = ocr_text
                                logger.info(f"📷 OCR 캐시 사용: {pdf_path.name} ({len(ocr_text)}자)")

                        res['content'] = full_text

                    # 메타데이터 추출 (첫 페이지 기준)
                    if self.metadata_extractor and pdf.pages:
                        first_page_text = pdf.pages[0].extract_text() or ""
                        metadata = self.metadata_extractor.extract_all(
                            first_page_text[:2000],
                            doc.get('filename', '')
                        )

                        # 추출된 정보 추가
                        summary = metadata.get('summary', {})
                        if summary.get('date'):
                            res['extracted_date'] = summary['date']
                        if summary.get('amount'):
                            res['extracted_amount'] = summary['amount']
                        if summary.get('department'):
                            res['extracted_dept'] = summary['department']
                        if summary.get('doc_type'):
                            res['extracted_type'] = summary['doc_type']
                        if summary.get('drafter'):
                            res['drafter'] = summary['drafter']

            except Exception as e:
                logger.debug(f"Preview extract failed: {pdf_path.name} - {e}")
                res['content'] = ''

            out.append(res)
        return out

    # 표 형식 변환 메서드
    def _format_table_as_markdown(self, table):
        """표를 마크다운 형식으로 변환"""
        if not table or not table[0]:
            return ""

        lines = []

        # 헤더 (첫 번째 행)
        header = " | ".join([str(cell or '').strip() for cell in table[0]])
        lines.append(header)

        # 구분선
        separator = " | ".join(["---"] * len(table[0]))
        lines.append(separator)

        # 데이터 행
        for row in table[1:]:
            row_text = " | ".join([str(cell or '').strip() for cell in row])
            lines.append(row_text)

        return "\n".join(lines)

    # OCR 캐시 관련 메서드
    def _load_ocr_cache(self):
        """OCR 캐시 로드"""
        ocr_cache_path = self.docs_dir / ".ocr_cache.json"
        if ocr_cache_path.exists():
            try:
                with open(ocr_cache_path, 'r', encoding='utf-8') as f:
                    self.ocr_cache = json.load(f)
                logger.info(f"✅ OCR 캐시 로드 완료: {len(self.ocr_cache)}개 문서")
            except Exception as e:
                logger.warning(f"OCR 캐시 로드 실패: {e}")
                self.ocr_cache = {}
        else:
            logger.debug("OCR 캐시 파일 없음")

    def _fast_md5(self, pdf_path: Path, chunk: int = 2*1024*1024) -> str:
        """빠른 MD5 해시 계산 (샘플 기반)"""
        import hashlib
        size = pdf_path.stat().st_size
        h = hashlib.md5()
        with open(pdf_path, 'rb') as f:
            h.update(f.read(chunk))
            if size > chunk:
                f.seek(max(0, size - chunk))
                h.update(f.read(chunk))
        h.update(str((size, pdf_path.stat().st_mtime_ns)).encode())
        return h.hexdigest()

    def _get_ocr_text(self, pdf_path: Path) -> str:
        """PDF에서 OCR 텍스트 가져오기 (캐시 우선)"""
        try:
            # 빠른 파일 해시 계산 (샘플 기반)
            file_hash = self._fast_md5(pdf_path)

            # 캐시에서 찾기
            if file_hash in self.ocr_cache:
                cached_data = self.ocr_cache[file_hash]
                return cached_data.get('text', '')

            return ""
        except Exception as e:
            logger.debug(f"OCR 텍스트 가져오기 실패: {e}")
            return ""

    # 유틸리티 메서드들
    def _extract_date_from_filename(self, filename: str) -> Optional[str]:
        """파일명에서 날짜 추출"""
        # 2024-08-13 형식
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, filename)
        if match:
            return match.group(1)

        # 2024_08_13 형식
        date_pattern2 = r'(\d{4}_\d{2}_\d{2})'
        match = re.search(date_pattern2, filename)
        if match:
            return match.group(1).replace('_', '-')

        return None

    def _extract_category_from_path(self, path: Path) -> str:
        """경로에서 카테고리 추출"""
        parts = path.parts
        for part in parts:
            if part.startswith('category_'):
                return part.replace('category_', '')
        return 'general'

    def clear_cache(self):
        """검색 캐시 초기화"""
        self.search_cache.clear()
        logger.info("Search cache cleared")