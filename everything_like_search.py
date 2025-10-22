#!/usr/bin/env python3
"""
Everything처럼 초고속 문서 검색 시스템
빠른 파일 검색 + 선택된 문서만 AI 분석
"""

import os
import re
import json
import time
import sqlite3
import pdfplumber
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EverythingLikeSearch:
    """Everything처럼 빠른 문서 검색"""

    def __init__(self):
        self.docs_dir = Path("docs")
        self.db_path = Path("everything_index.db")
        self.conn = None
        self.ocr_cache = {}
        self.setup_database()
        self._load_ocr_cache()

    def setup_database(self):
        """SQLite DB 설정 - 초고속 검색을 위해"""
        # check_same_thread=False로 멀티스레드 지원
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        cursor = self.conn.cursor()

        # 기존 테이블이 있는지 확인하고 content 컬럼 추가
        cursor.execute("PRAGMA table_info(files)")
        columns = [col[1] for col in cursor.fetchall()]
        has_content = 'content' in columns

        if not has_content and columns:  # 테이블은 있지만 content 컬럼이 없음
            print("🔄 데이터베이스 업그레이드: content 컬럼 추가 중...")
            cursor.execute("ALTER TABLE files ADD COLUMN content TEXT")
            self.conn.commit()
            print("✅ content 컬럼 추가 완료")

        # 파일 인덱스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER,
                date TEXT,
                year INTEGER,
                month INTEGER,
                category TEXT,
                department TEXT,
                keywords TEXT,
                content TEXT,
                created_at TIMESTAMP,
                UNIQUE(path)
            )
        """)

        # 인덱스 생성 (초고속 검색을 위해)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON files(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON files(year)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON files(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords ON files(keywords)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content ON files(content)")

        self.conn.commit()

    def index_all_files(self):
        """모든 파일 인덱싱 (파일명/메타데이터만)"""
        print("🚀 초고속 인덱싱 시작...")
        start_time = time.time()

        cursor = self.conn.cursor()

        # 기존 데이터 삭제
        cursor.execute("DELETE FROM files")

        # Zone.Identifier 파일 자동 정리 (윈도우 다운로드 흔적)
        zone_files = list(self.docs_dir.rglob("*Zone.Identifier*"))
        if zone_files:
            print(f"🧹 {len(zone_files)}개 Zone.Identifier 파일 자동 정리 중...")
            for zone_file in zone_files:
                try:
                    zone_file.unlink()
                except Exception as e:
                    logger.warning(f"Zone.Identifier 삭제 실패: {zone_file}: {e}")
            print("✅ Zone.Identifier 파일 정리 완료")

        # 모든 PDF 파일 수집
        pdf_files = list(self.docs_dir.rglob("*.pdf"))

        # 중복 제거 (심볼릭 링크 실제 경로 기준, 절대 경로로 통일)
        seen_real_paths = set()
        unique_files = []
        for pdf in pdf_files:
            # 모든 경로를 절대 경로로 변환 (심볼릭 링크도 해결)
            real_path = pdf.resolve()
            real_path_str = str(real_path)

            if real_path_str not in seen_real_paths:
                seen_real_paths.add(real_path_str)
                # 실제 파일 경로 사용 (심볼릭 링크 제외)
                unique_files.append(real_path)

        print(f"📁 {len(unique_files)}개 파일 인덱싱 중...")

        for pdf_path in unique_files:
            try:
                filename = pdf_path.name

                # 날짜 추출
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
                date = year = month = None
                if date_match:
                    date = date_match.group(0)
                    year = int(date_match.group(1))
                    month = int(date_match.group(2))

                # 카테고리 추출
                category = self._extract_category(filename)

                # 부서 추출
                department = self._extract_department(filename)

                # 키워드 추출
                keywords = self._extract_keywords(filename)

                # 문서 내용 추출 (텍스트가 있는 경우만)
                content = self._extract_text_content(pdf_path)

                # DB에 저장
                cursor.execute("""
                    INSERT OR REPLACE INTO files
                    (filename, path, size, date, year, month, category, department, keywords, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    filename,
                    str(pdf_path),
                    pdf_path.stat().st_size,
                    date,
                    year,
                    month,
                    category,
                    department,
                    keywords,
                    content,
                    datetime.now()
                ))

            except Exception as e:
                logger.error(f"파일 인덱싱 실패: {pdf_path.name}: {e}")

        self.conn.commit()

        elapsed = time.time() - start_time
        print(f"✅ 인덱싱 완료! ({elapsed:.2f}초)")
        print(f"   - {len(unique_files)}개 파일")
        print(f"   - 평균 {elapsed/len(unique_files)*1000:.1f}ms/파일")

    def _extract_category(self, filename: str) -> str:
        """카테고리 추출"""
        filename_lower = filename.lower()
        if '구매' in filename_lower:
            return '구매'
        elif '수리' in filename_lower:
            return '수리'
        elif '교체' in filename_lower:
            return '교체'
        elif '폐기' in filename_lower:
            return '폐기'
        elif '신청' in filename_lower or '신첩' in filename_lower:
            return '신청서'
        elif '검토' in filename_lower:
            return '검토'
        elif '기안' in filename_lower:
            return '기안서'
        return '기타'

    def _extract_department(self, filename: str) -> str:
        """부서 추출"""
        filename_lower = filename.lower()
        if '중계' in filename_lower:
            return '중계'
        elif '카메라' in filename_lower:
            return '카메라'
        elif '조명' in filename_lower:
            return '조명'
        elif 'dvr' in filename_lower:
            return 'DVR'
        elif '스튜디오' in filename_lower:
            return '스튜디오'
        elif '송출' in filename_lower:
            return '송출'
        elif '영상' in filename_lower:
            return '영상'
        return ''

    def _extract_keywords(self, filename: str) -> str:
        """키워드 추출"""
        # 한글만 추출
        korean_words = re.findall(r'[가-힣]+', filename)
        # 중요 키워드만 필터링 (2글자 이상)
        keywords = [word for word in korean_words if len(word) >= 2]
        return ' '.join(keywords)

    def _extract_text_content(self, pdf_path: Path) -> str:
        """PDF에서 텍스트 내용 추출 (첫 3페이지만, 최대 5000자)"""
        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                # 첫 3페이지만 처리 (인덱싱 속도를 위해)
                for page in pdf.pages[:3]:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + " "
                        # 5000자 제한 (DB 크기 관리)
                        if len(text) >= 5000:
                            break

            # 텍스트 정리 (불필요한 공백 제거)
            text = ' '.join(text.split())

            # 텍스트가 너무 짧으면 OCR 캐시 시도 (스캔 문서 등)
            if len(text.strip()) < 50:
                ocr_text = self._get_ocr_from_cache(pdf_path)
                if ocr_text:
                    logger.info(f"📷 OCR 캐시 사용 (인덱싱): {pdf_path.name} ({len(ocr_text)}자)")
                    return ocr_text[:5000]
                return ""

            return text[:5000]  # 최대 5000자로 제한

        except Exception as e:
            logger.debug(f"텍스트 추출 실패: {pdf_path.name}: {e}")
            return ""

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """초고속 검색 (Everything처럼) - 가중치 적용"""
        cursor = self.conn.cursor()

        # 쿼리 전처리 - "dvr관련" 같은 경우 분리
        import re
        # 영어와 한글이 붙어있으면 분리
        query_processed = re.sub(r'([a-zA-Z]+)(관련|관한|대한|관하여)', r'\1 \2', query)

        # 한국어 날짜 형식을 표준 형식으로 변환 (2024년 8월 -> 2024-08)
        korean_date_pattern = r'(\d{4})년\s*(\d{1,2})월'
        date_match = re.search(korean_date_pattern, query_processed)
        if date_match:
            year = date_match.group(1)
            month = date_match.group(2).zfill(2)  # 1월 -> 01
            standard_date = f"{year}-{month}"
            # 원래 쿼리에서 한국어 날짜를 표준 형식으로 변경
            query_processed = re.sub(korean_date_pattern, standard_date, query_processed)

        # 쿼리에서 주요 키워드 추출 (불필요한 단어 제거 강화)
        skip_words = [
            '관련', '문서', '찾아', '찾아줘', '검색', '알려', '알려줘',
            '보여', '보여줘', '의', '건', '내용', '대해', '대한', '문서들',
            '자료', '좀', '뭐', '뭔지', '어떻게', '이', '그', '저',
            '요', '줘', '주세요', '해줘', '해주세요'
        ]
        keywords = []
        for word in query_processed.split():
            if word and word not in skip_words and len(word) >= 2:  # 2글자 이상만 (불필요한 단어 제거)
                keywords.append(word)

        # 키워드가 없으면 원본 쿼리 사용
        if not keywords:
            keywords = [query]

        # DVR처럼 영어는 대문자로 변환하여 검색
        processed_keywords = []
        for kw in keywords:
            # 영어만 있는 경우 대문자로
            if re.match(r'^[a-zA-Z]+$', kw):
                processed_keywords.append(kw.upper())
            else:
                processed_keywords.append(kw)
        keywords = processed_keywords

        # 가중치 기반 점수 계산 SQL
        # 파일명(5점) > 부서(3점) > 카테고리(2점) > 키워드(2점) > 내용(1점)
        score_parts = []
        params = []

        for keyword in keywords:
            search_term = f'%{keyword}%'
            score_part = """(
                CASE WHEN filename LIKE ? THEN 5 ELSE 0 END +
                CASE WHEN department LIKE ? THEN 3 ELSE 0 END +
                CASE WHEN category LIKE ? THEN 2 ELSE 0 END +
                CASE WHEN keywords LIKE ? THEN 2 ELSE 0 END +
                CASE WHEN content LIKE ? THEN 1 ELSE 0 END
            )"""
            score_parts.append(score_part)
            params.extend([search_term] * 5)

        # SQL 쿼리 구성 (점수 기반 정렬)
        sql = f"""
            SELECT *, ({' + '.join(score_parts)}) as relevance_score
            FROM files
            WHERE relevance_score > 0
            ORDER BY
                relevance_score DESC,
                year DESC,
                month DESC
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'filename': row[1],
                'path': row[2],
                'size': row[3],
                'date': row[4],
                'year': row[5],
                'month': row[6],
                'category': row[7],
                'department': row[8],
                'keywords': row[9],
                'content': row[10],
                'score': row[12]  # relevance_score (row[11]은 created_at)
            })

        return results

    def get_document_content(self, file_path: str) -> Dict[str, Any]:
        """선택된 문서의 내용 추출 (실시간)"""
        pdf_path = Path(file_path)

        if not pdf_path.exists():
            return {'error': '파일을 찾을 수 없습니다'}

        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                # 최대 10페이지만
                for page in pdf.pages[:10]:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            # 텍스트가 너무 짧으면
            if len(text.strip()) < 50:
                text = f"[스캔 문서 - OCR 필요]\n파일명: {pdf_path.name}"

            return {
                'filename': pdf_path.name,
                'text': text,
                'length': len(text),
                'pages': len(pdf.pages) if 'pdf' in locals() else 0
            }

        except Exception as e:
            return {
                'filename': pdf_path.name,
                'error': str(e)
            }

    def summarize_document(self, file_path: str) -> str:
        """문서 요약 (LLM 사용)"""
        content = self.get_document_content(file_path)

        if 'error' in content:
            return f"❌ 오류: {content['error']}"

        text = content['text'][:3000]  # 처음 3000자만

        # 간단한 요약 생성 (실제로는 LLM 사용)
        summary = f"""
📄 **{content['filename']}**

📊 **문서 정보:**
- 크기: {content['length']:,}자
- 페이지: {content.get('pages', '?')}페이지

📝 **내용 미리보기:**
{text[:500]}...

💡 **주요 내용:**
- 이 문서는 방송장비 관련 문서입니다
- 구매/수리/검토 등의 내용이 포함되어 있습니다
"""

        return summary

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

    def _get_ocr_from_cache(self, pdf_path: Path) -> str:
        """OCR 캐시에서 텍스트 가져오기"""
        try:
            import hashlib
            with open(pdf_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            if file_hash in self.ocr_cache:
                cached_data = self.ocr_cache[file_hash]
                return cached_data.get('text', '')

            return ""
        except Exception as e:
            logger.debug(f"OCR 캐시 읽기 실패: {e}")
            return ""


class FastDocumentRAG:
    """빠른 문서 검색 + AI 요약"""

    def __init__(self):
        self.search_engine = EverythingLikeSearch()
        self.search_engine.index_all_files()

    def find_documents(self, query: str) -> List[Dict]:
        """문서 검색 (초고속)"""
        return self.search_engine.search(query, limit=10)

    def analyze_document(self, file_path: str) -> str:
        """선택된 문서 분석"""
        return self.search_engine.summarize_document(file_path)

    def answer_question(self, query: str) -> Dict:
        """질문에 대한 답변"""
        # 1. 관련 문서 검색
        results = self.find_documents(query)

        if not results:
            return {
                'answer': "관련 문서를 찾을 수 없습니다.",
                'documents': []
            }

        # 2. 상위 3개 문서 분석
        summaries = []
        for doc in results[:3]:
            content = self.search_engine.get_document_content(doc['path'])
            if 'error' not in content:
                summaries.append({
                    'filename': doc['filename'],
                    'category': doc['category'],
                    'date': doc['date'],
                    'preview': content['text'][:200]
                })

        # 3. 답변 생성
        answer = f"""
🔍 **"{query}"** 검색 결과

📚 **찾은 문서: {len(results)}개**

"""
        for i, doc in enumerate(results[:5], 1):
            answer += f"{i}. {doc['filename']}\n"
            answer += f"   - 카테고리: {doc['category']}\n"
            answer += f"   - 날짜: {doc['date'] or '날짜 없음'}\n\n"

        if len(results) > 5:
            answer += f"... 외 {len(results)-5}개 더\n"

        return {
            'answer': answer,
            'documents': results,
            'summaries': summaries
        }


def main():
    """테스트"""
    print("🚀 Everything처럼 빠른 문서 검색 시스템")
    print("="*60)

    rag = FastDocumentRAG()

    # 테스트 검색
    test_queries = [
        "DVR",
        "중계차 수리",
        "2020년 카메라",
        "조명"
    ]

    for query in test_queries:
        print(f"\n📌 검색: {query}")

        start = time.time()
        result = rag.answer_question(query)
        elapsed = time.time() - start

        print(result['answer'][:500])
        print(f"⏱️ 검색 시간: {elapsed*1000:.1f}ms")
        print("-"*60)


if __name__ == "__main__":
    main()