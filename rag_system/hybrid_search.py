"""
하이브리드 검색 시스템
벡터 검색 + BM25 검색을 RRF로 결합
"""

import os
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
import time
import re
from functools import lru_cache
import hashlib

from app.core.logging import get_logger

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .korean_vector_store import KoreanVectorStore
from .bm25_store import BM25Store
from .query_optimizer import QueryOptimizer
from .korean_reranker import KoreanReranker
from .query_expansion import QueryExpansion
from .document_compression import DocumentCompression
from .multilevel_filter import MultilevelFilter

# 검색 설정 상수 (.env에서 읽기)
DEFAULT_VECTOR_WEIGHT = float(os.getenv('SEARCH_VECTOR_WEIGHT', '0.1'))
DEFAULT_BM25_WEIGHT = float(os.getenv('SEARCH_BM25_WEIGHT', '0.9'))
DEFAULT_TOP_K = int(os.getenv('SEARCH_TOP_K', '5'))
DEFAULT_RRF_K = 20  # Reciprocal Rank Fusion 파라미터
DEFAULT_FUSION_METHOD = "weighted_sum"  # "rrf" 또는 "weighted_sum"

# 인덱스 경로 상수
DEFAULT_VECTOR_INDEX_PATH = "rag_system/db/korean_vector_index.faiss"
DEFAULT_BM25_INDEX_PATH = "rag_system/db/bm25_index.pkl"

# 결과 제한 상수
MAX_SEARCH_RESULTS = 100

class HybridSearch:
    """벡터 + BM25 하이브리드 검색"""
    
    def __init__(
        self,
        vector_index_path: str = None,
        bm25_index_path: str = None,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        bm25_weight: float = DEFAULT_BM25_WEIGHT,
        rrf_k: int = DEFAULT_RRF_K,
        use_reranker: bool = True,
        use_query_expansion: bool = True,
        use_document_compression: bool = True,
        use_multilevel_filter: bool = True,
        single_document_mode: bool = False,
        fusion_method: str = DEFAULT_FUSION_METHOD
    ):
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k  # RRF 파라미터
        self.use_reranker = use_reranker
        self.use_query_expansion = use_query_expansion
        self.use_document_compression = use_document_compression
        self.use_multilevel_filter = use_multilevel_filter
        self.single_document_mode = single_document_mode
        self.fusion_method = fusion_method

        self.logger = get_logger(__name__)
        self.query_optimizer = QueryOptimizer()

        # 검색 캐시 (쿼리 해시 -> 결과)
        self.search_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Advanced RAG 컴포넌트 초기화 (딥셔너리로 관리)
        self.optional_components = {
            'reranker': (use_reranker, KoreanReranker, "한국어 Reranker"),
            'query_expander': (use_query_expansion, QueryExpansion, "Query Expansion"),
            'doc_compressor': (use_document_compression, DocumentCompression, "Document Compression"),
            'multilevel_filter': (use_multilevel_filter, MultilevelFilter, "다단계 필터링 시스템")
        }

        for attr_name, (use_flag, component_class, component_name) in self.optional_components.items():
            self._init_optional_component(attr_name, use_flag, component_class, component_name)
        
        # 컴포넌트 초기화
        try:
            vector_path = vector_index_path or DEFAULT_VECTOR_INDEX_PATH
            bm25_path = bm25_index_path or DEFAULT_BM25_INDEX_PATH
            
            self.vector_store = KoreanVectorStore(index_path=vector_path)
            self.bm25_store = BM25Store(index_path=bm25_path)
            
            self.logger.info("하이브리드 검색 시스템 초기화 완료")
            
        except Exception as e:
            self.logger.error(f"하이브리드 검색 초기화 실패: {e}")
            raise
    
    def _init_optional_component(self, attr_name: str, use_flag: bool, component_class, component_name: str):
        """선택적 컴포넌트 초기화 헬퍼 메서드"""
        setattr(self, attr_name, None)
        if use_flag:
            try:
                setattr(self, attr_name, component_class())
                self.logger.info(f"{component_name} 초기화 완료")
            except Exception as e:
                self.logger.warning(f"{component_name} 초기화 실패, 비활성화: {e}")
                setattr(self, f"use_{attr_name.replace('_', '')}", False)
    
    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        """두 인덱스에 동시에 문서 추가"""
        try:
            self.vector_store.add_documents(texts, metadatas)
            self.bm25_store.add_documents(texts, metadatas)
            self.logger.info(f"{len(texts)}개 문서 하이브리드 인덱싱 완료")
        except Exception as e:
            self.logger.error(f"하이브리드 문서 추가 실패: {e}")
            raise
    
    def save_indexes(self):
        """두 인덱스 모두 저장"""
        try:
            self.vector_store.save_index()
            self.bm25_store.save_index()
            self.logger.info("하이브리드 인덱스 저장 완료")
        except Exception as e:
            self.logger.error(f"하이브리드 인덱스 저장 실패: {e}")
            raise
    
    def _get_doc_id(self, result: Dict[str, Any]) -> str:
        """문서 ID 추출 헬퍼 메서드"""
        return result.get('chunk_id', result.get('doc_id', result.get('source', '')))

    def _remove_duplicates(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """중복 제거 헬퍼 메서드"""
        seen_ids: Set[str] = set()
        unique_results = []

        for result in results:
            doc_id = self._get_doc_id(result)
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_results.append(result)

        return unique_results

    def _normalize_scores(self, results: List[Dict[str, Any]], score_key: str = 'score') -> List[Dict[str, Any]]:
        """스코어 정규화 (0~1 범위로)"""
        if not results:
            return results

        scores = [r[score_key] for r in results]
        min_score = min(scores)
        max_score = max(scores)

        # 정규화
        if max_score > min_score:
            for result in results:
                normalized = (result[score_key] - min_score) / (max_score - min_score)
                result[f'normalized_{score_key}'] = normalized
        else:
            for result in results:
                result[f'normalized_{score_key}'] = 1.0

        return results
    
    def _reciprocal_rank_fusion(
        self, 
        vector_results: List[Dict[str, Any]], 
        bm25_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """RRF로 결과 융합"""
        
        # 문서별 RRF 스코어 계산
        doc_scores = {}
        
        # 벡터 검색 결과의 RRF 스코어
        for rank, result in enumerate(vector_results):
            doc_id = result.get('chunk_id', result.get('doc_id', str(rank)))
            rrf_score = 1.0 / (self.rrf_k + rank + 1)
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    'vector_rrf': 0.0,
                    'bm25_rrf': 0.0,
                    'vector_result': None,
                    'bm25_result': None
                }
            
            doc_scores[doc_id]['vector_rrf'] = rrf_score
            doc_scores[doc_id]['vector_result'] = result
        
        # BM25 검색 결과의 RRF 스코어
        for rank, result in enumerate(bm25_results):
            doc_id = result.get('chunk_id', result.get('doc_id', str(rank)))
            rrf_score = 1.0 / (self.rrf_k + rank + 1)
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    'vector_rrf': 0.0,
                    'bm25_rrf': 0.0,
                    'vector_result': None,
                    'bm25_result': None
                }
            
            doc_scores[doc_id]['bm25_rrf'] = rrf_score
            doc_scores[doc_id]['bm25_result'] = result
        
        # 최종 RRF 스코어 계산 및 정렬
        final_results = []
        
        for doc_id, scores in doc_scores.items():
            # 가중 RRF 스코어
            final_rrf = (
                self.vector_weight * scores['vector_rrf'] + 
                self.bm25_weight * scores['bm25_rrf']
            )
            
            # 결과 구성 (벡터 결과 우선, 없으면 BM25 결과)
            base_result = scores['vector_result'] or scores['bm25_result']
            if base_result:
                final_result = {
                    **base_result,
                    'hybrid_score': final_rrf,
                    'vector_score': scores['vector_result']['score'] if scores['vector_result'] else 0.0,
                    'bm25_score': scores['bm25_result']['score'] if scores['bm25_result'] else 0.0,
                    'vector_rrf': scores['vector_rrf'],
                    'bm25_rrf': scores['bm25_rrf'],
                    'fusion_method': 'RRF'
                }
                final_results.append(final_result)
        
        # 하이브리드 스코어로 정렬
        final_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        
        # 순위 재부여
        for i, result in enumerate(final_results):
            result['rank'] = i + 1
        
        return final_results
    
    def _fuse_with_weighted_sum(self, vector_results: List[Dict], 
                               bm25_results: List[Dict]) -> List[Dict[str, Any]]:
        """단순 가중합을 사용한 융합 (RRF 대신)"""
        
        # 점수 정규화를 위한 최대값 계산
        vector_max_score = max([r.get('score', 0) for r in vector_results]) if vector_results else 1.0
        bm25_max_score = max([r.get('score', 0) for r in bm25_results]) if bm25_results else 1.0
        
        # 문서별 점수 수집
        doc_scores = {}
        
        # 벡터 검색 결과 처리
        for result in vector_results:
            doc_id = result.get('chunk_id', result.get('doc_id', result.get('filename', 'unknown')))
            normalized_score = result.get('score', 0) / vector_max_score
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    'vector_score': 0.0,
                    'bm25_score': 0.0,
                    'vector_result': None,
                    'bm25_result': None
                }
            
            doc_scores[doc_id]['vector_score'] = normalized_score
            doc_scores[doc_id]['vector_result'] = result
        
        # BM25 검색 결과 처리
        for result in bm25_results:
            doc_id = result.get('chunk_id', result.get('doc_id', result.get('filename', 'unknown')))
            normalized_score = result.get('score', 0) / bm25_max_score
            
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {
                    'vector_score': 0.0,
                    'bm25_score': 0.0,
                    'vector_result': None,
                    'bm25_result': None
                }
            
            doc_scores[doc_id]['bm25_score'] = normalized_score
            doc_scores[doc_id]['bm25_result'] = result
        
        # 가중합 계산 및 최종 결과 생성
        final_results = []
        
        for doc_id, scores in doc_scores.items():
            # 가중합 스코어 계산
            weighted_score = (
                self.vector_weight * scores['vector_score'] + 
                self.bm25_weight * scores['bm25_score']
            )
            
            # 결과 구성 (BM25 결과 우선, 없으면 벡터 결과)
            base_result = scores['bm25_result'] or scores['vector_result']
            if base_result and weighted_score > 0:
                final_result = {
                    **base_result,
                    'hybrid_score': weighted_score,
                    'vector_score': scores['vector_score'],
                    'bm25_score': scores['bm25_score'],
                    'fusion_method': 'weighted_sum'
                }
                final_results.append(final_result)
        
        # 하이브리드 스코어로 정렬
        final_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        
        # 순위 재부여
        for i, result in enumerate(final_results):
            result['rank'] = i + 1
        
        return final_results
    
    def _extract_year_from_query(self, query: str) -> Optional[str]:
        """쿼리에서 연도 정보 추출"""
        # 2024년, 2024, 24년 등 패턴 감지
        year_patterns = [
            r'(20\d{2})년',  # 2024년
            r'(20\d{2})',    # 2024
            r'(\d{2})년'     # 24년
        ]
        
        for pattern in year_patterns:
            match = re.search(pattern, query)
            if match:
                year_str = match.group(1)
                # 2자리 년도를 4자리로 변환 (24 → 2024)
                if len(year_str) == 2:
                    year_str = "20" + year_str
                return year_str
        return None
    
    def _apply_date_filtering(self, results: List[Dict[str, Any]], target_year: str) -> List[Dict[str, Any]]:
        """날짜 기반 필터링으로 결과 순위 조정"""
        if not target_year:
            return results
        
        boosted_results = []
        other_results = []
        
        for result in results:
            filename = result.get('filename', '')
            source = result.get('source', '')
            
            # 파일명이나 소스에서 년도 검사
            if target_year in filename or target_year in source:
                # 점수 부스트 (1.5배)
                if 'hybrid_score' in result:
                    result['hybrid_score'] *= 1.5
                    result['date_boosted'] = True
                boosted_results.append(result)
            else:
                other_results.append(result)
        
        # 부스트된 결과를 앞에 배치하고 점수순 재정렬
        all_results = boosted_results + other_results
        all_results.sort(key=lambda x: x.get('hybrid_score', 0), reverse=True)
        
        # 순위 재부여
        for i, result in enumerate(all_results):
            result['rank'] = i + 1
        
        return all_results
    
    def _extract_keywords_from_query(self, query: str) -> Dict[str, List[str]]:
        """쿼리에서 중요 키워드 추출"""
        keywords = {
            'amounts': [],
            'proper_nouns': [],
            'model_codes': []
        }
        
        # 금액 패턴 (2,370,000원, 237만원 등)
        amount_patterns = [
            r'[\d,]+원',       # 2,370,000원
            r'\d+만원',        # 237만원  
            r'\d+억원',        # 23억원
            r'[\d,]+',         # 2,370,000 (원 없이도)
            r'\d{1,3}(?:,\d{3})*'  # 컴마 구분 숫자
        ]
        for pattern in amount_patterns:
            matches = re.findall(pattern, query)
            keywords['amounts'].extend(matches)
        
        # 모델 코드 (ECM-77BC, HP Z8 등)
        model_patterns = [
            r'[A-Z]+-[0-9A-Z]+',  # ECM-77BC
            r'[A-Z]+\s+[A-Z0-9]+' # HP Z8
        ]
        for pattern in model_patterns:
            matches = re.findall(pattern, query)
            keywords['model_codes'].extend(matches)
        
        # 한국어 고유명사 (간단한 패턴)
        # 2-4글자 한글 단어 중 ㅇ으로 끝나는 경우 (예: 남준수, 노규민)
        korean_name_pattern = r'[가-힣]{2,4}'
        potential_names = re.findall(korean_name_pattern, query)
        for name in potential_names:
            if len(name) >= 3:  # 3글자 이상만 고유명사로 간주
                keywords['proper_nouns'].append(name)
        
        return keywords
    
    def _apply_keyword_boosting(self, results: List[Dict[str, Any]], keywords: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """키워드 정확 매칭 기반 점수 부스트"""
        if not any(keywords.values()):
            return results
        
        for result in results:
            content = result.get('content', '')
            filename = result.get('filename', '')
            boost_factor = 1.0
            boost_reasons = []
            
            # 금액 정확 매칭 (가장 중요)
            for amount in keywords['amounts']:
                # 정확 매칭
                if amount in content or amount in filename:
                    boost_factor *= 2.0  # 2배 부스트
                    boost_reasons.append(f"금액_정확매칭_{amount}")
                else:
                    # 숫자만 매칭 (콤마 제거 후)
                    clean_amount = amount.replace(',', '').replace('원', '')
                    if clean_amount.isdigit() and len(clean_amount) >= 4:
                        if clean_amount in content.replace(',', '') or clean_amount in filename.replace(',', ''):
                            boost_factor *= 1.8  # 1.8배 부스트
                            boost_reasons.append(f"금액_숫자매칭_{clean_amount}")
            
            # 모델 코드 매칭
            for model in keywords['model_codes']:
                if model in content or model in filename:
                    boost_factor *= 1.7  # 1.7배 부스트
                    boost_reasons.append(f"모델_매칭_{model}")
            
            # 고유명사 매칭
            for name in keywords['proper_nouns']:
                if name in content or name in filename:
                    boost_factor *= 1.5  # 1.5배 부스트
                    boost_reasons.append(f"이름_매칭_{name}")
            
            # 부스트 적용
            if boost_factor > 1.0:
                if 'hybrid_score' in result:
                    result['hybrid_score'] *= boost_factor
                result['keyword_boosted'] = True
                result['boost_factor'] = boost_factor
                result['boost_reasons'] = boost_reasons
        
        # 점수순 재정렬
        results.sort(key=lambda x: x.get('hybrid_score', 0), reverse=True)
        
        # 순위 재부여
        for i, result in enumerate(results):
            result['rank'] = i + 1
        
        return results
    
    def search(self, query: str, top_k: int = 5, include_debug: bool = False) -> Dict[str, Any]:
        """하이브리드 검색 수행 (문서별 검색 보장 포함)"""
        start_time = time.time()
        
        try:
            # 0. 특정 문서 지정 확인 (최우선)
            target_document = self._extract_document_name_from_query(query)
            if target_document:
                self.logger.info(f"문서별 검색 모드: {target_document}")
                return self._search_specific_document(query, target_document, top_k, include_debug)
            
            # 1. 쿼리에서 년도 및 키워드 추출
            target_year = self._extract_year_from_query(query)
            keywords = self._extract_keywords_from_query(query)
            # 1. Query Expansion (선택적)
            expansion_time = 0.0
            expanded_queries = [query]  # 원본 쿼리는 항상 포함
            expansion_info = None
            
            if self.use_query_expansion and self.query_expander:
                expansion_start = time.time()
                expansion_result = self.query_expander.expand_query(query)
                expansion_time = time.time() - expansion_start
                
                # 확장된 쿼리 추가 (상위 몇 개만)
                expanded_queries.extend(expansion_result['expanded_queries'][:2])  # 최대 2개 추가
                expansion_info = {
                    'total_expansions': len(expansion_result['expanded_queries']),
                    'used_expansions': min(2, len(expansion_result['expanded_queries'])),
                    'expansion_time': expansion_time
                }
                self.logger.info(f"Query expansion: {len(expanded_queries)}개 쿼리 생성 (시간: {expansion_time:.3f}초)")
            
            # 2. 쿼리 전처리: 한국어 조사 제거 (모든 쿼리에 적용)
            cleaned_queries = []
            for q in expanded_queries:
                cleaned = self.query_optimizer.clean_query_for_search(q)
                cleaned_queries.append(cleaned)
            
            self.logger.info(f"Query cleaning: {len(cleaned_queries)}개 쿼리 전처리 완료")
            
            # 3. 개별 검색 수행 (확장된 쿼리들로)
            all_vector_results = []
            all_bm25_results = []
            
            vector_start = time.time()
            for cleaned_query in cleaned_queries:
                vector_results = self.vector_store.search(cleaned_query, top_k=top_k * 2)
                all_vector_results.extend(vector_results)
            vector_time = time.time() - vector_start
            
            bm25_start = time.time()
            for cleaned_query in cleaned_queries:
                bm25_results = self.bm25_store.search(cleaned_query, top_k=top_k * 2)
                all_bm25_results.extend(bm25_results)
            bm25_time = time.time() - bm25_start
            
            # 중복 제거 (chunk_id 기준)
            seen_vector = set()
            unique_vector_results = []
            for result in all_vector_results:
                chunk_id = result.get('chunk_id', result.get('doc_id', ''))
                if chunk_id not in seen_vector:
                    seen_vector.add(chunk_id)
                    unique_vector_results.append(result)
            
            seen_bm25 = set()
            unique_bm25_results = []
            for result in all_bm25_results:
                chunk_id = result.get('chunk_id', result.get('doc_id', ''))
                if chunk_id not in seen_bm25:
                    seen_bm25.add(chunk_id)
                    unique_bm25_results.append(result)
            
            # 4. 다단계 필터링 적용 (신규)
            multilevel_stats = None
            if self.use_multilevel_filter and self.multilevel_filter:
                # 더 많은 후보 확보 (기존의 3배 → 대용량 필터링용으로 10배)
                vector_results_large = unique_vector_results[:top_k * 10]
                bm25_results_large = unique_bm25_results[:top_k * 10]

                # 스키마 정규화 (multilevel_filter 실행 전에 필수!)
                normalized_vector = []
                for result in vector_results_large:
                    result_id = result.get('chunk_id') or result.get('doc_id') or result.get('id') or result.get('filename', 'unknown')
                    normalized_vector.append({
                        'chunk_id': result_id,
                        'doc_id': result_id,
                        **result
                    })

                normalized_bm25 = []
                for result in bm25_results_large:
                    result_id = result.get('chunk_id') or result.get('doc_id') or result.get('id') or result.get('filename', 'unknown')
                    normalized_bm25.append({
                        'chunk_id': result_id,
                        'doc_id': result_id,
                        **result
                    })

                # 스코어 정규화
                vector_results_large = self._normalize_scores(normalized_vector, 'similarity')
                bm25_results_large = self._normalize_scores(normalized_bm25, 'score')
                
                # 다단계 필터링 파이프라인 실행
                multilevel_start = time.time()
                filtered_results, multilevel_stats = self.multilevel_filter.process_full_pipeline(
                    vector_results=vector_results_large,
                    bm25_results=bm25_results_large,
                    query=query,
                    reranker=self.reranker if self.use_reranker else None
                )
                multilevel_time = time.time() - multilevel_start
                
                # FilterResult를 기존 형식으로 변환
                fused_results = []
                for filter_result in filtered_results:
                    # 원본 vector/bm25 결과에서 메타데이터 가져오기
                    original_result = None
                    for vr in vector_results_large:
                        if vr.get('chunk_id') == filter_result.chunk_id:
                            original_result = vr
                            break
                    if not original_result:
                        for br in bm25_results_large:
                            if br.get('chunk_id') == filter_result.chunk_id:
                                original_result = br
                                break
                    
                    result_dict = {
                        'chunk_id': filter_result.chunk_id,
                        'content': filter_result.content,
                        'hybrid_score': filter_result.score,
                        'multilevel_phase': filter_result.phase,
                        'filter_reasoning': filter_result.reasoning,
                        'metadata': filter_result.metadata
                    }
                    
                    # 원본 결과의 추가 필드들 병합
                    if original_result:
                        result_dict.update({
                            k: v for k, v in original_result.items() 
                            if k not in result_dict
                        })
                    
                    fused_results.append(result_dict)
                
                # 시간 정보 업데이트
                multilevel_stats['multilevel_time'] = multilevel_time
                fusion_time = multilevel_stats.get('total_processing_time', multilevel_time)
                rerank_time = 0.0  # 다단계 필터링에 포함됨
                
                self.logger.info(f"다단계 필터링 완료: {len(vector_results_large)} → {len(fused_results)} (시간: {multilevel_time:.3f}초)")
            
            else:
                # 기존 방식 (다단계 필터링 비활성화 시)
                vector_results = unique_vector_results[:top_k * 3]
                bm25_results = unique_bm25_results[:top_k * 3]
                
                # 스코어 정규화
                vector_results = self._normalize_scores(vector_results, 'similarity')
                bm25_results = self._normalize_scores(bm25_results, 'score')
                
                # 융합 방법에 따라 결과 융합
                fusion_start = time.time()
                if self.fusion_method == "weighted_sum":
                    fused_results = self._fuse_with_weighted_sum(vector_results, bm25_results)
                else:
                    fused_results = self._reciprocal_rank_fusion(vector_results, bm25_results)
                fusion_time = time.time() - fusion_start
                
                # Reranker 적용 (선택적)
                rerank_time = 0.0
                if self.use_reranker and self.reranker and len(fused_results) > 1:
                    rerank_start = time.time()
                    fused_results = self.reranker.rerank_documents(query, fused_results[:top_k * 2], top_k)
                    rerank_time = time.time() - rerank_start
                    self.logger.info(f"Reranker 적용 완료 (시간: {rerank_time:.3f}초)")
                else:
                    fused_results = fused_results[:top_k]
            
            # 5. Document Compression 적용 (선택적)
            compression_time = 0.0
            compression_info = None
            
            if self.use_document_compression and self.doc_compressor and fused_results:
                compression_start = time.time()
                
                # 검색 결과를 Document Compression이 기대하는 형식으로 변환
                documents_for_compression = []
                for result in fused_results:
                    doc = {
                        'content': result.get('content', ''),
                        'filename': result.get('filename', ''),
                        'score': result.get('hybrid_score', result.get('score', 0.0)),
                        # 기타 메타데이터 유지
                        'doc_id': result.get('doc_id', ''),
                        'chunk_id': result.get('chunk_id', ''),
                        'metadata': result.get('metadata', {})
                    }
                    documents_for_compression.append(doc)
                
                # 문서 압축 수행
                compression_result = self.doc_compressor.compress_documents(
                    documents=documents_for_compression,
                    query=query,
                    target_length=500,  # 문서당 목표 길이
                    compression_ratio=0.7  # 70% 유지
                )
                
                compression_time = time.time() - compression_start
                
                # 압축된 결과를 원래 형식으로 다시 변환
                if compression_result['compressed_documents']:
                    compressed_final_results = []
                    for i, compressed_doc in enumerate(compression_result['compressed_documents']):
                        # 원본 결과에서 메타데이터 가져오기
                        original_result = fused_results[i] if i < len(fused_results) else {}
                        
                        compressed_result = {
                            **original_result,  # 원본 필드들 유지
                            'content': compressed_doc['content'],  # 압축된 내용으로 대체
                            'original_content_length': compressed_doc.get('original_length', 0),
                            'compressed_content_length': compressed_doc.get('compressed_length', 0),
                            'compression_ratio': compressed_doc.get('compression_ratio', 1.0),
                            'sentences_kept': compressed_doc.get('sentences_kept', 0),
                            'sentences_total': compressed_doc.get('sentences_total', 0)
                        }
                        compressed_final_results.append(compressed_result)
                    
                    final_results = compressed_final_results
                    compression_info = {
                        'applied': True,
                        'original_total_chars': compression_result['compression_stats']['original_total_chars'],
                        'compressed_total_chars': compression_result['compression_stats']['compressed_total_chars'],
                        'compression_ratio': compression_result['compression_stats']['compression_ratio'],
                        'processing_time': compression_time
                    }
                    self.logger.info(f"Document compression 적용 완료 (압축률: {compression_info['compression_ratio']:.2f}, 시간: {compression_time:.3f}초)")
                else:
                    final_results = fused_results
                    compression_info = {'applied': False, 'reason': 'compression_failed'}
            else:
                final_results = fused_results
                compression_info = {'applied': False, 'reason': 'disabled_or_no_results'}
            
            # 6. 날짜 기반 필터링 적용 (새로 추가)
            if target_year:
                final_results = self._apply_date_filtering(final_results, target_year)
                self.logger.info(f"날짜 필터링 적용: {target_year}년 문서 우선순위 부스트")
            
            # 7. 키워드 정확 매칭 부스트 적용 (새로 추가)
            if any(keywords.values()):
                final_results = self._apply_keyword_boosting(final_results, keywords)
                self.logger.info(f"키워드 부스팅 적용: {sum(len(v) for v in keywords.values())}개 키워드")
            
            # 8. 단일 문서 모드 적용 (환각 방지 강화)
            if self.single_document_mode and final_results:
                # 가장 높은 점수의 문서만 선택
                best_document_source = final_results[0].get('source', '')
                best_document_score = final_results[0].get('score', 0.0)
                single_doc_results = []

                # 점수 임계값 설정 (너무 낮은 점수 문서는 제외)
                score_threshold = max(0.1, best_document_score * 0.7)

                for result in final_results:
                    if (result.get('source', '') == best_document_source and
                        result.get('score', 0.0) >= score_threshold):
                        single_doc_results.append(result)

                    # 최대 3개 청크만 (같은 문서에서 고품질만)
                    if len(single_doc_results) >= 3:
                        break

                # 단일 문서에서 충분한 청크가 있을 때만 적용
                if len(single_doc_results) >= 2:
                    final_results = single_doc_results
                    self.logger.info(f"단일 문서 모드 적용: {best_document_source} - {len(final_results)}개 청크 (점수 임계값: {score_threshold:.3f})")
                else:
                    self.logger.info(f"단일 문서 모드 취소: 충분한 청크 없음 ({len(single_doc_results)}개 < 2개)")
                    # 원래 결과 유지하되 상위 3개로 제한
                    final_results = final_results[:3]

            # 9. 스키마 정규화: chunk_id, doc_id, snippet, page, meta 보장
            normalized_results = []
            for result in final_results:
                # ID 추출 (우선순위: chunk_id > doc_id > id > filename)
                result_id = result.get('chunk_id') or result.get('doc_id') or result.get('id') or result.get('filename', 'unknown')

                normalized = {
                    'chunk_id': result_id,
                    'doc_id': result_id,
                    'snippet': result.get('snippet') or result.get('content', ''),
                    'page': result.get('page', 0),
                    'meta': result.get('meta') or result.get('metadata', {}),
                    # 기존 필드 유지 (하위 호환성)
                    **{k: v for k, v in result.items() if k not in ['chunk_id', 'doc_id', 'snippet', 'page', 'meta']}
                }
                normalized_results.append(normalized)

            total_time = time.time() - start_time

            search_result = {
                'fused_results': normalized_results,
                'search_time': total_time,
                'timing': {
                    'expansion_time': expansion_time,
                    'vector_time': vector_time,
                    'bm25_time': bm25_time,
                    'fusion_time': fusion_time,
                    'rerank_time': rerank_time,
                    'compression_time': compression_time,
                    'total_time': total_time
                }
            }
            
            # 디버그 정보 추가
            if include_debug:
                debug_info = {
                    'vector_results': vector_results[:top_k],
                    'bm25_results': bm25_results[:top_k],
                    'fusion_method': 'RRF',
                    'weights': {
                        'vector': self.vector_weight,
                        'bm25': self.bm25_weight
                    },
                    'parameters': {
                        'rrf_k': self.rrf_k
                    },
                    'reranker_enabled': self.use_reranker,
                    'reranker_applied': rerank_time > 0.0,
                    'query_expansion_enabled': self.use_query_expansion,
                    'document_compression_enabled': self.use_document_compression,
                    'multilevel_filter_enabled': self.use_multilevel_filter
                }
                
                # Query Expansion 디버그 정보 추가
                if expansion_info:
                    debug_info['query_expansion'] = expansion_info
                    debug_info['expanded_queries'] = expanded_queries
                
                # Document Compression 디버그 정보 추가  
                if compression_info:
                    debug_info['document_compression'] = compression_info
                
                # Multilevel Filter 디버그 정보 추가
                if multilevel_stats:
                    debug_info['multilevel_filter'] = multilevel_stats
                
                search_result.update(debug_info)
            
            return search_result
            
        except Exception as e:
            self.logger.error(f"하이브리드 검색 실패: {e}")
            return {
                'fused_results': [],
                'search_time': time.time() - start_time,
                'error': str(e)
            }
    
    def should_use_full_document_mode(self, query: str) -> Tuple[bool, str]:
        """질문을 분석해서 전체 문서 모드를 사용할지 결정"""
        
        # 전체 문서 모드 트리거 키워드
        full_document_keywords = [
            '자세히', '상세히', '세부사항', '모든', '전체', '모두', 
            '요약', '정리', '내용', '빠짐없이', '완전히', '상세하게',
            '디테일', '구체적으로', '포괄적으로', '총정리', '전반적으로',
            '전문', '완전한', '상세한', '자세한', '종합적으로'
        ]
        
        # 문서 요약 키워드
        summary_keywords = [
            '요약', '정리', '개요', '총정리', '종합', '정리해서', '요약해서',
            '요약해줘', '정리해줘', '종합해서'
        ]
        
        # 1. 전체 문서 키워드 체크
        for keyword in full_document_keywords:
            if keyword in query:
                return True, f"키워드 '{keyword}' 감지"
        
        # 2. 문서 요약 요청 체크
        for keyword in summary_keywords:
            if keyword in query:
                return True, f"요약 요청 '{keyword}' 감지"
        
        # 3. 질문 길이 체크 (긴 질문은 복잡한 정보 요구)
        if len(query) > 50:
            return True, "복잡한 질문 (50자 이상)"
        
        # 4. 다중 조건 체크 ('그리고', '또한', '각각' 등)
        multi_conditions = ['그리고', '또한', '각각', '모두', '전부', '모든']
        for cond in multi_conditions:
            if cond in query:
                return True, f"다중 조건 '{cond}' 감지"
                
        return False, "간단한 사실 확인 질문"
    
    def load_full_document(self, file_path: str) -> Optional[str]:
        """전체 PDF 문서 내용 로드"""
        if pdfplumber is None:
            self.logger.error("pdfplumber가 설치되지 않았습니다. 'pip install pdfplumber' 실행 필요")
            return None
        
        try:
            full_text = ""
            
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        full_text += f"{page_text}\n"
            
            return full_text.strip() if full_text.strip() else None
        except Exception as e:
            self.logger.error(f"PDF 로드 실패 ({file_path}): {e}")
            return None
    
    def search_with_smart_mode(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """스마트 모드: 질문 유형에 따라 자동으로 청크 검색 vs 전체 문서 선택"""
        
        # 모드 결정
        use_full_mode, reason = self.should_use_full_document_mode(query)
        
        self.logger.info(f"스마트 모드 선택: {'전체 문서' if use_full_mode else '청크 검색'} ({reason})")
        
        if use_full_mode:
            return self._search_with_full_document(query)
        else:
            # 기존 청크 검색
            search_results = self.search(query, top_k=top_k)
            return {
                'mode': 'chunk_search',
                'reason': reason,
                'search_results': search_results,
                'success': len(search_results.get('fused_results', [])) > 0
            }
    
    def _search_with_full_document(self, query: str) -> Dict[str, Any]:
        """전체 문서 모드로 검색"""
        
        # 먼저 관련 문서 찾기 (단일 문서 모드)
        search_results = self.search(query, top_k=1)
        context_chunks = search_results.get('fused_results', [])
        
        if not context_chunks:
            return {
                'mode': 'full_document',
                'reason': '전체 문서 모드',
                'success': False,
                'error': '관련 문서를 찾을 수 없습니다.'
            }
        
        # 가장 관련성 높은 문서의 전체 내용 로드
        best_chunk = context_chunks[0]
        file_path = best_chunk.get('file_path', best_chunk.get('source', ''))
        
        if not file_path or not os.path.exists(file_path):
            return {
                'mode': 'full_document',
                'reason': '전체 문서 모드',
                'success': False,
                'error': '문서 파일을 찾을 수 없습니다.'
            }
        
        # 전체 문서 로드
        full_document_text = self.load_full_document(file_path)
        
        if not full_document_text:
            return {
                'mode': 'full_document',
                'reason': '전체 문서 모드',
                'success': False,
                'error': '문서를 읽을 수 없습니다.'
            }
        
        self.logger.info(f"전체 문서 로드: {Path(file_path).name} ({len(full_document_text):,}자)")
        
        # 전체 문서를 하나의 큰 청크로 구성
        full_doc_chunk = {
            'source': file_path,
            'content': full_document_text,
            'score': 1.0,  # 최고 점수
            'metadata': best_chunk.get('metadata', {}),
            'rank': 1
        }
        
        return {
            'mode': 'full_document',
            'reason': '전체 문서 모드',
            'success': True,
            'document_path': file_path,
            'document_length': len(full_document_text),
            'full_document_chunk': full_doc_chunk,
            'search_results': {
                'fused_results': [full_doc_chunk],
                'total_results': 1,
                'timing': {'total_time': 0.0}
            }
        }
    
    def _extract_document_name_from_query(self, query: str) -> Optional[str]:
        """쿼리에서 특정 PDF 파일명 추출"""
        # PDF 파일명 패턴 추출 (확장자 포함/미포함 모두)
        pdf_patterns = [
            r'(\d{4}[-_]\d{2}[-_]\d{2}[^.]*\.pdf)',  # 완전한 PDF 파일명
            r'(\d{4}[-_]\d{2}[-_]\d{2}[^.\s]*)',     # 확장자 없는 파일명
        ]
        
        for pattern in pdf_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                filename = matches[0]
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                return filename
        
        return None
    
    def _search_specific_document(self, query: str, target_document: str, top_k: int, include_debug: bool) -> Dict[str, Any]:
        """특정 문서에서만 검색 수행 (일관성 보장)"""
        start_time = time.time()
        
        try:
            # 벡터 검색에서 특정 문서 필터링
            vector_results = []
            if self.vector_store and self.vector_store.index.ntotal > 0:
                all_vector_results = self.vector_store.search(query, top_k=50)  # 넉넉히 검색
                for result in all_vector_results:
                    if result.get('filename', '').lower() == target_document.lower():
                        vector_results.append(result)
                vector_results = vector_results[:top_k]  # 상위 K개만
            
            # BM25 검색에서 특정 문서 필터링
            bm25_results = []
            if self.bm25_store:
                all_bm25_results = self.bm25_store.search(query, top_k=50)
                for result in all_bm25_results:
                    if result.get('filename', '').lower() == target_document.lower():
                        bm25_results.append(result)
                bm25_results = bm25_results[:top_k]
            
            # 결과가 없으면 에러 반환
            if not vector_results and not bm25_results:
                self.logger.error(f"지정된 문서에서 검색 결과 없음: {target_document}")
                return {
                    'fused_results': [],
                    'vector_results': [],
                    'bm25_results': [],
                    'processing_time': time.time() - start_time,
                    'error': f"문서 '{target_document}'에서 관련 내용을 찾을 수 없습니다.",
                    'target_document': target_document
                }
            
            # 점수 융합 (특정 문서 내에서만)
            if self.fusion_method == "weighted_sum":
                fused_results = self._fuse_with_weighted_sum(vector_results, bm25_results)
            else:
                fused_results = self._reciprocal_rank_fusion(vector_results, bm25_results)
            
            # top_k로 제한
            fused_results = fused_results[:top_k]
            
            # 모든 결과가 지정된 문서에서 나왔는지 검증
            for result in fused_results:
                if result.get('filename', '').lower() != target_document.lower():
                    self.logger.warning(f"문서 필터링 실패: {result.get('filename')} != {target_document}")

            # 스키마 정규화 적용
            normalized_results = []
            for result in fused_results:
                # ID 추출 (우선순위: chunk_id > doc_id > id > filename)
                result_id = result.get('chunk_id') or result.get('doc_id') or result.get('id') or result.get('filename', 'unknown')

                normalized = {
                    'chunk_id': result_id,
                    'doc_id': result_id,
                    'snippet': result.get('snippet') or result.get('content', ''),
                    'page': result.get('page', 0),
                    'meta': result.get('meta') or result.get('metadata', {}),
                    **{k: v for k, v in result.items() if k not in ['chunk_id', 'doc_id', 'snippet', 'page', 'meta']}
                }
                normalized_results.append(normalized)

            return {
                'fused_results': normalized_results,
                'vector_results': vector_results,
                'bm25_results': bm25_results,
                'processing_time': time.time() - start_time,
                'target_document': target_document,
                'document_specific_search': True
            }
            
        except Exception as e:
            self.logger.error(f"문서별 검색 실패: {e}")
            return {
                'fused_results': [],
                'vector_results': [],
                'bm25_results': [],
                'processing_time': time.time() - start_time,
                'error': str(e),
                'target_document': target_document
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """하이브리드 검색 통계"""
        try:
            vector_stats = self.vector_store.get_stats()
            bm25_stats = self.bm25_store.get_stats()
            
            return {
                'hybrid_config': {
                    'vector_weight': self.vector_weight,
                    'bm25_weight': self.bm25_weight,
                    'rrf_k': self.rrf_k
                },
                'vector_store': vector_stats,
                'bm25_store': bm25_stats
            }
        except Exception as e:
            self.logger.error(f"하이브리드 통계 조회 실패: {e}")
            return {'error': str(e)}
    
    def update_weights(self, vector_weight: float, bm25_weight: float):
        """검색 가중치 업데이트"""
        if vector_weight + bm25_weight != 1.0:
            self.logger.warning(f"가중치 합이 1.0이 아닙니다: {vector_weight + bm25_weight}")
        
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.logger.info(f"가중치 업데이트: 벡터={vector_weight}, BM25={bm25_weight}")

# 테스트 함수
def test_hybrid_search():
    """하이브리드 검색 테스트"""
    print("🔍 하이브리드 검색 테스트 시작")
    
    # 테스트 데이터
    test_texts = [
        "핀마이크 모델 ECM-77BC를 구매 검토합니다. 가격은 336,000원입니다.",
        "영상편집팀 워크스테이션 교체 비용은 179,300,000원입니다. HP Z8 모델입니다.",
        "광화문 스튜디오 모니터 교체 총액은 9,760,000원입니다. LG 모니터 3대입니다.",
        "카메라 장비 구매를 위한 예산 검토서입니다. 총 예산은 50,000,000원입니다.",
        "스튜디오 조명 시설 교체에 대한 기안서입니다. 필립스 LED 조명 20대를 구매합니다."
    ]
    
    test_metadatas = [
        {
            'doc_id': 'doc1',
            'chunk_id': 'chunk1_1',
            'filename': '2021-05-13_핀마이크_구매검토.pdf',
            'content': test_texts[0],
            'metadata': {'doc_type': '기안서', 'amount': 336000}
        },
        {
            'doc_id': 'doc2',
            'chunk_id': 'chunk2_1',
            'filename': '2022-02-03_워크스테이션_교체검토.pdf',
            'content': test_texts[1],
            'metadata': {'doc_type': '검토서', 'amount': 179300000}
        },
        {
            'doc_id': 'doc3',
            'chunk_id': 'chunk3_1',
            'filename': '2025-01-09_모니터_교체검토.pdf',
            'content': test_texts[2],
            'metadata': {'doc_type': '기안서', 'amount': 9760000}
        },
        {
            'doc_id': 'doc4',
            'chunk_id': 'chunk4_1',
            'filename': '2023-07-15_카메라장비_예산검토.pdf',
            'content': test_texts[3],
            'metadata': {'doc_type': '예산서', 'amount': 50000000}
        },
        {
            'doc_id': 'doc5',
            'chunk_id': 'chunk5_1',
            'filename': '2024-03-20_조명시설_교체기안.pdf',
            'content': test_texts[4],
            'metadata': {'doc_type': '기안서', 'amount': 0}
        }
    ]
    
    try:
        # 하이브리드 검색 시스템 생성 (.env 설정 사용)
        hybrid = HybridSearch(
            vector_index_path="rag_system/db/test_hybrid_vector.faiss",
            bm25_index_path="rag_system/db/test_hybrid_bm25.pkl",
            vector_weight=DEFAULT_VECTOR_WEIGHT,
            bm25_weight=DEFAULT_BM25_WEIGHT
        )
        
        # 문서 추가
        print("📝 테스트 문서 추가 중...")
        hybrid.add_documents(test_texts, test_metadatas)
        
        # 인덱스 저장
        hybrid.save_indexes()
        
        # 검색 테스트
        test_queries = [
            "핀마이크 가격은 얼마인가요?",
            "워크스테이션 HP Z8",
            "모니터 3대",
            "카메라 예산 5000만원",
            "LED 조명 교체"
        ]
        
        for query in test_queries:
            print(f"\n🔍 하이브리드 검색: '{query}'")
            results = hybrid.search(query, top_k=3, include_debug=True)
            
            print(f"  검색 시간: {results['timing']['total_time']:.3f}초")
            print(f"    - 벡터: {results['timing']['vector_time']:.3f}초")
            print(f"    - BM25: {results['timing']['bm25_time']:.3f}초") 
            print(f"    - 융합: {results['timing']['fusion_time']:.3f}초")
            
            for result in results['fused_results']:
                print(f"  순위 {result['rank']}: {result['filename']}")
                print(f"    하이브리드 스코어: {result['hybrid_score']:.4f}")
                print(f"    벡터 스코어: {result['vector_score']:.3f}")
                print(f"    BM25 스코어: {result['bm25_score']:.3f}")
                print(f"    내용: {result['content'][:40]}...")
        
        # 통계 출력
        stats = hybrid.get_stats()
        print(f"\n📊 하이브리드 검색 통계:")
        print(f"  가중치: 벡터={stats['hybrid_config']['vector_weight']}, BM25={stats['hybrid_config']['bm25_weight']}")
        print(f"  RRF 파라미터: k={stats['hybrid_config']['rrf_k']}")
        print(f"  벡터 문서 수: {stats['vector_store']['total_vectors']}")
        print(f"  BM25 문서 수: {stats['bm25_store']['total_documents']}")
        
        print("✅ 하이브리드 검색 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ 하이브리드 검색 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_hybrid_search()