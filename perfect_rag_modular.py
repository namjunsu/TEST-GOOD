"""
Perfect RAG System - Modularized Version
Clean Architecture Implementation
"""

from pathlib import Path
from typing import Optional, List, Dict, Any

# Internal modules
from rag_modules.core.config import RAGConfig
from rag_modules.core.exceptions import RAGException
from rag_modules.document.processor import DocumentProcessor
from rag_modules.search.engine import SearchEngine
from rag_modules.cache.manager import CacheManager

import logging

logger = logging.getLogger(__name__)

class PerfectRAG:
    """메인 RAG 시스템 - 모듈화된 버전"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()

        # 모듈 초기화
        self.document_processor = DocumentProcessor()
        self.search_engine = SearchEngine(self.config.parallel)
        self.cache_manager = CacheManager(self.config.cache)

        logger.info("PerfectRAG 시스템 초기화 완료")

    def search(self, query: str) -> str:
        """문서 검색 메인 메서드"""
        try:
            # 캐시 확인
            cache_key = f"search:{query}"
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                logger.info("Cache hit")
                return cached_result

            # 문서 로드
            documents = self._load_documents()

            # 검색 수행
            results = self.search_engine.search(query, documents)

            # 결과 포맷팅
            formatted_result = self._format_results(results)

            # 캐시 저장
            self.cache_manager.set(cache_key, formatted_result)

            return formatted_result

        except Exception as e:
            logger.error(f"Search error: {e}")
            raise RAGException(f"검색 중 오류 발생: {str(e)}")

    def _load_documents(self) -> List[Dict]:
        """문서 로드"""
        documents = []

        for pdf_file in self.config.docs_dir.glob("**/*.pdf"):
            try:
                content = self.document_processor.extract_text(pdf_file)
                documents.append({
                    'path': pdf_file,
                    'content': content
                })
            except Exception as e:
                logger.error(f"Document load error: {e}")

        return documents

    def _format_results(self, results: List[Dict]) -> str:
        """결과 포맷팅"""
        if not results:
            return "검색 결과가 없습니다."

        formatted = []
        for i, result in enumerate(results[:5], 1):
            doc = result['document']
            score = result['score']
            formatted.append(f"[{i}] {doc['path'].name} (점수: {score:.2f})")

        return '\n'.join(formatted)

# 하위 호환성을 위한 별칭
ModularPerfectRAG = PerfectRAG
