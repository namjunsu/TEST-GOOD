"""
쿼리 확장 (Query Expansion) 모듈
Advanced RAG 기법 중 하나로, 사용자 쿼리를 다양한 방법으로 확장하여 검색 정확도 향상

YAML 기반 설정으로 하드코딩 제거
"""

from app.core.logging import get_logger
import time
import hashlib
import yaml
import os
from pathlib import Path
from functools import lru_cache
from typing import List, Dict, Any, Set, Tuple, Optional
import re
from collections import defaultdict


class QueryExpansion:
    """쿼리 확장 모듈 (YAML 기반)"""

    # 상수 정의
    MAX_SYNONYMS_EXPANSIONS = 3
    MAX_PATTERN_EXPANSIONS = 2
    MAX_MORPHOLOGY_EXPANSIONS = 2
    DEFAULT_METHODS = ['synonyms', 'abbreviations', 'patterns', 'morphology']
    WORD_PATTERN = r'[가-힣a-zA-Z0-9]+'
    CONFIG_FILE = "config/query_expansion.yaml"

    def __init__(self, config_path: Optional[str] = None):
        self.logger = get_logger(__name__)

        # 설정 파일 경로
        if config_path is None:
            # 프로젝트 루트 기준으로 경로 설정
            project_root = Path(__file__).parent.parent
            self.config_path = project_root / self.CONFIG_FILE
        else:
            self.config_path = Path(config_path)

        # 설정 로드
        self.config = {}
        self.synonyms = {}
        self.abbreviations = {}
        self.expansion_patterns = {}
        self.rules = []
        self.performance_config = {}

        # 파일 변경 감지용
        self.config_mtime = 0
        self.last_check_time = 0

        # 초기 설정 로드
        self._load_config()

        # 성능 통계
        self.expansion_count = 0
        self.total_expansion_time = 0.0
        self.method_usage = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0

        # 형태소 패턴 초기화
        self._init_morphology_patterns()
        self._compile_patterns()

    def _load_config(self) -> bool:
        """YAML 설정 파일 로드"""
        try:
            if not self.config_path.exists():
                self.logger.warning(f"설정 파일 없음: {self.config_path}, 기본값 사용")
                self._use_default_config()
                return False

            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}

            # 동의어 로드
            self.synonyms = {}
            if 'synonyms' in self.config:
                for key, values in self.config['synonyms'].items():
                    if isinstance(values, list):
                        self.synonyms[key] = values
                    else:
                        self.logger.warning(f"잘못된 동의어 형식: {key}")

            # 규칙 로드
            self.rules = self.config.get('rules', [])

            # 성능 설정 로드
            self.performance_config = self.config.get('performance', {
                'cache_ttl': 3600,
                'hot_reload_interval': 60,
                'max_expansions': 10
            })

            # 형태소 패턴 설정 로드
            morpheme_config = self.config.get('morpheme_patterns', {})
            self.morpheme_enabled = morpheme_config.get('noun_verb', {}).get('enabled', True)

            # 파일 mtime 갱신
            self.config_mtime = self.config_path.stat().st_mtime

            self.logger.info(
                f"설정 로드 완료: {len(self.synonyms)}개 동의어 그룹, "
                f"{len(self.rules)}개 규칙"
            )
            return True

        except Exception as e:
            self.logger.error(f"설정 로드 실패: {e}, 기본값 사용")
            self._use_default_config()
            return False

    def _use_default_config(self):
        """기본 설정 사용 (YAML 로드 실패 시 fallback)"""
        self.synonyms = {
            '구매': ['구매', '구입', '발주', '매입'],
            '수리': ['수리', '정비', '보수', '수선'],
            '카메라': ['카메라', '캠', '촬영기'],
        }
        self.abbreviations = {
            'ENG': '뉴스취재',
            'LED': '발광다이오드'
        }
        self.expansion_patterns = {
            '최근': ['최근', '최신', '신규']
        }
        self.rules = []
        self.performance_config = {
            'cache_ttl': 3600,
            'hot_reload_interval': 60,
            'max_expansions': 10
        }
        self.logger.warning("기본 설정 사용 중 (제한된 동의어)")

    def _check_and_reload(self) -> bool:
        """설정 파일 변경 감지 및 재로드 (hot reload)"""
        try:
            # hot_reload_interval 확인
            reload_interval = self.performance_config.get('hot_reload_interval', 60)
            current_time = time.time()

            if current_time - self.last_check_time < reload_interval:
                return False

            self.last_check_time = current_time

            # 파일 mtime 확인
            if not self.config_path.exists():
                return False

            current_mtime = self.config_path.stat().st_mtime
            if current_mtime > self.config_mtime:
                self.logger.info("설정 파일 변경 감지, 재로드 중...")
                # 캐시 클리어
                if hasattr(self._expand_query_cached, 'cache_clear'):
                    self._expand_query_cached.cache_clear()
                # 설정 재로드
                success = self._load_config()
                if success:
                    # 패턴 재컴파일
                    self._compile_patterns()
                    self.logger.info("설정 재로드 완료")
                return success

            return False

        except Exception as e:
            self.logger.error(f"재로드 실패: {e}")
            return False

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
                synonym_lower = synonym.lower()
                if synonym_lower not in self.synonym_index:
                    self.synonym_index[synonym_lower] = []
                self.synonym_index[synonym_lower].append(key)

        self.logger.info(
            f"패턴 컴파일 완료: {len(self.compiled_morphology)}개 형태소 패턴, "
            f"{len(self.synonym_index)}개 동의어 인덱스"
        )

    def expand_query(self, query: str, methods: List[str] = None) -> Dict[str, Any]:
        """쿼리를 다양한 방법으로 확장 (캐싱됨)"""
        # hot reload 체크
        self._check_and_reload()

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
        """동의어 기반 쿼리 확장 (YAML 기반, 최적화)"""
        expanded = []
        words = self.compiled_word_pattern.findall(query)

        # 동의어 인덱스 활용
        for word in words:
            word_lower = word.lower()
            if word_lower in self.synonym_index:
                # 해당 단어가 속한 동의어 그룹들을 찾음
                for synonym_key in self.synonym_index[word_lower]:
                    if synonym_key in self.synonyms:
                        for synonym in self.synonyms[synonym_key]:
                            if synonym.lower() != word_lower:  # 원본과 다른 경우만
                                # 대소문자 구분 없이 치환
                                new_query = re.sub(
                                    re.escape(word),
                                    synonym,
                                    query,
                                    flags=re.IGNORECASE
                                )
                                if new_query != query and new_query not in expanded:
                                    expanded.append(new_query)

        max_expansions = self.performance_config.get('max_expansions', 10)
        return self._limit_expansions(expanded, min(self.MAX_SYNONYMS_EXPANSIONS, max_expansions))

    def _expand_abbreviations(self, query: str) -> List[str]:
        """약어 확장 (현재는 비활성, YAML 추가 시 활성화 가능)"""
        expanded = []

        # abbreviations가 설정에 있다면 사용
        abbreviations = self.config.get('abbreviations', {})
        for abbr, full_form in abbreviations.items():
            if abbr in query:
                expanded_query = query.replace(abbr, full_form)
                expanded.append(expanded_query)
            elif full_form in query:
                expanded_query = query.replace(full_form, abbr)
                expanded.append(expanded_query)

        return expanded

    def _expand_with_patterns(self, query: str) -> List[str]:
        """패턴 기반 확장 (YAML rules 기반)"""
        expanded = []

        # YAML rules 적용
        for rule in self.rules:
            match_keywords = rule.get('match', [])
            boosts = rule.get('boosts', {})

            # 매치되는 키워드가 있는지 확인
            for keyword in match_keywords:
                if keyword in query:
                    # 날짜 관련 규칙 처리
                    if boosts.get('date_desc'):
                        # 현재 년도/신규 키워드 추가
                        current_year = time.strftime("%Y")
                        alternatives = ['최신', '신규', current_year]
                        for alt in alternatives:
                            if alt not in query:
                                new_query = f"{query} {alt}"
                                if new_query not in expanded:
                                    expanded.append(new_query)

                    # top_k override 처리
                    if 'top_k_override' in boosts:
                        # 메타데이터에 저장 (실제 검색 시 사용)
                        pass

                    break

        max_expansions = self.performance_config.get('max_expansions', 10)
        return self._limit_expansions(expanded, min(self.MAX_PATTERN_EXPANSIONS, max_expansions))

    def _expand_morphology(self, query: str) -> List[str]:
        """형태소 기반 확장 (한국어 특화, 컴파일된 패턴 사용)"""
        if not self.morpheme_enabled:
            return []

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

        # 방법별 통계
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
            'compiled_patterns': len(self.compiled_morphology),
            'config_loaded': len(self.synonyms) > 0,
            'config_path': str(self.config_path),
            'hot_reload_enabled': self.performance_config.get('hot_reload_interval', 0) > 0
        }
        return stats


# 테스트 함수
def test_query_expansion():
    """쿼리 확장 테스트 (YAML 기반)"""
    print("🔍 쿼리 확장 테스트 시작 (YAML 기반)")

    try:
        # 쿼리 확장기 초기화
        expander = QueryExpansion()

        # 테스트 쿼리들
        test_queries = [
            "DVR 구매 최근 문서",
            "녹화기 발주 내역",
            "카메라 수리 건",
            "LED 조명 최신",
            "구매했던 장비"
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

        # 전체 통계
        print("\n" + "="*60)
        overall_stats = expander.get_stats()
        print(f"📊 전체 통계:")
        print(f"  - 설정 로드됨: {overall_stats['config_loaded']}")
        print(f"  - 동의어 인덱스 크기: {overall_stats['synonym_index_size']}")
        print(f"  - Hot reload 활성: {overall_stats['hot_reload_enabled']}")

        print("\n✅ 쿼리 확장 테스트 완료")
        return True

    except Exception as e:
        print(f"❌ 쿼리 확장 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_query_expansion()
