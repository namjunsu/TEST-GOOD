"""
스마트 검색 개선 모듈 - 하드코딩 없는 동적 학습 시스템
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
import re
from typing import Dict, List, Set, Tuple, Optional, Any
import pickle
import threading
import time
from functools import lru_cache
import hashlib
from datetime import datetime, timedelta
import os

class SmartSearchEnhancer:
    """파일명 패턴 학습 및 동의어 자동 생성 - 최적화 버전"""

    def __init__(self, docs_dir: Path, cache_ttl: int = 3600, max_cache_size: int = 1000):
        self.docs_dir = docs_dir
        self.cache_ttl = cache_ttl  # 캐시 TTL (초)
        self.max_cache_size = max_cache_size

        # 학습 데이터 저장 경로
        self.data_dir = Path("search_enhancement_data")
        self.data_dir.mkdir(exist_ok=True)

        # 스레드 안전성
        self._lock = threading.RLock()
        self._file_list_cache = None
        self._file_list_cache_time = 0

        # 캐싱
        self._keyword_cache = {}  # 키워드 추출 캐시
        self._search_cache = {}  # 검색 결과 캐시
        self._pattern_cache = {}  # 패턴 캐시

        # 동적으로 학습되는 데이터 (지연 로딩)
        self.synonym_groups = None
        self.file_patterns = None
        self.category_map = None
        self._data_loaded = False

        # 통계 추적
        self.search_stats = Counter()
        self.performance_stats = {}
    
    def _ensure_data_loaded(self):
        """데이터 지연 로딩"""
        if not self._data_loaded:
            with self._lock:
                if not self._data_loaded:
                    self.synonym_groups = self.load_or_create_synonyms()
                    self.file_patterns = self.learn_file_patterns()
                    self.category_map = self.auto_categorize()
                    self._data_loaded = True

    @lru_cache(maxsize=1000)
    def extract_keywords(self, text: str) -> List[str]:
        """간단한 키워드 추출 (형태소 분석기 대체) - 캐싱 지원"""
        # 캐시 키 생성
        cache_key = hashlib.md5(text.encode()).hexdigest()

        # 캐시 확인
        if cache_key in self._keyword_cache:
            cached_time, keywords = self._keyword_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return keywords

        # 특수문자, 숫자 제거
        text = re.sub(r'[0-9\-_]', ' ', text)
        # 공백으로 분리
        words = text.split()
        # 2글자 이상만 추출
        keywords = [w for w in words if len(w) >= 2]

        # 캐시 저장
        self._keyword_cache[cache_key] = (time.time(), keywords)

        # 캐시 크기 제한
        if len(self._keyword_cache) > self.max_cache_size:
            # 가장 오래된 항목 제거
            oldest_key = min(self._keyword_cache.keys(),
                           key=lambda k: self._keyword_cache[k][0])
            del self._keyword_cache[oldest_key]

        return keywords
        
    def load_or_create_synonyms(self) -> Dict[str, Set[str]]:
        """기본 동의어 + 사용 패턴 학습"""
        synonym_file = self.data_dir / "learned_synonyms.json"
        
        if synonym_file.exists():
            with open(synonym_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k: set(v) for k, v in data.items()}
        
        # 초기 시드 동의어 (최소한의 시작점)
        base_synonyms = {
            '영상': {'비디오', '동영상', '화면'},
            '구매': {'구입', '조달', '도입'},
            '보수': {'수리', '정비', '유지보수'},
        }
        
        # 파일명에서 자동으로 동의어 학습
        learned = self._learn_from_filenames()
        
        # 병합
        for key, values in learned.items():
            if key in base_synonyms:
                base_synonyms[key].update(values)
            else:
                base_synonyms[key] = values
                
        return base_synonyms
    
    def _learn_from_filenames(self) -> Dict[str, Set[str]]:
        """파일명에서 패턴을 학습하여 동의어 자동 생성"""
        word_groups = defaultdict(set)
        
        # 모든 PDF 파일명 분석
        for pdf_file in self.docs_dir.glob("*.pdf"):
            filename = pdf_file.stem
            
            # 날짜 제거
            filename = re.sub(r'\d{4}-\d{2}-\d{2}_', '', filename)
            
            # 간단한 단어 추출 (형태소 분석 대체)
            nouns = self.extract_keywords(filename)
            
            # 비슷한 위치에 나타나는 단어들을 그룹화
            for i, word in enumerate(nouns):
                if len(word) >= 2:  # 2글자 이상만
                    # 앞뒤 단어와 연관성 학습
                    if i > 0:
                        word_groups[word].add(nouns[i-1])
                    if i < len(nouns) - 1:
                        word_groups[word].add(nouns[i+1])
        
        # 상호 연관된 단어들을 동의어로 간주
        synonyms = {}
        for word, related in word_groups.items():
            if len(related) >= 2:  # 2개 이상 연관 단어가 있으면
                synonyms[word] = related
                
        return synonyms
    
    def _get_file_list(self) -> List[Path]:
        """파일 리스트 가져오기 - 캐싱 지원"""
        current_time = time.time()

        # 캐시 확인
        if self._file_list_cache and (current_time - self._file_list_cache_time) < 60:  # 60초 캐시
            return self._file_list_cache

        with self._lock:
            # 파일 리스트 갱신
            self._file_list_cache = list(self.docs_dir.glob("*.pdf"))
            self._file_list_cache_time = current_time

        return self._file_list_cache

    def learn_file_patterns(self) -> Dict[str, str]:
        """파일명 패턴 자동 학습 - 최적화"""
        # 캐시 확인
        if self._pattern_cache:
            return self._pattern_cache

        patterns = defaultdict(list)
        file_list = self._get_file_list()

        for pdf_file in file_list:
            filename = pdf_file.stem

            # 패턴 추출 (날짜_****_유형.pdf)
            match = re.match(r'(\d{4}-\d{2}-\d{2})_(.+?)_(\w+)(?:의?\s*건)?$', filename)
            if match:
                date, content, doc_type = match.groups()
                patterns[doc_type].append(content)

        # 각 문서 유형별 공통 패턴 찾기
        result = {}
        for doc_type, contents in patterns.items():
            if len(contents) >= 2:  # 2개 이상 있으면 패턴으로 인정
                # 공통 키워드 추출
                common_words = self._find_common_keywords(contents)
                if common_words:
                    result[doc_type] = f"*{common_words[0]}*_{doc_type}*.pdf"
                else:
                    result[doc_type] = f"****_{doc_type}*.pdf"

        self._pattern_cache = result
        return result

    def _find_common_keywords(self, texts: List[str]) -> List[str]:
        """공통 키워드 찾기"""
        word_counter = Counter()

        for text in texts:
            keywords = self.extract_keywords(text)
            word_counter.update(keywords)

        # 가장 빈번한 키워드 반환
        common = word_counter.most_common(3)
        return [word for word, count in common if count >= len(texts) * 0.3]
    
    def auto_categorize(self) -> Dict[str, List[str]]:
        """문서 자동 카테고리화 - 최적화"""
        categories = defaultdict(list)
        file_list = self._get_file_list()

        # 카테고리 키워드 상수화
        EQUIPMENT_KEYWORDS = ['카메라', '모니터', 'DVR', '서버', '장비', 'CCU', '마이크']
        PURCHASE_KEYWORDS = ['구매', '구입', '조달', '도입']
        MAINTENANCE_KEYWORDS = ['보수', '수리', '정비', '유지보수']
        REVIEW_KEYWORDS = ['검토', '분석', '보고', '평가']
        LOCATION_KEYWORDS = ['광화문', '중계차', '스튜디오', '편집실']

        for pdf_file in file_list:
            filename = pdf_file.stem
            
            # 형태소 분석으로 주요 명사 추출
            nouns = self.extract_keywords(filename)
            filename_lower = filename.lower()

            # 장비 검색 (한번만)
            if not '장비' in categories[filename]:
                if any(equip.lower() in filename_lower for equip in EQUIPMENT_KEYWORDS):
                    categories[filename].append('장비')

            # 문서 유형 (중복 방지)
            doc_type_added = False
            if any(keyword in filename_lower for keyword in [k.lower() for k in PURCHASE_KEYWORDS]):
                categories[filename].append('구매문서')
                doc_type_added = True
            elif not doc_type_added and any(keyword in filename_lower for keyword in [k.lower() for k in MAINTENANCE_KEYWORDS]):
                categories[filename].append('유지보수문서')
                doc_type_added = True
            elif not doc_type_added and any(keyword in filename_lower for keyword in [k.lower() for k in REVIEW_KEYWORDS]):
                categories[filename].append('검토문서')

            # 위치 검색
            for loc in LOCATION_KEYWORDS:
                if loc in filename:
                    if '위치정보' not in categories[filename]:
                        categories[filename].append('위치정보')
                    break
                        
            # 연도 추출
            year_match = re.search(r'(20\d{2})', filename)
            if year_match:
                categories[filename].append(f"{year_match.group(1)}년")
                
        return dict(categories)
    
    def expand_query(self, query: str) -> List[str]:
        """쿼리 확장 - 동의어 및 관련어 추가"""
        expanded = [query]
        words = self.extract_keywords(query)
        
        for word in words:
            # 동의어 그룹에서 찾기
            for key, synonyms in self.synonym_groups.items():
                if word == key or word in synonyms:
                    # 모든 동의어 추가
                    for syn in synonyms:
                        expanded_query = query.replace(word, syn)
                        if expanded_query not in expanded:
                            expanded.append(expanded_query)
                            
        return expanded
    
    def smart_date_parse(self, query: str) -> Dict[str, any]:
        """자연어 날짜 해석"""
        import datetime
        today = datetime.date.today()
        
        date_info = {}
        
        # 상대적 날짜 표현
        if '작년' in query:
            date_info['year'] = today.year - 1
        elif '올해' in query or '이번' in query:
            date_info['year'] = today.year
        elif '최근' in query:
            if '3개월' in query:
                date_info['start_date'] = today - datetime.timedelta(days=90)
            elif '6개월' in query:
                date_info['start_date'] = today - datetime.timedelta(days=180)
                
        # 계절
        if '봄' in query:
            date_info['months'] = [3, 4, 5]
        elif '여름' in query:
            date_info['months'] = [6, 7, 8]
        elif '가을' in query:
            date_info['months'] = [9, 10, 11]
        elif '겨울' in query:
            date_info['months'] = [12, 1, 2]
            
        # 상/하반기
        if '상반기' in query:
            date_info['months'] = list(range(1, 7))
        elif '하반기' in query:
            date_info['months'] = list(range(7, 13))
            
        return date_info
    
    def search_with_enhancement(self, query: str, file_list: Optional[List[str]] = None) -> List[Tuple[str, float]]:
        """개선된 검색 - 동의어, 패턴, 카테고리 활용 (캐싱 지원)"""
        # 데이터 확인
        self._ensure_data_loaded()

        # 캐시 키 생성
        cache_key = hashlib.md5(f"{query}:{file_list}".encode()).hexdigest()

        # 캐시 확인
        if cache_key in self._search_cache:
            cached_time, results = self._search_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                self.search_stats['cache_hits'] += 1
                return results

        self.search_stats['cache_misses'] += 1
        start_time = time.time()

        # 파일 리스트 확인
        if file_list is None:
            file_list = [f.name for f in self._get_file_list()]

        scores = defaultdict(float)
        
        # 1. 쿼리 확장
        expanded_queries = self.expand_query(query)
        
        # 2. 날짜 파싱
        date_info = self.smart_date_parse(query)
        
        # 3. 각 파일에 대해 점수 계산
        for filename in file_list:
            score = 0
            
            # 확장된 쿼리로 매칭
            for exp_query in expanded_queries:
                query_words = self.extract_keywords(exp_query.lower())
                file_words = self.extract_keywords(filename.lower())
                
                # 단어 매칭 점수
                for q_word in query_words:
                    if q_word in file_words:
                        score += 10
                    # 부분 매칭
                    elif any(q_word in f_word or f_word in q_word 
                            for f_word in file_words):
                        score += 5
            
            # 카테고리 매칭
            if filename in self.category_map:
                categories = self.category_map[filename]
                for category in categories:
                    if category.lower() in query.lower():
                        score += 15
            
            # 날짜 매칭
            if date_info:
                file_year = re.search(r'(20\d{2})', filename)
                if file_year and 'year' in date_info:
                    if int(file_year.group(1)) == date_info['year']:
                        score += 20
                        
            scores[filename] = score
        
        # 점수순 정렬
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = [(f, s) for f, s in sorted_results if s > 0]

        # 캐시 저장
        self._search_cache[cache_key] = (time.time(), results)

        # 캐시 크기 제한
        if len(self._search_cache) > self.max_cache_size:
            # 가장 오래된 항목 제거
            oldest_key = min(self._search_cache.keys(),
                           key=lambda k: self._search_cache[k][0])
            del self._search_cache[oldest_key]

        # 성능 통계 기록
        elapsed = time.time() - start_time
        self.performance_stats['search_times'] = self.performance_stats.get('search_times', [])
        self.performance_stats['search_times'].append(elapsed)

        return results
    
    def save_learned_data(self):
        """학습된 데이터 저장"""
        # 동의어 저장
        synonym_data = {k: list(v) for k, v in self.synonym_groups.items()}
        with open(self.data_dir / "learned_synonyms.json", 'w', encoding='utf-8') as f:
            json.dump(synonym_data, f, ensure_ascii=False, indent=2)
        
        # 패턴 저장
        with open(self.data_dir / "file_patterns.json", 'w', encoding='utf-8') as f:
            json.dump(self.file_patterns, f, ensure_ascii=False, indent=2)
        
        # 카테고리 저장
        with open(self.data_dir / "categories.json", 'w', encoding='utf-8') as f:
            json.dump(self.category_map, f, ensure_ascii=False, indent=2)
    
    def learn_from_user_feedback(self, query: str, selected_file: str, weight: float = 1.0):
        """사용자 선택으로부터 학습 - 가중치 지원"""
        self._ensure_data_loaded()

        with self._lock:
            query_words = self.extract_keywords(query)
            file_words = self.extract_keywords(selected_file)

            # 쿼리 단어와 파일 단어의 연관성 학습
            for q_word in query_words:
                for f_word in file_words:
                    if q_word != f_word and len(q_word) >= 2 and len(f_word) >= 2:
                        # 동의어 관계로 추가 (가중치 반영)
                        if q_word not in self.synonym_groups:
                            self.synonym_groups[q_word] = set()
                        self.synonym_groups[q_word].add(f_word)

                        # 학습 횟수 기록
                        self.search_stats[f'learned_{q_word}_{f_word}'] += weight

            # 캐시 무효화
            self._search_cache.clear()

            # 비동기 저장 (블로킹 방지)
            threading.Thread(target=self.save_learned_data, daemon=True).start()

    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        stats = {
            'cache_hits': self.search_stats.get('cache_hits', 0),
            'cache_misses': self.search_stats.get('cache_misses', 0),
            'cache_hit_rate': 0,
            'avg_search_time': 0,
            'total_searches': 0,
            'learned_patterns': len(self.synonym_groups) if self.synonym_groups else 0,
            'cached_keywords': len(self._keyword_cache),
            'cached_searches': len(self._search_cache)
        }

        total = stats['cache_hits'] + stats['cache_misses']
        if total > 0:
            stats['cache_hit_rate'] = stats['cache_hits'] / total * 100
            stats['total_searches'] = total

        if 'search_times' in self.performance_stats:
            times = self.performance_stats['search_times']
            if times:
                stats['avg_search_time'] = sum(times) / len(times)

        return stats


# 사용 예시
if __name__ == "__main__":
    from pathlib import Path
    
    docs_dir = Path("/home/wnstn4647/AI-CHAT/docs")
    enhancer = SmartSearchEnhancer(docs_dir)
    
    # 테스트
    test_queries = [
        "비디오 관련 문서",  # 영상 → 비디오 동의어
        "작년 구입한 장비",   # 구매 → 구입 동의어 + 날짜 파싱
        "중계차 수리 내역",   # 보수 → 수리 동의어
    ]
    
    file_list = [f.name for f in docs_dir.glob("*.pdf")]
    
    for query in test_queries:
        print(f"\n검색: {query}")
        results = enhancer.search_with_enhancement(query, file_list)
        for filename, score in results[:3]:
            print(f"  - {filename} (점수: {score})")