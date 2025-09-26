#!/usr/bin/env python3
"""
PDF 내용 검색 기능 추가
Phase 1.1: 간단한 내용 검색
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber
from collections import OrderedDict
import time

logger = logging.getLogger(__name__)

class ContentSearcher:
    """PDF 내용 기반 검색"""

    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = Path(docs_dir)
        self.text_cache = OrderedDict()  # PDF 텍스트 캐시
        self.cache_max_size = 100  # 최대 캐시 크기

        # 성능 통계
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'total_searches': 0,
            'avg_search_time': 0
        }

        logger.info("ContentSearcher 초기화 완료")

    def extract_pdf_text(self, pdf_path: Path) -> str:
        """PDF에서 텍스트 추출 (캐시 사용)"""

        # 캐시 확인
        cache_key = str(pdf_path)
        if cache_key in self.text_cache:
            self.stats['cache_hits'] += 1
            # LRU 업데이트
            self.text_cache.move_to_end(cache_key)
            return self.text_cache[cache_key]

        self.stats['cache_misses'] += 1

        # PDF 텍스트 추출
        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                # 최대 50페이지까지만
                for page in pdf.pages[:50]:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            # 캐시에 저장
            if len(self.text_cache) >= self.cache_max_size:
                # 가장 오래된 항목 제거
                self.text_cache.popitem(last=False)

            self.text_cache[cache_key] = text
            return text

        except Exception as e:
            logger.error(f"PDF 텍스트 추출 실패: {pdf_path} - {e}")
            return ""

    def search_by_content(self, query: str, pdf_files: List[Path], top_k: int = 10, max_files: int = 50) -> List[Dict[str, Any]]:
        """PDF 내용 검색

        Args:
            query: 검색 쿼리
            pdf_files: 검색할 PDF 파일 목록
            top_k: 상위 k개 결과 반환
            max_files: 최대 검색할 파일 수 (성능 최적화)

        Returns:
            검색 결과 리스트 (점수순 정렬)
        """

        start_time = time.time()
        self.stats['total_searches'] += 1

        results = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        # 성능을 위해 파일 수 제한
        search_files = pdf_files[:max_files] if len(pdf_files) > max_files else pdf_files
        logger.info(f"내용 검색: {len(search_files)}개 파일 검색 (전체 {len(pdf_files)}개 중)")

        for pdf_path in search_files:
            # 텍스트 추출 (캐시 사용)
            text = self.extract_pdf_text(pdf_path)
            if not text:
                continue

            text_lower = text.lower()

            # 점수 계산
            score = 0

            # 1. 정확한 구문 매칭 (높은 점수)
            if query_lower in text_lower:
                score += 100
                # 등장 횟수에 따라 추가 점수
                count = text_lower.count(query_lower)
                score += min(count * 10, 50)  # 최대 50점

            # 2. 모든 토큰이 포함되는지 (중간 점수)
            tokens_found = sum(1 for token in query_tokens if token in text_lower)
            if tokens_found == len(query_tokens):
                score += 50
            else:
                score += (tokens_found / len(query_tokens)) * 30

            # 3. 키워드 근접도 (토큰들이 가까이 있을수록 높은 점수)
            if len(query_tokens) > 1:
                proximity_score = self._calculate_proximity(query_tokens, text_lower)
                score += proximity_score

            # 4. 문서 관련성 (제목, 날짜 등)
            filename = pdf_path.name.lower()
            if any(token in filename for token in query_tokens):
                score += 20

            if score > 0:
                results.append({
                    'path': pdf_path,
                    'filename': pdf_path.name,
                    'score': score,
                    'snippet': self._extract_snippet(text, query_lower, max_length=200)
                })

        # 점수순 정렬
        results.sort(key=lambda x: x['score'], reverse=True)

        # 통계 업데이트
        search_time = time.time() - start_time
        self.stats['avg_search_time'] = (
            (self.stats['avg_search_time'] * (self.stats['total_searches'] - 1) + search_time)
            / self.stats['total_searches']
        )

        logger.info(f"내용 검색 완료: {len(results)}개 결과 ({search_time:.2f}초)")

        return results[:top_k]

    def _calculate_proximity(self, tokens: set, text: str, window_size: int = 100) -> float:
        """토큰들의 근접도 계산"""

        if len(tokens) < 2:
            return 0

        # 텍스트를 window_size 크기로 슬라이딩
        max_score = 0
        for i in range(0, len(text) - window_size, window_size // 2):
            window = text[i:i + window_size]
            tokens_in_window = sum(1 for token in tokens if token in window)

            if tokens_in_window == len(tokens):
                # 모든 토큰이 window 내에 있으면 높은 점수
                return 30
            elif tokens_in_window > 1:
                # 일부 토큰이 window 내에 있으면 부분 점수
                score = (tokens_in_window / len(tokens)) * 20
                max_score = max(max_score, score)

        return max_score

    def _extract_snippet(self, text: str, query: str, max_length: int = 200) -> str:
        """검색 결과 스니펫 추출"""

        text_lower = text.lower()
        query_lower = query.lower()

        # 쿼리가 등장하는 위치 찾기
        pos = text_lower.find(query_lower)

        if pos == -1:
            # 쿼리가 정확히 매칭되지 않으면 첫 토큰으로 시도
            tokens = query_lower.split()
            if tokens:
                pos = text_lower.find(tokens[0])

        if pos == -1:
            # 그래도 못 찾으면 문서 시작 부분 반환
            return text[:max_length] + "..."

        # 문맥을 포함한 스니펫 추출
        start = max(0, pos - 50)
        end = min(len(text), pos + max_length - 50)

        snippet = text[start:end]

        # 문장 경계에서 자르기
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet

    def get_statistics(self) -> Dict[str, Any]:
        """검색 통계 반환"""

        total = self.stats['cache_hits'] + self.stats['cache_misses']
        hit_rate = (self.stats['cache_hits'] / total * 100) if total > 0 else 0

        return {
            'cache_hit_rate': f"{hit_rate:.1f}%",
            'total_searches': self.stats['total_searches'],
            'avg_search_time': f"{self.stats['avg_search_time']:.2f}초",
            'cache_size': len(self.text_cache)
        }

    def clear_cache(self):
        """캐시 초기화"""
        self.text_cache.clear()
        logger.info("텍스트 캐시 초기화 완료")

# 기존 PerfectRAG와 통합을 위한 헬퍼 함수
def integrate_content_search(perfect_rag_instance):
    """PerfectRAG에 내용 검색 기능 통합"""

    # ContentSearcher 인스턴스 생성
    content_searcher = ContentSearcher(perfect_rag_instance.docs_dir)

    # PerfectRAG에 메서드 추가
    perfect_rag_instance.content_searcher = content_searcher
    perfect_rag_instance.search_by_content = content_searcher.search_by_content

    logger.info("ContentSearcher가 PerfectRAG에 통합되었습니다")

    return content_searcher