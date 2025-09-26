"""
쿼리 확장 (Query Expansion) 모듈
Advanced RAG 기법 중 하나로, 사용자 쿼리를 다양한 방법으로 확장하여 검색 정확도 향상
"""

import logging
import time
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Set, Tuple
import re
from collections import defaultdict

class QueryExpansion:
    """쿼리 확장 모듈"""
    
    # 상수 정의
    MAX_SYNONYMS_EXPANSIONS = 3
    MAX_PATTERN_EXPANSIONS = 2
    MAX_MORPHOLOGY_EXPANSIONS = 2
    DEFAULT_METHODS = ['synonyms', 'abbreviations', 'patterns', 'morphology']
    WORD_PATTERN = r'[가-힣a-zA-Z0-9]+'
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 성능 통계
        self.expansion_count = 0
        self.total_expansion_time = 0.0
        self.method_usage = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0

        # 한국어 방송기술 도메인 동의어 사전
        self.synonyms = {
            # 장비 관련
            '워크스테이션': ['워크스테이션', '컴퓨터', 'PC', '편집기', '작업용컴퓨터'],
            '모니터': ['모니터', '디스플레이', '화면', '스크린', '영상표시장치'],
            '카메라': ['카메라', '캠', '촬영기', '영상기', '방송카메라'],
            '마이크': ['마이크', '마이크로폰', '음성입력', '음향장비', '핀마이크'],
            '케이블': ['케이블', '선', '연결선', '케이블류', '배선'],
            '삼각대': ['삼각대', '트라이포드', '거치대', '스탠드'],
            '드론': ['드론', '무인항공기', '헬리캠', '항공촬영기'],
            '조명': ['조명', '라이트', '조명기', '라이팅', 'LED'],
            
            # 가격 관련
            '가격': ['가격', '금액', '비용', '예산', '구매비', '총액'],
            '비용': ['비용', '가격', '금액', '예산', '소요비용', '구매비'],
            '금액': ['금액', '가격', '비용', '예산', '총액', '구매금액'],
            
            # 브랜드 관련
            'HP': ['HP', '휴렛팩커드', 'Hewlett-Packard'],
            'LG': ['LG', '엘지', 'LG전자'],
            'TVLogic': ['TVLogic', '티비로직', 'TV Logic'],
            'Sony': ['Sony', '소니'],
            'Canon': ['Canon', '캐논'],
            
            # 기술 용어
            '교체': ['교체', '대체', '변경', '업그레이드', '갱신'],
            '구매': ['구매', '구입', '조달', '도입', '매입'],
            '수리': ['수리', '정비', '보수', '수선', '복구'],
            '설치': ['설치', '구축', '도입', '배치', '셋업']
        }
        
        # 기술 약어 사전
        self.abbreviations = {
            'NLE': '영상편집',
            'ENG': '뉴스취재',
            'SDI': '영상신호',
            'HDMI': '영상연결',
            'BNC': '동축커넥터',
            'UTP': '네트워크케이블',
            'LED': '발광다이오드'
        }
        
        # 관련 용어 확장 패턴
        self.expansion_patterns = {
            '최근': ['최근', '최신', '신규', '새로운', '2024', '2025'],
            '고액': ['고액', '비싼', '고가', '대형', '큰'],
            '장비': ['장비', '기기', '기구', '도구', '시설'],
            '문서': ['문서', '기안서', '보고서', '검토서', '계획서']
        }
        
        # 형태소 패턴 초기화
        self._init_morphology_patterns()
        self._compile_patterns()

    def _init_morphology_patterns(self):
        """형태소 변형 패턴 초기화"""
        self.morphology_patterns = [
            (r'(\w+)을', r'\1를'),
            (r'(\w+)를', r'\1을'),
            (r'(\w+)이', r'\1가'),
            (r'(\w+)가', r'\1이'),
            (r'(\w+)은', r'\1는'),
            (r'(\w+)는', r'\1은'),
            (r'(\w+)에서', r'\1의'),
            (r'(\w+)의', r'\1에서')
        ]

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        # 단어 추출 패턴 컴파일
        self.compiled_word_pattern = re.compile(self.WORD_PATTERN)

        # 형태소 패턴 컴파일
        self.compiled_morphology = [(re.compile(p), r) for p, r in self.morphology_patterns]

        # 동의어 역 인덱스 구축 (빠른 검색용)
        self.synonym_index = {}
        for key, synonyms in self.synonyms.items():
            for synonym in synonyms:
                if synonym not in self.synonym_index:
                    self.synonym_index[synonym] = []
                self.synonym_index[synonym].append(key)

        self.logger.info(f"패턴 컴파일 완료: {len(self.compiled_morphology)}개 형태소 패턴, {len(self.synonym_index)}개 동의어 인덱스")
        
    def expand_query(self, query: str, methods: List[str] = None) -> Dict[str, Any]:
        """쿼리를 다양한 방법으로 확장 (캐싱됨)"""
        if methods is None:
            methods = self.DEFAULT_METHODS

        # 캐시 키 생성
        cache_key = hashlib.md5(f"{query}:{':'.join(sorted(methods))}".encode()).hexdigest()
        return self._expand_query_cached(cache_key, query, tuple(methods))

    @lru_cache(maxsize=512)
    def _expand_query_cached(self, cache_key: str, query: str, methods: Tuple[str]) -> Dict[str, Any]:
        """실제 쿼리 확장 (캐싱됨)"""
        start_time = time.time()
        methods = list(methods)  # 튜플을 리스트로 변환
        
        expansion_result = {
            'original_query': query,
            'expanded_queries': [],
            'expansion_methods': {},  # 메서드별로 확장 결과 저장
            'methods_used': methods,
            'processing_time': 0.0
        }
        
        try:
            # 확장 메서드 매핑
            expansion_methods = {
                'synonyms': self._expand_with_synonyms,
                'abbreviations': self._expand_abbreviations,
                'patterns': self._expand_with_patterns,
                'morphology': self._expand_morphology
            }
            
            # 각 메서드 실행
            for method in methods:
                if method in expansion_methods:
                    method_expansions = expansion_methods[method](query)
                    expansion_result['expansion_methods'][method] = method_expansions
                    expansion_result['expanded_queries'].extend(method_expansions)
            
            # 중복 제거
            unique_queries = []
            seen = set()
            for q in [query] + expansion_result['expanded_queries']:
                if q not in seen:
                    unique_queries.append(q)
                    seen.add(q)
            
            expansion_result['expanded_queries'] = unique_queries[1:]  # 원본 제외
            expansion_result['total_queries'] = len(unique_queries)
            expansion_result['processing_time'] = time.time() - start_time

            # 통계 업데이트
            self.expansion_count += 1
            self.total_expansion_time += expansion_result['processing_time']
            for method in methods:
                self.method_usage[method] += 1

            self.logger.info(
                f"쿼리 확장 완료: '{query}' → {len(unique_queries)}개 쿼리 "
                f"(시간: {expansion_result['processing_time']:.3f}초)"
            )

            return expansion_result
            
        except Exception as e:
            self.logger.error(f"쿼리 확장 실패: {e}")
            expansion_result['processing_time'] = time.time() - start_time
            return expansion_result
    
    def _expand_with_synonyms(self, query: str) -> List[str]:
        """동의어 기반 쿼리 확장 (최적화)"""
        expanded = []
        words = self.compiled_word_pattern.findall(query)

        # 동의어 인덱스 활용
        for word in words:
            if word in self.synonym_index:
                # 해당 단어가 속한 동의어 그룹들을 찾음
                for synonym_key in self.synonym_index[word]:
                    for synonym in self.synonyms[synonym_key]:
                        if synonym != word:  # 원본과 다른 경우만
                            new_query = query.replace(word, synonym)
                            if new_query != query and new_query not in expanded:
                                expanded.append(new_query)

        return self._limit_expansions(expanded, self.MAX_SYNONYMS_EXPANSIONS)
    
    def _expand_abbreviations(self, query: str) -> List[str]:
        """약어 확장"""
        expanded = []
        
        for abbr, full_form in self.abbreviations.items():
            if abbr in query:
                expanded_query = query.replace(abbr, full_form)
                expanded.append(expanded_query)
            elif full_form in query:
                expanded_query = query.replace(full_form, abbr)
                expanded.append(expanded_query)
        
        return expanded
    
    def _expand_with_patterns(self, query: str) -> List[str]:
        """패턴 기반 확장"""
        expanded = []
        
        for pattern, alternatives in self.expansion_patterns.items():
            if pattern in query:
                for alt in alternatives:
                    if alt != pattern:
                        new_query = query.replace(pattern, alt)
                        expanded.append(new_query)
        
        return self._limit_expansions(expanded, self.MAX_PATTERN_EXPANSIONS)
    
    def _expand_morphology(self, query: str) -> List[str]:
        """형태소 기반 확장 (한국어 특화, 컴파일된 패턴 사용)"""
        expanded = []

        for pattern, replacement in self.compiled_morphology:
            new_query = pattern.sub(replacement, query)
            if new_query != query and new_query not in expanded:
                expanded.append(new_query)

        return self._limit_expansions(expanded, self.MAX_MORPHOLOGY_EXPANSIONS)
    
    def get_expansion_statistics(self, expansion_result: Dict[str, Any]) -> Dict[str, Any]:
        """확장 통계 정보"""
        stats = {
            'original_length': len(expansion_result['original_query']),
            'total_expansions': len(expansion_result['expanded_queries']),
            'methods_breakdown': {},
            'processing_time': expansion_result['processing_time'],
            'expansion_ratio': 0.0
        }
        
        # 방법별 통계 (개선된 버전)
        if 'expansion_methods' in expansion_result:
            for method, expansions in expansion_result['expansion_methods'].items():
                stats['methods_breakdown'][method] = len(expansions)
        
        # 확장 비율
        if expansion_result['original_query']:
            total_chars = sum(len(q) for q in expansion_result['expanded_queries'])
            stats['expansion_ratio'] = total_chars / len(expansion_result['original_query'])
        
        return stats
    
    def _limit_expansions(self, expansions: List[str], max_count: int) -> List[str]:
        """확장 결과를 최대 개수로 제한"""
        return expansions[:max_count]

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        stats = {
            'expansion_count': self.expansion_count,
            'total_expansion_time': self.total_expansion_time,
            'avg_expansion_time': self.total_expansion_time / self.expansion_count if self.expansion_count > 0 else 0.0,
            'method_usage': dict(self.method_usage),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) * 100 if (self.cache_hits + self.cache_misses) > 0 else 0.0,
            'cache_info': self._expand_query_cached.cache_info() if hasattr(self._expand_query_cached, 'cache_info') else None,
            'synonym_index_size': len(self.synonym_index),
            'compiled_patterns': len(self.compiled_morphology)
        }
        return stats

# 테스트 함수
def test_query_expansion():
    """쿼리 확장 테스트"""
    print("🔍 쿼리 확장 테스트 시작")
    
    try:
        # 쿼리 확장기 초기화
        expander = QueryExpansion()
        
        # 테스트 쿼리들
        test_queries = [
            "HP Z8 워크스테이션 가격은 얼마인가요?",
            "최근 모니터 교체 비용",
            "NLE 장비 구매 계획",
            "카메라를 수리한 문서",
            "가장 고액인 장비"
        ]
        
        for query in test_queries:
            print(f"\n🔍 원본 쿼리: '{query}'")
            
            # 쿼리 확장
            result = expander.expand_query(query)
            
            print(f"📊 확장된 쿼리 수: {len(result['expanded_queries'])}")
            print(f"⏱️ 처리 시간: {result['processing_time']:.3f}초")
            
            # 확장된 쿼리들 출력
            for i, expanded in enumerate(result['expanded_queries'][:5], 1):
                # 어느 메서드에서 생성되었는지 찾기
                method_name = 'unknown'
                if 'expansion_methods' in result:
                    for method, expansions in result['expansion_methods'].items():
                        if expanded in expansions:
                            method_name = method
                            break
                print(f"  {i}. [{method_name}] {expanded}")
            
            # 통계 정보
            stats = expander.get_expansion_statistics(result)
            print(f"📈 방법별 확장 수: {stats['methods_breakdown']}")
            print(f"📏 확장 비율: {stats['expansion_ratio']:.2f}")
        
        print("\n✅ 쿼리 확장 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ 쿼리 확장 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_query_expansion()