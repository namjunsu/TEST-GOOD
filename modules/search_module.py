#!/usr/bin/env python3
"""
검색 모듈 - Perfect RAG에서 분리된 검색 기능
2025-09-29 리팩토링

이 모듈은 perfect_rag.py에서 검색 관련 기능을 분리하여
유지보수성과 가독성을 높이기 위해 생성되었습니다.
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

# 검색 관련 모듈들
from everything_like_search import EverythingLikeSearch
from modules.metadata_extractor import MetadataExtractor
from modules.metadata_db import MetadataDB

logger = logging.getLogger(__name__)


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

    def search_by_drafter(self, drafter_name: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        기안자별 문서 검색 - department 필드에서 정확히 일치하는 문서만 반환

        Args:
            drafter_name: 기안자 이름
            top_k: 반환할 최대 문서 수

        Returns:
            기안자가 작성한 문서 리스트
        """
        if self.everything_search:
            try:
                # 직접 SQL 쿼리로 department 필드에서 정확한 기안자 검색
                import sqlite3
                conn = sqlite3.connect('everything_index.db')
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM files
                    WHERE department LIKE ?
                    ORDER BY year DESC, month DESC
                    LIMIT ?
                """, (f'%{drafter_name}%', top_k))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'filename': row[1],
                        'path': row[2],
                        'score': 2.0,  # 높은 점수 (정확한 매칭)
                        'date': row[4],
                        'category': row[7],
                        'department': row[8],
                        'keywords': row[9]
                    })

                conn.close()
                logger.info(f"Found {len(results)} documents by drafter: {drafter_name}")
                return results

            except Exception as e:
                logger.error(f"Drafter search failed: {e}")
                return []

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
        # Everything-like 검색 사용 가능한 경우
        if self.everything_search:
            try:
                # 초고속 SQLite 검색
                search_results = self.everything_search.search(query, limit=top_k)

                results = []
                for doc in search_results:
                    result = {
                        'filename': doc['filename'],
                        'path': doc['path'],
                        'score': doc.get('score', 1.0),
                        'date': doc.get('date', ''),
                        'category': doc.get('category', ''),
                        'keywords': doc.get('keywords', ''),
                        'department': doc.get('department', '')  # 기안자 정보 포함
                    }

                    # 문서 전체 텍스트 및 메타데이터 추가
                    if doc['path']:
                        try:
                            pdf_path = Path(doc['path'])
                            if pdf_path.exists() and pdf_path.suffix.lower() == '.pdf':
                                with pdfplumber.open(pdf_path) as pdf:
                                    # 전체 페이지 텍스트 추출 (최대 5000자)
                                    full_text = ""
                                    for page in pdf.pages[:5]:  # 최대 5페이지
                                        page_text = page.extract_text() or ""
                                        full_text += page_text + "\n\n"
                                        if len(full_text) > 5000:
                                            break

                                    result['content'] = full_text[:5000]  # AI 분석용 전체 내용

                                    # 메타데이터 추출 (첫 페이지 기준)
                                    if self.metadata_extractor and pdf.pages:
                                        first_page_text = pdf.pages[0].extract_text() or ""
                                        metadata = self.metadata_extractor.extract_all(
                                            first_page_text[:2000],
                                            doc['filename']
                                        )

                                        # 추출된 정보 추가
                                        summary = metadata.get('summary', {})
                                        if summary.get('date'):
                                            result['extracted_date'] = summary['date']
                                        if summary.get('amount'):
                                            result['extracted_amount'] = summary['amount']
                                        if summary.get('department'):
                                            result['extracted_dept'] = summary['department']
                                        if summary.get('doc_type'):
                                            result['extracted_type'] = summary['doc_type']
                                        if summary.get('drafter'):
                                            result['drafter'] = summary['drafter']
                        except Exception as e:
                            logger.debug(f"텍스트/메타데이터 추출 실패: {e}")
                            result['content'] = ""  # 실패시 빈 문자열

                    results.append(result)

                logger.info(f"Everything search found {len(results)} documents for query: {query}")
                return results

            except Exception as e:
                logger.error(f"Everything search failed: {e}, falling back to legacy search")
                return self._legacy_search(query, top_k)
        else:
            return self._legacy_search(query, top_k)

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
        stats = {
            'total_documents': len(list(self.docs_dir.rglob("*.pdf"))),
            'categories': len([d for d in self.docs_dir.iterdir() if d.is_dir() and d.name.startswith('category_')]),
            'years': len([d for d in self.docs_dir.iterdir() if d.is_dir() and d.name.startswith('year_')]),
            'cache_size': len(self.search_cache)
        }

        if self.metadata_db:
            stats['indexed_documents'] = self.metadata_db.get_document_count()

        return stats

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