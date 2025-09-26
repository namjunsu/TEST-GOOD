"""
Professional RAG Core Engine
진짜 RAG 시스템의 핵심 엔진
"""

import os
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import numpy as np

@dataclass
class Document:
    """문서 데이터 클래스"""
    id: str
    content: str
    metadata: Dict[str, Any]
    chunks: List['Chunk'] = None
    embeddings: np.ndarray = None

@dataclass
class Chunk:
    """문서 청크 데이터 클래스"""
    id: str
    doc_id: str
    content: str
    metadata: Dict[str, Any]
    embedding: np.ndarray = None
    start_pos: int = 0
    end_pos: int = 0

class RAGCore:
    """프로덕션급 RAG 코어 엔진"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.documents = {}
        self.chunks = {}
        self.index = None
        self.vector_store = None
        self.llm = None

        # 초기화
        self._initialize_components()

    def _initialize_components(self):
        """컴포넌트 초기화"""
        from document_processor import DocumentProcessor
        from vector_store import VectorStore
        from search_engine import SearchEngine
        from llm_handler import LLMHandler

        self.doc_processor = DocumentProcessor(self.config)
        self.vector_store = VectorStore(self.config)
        self.search_engine = SearchEngine(self.config, self.vector_store)
        self.llm_handler = LLMHandler(self.config)

        print("✅ RAG Core 초기화 완료")

    def index_documents(self, doc_dir: str) -> Dict[str, Any]:
        """문서 인덱싱"""
        print(f"📚 문서 인덱싱 시작: {doc_dir}")

        start_time = time.time()
        results = {
            'processed': 0,
            'failed': 0,
            'chunks_created': 0
        }

        # 문서 로드 및 처리
        doc_paths = list(Path(doc_dir).rglob("*.pdf"))
        doc_paths.extend(list(Path(doc_dir).rglob("*.txt")))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for doc_path in doc_paths:
                future = executor.submit(self._process_document, doc_path)
                futures.append(future)

            for future in futures:
                try:
                    doc = future.result()
                    if doc:
                        self.documents[doc.id] = doc
                        results['processed'] += 1
                        results['chunks_created'] += len(doc.chunks) if doc.chunks else 0
                except Exception as e:
                    results['failed'] += 1
                    print(f"❌ 문서 처리 실패: {e}")

        # 벡터 인덱스 구축
        if self.documents:
            self._build_vector_index()

        elapsed = time.time() - start_time
        print(f"✅ 인덱싱 완료: {results['processed']}개 문서, "
              f"{results['chunks_created']}개 청크 ({elapsed:.1f}초)")

        return results

    def _process_document(self, doc_path: Path) -> Optional[Document]:
        """개별 문서 처리"""
        try:
            # 문서 로드
            content = self.doc_processor.load_document(doc_path)
            if not content:
                return None

            # 문서 ID 생성
            doc_id = hashlib.md5(str(doc_path).encode()).hexdigest()

            # 메타데이터 추출
            metadata = self.doc_processor.extract_metadata(doc_path, content)

            # 문서 객체 생성
            doc = Document(
                id=doc_id,
                content=content,
                metadata=metadata
            )

            # 청킹
            chunks = self.doc_processor.chunk_document(doc)
            doc.chunks = chunks

            # 청크 저장
            for chunk in chunks:
                self.chunks[chunk.id] = chunk

            return doc

        except Exception as e:
            print(f"❌ 문서 처리 오류 ({doc_path}): {e}")
            return None

    def _build_vector_index(self):
        """벡터 인덱스 구축"""
        print("🔧 벡터 인덱스 구축 중...")

        # 모든 청크의 임베딩 생성
        chunk_list = list(self.chunks.values())
        texts = [chunk.content for chunk in chunk_list]

        # 배치 임베딩
        embeddings = self.vector_store.create_embeddings(texts)

        # 청크에 임베딩 할당
        for chunk, embedding in zip(chunk_list, embeddings):
            chunk.embedding = embedding

        # 벡터 스토어에 추가
        self.vector_store.add_documents(chunk_list)

        print(f"✅ 벡터 인덱스 구축 완료: {len(chunk_list)}개 청크")

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """하이브리드 검색"""
        # 벡터 검색 + BM25 + 재순위
        results = self.search_engine.hybrid_search(
            query=query,
            documents=self.documents,
            chunks=self.chunks,
            top_k=top_k
        )

        return results

    def generate_answer(self, query: str, context: List[Dict[str, Any]]) -> str:
        """답변 생성"""
        # 컨텍스트 구성
        context_text = self._build_context(context)

        # LLM으로 답변 생성
        answer = self.llm_handler.generate(
            query=query,
            context=context_text
        )

        return answer

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """검색 결과로부터 컨텍스트 구성"""
        context_parts = []

        for i, result in enumerate(search_results, 1):
            chunk = self.chunks.get(result['chunk_id'])
            if chunk:
                doc = self.documents.get(chunk.doc_id)
                source = doc.metadata.get('filename', '알 수 없음') if doc else '알 수 없음'
                context_parts.append(f"[{i}. {source}]\n{chunk.content}\n")

        return "\n".join(context_parts)

    def query(self, question: str) -> Dict[str, Any]:
        """질의 응답 메인 함수"""
        start_time = time.time()

        # 검색
        search_results = self.search(question)

        # 답변 생성
        answer = self.generate_answer(question, search_results)

        # 결과 구성
        result = {
            'answer': answer,
            'sources': [r['metadata'] for r in search_results],
            'time': time.time() - start_time
        }

        return result

def create_rag_engine(config_path: str = "config.py") -> RAGCore:
    """RAG 엔진 생성 팩토리 함수"""
    import config

    rag_config = {
        'chunk_size': 500,
        'chunk_overlap': 100,
        'embedding_model': 'ko-sroberta-multitask',
        'vector_db': 'chromadb',
        'llm_model': 'qwen2.5-7b',
        'search_type': 'hybrid'
    }

    return RAGCore(rag_config)