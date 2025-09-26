"""
쿼리 최적화 및 가중치 자동 조정
"""

import re
import logging
import time
from functools import lru_cache
from typing import List, Tuple, Dict, Any

class QueryOptimizer:
    """쿼리 최적화 및 가중치 자동 조정"""
    
    # 가중치 상수 정의
    DEFAULT_VECTOR_WEIGHT = 0.3
    DEFAULT_BM25_WEIGHT = 0.7
    
    SHORT_QUERY_VECTOR_WEIGHT = 0.45
    SHORT_QUERY_BM25_WEIGHT = 0.55
    
    MODEL_CODE_VECTOR_WEIGHT = 0.4
    MODEL_CODE_BM25_WEIGHT = 0.6
    
    AMOUNT_QUERY_VECTOR_WEIGHT = 0.45
    AMOUNT_QUERY_BM25_WEIGHT = 0.55
    
    GENERAL_LONG_VECTOR_WEIGHT = 0.7
    GENERAL_LONG_BM25_WEIGHT = 0.3
    
    SHORT_QUERY_TOKEN_THRESHOLD = 3
    LONG_QUERY_TOKEN_THRESHOLD = 5
    
    def __init__(self):
        self.tokenizer = None  # 나중에 한국어 토크나이저 연결
        self.logger = logging.getLogger(__name__)
        self._init_cleaning_patterns()
        self._compile_patterns()

        # 성능 통계
        self.analyze_count = 0
        self.total_analyze_time = 0.0
        self.clean_count = 0
        self.total_clean_time = 0.0
        self.weight_count = 0
        self.total_weight_time = 0.0
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """쿼리 분석 및 특성 추출"""
        start_time = time.time()

        # 간단한 토큰화 (공백 기준)
        tokens = query.strip().split()

        # 컴파일된 패턴으로 감지
        has_numbers = bool(self.number_pattern.search(query))
        has_model_codes = bool(self.model_code_pattern.search(query))
        has_amounts = bool(self.amount_pattern.search(query))

        # 질문 유형 추정
        question_type = self._classify_question_type(query)

        # 통계 업데이트
        self.analyze_count += 1
        self.total_analyze_time += time.time() - start_time

        return {
            'token_count': len(tokens),
            'has_numbers': has_numbers,
            'has_model_codes': has_model_codes,
            'has_amounts': has_amounts,
            'question_type': question_type,
            'query_length': len(query)
        }
    
    def _classify_question_type(self, query: str) -> str:
        """질문 유형 분류"""
        if any(keyword in query for keyword in ['얼마', '금액', '비용', '가격', '원']):
            return 'amount'
        elif any(keyword in query for keyword in ['언제', '날짜', '기간', '년', '월']):
            return 'date'
        elif any(keyword in query for keyword in ['누구', '기안자', '작성자', '담당자']):
            return 'person'
        elif any(keyword in query for keyword in ['모델', '장비', '제품', '기기']):
            return 'equipment'
        else:
            return 'general'
    
    def _init_cleaning_patterns(self):
        """정규식 패턴 초기화"""
        # 복잡한 질문 패턴들
        self.complex_patterns = [
            (r'을?\s*교체하는데\s*드는\s*비용이?\s*얼마나?\s*될까요\?*', ' 교체 비용'),
            (r'를?\s*교체하는데\s*드는\s*비용이?\s*얼마나?\s*될까요\?*', ' 교체 비용'),
            (r'이?\s*언제\s*교체되었나요\?*', ' 교체 날짜'),
            (r'가?\s*언제\s*교체되었나요\?*', ' 교체 날짜'),
            (r'께서\s*작성하신\s*문서들?\s*중에서', ' 기안자'),
            (r'에\s*대해서는?\s*어떤\s*내용이\s*있습니까\?*', ''),
            (r'에\s*대해\s*어떤\s*내용이\s*있나요\?*', ''),
            (r'는?\s*몇\s*개나?\s*구매했습니까\?*', ' 구매 수량'),
            (r'을?\s*구매한?\s*이유가?\s*뭔?가요\?*', ' 구매 이유'),
            (r'를?\s*구매한?\s*이유가?\s*뭔?가요\?*', ' 구매 이유'),
            (r'가장\s*최근에?\s*작성된?\s*문서는?\s*언제\s*것인?가요\?*', ' 최근 문서 날짜'),
            (r'라는?\s*기안자가?\s*작성한?\s*문서에?서?는?\s*어떤\s*장비들?이?\s*나오나요\?*', ' 기안자 문서 장비'),
        ]
        
        # 기본 질문 패턴들
        self.basic_patterns = [
            (r'은\s*얼마', ''),
            (r'는\s*얼마', ''),
            (r'가\s*얼마', ''),
            (r'을\s*얼마', ''),
            (r'를\s*얼마', ''),
            (r'의?\s*가격은?\s*대략\s*어느?정도\s*인?가요\?*', ' 가격'),
            (r'얼마나?\s*될까요\?*', ''),
            (r'얼마인가요\?*', ''),
            (r'입니까\?*', ''),
            (r'인가요\?*', ''),
            (r'무엇인가요\?*', ''),
            (r'어떻게\s*되나요\?*', ''),
            (r'을\s*알려주시겠어요\?*', ''),
            (r'를\s*알려주시겠어요\?*', ''),
        ]
        
        # 조사 및 어미 패턴들
        self.particle_patterns = [
            (r'이라는', ''),
            (r'에서는?', ' '),
            (r'로서는?', ' '),
            (r'께서', ' '),
            (r'들은?\s*어떻게', ''),
            (r'들이?\s*어떻게', ''),
            (r'었습니까', ''),
            (r'습니까', ''),
            (r'하나요', ''),
            (r'나오나요', ' 포함'),
        ]

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        # 패턴 컴파일
        self.compiled_complex = [(re.compile(p), r) for p, r in self.complex_patterns]
        self.compiled_basic = [(re.compile(p), r) for p, r in self.basic_patterns]
        self.compiled_particles = [(re.compile(p), r) for p, r in self.particle_patterns]

        # 분석용 컴파일 패턴
        self.number_pattern = re.compile(r'\d+')
        self.model_code_pattern = re.compile(r'[A-Z]+-[0-9A-Z]+')
        self.amount_pattern = re.compile(r'[\d,]+원|금액|비용|가격')

        self.logger.info(f"패턴 컴파일 완료: {len(self.compiled_complex) + len(self.compiled_basic) + len(self.compiled_particles)}개")

    @lru_cache(maxsize=512)
    def clean_query_for_search(self, query: str) -> str:
        """한국어 조사 제거 및 키워드 추출"""
        start_time = time.time()
        cleaned = query

        # 컴파일된 패턴 적용
        for pattern, replacement in self.compiled_complex + self.compiled_basic + self.compiled_particles:
            cleaned = pattern.sub(replacement, cleaned)

        # 다중 공백 정리
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # 통계 업데이트
        self.clean_count += 1
        self.total_clean_time += time.time() - start_time

        return cleaned
    
    def get_optimal_weights(self, query: str) -> Tuple[float, float]:
        """쿼리 특성에 따른 최적 가중치 반환"""
        start_time = time.time()
        analysis = self.analyze_query(query)

        # 기본 가중치
        vector_weight = self.DEFAULT_VECTOR_WEIGHT
        bm25_weight = self.DEFAULT_BM25_WEIGHT

        # 토큰 수가 적으면 BM25 가중치 상향 (정확한 키워드 매칭 중요)
        if analysis['token_count'] <= self.SHORT_QUERY_TOKEN_THRESHOLD:
            vector_weight = self.SHORT_QUERY_VECTOR_WEIGHT
            bm25_weight = self.SHORT_QUERY_BM25_WEIGHT

        # 모델명/코드가 있으면 BM25 가중치 상향
        if analysis['has_model_codes']:
            vector_weight = self.MODEL_CODE_VECTOR_WEIGHT
            bm25_weight = self.MODEL_CODE_BM25_WEIGHT

        # 금액 질문이면 BM25 가중치 상향 (정확한 숫자 매칭)
        if analysis['question_type'] == 'amount':
            vector_weight = self.AMOUNT_QUERY_VECTOR_WEIGHT
            bm25_weight = self.AMOUNT_QUERY_BM25_WEIGHT

        # 일반적인 의미 질문이면 벡터 가중치 상향
        if analysis['question_type'] == 'general' and analysis['token_count'] > self.LONG_QUERY_TOKEN_THRESHOLD:
            vector_weight = self.GENERAL_LONG_VECTOR_WEIGHT
            bm25_weight = self.GENERAL_LONG_BM25_WEIGHT

        # 통계 업데이트
        self.weight_count += 1
        self.total_weight_time += time.time() - start_time

        self.logger.debug(f"Query: {query[:50]}... | Vector: {vector_weight:.2f}, BM25: {bm25_weight:.2f}")
        return vector_weight, bm25_weight

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        stats = {
            'analyze_count': self.analyze_count,
            'total_analyze_time': self.total_analyze_time,
            'avg_analyze_time': self.total_analyze_time / self.analyze_count if self.analyze_count > 0 else 0.0,
            'clean_count': self.clean_count,
            'total_clean_time': self.total_clean_time,
            'avg_clean_time': self.total_clean_time / self.clean_count if self.clean_count > 0 else 0.0,
            'weight_count': self.weight_count,
            'total_weight_time': self.total_weight_time,
            'avg_weight_time': self.total_weight_time / self.weight_count if self.weight_count > 0 else 0.0,
            'cache_info': self.clean_query_for_search.cache_info() if hasattr(self.clean_query_for_search, 'cache_info') else None
        }
        return stats