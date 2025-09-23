"""
벡터 검색 모듈
==============

임베딩 기반 시맨틱 검색을 제공합니다.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import pickle

from ..config import RAGConfig
from ..exceptions import SearchException, handle_errors

logger = logging.getLogger(__name__)


class VectorSearch:
    """벡터 검색 엔진 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.model = None
        self.index = None
        self.documents = []
        self.document_ids = []
        self.embeddings = None

        # 모델 설정
        self.model_name = 'snunlp/KR-SBERT-V40K-klueNLI-augSTS'
        self.embedding_dim = 768
        self.index_path = config.cache_dir / "vector_index.faiss"
        self.metadata_path = config.cache_dir / "vector_metadata.pkl"

        # 초기화
        self._init_model()

    def _init_model(self) -> None:
        """임베딩 모델 초기화"""
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise SearchException(f"Model initialization failed: {e}")

    @handle_errors(default_return=None)
    def encode(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        텍스트를 벡터로 변환

        Args:
            texts: 텍스트 리스트
            batch_size: 배치 크기

        Returns:
            임베딩 벡터 배열
        """
        if not self.model:
            raise SearchException("Model not initialized")

        # 빈 텍스트 처리
        texts = [text if text else " " for text in texts]

        # 임베딩 생성
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
            convert_to_numpy=True
        )

        return embeddings

    @handle_errors(default_return=None)
    def build_index(self, documents: List[Dict]) -> None:
        """
        FAISS 인덱스 구축

        Args:
            documents: 문서 딕셔너리 리스트
        """
        logger.info(f"Building vector index for {len(documents)} documents")

        self.documents = documents
        self.document_ids = [doc['id'] for doc in documents]

        # 텍스트 추출
        texts = [doc.get('text', '') for doc in documents]

        # 임베딩 생성
        self.embeddings = self.encode(texts, batch_size=self.config.batch_size)

        # FAISS 인덱스 생성
        self.index = faiss.IndexFlatIP(self.embedding_dim)  # Inner Product (코사인 유사도)

        # L2 정규화 (코사인 유사도를 위해)
        faiss.normalize_L2(self.embeddings)

        # 인덱스에 벡터 추가
        self.index.add(self.embeddings)

        # 인덱스 저장
        self.save_index()

        logger.info("Vector index built successfully")

    def save_index(self) -> None:
        """인덱스를 파일로 저장"""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            # FAISS 인덱스 저장
            faiss.write_index(self.index, str(self.index_path))

            # 메타데이터 저장
            metadata = {
                'documents': self.documents,
                'document_ids': self.document_ids,
                'embeddings': self.embeddings,
                'embedding_dim': self.embedding_dim
            }

            with open(self.metadata_path, 'wb') as f:
                pickle.dump(metadata, f)

            logger.info(f"Vector index saved to {self.index_path}")

        except Exception as e:
            logger.error(f"Failed to save index: {e}")

    def load_index(self) -> bool:
        """저장된 인덱스 로드"""
        try:
            if not self.index_path.exists() or not self.metadata_path.exists():
                return False

            # FAISS 인덱스 로드
            self.index = faiss.read_index(str(self.index_path))

            # 메타데이터 로드
            with open(self.metadata_path, 'rb') as f:
                metadata = pickle.load(f)

            self.documents = metadata['documents']
            self.document_ids = metadata['document_ids']
            self.embeddings = metadata['embeddings']
            self.embedding_dim = metadata['embedding_dim']

            logger.info(f"Vector index loaded from {self.index_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False

    @handle_errors(default_return=[])
    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0
    ) -> List[Dict]:
        """
        벡터 검색 수행

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            min_score: 최소 점수 임계값

        Returns:
            검색 결과 리스트
        """
        if not self.index:
            raise SearchException("Vector index not built")

        # 쿼리 임베딩
        query_embedding = self.encode([query])[0]
        query_embedding = query_embedding.reshape(1, -1)

        # L2 정규화
        faiss.normalize_L2(query_embedding)

        # 검색 수행
        scores, indices = self.index.search(query_embedding, top_k)

        # 결과 생성
        results = []
        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx == -1 or score < min_score:
                break

            result = {
                'id': self.document_ids[idx],
                'score': float(score),
                'text': self.documents[idx].get('text', ''),
                'metadata': self.documents[idx].get('metadata', {}),
                'type': 'vector'
            }
            results.append(result)

        logger.info(f"Vector search returned {len(results)} results for query: {query[:50]}")
        return results

    def add_document(self, doc: Dict) -> bool:
        """
        단일 문서 추가

        Args:
            doc: 문서 딕셔너리

        Returns:
            성공 여부
        """
        try:
            # 문서 추가
            self.documents.append(doc)
            self.document_ids.append(doc['id'])

            # 임베딩 생성
            embedding = self.encode([doc.get('text', '')])[0]
            embedding = embedding.reshape(1, -1)
            faiss.normalize_L2(embedding)

            # 인덱스에 추가
            self.index.add(embedding)

            # 임베딩 배열 업데이트
            if self.embeddings is not None:
                self.embeddings = np.vstack([self.embeddings, embedding])
            else:
                self.embeddings = embedding

            # 저장
            self.save_index()

            return True

        except Exception as e:
            logger.error(f"Failed to add document: {e}")
            return False

    def get_similar_documents(
        self,
        doc_id: str,
        top_k: int = 5
    ) -> List[Dict]:
        """
        유사한 문서 찾기

        Args:
            doc_id: 기준 문서 ID
            top_k: 반환할 문서 수

        Returns:
            유사 문서 리스트
        """
        try:
            # 문서 인덱스 찾기
            idx = self.document_ids.index(doc_id)

            # 해당 문서의 임베딩
            doc_embedding = self.embeddings[idx].reshape(1, -1)

            # 검색 수행 (자기 자신 제외하기 위해 top_k+1)
            scores, indices = self.index.search(doc_embedding, top_k + 1)

            # 결과 생성 (자기 자신 제외)
            results = []
            for score, result_idx in zip(scores[0], indices[0]):
                if result_idx != idx and result_idx != -1:
                    results.append({
                        'id': self.document_ids[result_idx],
                        'score': float(score),
                        'text': self.documents[result_idx].get('text', ''),
                        'metadata': self.documents[result_idx].get('metadata', {})
                    })

            return results[:top_k]

        except ValueError:
            logger.error(f"Document {doc_id} not found")
            return []
        except Exception as e:
            logger.error(f"Failed to find similar documents: {e}")
            return []

    def get_stats(self) -> Dict:
        """
        인덱스 통계 반환

        Returns:
            통계 정보
        """
        if not self.index:
            return {'status': 'not_built'}

        return {
            'status': 'ready',
            'num_documents': len(self.documents),
            'embedding_dim': self.embedding_dim,
            'index_size': self.index.ntotal,
            'model_name': self.model_name,
            'index_file_size': self.index_path.stat().st_size if self.index_path.exists() else 0
        }