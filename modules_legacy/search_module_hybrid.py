#!/usr/bin/env python3
"""
하이브리드 검색 모듈 - BM25 + Vector 검색 통합
SearchModule을 확장하여 하이브리드 검색 기능 추가
"""

from app.core.logging import get_logger
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.search_module import SearchModule
from rag_system.hybrid_search import HybridSearch

logger = get_logger(__name__)


class SearchModuleHybrid(SearchModule):
    """하이브리드 검색을 지원하는 SearchModule"""

    def __init__(self, docs_dir: str = "docs", config: Dict = None, use_hybrid: bool = True):
        """
        Args:
            docs_dir: 문서 디렉토리 경로
            config: 설정 딕셔너리
            use_hybrid: 하이브리드 검색 사용 여부
        """
        super().__init__(docs_dir, config)

        self.use_hybrid = use_hybrid
        self.hybrid_search = None

        # 하이브리드 검색 초기화 (지연 로딩)
        if self.use_hybrid:
            self._init_hybrid_search()

    def _init_hybrid_search(self):
        """하이브리드 검색 초기화"""
        try:
            logger.info("🔨 하이브리드 검색 초기화 중...")
            start = time.time()

            # .env에서 가중치 읽기
            vector_weight = float(os.getenv('SEARCH_VECTOR_WEIGHT', '0.1'))
            bm25_weight = float(os.getenv('SEARCH_BM25_WEIGHT', '0.9'))

            self.hybrid_search = HybridSearch(
                vector_index_path="var/index/korean_vector_index.faiss",
                bm25_index_path="var/index/bm25_index.pkl",
                vector_weight=vector_weight,
                bm25_weight=bm25_weight,
                use_reranker=False,  # 재랭킹 비활성화 (속도 우선)
                use_query_expansion=False,  # 쿼리 확장 비활성화
                use_document_compression=False,
                use_multilevel_filter=False
            )

            elapsed = time.time() - start
            logger.info(f"✅ 하이브리드 검색 초기화 완료: {elapsed:.2f}초")

        except Exception as e:
            logger.error(f"❌ 하이브리드 검색 초기화 실패: {e}")
            self.use_hybrid = False
            self.hybrid_search = None

    def search_by_content(self, query: str, top_k: int = 20, mode: str = "auto") -> List[Dict[str, Any]]:
        """
        내용 기반 문서 검색 - 하이브리드 또는 기본 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 문서 수
            mode: 검색 모드 ("hybrid", "basic", "auto")
                - hybrid: 하이브리드 검색 강제 사용
                - basic: 기본 검색만 사용
                - auto: 자동 선택 (복잡한 쿼리는 hybrid, 간단한 쿼리는 basic)

        Returns:
            검색 결과 리스트
        """
        # 모드 자동 선택
        if mode == "auto":
            mode = self._determine_search_mode(query)
            logger.info(f"🎯 자동 모드 선택: {mode}")

        # 하이브리드 검색 사용
        if mode == "hybrid" and self.hybrid_search:
            return self._hybrid_search(query, top_k)

        # 기본 검색 사용 (상위 클래스 메서드)
        return super().search_by_content(query, top_k)

    def _determine_search_mode(self, query: str) -> str:
        """쿼리 복잡도에 따라 검색 모드 자동 선택"""

        # 하이브리드가 유용한 경우:
        # 1. 의미 기반 검색이 필요한 경우
        # 2. 복잡한 쿼리
        # 3. 유사어 검색이 필요한 경우

        hybrid_keywords = [
            # 의미/개념 검색
            '관련', '유사', '비슷', '같은', '종류',
            # 복잡한 질문
            '어떤', '무엇', '왜', '어떻게', '설명',
            # 범위 검색
            '모든', '전체', '전부', '다', '여러'
        ]

        # 기본 검색이 충분한 경우:
        basic_keywords = [
            # 정확한 매칭
            '파일', '문서', '날짜', '기안자', '찾아',
            # 특정 항목
            '구매', '수리', '검토서', 'DVR', '카메라'
        ]

        query_lower = query.lower()

        # 기본 검색 우선 체크
        for keyword in basic_keywords:
            if keyword in query_lower:
                return "basic"

        # 하이브리드 검색 체크
        for keyword in hybrid_keywords:
            if keyword in query_lower:
                return "hybrid"

        # 기본값: 쿼리 길이로 판단
        return "hybrid" if len(query) > 20 else "basic"

    def _hybrid_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """하이브리드 검색 실행"""
        try:
            logger.info(f"🔍 하이브리드 검색: {query}")
            start = time.time()

            # 하이브리드 검색 실행
            results = self.hybrid_search.search(
                query=query,
                top_k=top_k,
                include_debug=False
            )

            # 결과 포맷팅
            formatted_results = []

            # HybridSearch는 Dict를 반환 ('fused_results' 키에 실제 결과)
            if isinstance(results, dict):
                actual_results = results.get('fused_results', results.get('results', []))
            else:
                actual_results = results

            for result in actual_results:
                # 메타데이터에서 파일 정보 추출
                metadata = result.get('metadata', {})

                formatted = {
                    'filename': metadata.get('filename', '알 수 없음'),
                    'path': metadata.get('path', ''),
                    'score': result.get('hybrid_score', result.get('score', 0.0)),
                    'content': result.get('content', ''),
                    # 추가 정보
                    'source': 'hybrid',
                    'bm25_score': result.get('bm25_score', 0.0),
                    'vector_score': result.get('vector_score', 0.0)
                }

                # 날짜 추출 (파일명에서)
                date = self._extract_date_from_filename(formatted['filename'])
                if date:
                    formatted['date'] = date

                # 카테고리 추출
                formatted['category'] = self._extract_category_from_path(Path(formatted['path']))

                formatted_results.append(formatted)

            elapsed = time.time() - start
            logger.info(f"✅ 하이브리드 검색 완료: {len(formatted_results)}개 결과, {elapsed:.2f}초")

            return formatted_results

        except Exception as e:
            logger.error(f"❌ 하이브리드 검색 실패: {e}")
            # 실패 시 기본 검색으로 폴백
            return super().search_by_content(query, top_k)

    def get_search_statistics(self) -> Dict[str, Any]:
        """검색 통계 반환 (하이브리드 포함)"""
        stats = super().get_search_statistics()

        if self.hybrid_search:
            stats['hybrid_available'] = True
            stats['hybrid_stats'] = {
                'vector_index_size': getattr(self.hybrid_search, 'vector_store_size', 0),
                'bm25_index_size': getattr(self.hybrid_search, 'bm25_store_size', 0),
                'cache_hits': getattr(self.hybrid_search, 'cache_hits', 0),
                'cache_misses': getattr(self.hybrid_search, 'cache_misses', 0)
            }
        else:
            stats['hybrid_available'] = False

        return stats


def test_hybrid_search():
    """하이브리드 검색 테스트"""
    print("🧪 하이브리드 검색 모듈 테스트")
    print("=" * 60)

    # 하이브리드 검색 모듈 초기화
    search = SearchModuleHybrid(use_hybrid=True)

    test_queries = [
        ("카메라 수리", "basic"),
        ("DVR 관련 문서를 모두 찾아줘", "hybrid"),
        ("2024년 구매 검토서", "auto"),
        ("비슷한 종류의 장비 구매 건", "hybrid")
    ]

    for query, expected_mode in test_queries:
        print(f"\n📝 쿼리: {query}")
        print(f"   예상 모드: {expected_mode}")

        # 자동 모드로 검색
        results = search.search_by_content(query, top_k=3, mode="auto")

        print(f"   결과: {len(results)}개")
        for i, doc in enumerate(results[:3], 1):
            source = doc.get('source', 'unknown')
            print(f"   {i}. [{source}] {doc['filename'][:50]}... (점수: {doc.get('score', 0):.2f})")

    # 통계 출력
    stats = search.get_search_statistics()
    print(f"\n📊 통계:")
    print(f"   하이브리드 사용 가능: {stats['hybrid_available']}")
    print(f"   총 문서: {stats['total_documents']}")


if __name__ == "__main__":
    test_hybrid_search()