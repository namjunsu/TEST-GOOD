#!/usr/bin/env python3
"""
향상된 PDF 캐싱 시스템 - 텍스트와 메타데이터 사전 추출
"""

import sqlite3
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

# OCR 프로세서 임포트
try:
    from ocr_processor import OCRProcessor
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedPDFCache:
    """향상된 PDF 캐시 시스템"""

    def __init__(self, db_path: str = "./pdf_cache.db"):
        self.db_path = db_path
        self.ocr_processor = OCRProcessor() if OCR_AVAILABLE else None
        self._init_db()

        # 메타데이터 추출 패턴
        self.patterns = {
            'date': [
                r'(\d{4})[년\-\.\/](\d{1,2})[월\-\.\/](\d{1,2})',
                r'(\d{4})\.(\d{1,2})\.(\d{1,2})',
                r'(\d{2,4})년\s*(\d{1,2})월\s*(\d{1,2})일'
            ],
            'amount': [
                r'([0-9,]+)\s*원',
                r'￦\s*([0-9,]+)',
                r'금액\s*:\s*([0-9,]+)',
                r'합계\s*:\s*([0-9,]+)'
            ],
            'dept': [
                r'(카메라|조명|음향|스튜디오|중계|편집|송출)',
                r'(제작[1-9]|보도|교양|예능|드라마)부',
                r'부서\s*:\s*([가-힣]+)'
            ],
            'doc_type': {
                '구매': ['구매', '구입', '발주', '계약서', '견적'],
                '수리': ['수리', '정비', 'A/S', '고장', '수선'],
                '신청': ['신청서', '요청서', '의뢰서'],
                '보고': ['보고서', '결과', '분석'],
                '회의': ['회의록', '회의', '미팅']
            }
        }

    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 메인 캐시 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_cache (
                file_hash TEXT PRIMARY KEY,
                file_path TEXT,
                file_name TEXT,
                text_content TEXT,
                text_length INTEGER,

                -- 메타데이터
                doc_date TEXT,
                doc_year INTEGER,
                doc_type TEXT,
                department TEXT,
                total_amount REAL,

                -- 추출 정보
                is_scanned BOOLEAN,
                ocr_used BOOLEAN,
                page_count INTEGER,

                -- 시스템 정보
                indexed_at TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,

                -- 검색 최적화
                search_text TEXT  -- 소문자 변환된 검색용 텍스트
            )
        ''')

        # 검색 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_doc_year ON pdf_cache(doc_year)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_doc_type ON pdf_cache(doc_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_department ON pdf_cache(department)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_search_text ON pdf_cache(search_text)
        ''')

        # 키워드 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_keywords (
                file_hash TEXT,
                keyword TEXT,
                frequency INTEGER,
                PRIMARY KEY (file_hash, keyword),
                FOREIGN KEY (file_hash) REFERENCES pdf_cache(file_hash)
            )
        ''')

        conn.commit()
        conn.close()

    def _get_file_hash(self, file_path: str) -> str:
        """파일 해시 생성"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _extract_text(self, pdf_path: str) -> Tuple[str, bool, bool]:
        """
        PDF에서 텍스트 추출 (OCR 포함)

        Returns:
            (text, is_scanned, ocr_used)
        """
        text = ""
        is_scanned = False
        ocr_used = False

        try:
            # 먼저 일반 추출 시도
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:5]:  # 처음 5페이지만 테스트
                    page_text = page.extract_text() or ""
                    text += page_text

            # 텍스트가 너무 적으면 스캔 문서로 판단
            if len(text.strip()) < 100:
                is_scanned = True

                # OCR 처리
                if self.ocr_processor:
                    logger.info(f"OCR 처리 필요: {Path(pdf_path).name}")
                    ocr_result = self.ocr_processor.extract_with_ocr(pdf_path)
                    text = ocr_result['text']
                    ocr_used = True
                    is_scanned = ocr_result['is_scanned']

            else:
                # 전체 페이지에서 텍스트 추출
                with pdfplumber.open(pdf_path) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += (page.extract_text() or "") + "\n"

        except Exception as e:
            logger.error(f"텍스트 추출 실패 {pdf_path}: {e}")

        return text, is_scanned, ocr_used

    def _extract_metadata(self, text: str, file_name: str) -> Dict:
        """텍스트에서 메타데이터 추출"""
        metadata = {
            'doc_date': None,
            'doc_year': None,
            'doc_type': None,
            'department': None,
            'total_amount': None
        }

        # 날짜 추출
        for pattern in self.patterns['date']:
            match = re.search(pattern, text)
            if match:
                try:
                    year = int(match.group(1))
                    if year < 100:  # 2자리 연도
                        year = 2000 + year if year < 50 else 1900 + year

                    month = int(match.group(2))
                    day = int(match.group(3))

                    metadata['doc_date'] = f"{year:04d}-{month:02d}-{day:02d}"
                    metadata['doc_year'] = year
                    break
                except:
                    pass

        # 파일명에서도 연도 추출 시도
        if not metadata['doc_year']:
            year_match = re.search(r'(20\d{2}|19\d{2})', file_name)
            if year_match:
                metadata['doc_year'] = int(year_match.group(1))

        # 금액 추출
        amounts = []
        for pattern in self.patterns['amount']:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    amount_str = match.group(1).replace(',', '')
                    amount = float(amount_str)
                    amounts.append(amount)
                except:
                    pass

        if amounts:
            metadata['total_amount'] = max(amounts)  # 최대 금액 선택

        # 부서 추출
        for pattern in self.patterns['dept']:
            match = re.search(pattern, text + " " + file_name)
            if match:
                metadata['department'] = match.group(1)
                break

        # 문서 유형 추출
        text_lower = (text + " " + file_name).lower()
        for doc_type, keywords in self.patterns['doc_type'].items():
            for keyword in keywords:
                if keyword in text_lower:
                    metadata['doc_type'] = doc_type
                    break
            if metadata['doc_type']:
                break

        return metadata

    def _extract_keywords(self, text: str, top_n: int = 20) -> List[Tuple[str, int]]:
        """주요 키워드 추출"""
        # 한국어 키워드 추출 (간단한 버전)
        words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}|\d{4,}', text)

        # 불용어 제거
        stopwords = {'있다', '있는', '있습니다', '합니다', '됩니다', '위한', '대한', '통해'}
        words = [w for w in words if w not in stopwords]

        # 빈도 계산
        word_freq = {}
        for word in words:
            word_lower = word.lower()
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1

        # 상위 N개 반환
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return sorted_words[:top_n]

    def index_pdf(self, pdf_path: str, force: bool = False) -> bool:
        """
        PDF 인덱싱

        Args:
            pdf_path: PDF 파일 경로
            force: 강제 재인덱싱

        Returns:
            성공 여부
        """
        try:
            file_hash = self._get_file_hash(pdf_path)

            # 캐시 확인
            if not force:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM pdf_cache WHERE file_hash = ?', (file_hash,))
                if cursor.fetchone():
                    conn.close()
                    logger.info(f"이미 캐시됨: {Path(pdf_path).name}")
                    return True
                conn.close()

            logger.info(f"인덱싱: {Path(pdf_path).name}")

            # 텍스트 추출
            text, is_scanned, ocr_used = self._extract_text(pdf_path)

            # 메타데이터 추출
            metadata = self._extract_metadata(text, Path(pdf_path).name)

            # 키워드 추출
            keywords = self._extract_keywords(text)

            # 페이지 수 확인
            page_count = 0
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
            except:
                pass

            # DB 저장
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO pdf_cache
                (file_hash, file_path, file_name, text_content, text_length,
                 doc_date, doc_year, doc_type, department, total_amount,
                 is_scanned, ocr_used, page_count,
                 indexed_at, search_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_hash,
                str(pdf_path),
                Path(pdf_path).name,
                text,
                len(text),
                metadata['doc_date'],
                metadata['doc_year'],
                metadata['doc_type'],
                metadata['department'],
                metadata['total_amount'],
                is_scanned,
                ocr_used,
                page_count,
                datetime.now(),
                text.lower()  # 검색용 소문자 텍스트
            ))

            # 키워드 저장
            for keyword, freq in keywords:
                cursor.execute('''
                    INSERT OR REPLACE INTO pdf_keywords (file_hash, keyword, frequency)
                    VALUES (?, ?, ?)
                ''', (file_hash, keyword, freq))

            conn.commit()
            conn.close()

            logger.info(f"인덱싱 완료: {Path(pdf_path).name}")
            return True

        except Exception as e:
            logger.error(f"인덱싱 실패 {pdf_path}: {e}")
            return False

    def search(self, query: str,
              year: Optional[int] = None,
              doc_type: Optional[str] = None,
              department: Optional[str] = None,
              limit: int = 10) -> List[Dict]:
        """
        캐시된 PDF 검색

        Args:
            query: 검색 쿼리
            year: 연도 필터
            doc_type: 문서 유형 필터
            department: 부서 필터
            limit: 결과 개수 제한

        Returns:
            검색 결과 리스트
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 기본 쿼리
        sql = '''
            SELECT file_path, file_name, text_content,
                   doc_year, doc_type, department, total_amount,
                   is_scanned, page_count
            FROM pdf_cache
            WHERE 1=1
        '''
        params = []

        # 텍스트 검색
        if query:
            sql += ' AND search_text LIKE ?'
            params.append(f'%{query.lower()}%')

        # 필터 적용
        if year:
            sql += ' AND doc_year = ?'
            params.append(year)

        if doc_type:
            sql += ' AND doc_type = ?'
            params.append(doc_type)

        if department:
            sql += ' AND department = ?'
            params.append(department)

        sql += ' ORDER BY indexed_at DESC LIMIT ?'
        params.append(limit)

        cursor.execute(sql, params)
        results = cursor.fetchall()

        # 결과 포맷팅
        formatted_results = []
        for row in results:
            formatted_results.append({
                'file_path': row[0],
                'file_name': row[1],
                'text_preview': row[2][:500] if row[2] else "",
                'year': row[3],
                'doc_type': row[4],
                'department': row[5],
                'amount': row[6],
                'is_scanned': row[7],
                'page_count': row[8]
            })

        # 접근 카운트 업데이트
        for row in results:
            cursor.execute('''
                UPDATE pdf_cache
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE file_path = ?
            ''', (datetime.now(), row[0]))

        conn.commit()
        conn.close()

        return formatted_results

    def get_statistics(self) -> Dict:
        """캐시 통계"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_scanned THEN 1 ELSE 0 END) as scanned,
                SUM(CASE WHEN ocr_used THEN 1 ELSE 0 END) as ocr_processed,
                AVG(text_length) as avg_text_length,
                AVG(page_count) as avg_pages,
                COUNT(DISTINCT doc_year) as years_covered,
                COUNT(DISTINCT doc_type) as doc_types,
                COUNT(DISTINCT department) as departments
            FROM pdf_cache
        ''')

        stats = cursor.fetchone()
        conn.close()

        return {
            'total_documents': stats[0] or 0,
            'scanned_documents': stats[1] or 0,
            'ocr_processed': stats[2] or 0,
            'avg_text_length': int(stats[3] or 0),
            'avg_pages': int(stats[4] or 0),
            'years_covered': stats[5] or 0,
            'doc_types': stats[6] or 0,
            'departments': stats[7] or 0
        }

    def build_index(self, directory: str, pattern: str = "**/*.pdf",
                   max_workers: int = 4) -> Dict:
        """
        디렉토리 전체 인덱싱

        Args:
            directory: PDF 디렉토리
            pattern: 파일 패턴
            max_workers: 병렬 처리 워커 수

        Returns:
            처리 통계
        """
        pdf_dir = Path(directory)
        pdf_files = list(pdf_dir.glob(pattern))

        logger.info(f"총 {len(pdf_files)}개 PDF 인덱싱 시작")

        stats = {
            'total': len(pdf_files),
            'success': 0,
            'failed': 0,
            'cached': 0
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.index_pdf, str(pdf)): pdf
                for pdf in pdf_files
            }

            for future in as_completed(futures):
                pdf_path = futures[future]
                try:
                    if future.result():
                        stats['success'] += 1
                    else:
                        stats['failed'] += 1
                except Exception as e:
                    logger.error(f"처리 실패 {pdf_path.name}: {e}")
                    stats['failed'] += 1

                # 진행 상황 출력
                processed = stats['success'] + stats['failed']
                if processed % 10 == 0:
                    logger.info(f"진행: {processed}/{stats['total']}")

        logger.info(f"인덱싱 완료: 성공 {stats['success']}, 실패 {stats['failed']}")
        return stats


# 테스트
if __name__ == "__main__":
    cache = EnhancedPDFCache()

    # 통계 확인
    print("캐시 통계:", cache.get_statistics())

    # 검색 테스트
    results = cache.search("DVR", limit=5)
    for r in results:
        print(f"- {r['file_name']}: {r['doc_type']} ({r['year']})")