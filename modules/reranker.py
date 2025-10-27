#!/usr/bin/env python3
"""
리랭커 모듈 - L2 RAG 완성을 위한 규칙 기반 리랭커
2025-10-25 생성

검색 결과를 다음 기준으로 재정렬:
1. 제목 정확 매치: 쿼리 키워드가 filename에 정확히 포함 시 +0.3
2. 최근 7일: 문서 날짜가 현재로부터 7일 이내 시 +0.2
3. 카테고리 일치: 카테고리가 쿼리와 매칭 시 +0.1
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class RuleBasedReranker:
    """규칙 기반 리랭커 - 가중치를 통한 검색 결과 재정렬"""

    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: 리랭커 설정
                - title_match_boost: 제목 매치 가중치 (기본값: 0.3)
                - recent_boost: 최근 문서 가중치 (기본값: 0.2)
                - category_boost: 카테고리 매치 가중치 (기본값: 0.1)
                - recent_days: 최근 문서 기준 일수 (기본값: 7)
        """
        self.config = config or {}
        self.title_match_boost = self.config.get('title_match_boost', 0.5)  # 0.3 → 0.5 (제목 일치 강화)
        self.recent_boost = self.config.get('recent_boost', 0.3)  # 0.2 → 0.3 (최근 문서 강화)
        self.category_boost = self.config.get('category_boost', 0.1)
        self.recent_days = self.config.get('recent_days', 14)  # 7 → 14 (최근 문서 기준 확대)

        logger.info(f"✅ RuleBasedReranker 초기화 완료 "
                   f"(title_boost={self.title_match_boost}, "
                   f"recent_boost={self.recent_boost}, "
                   f"category_boost={self.category_boost}, "
                   f"recent_days={self.recent_days})")

    def rerank(self, query: str, results: List[Dict[str, Any]], top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        검색 결과 재정렬

        Args:
            query: 사용자 질의
            results: 검색 결과 리스트 (각 항목에 filename, date, category, score 포함)
            top_k: 반환할 최대 문서 수 (None이면 전체)

        Returns:
            재정렬된 검색 결과 리스트 (rerank_score, boost_reason 필드 추가)
        """
        if not results:
            return []

        # 쿼리 키워드 추출 (공백 기준 분리 + 특수문자 제거)
        query_keywords = self._extract_keywords(query)

        # 카테고리 키워드 추출 (예: "방송", "구매", "소모품" 등)
        category_keywords = self._extract_category_keywords(query)

        # 현재 날짜 (최근 문서 판단 기준)
        today = datetime.now()
        recent_threshold = today - timedelta(days=self.recent_days)

        reranked_results = []
        for doc in results:
            # 기본 점수 (원래 검색 점수)
            base_score = doc.get('score', 1.0)
            boost = 0.0
            boost_reasons = []

            # 1. 제목 정확 매치 체크
            title_boost = self._calculate_title_boost(doc.get('filename', ''), query_keywords)
            if title_boost > 0:
                boost += title_boost
                boost_reasons.append(f"제목매치+{title_boost:.1f}")

            # 2. 최근 문서 체크
            recent_boost_val = self._calculate_recent_boost(doc.get('date', ''), recent_threshold)
            if recent_boost_val > 0:
                boost += recent_boost_val
                boost_reasons.append(f"최근7일+{recent_boost_val:.1f}")

            # 3. 카테고리 일치 체크
            category_boost_val = self._calculate_category_boost(
                doc.get('category', ''),
                category_keywords
            )
            if category_boost_val > 0:
                boost += category_boost_val
                boost_reasons.append(f"카테고리+{category_boost_val:.1f}")

            # 최종 점수 = 기본 점수 + 부스트
            final_score = base_score + boost

            # 결과에 리랭크 정보 추가
            reranked_doc = doc.copy()
            reranked_doc['rerank_score'] = final_score
            reranked_doc['base_score'] = base_score
            reranked_doc['boost'] = boost
            reranked_doc['boost_reasons'] = boost_reasons

            reranked_results.append(reranked_doc)

        # 리랭크 점수 기준 정렬 (내림차순)
        reranked_results.sort(key=lambda x: x['rerank_score'], reverse=True)

        # top_k 제한
        if top_k:
            reranked_results = reranked_results[:top_k]

        # 로그 출력
        logger.info(f"🔄 리랭킹 완료: {len(results)}건 → {len(reranked_results)}건 반환 "
                   f"(부스트 적용: {sum(1 for r in reranked_results if r['boost'] > 0)}건)")

        if reranked_results and reranked_results[0].get('boost_reasons'):
            logger.debug(f"   최상위 문서 부스트: {reranked_results[0]['boost_reasons']}")

        return reranked_results

    def _extract_keywords(self, query: str) -> List[str]:
        """
        쿼리에서 키워드 추출

        Args:
            query: 사용자 질의

        Returns:
            키워드 리스트 (소문자 변환, 2글자 이상, 불용어 제거)
        """
        # 한글, 영어, 숫자만 추출
        clean_query = re.sub(r'[^\w\s가-힣]', ' ', query)

        # 공백 기준 분리
        keywords = clean_query.split()

        # 불용어 제거 (연도 패턴 제외, 조사 제거 등)
        stopwords = ['이', '그', '저', '의', '가', '을', '를', '에', '와', '과', '은', '는',
                    '문서', '찾아', '줘', '보여', '알려', '있는', '있어', '해', '해줘']

        # 2글자 이상 + 불용어 제외
        filtered = [kw.lower() for kw in keywords if len(kw) >= 2 and kw not in stopwords]

        return filtered

    def _extract_category_keywords(self, query: str) -> List[str]:
        """
        쿼리에서 카테고리 관련 키워드 추출

        Args:
            query: 사용자 질의

        Returns:
            카테고리 키워드 리스트
        """
        # 일반적인 카테고리 패턴
        category_patterns = [
            r'(방송|영상|제작)',
            r'(소모품|구매|장비)',
            r'(인사|총무|재무)',
            r'(계약|검토|협약)',
            r'(보고서|기안서|검토서)',
        ]

        categories = []
        for pattern in category_patterns:
            match = re.search(pattern, query)
            if match:
                categories.append(match.group(1))

        return categories

    def _calculate_title_boost(self, filename: str, query_keywords: List[str]) -> float:
        """
        제목 매치 부스트 계산

        Args:
            filename: 파일명
            query_keywords: 쿼리 키워드 리스트

        Returns:
            부스트 점수 (0 ~ title_match_boost)
        """
        if not filename or not query_keywords:
            return 0.0

        filename_lower = filename.lower()

        # 정확히 매칭되는 키워드 개수 계산
        matched_count = sum(1 for kw in query_keywords if kw in filename_lower)

        # 키워드가 1개 이상 매칭되면 부스트 적용
        if matched_count > 0:
            # 매칭 비율에 따라 부스트 조정 (최대 title_match_boost)
            match_ratio = matched_count / len(query_keywords)
            return self.title_match_boost * match_ratio

        return 0.0

    def _calculate_recent_boost(self, date_str: str, threshold: datetime) -> float:
        """
        최근 문서 부스트 계산

        Args:
            date_str: 문서 날짜 (YYYY-MM-DD 형식)
            threshold: 최근 문서 기준 날짜 (현재 - N일)

        Returns:
            부스트 점수 (0 또는 recent_boost)
        """
        if not date_str:
            return 0.0

        try:
            # 날짜 파싱 (YYYY-MM-DD 또는 YYYY_MM_DD)
            date_str_normalized = date_str.replace('_', '-')
            doc_date = datetime.strptime(date_str_normalized[:10], '%Y-%m-%d')

            # 최근 N일 이내 문서면 부스트
            if doc_date >= threshold:
                # 최근일수록 더 높은 부스트 (최대 recent_boost)
                days_diff = (datetime.now() - doc_date).days
                boost_ratio = 1.0 - (days_diff / self.recent_days)
                return self.recent_boost * boost_ratio

        except (ValueError, TypeError) as e:
            logger.debug(f"날짜 파싱 실패: {date_str} ({e})")

        return 0.0

    def _calculate_category_boost(self, category: str, category_keywords: List[str]) -> float:
        """
        카테고리 일치 부스트 계산

        Args:
            category: 문서 카테고리
            category_keywords: 쿼리에서 추출한 카테고리 키워드

        Returns:
            부스트 점수 (0 또는 category_boost)
        """
        if not category or not category_keywords:
            return 0.0

        category_lower = category.lower()

        # 카테고리 키워드 중 하나라도 매칭되면 부스트
        for kw in category_keywords:
            if kw.lower() in category_lower:
                return self.category_boost

        return 0.0

    def get_stats(self, reranked_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        리랭킹 통계 반환

        Args:
            reranked_results: rerank() 메서드의 반환값

        Returns:
            통계 딕셔너리
        """
        if not reranked_results:
            return {}

        boosted_count = sum(1 for r in reranked_results if r.get('boost', 0) > 0)
        avg_boost = sum(r.get('boost', 0) for r in reranked_results) / len(reranked_results)

        return {
            'total_documents': len(reranked_results),
            'boosted_documents': boosted_count,
            'avg_boost': round(avg_boost, 3),
            'max_boost': max((r.get('boost', 0) for r in reranked_results), default=0),
            'top_score': reranked_results[0].get('rerank_score', 0) if reranked_results else 0
        }


# 편의 함수
def rerank_search_results(query: str, results: List[Dict[str, Any]],
                         top_k: Optional[int] = None,
                         config: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """
    검색 결과 리랭킹 (함수형 인터페이스)

    Args:
        query: 사용자 질의
        results: 검색 결과 리스트
        top_k: 반환할 최대 문서 수
        config: 리랭커 설정

    Returns:
        재정렬된 검색 결과
    """
    reranker = RuleBasedReranker(config)
    return reranker.rerank(query, results, top_k)
