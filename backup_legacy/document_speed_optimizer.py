#!/usr/bin/env python3
"""
문서 검색 속도 최적화 패치
병렬 처리와 문서 제한으로 183초 → 30초 목표
"""

import os
from pathlib import Path
import json

def optimize_document_search():
    """문서 검색 성능 최적화 코드 생성"""

    optimization_code = '''
# perfect_rag.py의 _search_documents 메서드 최적화

import concurrent.futures
from functools import lru_cache
import time

class DocumentSearchOptimizer:
    """문서 검색 최적화"""

    def __init__(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.pdf_text_cache = {}  # PDF 텍스트 캐시

    def _search_documents_optimized(self, query: str) -> list:
        """최적화된 문서 검색"""

        # 1. 관련 PDF 빠르게 필터링 (메타데이터만 사용)
        relevant_pdfs = self._quick_filter_pdfs(query, limit=10)  # 10개로 제한

        if not relevant_pdfs:
            return []

        # 2. 병렬로 PDF 텍스트 추출 (캐시 활용)
        futures = []
        for pdf_path in relevant_pdfs[:5]:  # 최대 5개만 처리
            future = self.executor.submit(self._get_pdf_text_cached, pdf_path)
            futures.append((pdf_path, future))

        # 3. 결과 수집
        results = []
        for pdf_path, future in futures:
            try:
                text = future.result(timeout=5)  # 5초 타임아웃
                if text:
                    results.append({
                        'path': pdf_path,
                        'text': text[:5000],  # 텍스트 길이 제한
                        'score': self._calculate_relevance(text, query)
                    })
            except Exception:
                continue

        # 4. 관련성 순으로 정렬하여 상위 3개만 반환
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:3]

    @lru_cache(maxsize=100)
    def _get_pdf_text_cached(self, pdf_path: str) -> str:
        """PDF 텍스트 캐싱"""

        # 캐시 확인
        if pdf_path in self.pdf_text_cache:
            return self.pdf_text_cache[pdf_path]

        # PDF 텍스트 추출 (에러 처리 포함)
        try:
            import pdfplumber
            text = ""

            with pdfplumber.open(pdf_path) as pdf:
                # 최대 10페이지만 추출
                for i, page in enumerate(pdf.pages[:10]):
                    try:
                        page_text = page.extract_text()
                        if page_text and len(page_text.strip()) > 10:
                            text += page_text + "\\n"
                    except Exception:
                        continue

                    # 텍스트 길이 제한
                    if len(text) > 20000:
                        break

            # 캐시 저장
            self.pdf_text_cache[pdf_path] = text
            return text

        except Exception:
            return ""

    def _quick_filter_pdfs(self, query: str, limit: int = 10) -> list:
        """메타데이터 기반 빠른 PDF 필터링"""

        query_lower = query.lower()
        query_keywords = query_lower.split()

        scored_pdfs = []

        for cache_key, metadata in self.metadata_cache.items():
            filename = metadata.get('filename', '').lower()

            # 빠른 점수 계산
            score = 0
            for keyword in query_keywords:
                if keyword in filename:
                    score += 2  # 파일명 매치 가중치
                if metadata.get('year') and keyword == str(metadata['year']):
                    score += 3  # 연도 매치 가중치

            if score > 0:
                scored_pdfs.append((metadata['path'], score))

        # 점수순 정렬하여 상위 N개만 반환
        scored_pdfs.sort(key=lambda x: x[1], reverse=True)
        return [pdf[0] for pdf in scored_pdfs[:limit]]

    def _calculate_relevance(self, text: str, query: str) -> float:
        """관련성 점수 계산"""

        text_lower = text.lower()
        query_lower = query.lower()
        keywords = query_lower.split()

        score = 0
        for keyword in keywords:
            # 키워드 빈도 계산
            count = text_lower.count(keyword)
            score += min(count, 10)  # 최대 10점

        return score / len(keywords) if keywords else 0
'''

    print("📝 문서 검색 최적화 코드:")
    print("-" * 50)
    print(optimization_code)
    return optimization_code


def create_pdf_error_handler():
    """PDF 추출 오류 처리 개선"""

    error_handler = '''
# PDF 텍스트 추출 오류 처리 개선

def safe_extract_pdf_text(pdf_path: str, max_pages: int = 10) -> str:
    """안전한 PDF 텍스트 추출"""

    text = ""

    # 1차 시도: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                try:
                    page_text = page.extract_text()
                    if page_text and len(page_text.strip()) > 10:
                        # 인코딩 문제 처리
                        page_text = page_text.encode('utf-8', errors='ignore').decode('utf-8')
                        text += page_text + "\\n"
                except (ValueError, TypeError, KeyError):
                    # 알려진 오류들 무시
                    continue
                except Exception:
                    continue

                if len(text) > 20000:
                    break
    except Exception:
        pass

    # 2차 시도: PyPDF2 (pdfplumber 실패시)
    if not text:
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for i in range(min(len(reader.pages), max_pages)):
                    try:
                        page = reader.pages[i]
                        page_text = page.extract_text()
                        if page_text and len(page_text.strip()) > 10:
                            text += page_text + "\\n"
                    except Exception:
                        continue

                    if len(text) > 20000:
                        break
        except Exception:
            pass

    return text
'''

    print("\n📝 PDF 오류 처리 코드:")
    print("-" * 50)
    print(error_handler)
    return error_handler


def apply_optimizations():
    """perfect_rag.py에 최적화 적용 지침"""

    instructions = """
🔧 perfect_rag.py 최적화 적용 방법:

1. **문서 처리 개수 제한** (라인 약 850-900)
   - filtered_pdfs[:15] → filtered_pdfs[:5] 로 변경
   - 최대 5개 문서만 처리하도록 제한

2. **병렬 처리 추가**
   - DocumentSearchOptimizer 클래스를 __init__에 추가
   - _search_documents 메서드를 _search_documents_optimized로 교체

3. **PDF 텍스트 캐싱**
   - pdf_text_cache 딕셔너리 추가
   - LRU 캐시로 100개 PDF 캐싱

4. **타임아웃 설정**
   - 각 PDF 처리에 5초 타임아웃
   - 전체 검색에 20초 제한

5. **텍스트 길이 제한**
   - 페이지당 최대 10페이지
   - 문서당 최대 20,000자

예상 개선 효과:
- 문서 검색: 183초 → 30-40초 (80% 개선)
- 메모리 사용: 병렬 처리로 효율화
- 오류 감소: 강력한 예외 처리
"""

    print("\n" + "=" * 50)
    print("📋 최적화 적용 지침")
    print("=" * 50)
    print(instructions)


def create_config_update():
    """config.py 업데이트"""

    config_update = """
# config.py에 추가할 설정

# 문서 검색 최적화
MAX_DOCUMENTS_TO_PROCESS = 5  # 15 → 5
MAX_PAGES_PER_PDF = 10       # 50 → 10
PDF_TIMEOUT_SECONDS = 5      # PDF당 타임아웃
SEARCH_TIMEOUT_SECONDS = 20  # 전체 검색 타임아웃

# 병렬 처리
PARALLEL_WORKERS = 4          # 병렬 워커 수
BATCH_SIZE = 5               # 배치 크기

# 캐싱
PDF_TEXT_CACHE_SIZE = 100    # PDF 텍스트 캐시 크기
RESPONSE_CACHE_TTL = 7200    # 응답 캐시 TTL (2시간)
"""

    print("\n📝 config.py 추가 설정:")
    print("-" * 50)
    print(config_update)


def main():
    print("=" * 60)
    print("🚀 문서 검색 속도 최적화 패치")
    print("=" * 60)
    print("\n현재 문제: 문서 모드 평균 183초 (너무 느림)")
    print("목표: 30-40초로 단축\n")

    # 1. 문서 검색 최적화 코드
    optimize_document_search()

    # 2. PDF 오류 처리
    create_pdf_error_handler()

    # 3. 적용 지침
    apply_optimizations()

    # 4. 설정 업데이트
    create_config_update()

    print("\n" + "=" * 60)
    print("✅ 최적화 패치 준비 완료")
    print("=" * 60)

    print("\n⚡ 예상 성능 향상:")
    print("- 문서 처리: 15개 → 5개 (66% 감소)")
    print("- 병렬 처리: 4개 워커 동시 실행")
    print("- PDF 캐싱: 100개 캐시 (재사용율 향상)")
    print("- 응답 시간: 183초 → 30-40초 (80% 개선)")
    print("\n🎯 이제 perfect_rag.py에 위 코드들을 적용하세요!")


if __name__ == "__main__":
    main()