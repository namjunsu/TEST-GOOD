# perfect_rag_refactored.py 일부

class DocumentSearcher:
    """문서 검색 전문 클래스"""

    def __init__(self, rag_instance):
        self.rag = rag_instance
        self.cache = rag_instance.response_cache

    def search_and_analyze(self, query: str, search_mode: str) -> Dict:
        """메인 검색 메서드 (기존 315줄 → 30줄)"""
        # 1. 검증
        if not self._validate_query(query):
            return {"error": "Invalid query"}

        # 2. 캐시 체크
        cached = self._check_cache(query, search_mode)
        if cached:
            return cached

        # 3. 검색 실행
        results = self._execute_search(query, search_mode)

        # 4. 분석
        analyzed = self._analyze_results(results, query)

        # 5. 캐싱 및 반환
        return self._cache_and_return(query, analyzed)

    def _validate_query(self, query: str) -> bool:
        """쿼리 검증 (20줄)"""
        if not query or len(query) < 2:
            return False
        return True

    def _check_cache(self, query: str, mode: str) -> Optional[Dict]:
        """캐시 확인 (15줄)"""
        cache_key = f"{mode}_{query}"
        return self.cache.get(cache_key)

    def _execute_search(self, query: str, mode: str) -> List[Dict]:
        """검색 실행 (50줄)"""
        if mode == "hybrid":
            return self._hybrid_search(query)
        elif mode == "vector":
            return self._vector_search(query)
        else:
            return self._keyword_search(query)

    def _analyze_results(self, results: List[Dict], query: str) -> Dict:
        """결과 분석 (40줄)"""
        if not results:
            return {"message": "No results found"}

        # 관련도 점수 계산
        scored = self._calculate_relevance(results, query)

        # 상위 결과 선택
        top_results = self._select_top_results(scored)

        # 요약 생성
        summary = self._generate_summary(top_results)

        return {
            "results": top_results,
            "summary": summary,
            "count": len(results)
        }

    def _hybrid_search(self, query: str) -> List[Dict]:
        """하이브리드 검색 (30줄)"""
        bm25_results = self.rag.bm25_search(query)
        vector_results = self.rag.vector_search(query)
        return self._merge_results(bm25_results, vector_results)

    def _calculate_relevance(self, results: List, query: str) -> List:
        """관련도 계산 (25줄)"""
        # 구현...
        return results

    def _select_top_results(self, results: List, top_k: int = 5) -> List:
        """상위 결과 선택 (10줄)"""
        return results[:top_k]

    def _generate_summary(self, results: List) -> str:
        """요약 생성 (30줄)"""
        # LLM을 사용한 요약
        return "Summary of results..."

    def _cache_and_return(self, query: str, result: Dict) -> Dict:
        """캐싱 및 반환 (10줄)"""
        self.cache[query] = result
        return result
