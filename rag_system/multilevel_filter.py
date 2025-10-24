"""
다단계 필터링 시스템
대용량 문서에서 고품질 검색 결과를 위한 4단계 필터링 파이프라인
"""

from app.core.logging import get_logger
import os
import time
import re
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class FilterResult:
    """필터링 결과 데이터 클래스"""
    chunk_id: str
    content: str
    score: float
    metadata: Dict[str, Any]
    phase: str
    reasoning: str


def _get_chunk_id(result: dict) -> Optional[str]:
    """
    스키마 호환 헬퍼: chunk_id 또는 doc_id 추출

    레거시 계층에서 chunk_id를 쓰거나 신규 계층에서 doc_id를 쓰더라도
    양쪽 키를 모두 허용하여 스키마 불일치 방지.

    Args:
        result: 검색 결과 딕셔너리

    Returns:
        chunk_id 또는 doc_id (둘 다 없으면 None)
    """
    return result.get("chunk_id") or result.get("doc_id")


class QueryComplexityAnalyzer:
    """쿼리 복잡도 분석기"""
    
    # 복잡도별 반환 상수
    COMPARISON_K = 10
    COMPLEX_K = 7
    SIMPLE_K = 3
    QUERY_LENGTH_THRESHOLD = 5
    
    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """패턴 컴파일"""
        self.simple_patterns = [
            re.compile(p) for p in [
            r'가격',
            r'얼마',
            r'언제',
            r'어디',
            r'누구',
            r'무엇'
            ]
        ]

        self.complex_patterns = [
            re.compile(p) for p in [
            r'비교',
            r'차이',
            r'장단점',
            r'분석',
            r'어떻게',
            r'왜'
            ]
        ]

        self.comparison_patterns = [
            re.compile(p) for p in [
            r'vs',
            r'대비',
            r'보다',
            r'와|과.*비교',
            r'중에서.*좋은',
            r'어느.*나은'
            ]
        ]
    
    def analyze(self, query: str) -> Dict[str, Any]:
        """
        쿼리 복잡도 분석
        Returns: {"complexity_level": str, "type": str, "recommended_k": int}
        """
        query = query.lower()
        
        # 비교 질문 검사
        for pattern in self.comparison_patterns:
            if pattern.search(query):
                return {
                    "complexity_level": "complex",
                    "type": "comparison",
                    "recommended_k": self.COMPARISON_K
                }
        
        # 복잡한 질문 검사
        for pattern in self.complex_patterns:
            if pattern.search(query):
                return {
                    "complexity_level": "complex",
                    "type": "complex",
                    "recommended_k": self.COMPLEX_K
                }

        # 단순한 질문 검사
        for pattern in self.simple_patterns:
            if pattern.search(query):
                return {
                    "complexity_level": "simple",
                    "type": "simple",
                    "recommended_k": self.SIMPLE_K
                }
        
        # 기본값
        if len(query.split()) > self.QUERY_LENGTH_THRESHOLD:
            return {
                "complexity_level": "complex",
                "type": "complex",
                "recommended_k": self.COMPLEX_K
            }
        else:
            return {
                "complexity_level": "simple",
                "type": "simple",
                "recommended_k": self.SIMPLE_K
            }

class MultilevelFilter:
    """다단계 필터링 시스템"""

    # 필터링 상수
    PHASE1_MAX_CANDIDATES = 50
    PHASE2_MAX_CANDIDATES = 20
    PHASE3_MAX_CANDIDATES = 10
    DEFAULT_THRESHOLD = float(os.getenv('DEFAULT_THRESHOLD', '0.20'))  # .env에서 읽기
    
    # 점수 가중치
    VECTOR_WEIGHT = 0.5
    BM25_WEIGHT = 0.3
    KEYWORD_WEIGHT = 0.2
    
    # 키워드 빈도 계산 상수
    FREQUENCY_MULTIPLIER = 0.3
    
    # 도메인 키워드 가중치 상수
    EQUIPMENT_WEIGHT = 2.0
    PRICE_WEIGHT = 2.5
    ACTION_WEIGHT = 1.5
    YEAR_WEIGHT = 1.8
    GENERAL_WEIGHT = 1.2
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.complexity_analyzer = QueryComplexityAnalyzer()

        # 성능 통계
        self.filter_count = 0
        self.total_filter_time = 0.0
        self.phase_stats = {'phase1': 0, 'phase2': 0, 'phase3': 0, 'phase4': 0}

        # 도메인 특화 키워드 가중치
        self._init_domain_keywords()
    
    def _init_domain_keywords(self):
        """도메인 키워드 초기화"""
        self.domain_keywords = {
            # 장비 관련
            '카메라': self.EQUIPMENT_WEIGHT, 
            '워크스테이션': self.EQUIPMENT_WEIGHT, 
            '모니터': self.EQUIPMENT_WEIGHT, 
            '마이크': self.EQUIPMENT_WEIGHT,
            '트라이포드': self.EQUIPMENT_WEIGHT, 
            '배터리': self.EQUIPMENT_WEIGHT * 0.9, 
            '짐벌': self.EQUIPMENT_WEIGHT * 0.9, 
            '드론': self.EQUIPMENT_WEIGHT * 0.9,
            
            # 가격 관련
            '가격': self.PRICE_WEIGHT, 
            '금액': self.PRICE_WEIGHT, 
            '비용': self.PRICE_WEIGHT, 
            '원': self.PRICE_WEIGHT * 0.8, 
            '만원': self.PRICE_WEIGHT * 0.8,
            
            # 기술 관련
            '수리': self.ACTION_WEIGHT, 
            '교체': self.ACTION_WEIGHT, 
            '구매': self.ACTION_WEIGHT, 
            '검토': self.ACTION_WEIGHT,
            
            # 시간 관련
            '2024': self.YEAR_WEIGHT, 
            '2025': self.YEAR_WEIGHT, 
            '년': self.YEAR_WEIGHT * 0.7, 
            '월': self.YEAR_WEIGHT * 0.7
        }
    
    def phase1_semantic_filtering(self, vector_results: List[Dict], 
                                query: str, threshold: float = None) -> List[FilterResult]:
        """
        Phase 1: 의미론적 대용량 필터링
        벡터 검색 결과에서 top_50 후보 추출 (임계값 기준)
        """
        start_time = time.time()
        
        # 임계값 설정
        if threshold is None:
            threshold = self.DEFAULT_THRESHOLD
            
        # 임계값 이상의 결과만 필터링
        filtered_results = []
        for result in vector_results[:self.PHASE1_MAX_CANDIDATES]:
            if result.get('similarity', 0) >= threshold:
                chunk_id = _get_chunk_id(result)
                if chunk_id is None:
                    self.logger.warning("Filter input lacks chunk_id/doc_id; skipping one result")
                    continue
                filtered_results.append(FilterResult(
                    chunk_id=chunk_id,
                    content=result.get('content', ''),
                    score=result.get('similarity', 0),
                    metadata=result.get('metadata', {}),
                    phase="phase1_semantic",
                    reasoning=f"Cosine similarity: {result.get('similarity', 0):.3f} >= {threshold}"
                ))
        
        processing_time = time.time() - start_time
        self.logger.info(f"Phase 1: {len(vector_results)} → {len(filtered_results)} 후보 추출 ({processing_time:.3f}초)")
        
        return filtered_results
    
    def phase2_keyword_enhancement(self, phase1_results: List[FilterResult], 
                                 bm25_results: List[Dict], query: str) -> List[FilterResult]:
        """
        Phase 2: 키워드 매칭 강화
        BM25 + 도메인 키워드 가중치로 top_20 정제
        """
        start_time = time.time()
        
        # BM25 결과를 딕셔너리로 변환 (빠른 검색을 위해)
        bm25_scores = {}
        for result in bm25_results:
            chunk_id = _get_chunk_id(result)
            if chunk_id is not None:
                bm25_scores[chunk_id] = result.get('score', 0)
        
        # 쿼리에서 도메인 키워드 추출
        query_keywords = self._extract_domain_keywords(query)
        
        enhanced_results = []
        for result in phase1_results:
            # BM25 점수 추가
            bm25_score = bm25_scores.get(result.chunk_id, 0)
            
            # 도메인 키워드 매칭 점수 계산
            keyword_score = self._calculate_keyword_score(result.content, query_keywords)
            
            # 통합 점수 계산
            combined_score = (
                result.score * self.VECTOR_WEIGHT + 
                bm25_score * self.BM25_WEIGHT + 
                keyword_score * self.KEYWORD_WEIGHT
            )
            
            enhanced_results.append(FilterResult(
                chunk_id=result.chunk_id,
                content=result.content,
                score=combined_score,
                metadata=result.metadata,
                phase="phase2_keyword",
                reasoning=f"Combined: vec={result.score:.3f}, bm25={bm25_score:.3f}, kw={keyword_score:.3f}"
            ))
        
        # 점수 기준 정렬 후 상위 N개
        enhanced_results.sort(key=lambda x: x.score, reverse=True)
        top_results = enhanced_results[:self.PHASE2_MAX_CANDIDATES]
        
        processing_time = time.time() - start_time
        self.logger.info(f"Phase 2: {len(enhanced_results)} → {len(top_results)} 키워드 강화 ({processing_time:.3f}초)")
        
        return top_results
    
    def phase3_reranking(self, phase2_results: List[FilterResult], 
                        query: str, reranker=None) -> List[FilterResult]:
        """
        Phase 3: 정밀 순위 재조정
        Korean Reranker로 top_10 최종 순위 결정
        """
        start_time = time.time()
        
        if not reranker or len(phase2_results) <= self.PHASE3_MAX_CANDIDATES:
            # Reranker가 없거나 결과가 N개 이하면 그대로 반환
            final_results = phase2_results[:self.PHASE3_MAX_CANDIDATES]
            for result in final_results:
                result.phase = "phase3_passthrough"
                result.reasoning += " | No reranking needed"
        else:
            # Reranker 적용
            try:
                # Reranker 입력 형식으로 변환
                rerank_input = []
                for result in phase2_results:
                    rerank_input.append({
                        'chunk_id': result.chunk_id,
                        'content': result.content
                    })
                
                # Reranking 수행
                reranked_results = reranker.rerank(query, rerank_input, top_k=self.PHASE3_MAX_CANDIDATES)
                
                # 결과를 FilterResult 형식으로 변환
                # 빠른 검색을 위한 딕셔너리 생성
                phase2_dict = {r.chunk_id: r for r in phase2_results}
                
                final_results = []
                for idx, reranked in enumerate(reranked_results):
                    # 원본 결과 찾기 (딕셔너리 사용)
                    reranked_chunk_id = _get_chunk_id(reranked)
                    if reranked_chunk_id is None:
                        continue
                    original = phase2_dict.get(reranked_chunk_id)
                    if not original:
                        continue
                    
                    final_results.append(FilterResult(
                        chunk_id=original.chunk_id,
                        content=original.content,
                        score=reranked['rerank_score'],
                        metadata=original.metadata,
                        phase="phase3_reranked",
                        reasoning=f"{original.reasoning} | Rerank: {reranked['rerank_score']:.3f}"
                    ))
                
            except Exception as e:
                # 오류 로그를 디버그 레벨로 변경 (경고 대신)
                self.logger.debug(f"Reranking 폴백 모드 사용: {e}")
                final_results = phase2_results[:self.PHASE3_MAX_CANDIDATES]
                for result in final_results:
                    result.phase = "phase3_fallback"
                    result.reasoning += " | Using fallback ranking"
        
        processing_time = time.time() - start_time
        self.logger.info(f"Phase 3: {len(phase2_results)} → {len(final_results)} 순위 재조정 ({processing_time:.3f}초)")
        
        return final_results
    
    def phase4_adaptive_selection(self, phase3_results: List[FilterResult], 
                                query: str) -> List[FilterResult]:
        """
        Phase 4: 적응형 선택
        쿼리 복잡도에 따라 top_k 동적 조정
        """
        start_time = time.time()
        
        # 쿼리 복잡도 분석
        complexity_result = self.complexity_analyzer.analyze(query)
        complexity_type = complexity_result['type']
        recommended_k = complexity_result['recommended_k']

        # 결과 개수 조정
        final_k = min(recommended_k, len(phase3_results))
        selected_results = phase3_results[:final_k]
        
        # 메타데이터 업데이트
        for result in selected_results:
            result.phase = f"phase4_adaptive_{complexity_type}"
            result.reasoning += f" | Selected k={final_k} for {complexity_type} query"
        
        processing_time = time.time() - start_time
        self.logger.info(f"Phase 4: {len(phase3_results)} → {len(selected_results)} 적응형 선택 ({complexity_type}, k={final_k}) ({processing_time:.3f}초)")
        
        return selected_results
    
    def _extract_domain_keywords(self, query: str) -> Dict[str, float]:
        """쿼리에서 도메인 키워드 추출"""
        found_keywords = {}
        query_lower = query.lower()
        
        for keyword, weight in self.domain_keywords.items():
            if keyword in query_lower:
                found_keywords[keyword] = weight
        
        return found_keywords
    
    @lru_cache(maxsize=1024)
    def _calculate_keyword_score_cached(self, content_hash: str, keywords_hash: str) -> float:
        """캐시된 키워드 점수 계산"""
        # 실제 계산은 _calculate_keyword_score에서
        return 0.0  # placeholder, will be overridden

    def _calculate_keyword_score(self, content: str, query_keywords: Dict[str, float]) -> float:
        """문서 내용에서 키워드 매칭 점수 계산"""
        if not query_keywords:
            return 0.0
        
        content_lower = content.lower()
        total_score = 0.0
        max_possible_score = sum(query_keywords.values())
        
        for keyword, weight in query_keywords.items():
            if keyword in content_lower:
                # 키워드 빈도에 따른 점수 (최대 가중치까지)
                frequency = content_lower.count(keyword)
                score = min(weight, weight * frequency * self.FREQUENCY_MULTIPLIER)
                total_score += score
        
        # 정규화 (0-1 범위)
        if max_possible_score > 0:
            return min(1.0, total_score / max_possible_score)
        return 0.0
    
    def process_full_pipeline(self, vector_results: List[Dict], 
                            bm25_results: List[Dict], 
                            query: str, reranker=None) -> Tuple[List[FilterResult], Dict[str, Any]]:
        """
        전체 4단계 필터링 파이프라인 실행
        """
        start_time = time.time()
        
        # Phase 1: 의미론적 필터링
        phase1_results = self.phase1_semantic_filtering(vector_results, query)
        
        # Phase 2: 키워드 강화
        phase2_results = self.phase2_keyword_enhancement(phase1_results, bm25_results, query)
        
        # Phase 3: 순위 재조정
        phase3_results = self.phase3_reranking(phase2_results, query, reranker)
        
        # Phase 4: 적응형 선택
        final_results = self.phase4_adaptive_selection(phase3_results, query)
        
        total_time = time.time() - start_time

        # 성능 통계 업데이트
        self.filter_count += 1
        self.total_filter_time += total_time

        # 복잡도 결과 가져오기 (phase4에서 이미 계산됨)
        complexity_result = self.complexity_analyzer.analyze(query)
        complexity_type = complexity_result['type']
        recommended_k = complexity_result['recommended_k']
        
        stats = {
            "total_processing_time": total_time,
            "phase_counts": {
                "phase1_semantic": len(phase1_results),
                "phase2_keyword": len(phase2_results),
                "phase3_reranking": len(phase3_results),
                "phase4_final": len(final_results)
            },
            "query_complexity": complexity_type,
            "recommended_k": recommended_k,
            "filtering_ratio": len(final_results) / len(vector_results) if vector_results else 0
        }
        
        self.logger.info(f"다단계 필터링 완료: {len(vector_results)} → {len(final_results)} ({total_time:.3f}초)")

        return final_results, stats

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        stats = {
            'filter_count': self.filter_count,
            'total_filter_time': self.total_filter_time,
            'avg_filter_time': self.total_filter_time / self.filter_count if self.filter_count > 0 else 0.0,
            'phase_stats': dict(self.phase_stats),
            'cache_info': self._calculate_keyword_score_cached.cache_info() if hasattr(self._calculate_keyword_score_cached, 'cache_info') else None
        }
        return stats