"""
PerfectRAG v2 - 모듈화된 RAG 시스템
====================================

기존 perfect_rag.py의 리팩토링 버전입니다.
새로운 모듈 시스템을 사용하여 깔끔하고 유지보수가 쉬운 구조로 변경되었습니다.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import hashlib

from rag_core.config import RAGConfig
from rag_core.exceptions import RAGException, handle_errors
from rag_core.document.pdf_processor import PDFProcessor
from rag_core.search import HybridSearch
from rag_core.llm.qwen_model import QwenLLM
from rag_core.llm.prompt_manager import PromptManager
from rag_core.cache.lru_cache import LRUCache
from log_system import get_logger
from response_formatter import format_as_markdown
from smart_search_enhancer import SmartSearchEnhancer

logger = logging.getLogger(__name__)


class PerfectRAG:
    """
    리팩토링된 PerfectRAG 클래스

    기존 인터페이스를 유지하면서 새로운 모듈 시스템을 사용합니다.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 설정 파일 경로
        """
        # 로깅 초기화
        self.chat_logger = get_logger()
        logger.info("PerfectRAG v2 initializing...")

        # 설정 로드
        self.config = RAGConfig.from_file(config_path) if config_path else RAGConfig()
        self.config.validate()

        # 모듈 초기화
        self._init_modules()

        # 통계
        self.stats = {
            'queries_processed': 0,
            'cache_hits': 0,
            'total_time': 0.0
        }

        logger.info("PerfectRAG v2 initialized successfully")

    def _init_modules(self):
        """모듈 초기화"""
        try:
            # 문서 처리
            self.pdf_processor = PDFProcessor(self.config)

            # 검색 시스템
            self.search_engine = HybridSearch(self.config)

            # LLM
            self.llm = QwenLLM.get_instance(self.config)
            self.prompt_manager = PromptManager(self.config)

            # 캐시
            self.cache = LRUCache(self.config)

            # 검색 개선
            self.search_enhancer = SmartSearchEnhancer()

            # 문서 메타데이터 캐시
            self.metadata_cache = {}

            # 초기 인덱싱 (테스트 모드에서는 스킵)
            if os.environ.get('RAG_SKIP_INDEX_BUILD') != 'true':
                self._build_initial_index()
            else:
                logger.info("Skipping index build in test mode")

        except Exception as e:
            logger.error(f"Module initialization failed: {e}")
            raise RAGException(f"Failed to initialize modules: {e}")

    def _build_initial_index(self):
        """초기 인덱스 구축"""
        try:
            # 저장된 인덱스 로드 시도
            if self.search_engine.load_index():
                logger.info("Loaded existing search index")
                return

            # 새 인덱스 구축
            logger.info("Building new search index...")
            documents = self._scan_documents()

            if documents:
                self.search_engine.build_index(documents)
                logger.info(f"Built index for {len(documents)} documents")
            else:
                logger.warning("No documents found for indexing")

        except Exception as e:
            logger.error(f"Index building failed: {e}")

    def _scan_documents(self) -> List[Dict]:
        """문서 스캔 및 로드"""
        documents = []
        docs_dir = self.config.docs_dir

        # PDF 파일 스캔
        pdf_files = list(docs_dir.glob("**/*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files")

        # 배치 처리
        for i in range(0, len(pdf_files), self.config.batch_size):
            batch = pdf_files[i:i + self.config.batch_size]
            results = self.pdf_processor.process_batch(batch)

            for result in results:
                if result['success']:
                    doc_id = str(result['path'])
                    documents.append({
                        'id': doc_id,
                        'text': result['text'],
                        'metadata': result['metadata']
                    })

                    # 메타데이터 캐시 저장
                    self.metadata_cache[doc_id] = result['metadata']

        return documents

    @handle_errors(default_return="")
    def search_and_generate(
        self,
        query: str,
        mode: str = 'document',
        top_k: int = 5,
        use_cache: bool = True
    ) -> str:
        """
        검색 및 응답 생성 (메인 인터페이스)

        Args:
            query: 사용자 질의
            mode: 검색 모드 ('document' or 'asset')
            top_k: 반환할 검색 결과 수
            use_cache: 캐시 사용 여부

        Returns:
            생성된 응답
        """
        start_time = time.time()
        self.stats['queries_processed'] += 1

        logger.info(f"Processing query: {query[:100]}...")

        # 캐시 확인
        if use_cache:
            cache_key = {'query': query, 'mode': mode, 'top_k': top_k}
            cached_response = self.cache.get(cache_key)

            if cached_response:
                self.stats['cache_hits'] += 1
                elapsed_time = time.time() - start_time
                self.stats['total_time'] += elapsed_time
                logger.info(f"Cache hit! Response time: {elapsed_time:.3f}s")
                return cached_response

        try:
            # 쿼리 개선
            enhanced_query = self.search_enhancer.enhance_query(query)

            # 검색 수행
            search_results = self._perform_search(enhanced_query, mode, top_k)

            # 컨텍스트 생성
            context = self._build_context(search_results)

            # 응답 생성
            response = self._generate_response(query, context, search_results)

            # 캐시 저장
            if use_cache:
                self.cache.set(cache_key, response)

            # 통계 업데이트
            elapsed_time = time.time() - start_time
            self.stats['total_time'] += elapsed_time
            logger.info(f"Query processed in {elapsed_time:.3f}s")

            return response

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"

    def _perform_search(self, query: str, mode: str, top_k: int) -> List[Dict]:
        """검색 수행"""
        if mode == 'asset':
            # Asset 모드는 별도 처리 (간단히 구현)
            return self._search_assets(query, top_k)
        else:
            # Document 모드
            return self.search_engine.search(query, top_k=top_k, use_reranker=True)

    def _search_assets(self, query: str, top_k: int) -> List[Dict]:
        """자산 검색 (간단한 구현)"""
        # 실제 자산 검색 로직은 기존 코드 참조
        # 여기서는 간단히 빈 리스트 반환
        logger.info("Asset search not fully implemented in v2")
        return []

    def _build_context(self, search_results: List[Dict]) -> str:
        """검색 결과로부터 컨텍스트 생성"""
        if not search_results:
            return ""

        context_parts = []
        for i, result in enumerate(search_results, 1):
            text = result.get('text', '')[:1000]  # 각 결과당 최대 1000자
            score = result.get('score', 0.0)
            source = result.get('metadata', {}).get('filename', 'Unknown')

            context_parts.append(
                f"[문서 {i}] (관련도: {score:.2f}, 출처: {source})\n{text}\n"
            )

        return "\n---\n".join(context_parts)

    def _generate_response(
        self,
        query: str,
        context: str,
        search_results: List[Dict]
    ) -> str:
        """LLM을 사용한 응답 생성"""
        # 프롬프트 생성
        prompt = self.prompt_manager.create_rag_prompt(query, context)

        # LLM 생성
        raw_response = self.llm.generate(
            prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )

        # 응답 포맷팅
        formatted_response = format_as_markdown({
            'response': raw_response,
            'sources': search_results
        }, formatter_type='document')

        return formatted_response

    def update_index(self, file_path: Path) -> bool:
        """단일 문서 인덱스 업데이트"""
        try:
            # PDF 처리
            text = self.pdf_processor.extract_text(file_path)
            metadata = self.pdf_processor.extract_metadata(file_path)

            # 문서 생성
            doc = {
                'id': str(file_path),
                'text': text,
                'metadata': metadata
            }

            # 인덱스 업데이트
            # Vector search에 추가
            if hasattr(self.search_engine.vector_search, 'add_document'):
                self.search_engine.vector_search.add_document(doc)

            # 메타데이터 캐시 업데이트
            self.metadata_cache[str(file_path)] = metadata

            logger.info(f"Index updated for: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to update index for {file_path}: {e}")
            return False

    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        cache_stats = self.cache.get_stats()
        llm_info = self.llm.get_model_info()
        search_stats = self.search_engine.get_stats()

        return {
            'rag_stats': self.stats,
            'cache_stats': cache_stats,
            'llm_info': llm_info,
            'search_stats': search_stats,
            'num_documents': len(self.metadata_cache)
        }

    def clear_cache(self):
        """캐시 클리어"""
        self.cache.clear()
        logger.info("Cache cleared")

    def save_state(self):
        """상태 저장"""
        self.cache.save_cache()
        logger.info("State saved")


# 기존 코드와의 호환성을 위한 함수
def main():
    """테스트용 메인 함수"""
    rag = PerfectRAG()

    # 테스트 쿼리
    test_query = "2024년 장비 구매 계획"
    response = rag.search_and_generate(test_query)

    print(f"Query: {test_query}")
    print(f"Response: {response[:500]}...")

    # 통계 출력
    stats = rag.get_stats()
    print(f"\nStats: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()