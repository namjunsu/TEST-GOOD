"""
Vector Store Module
벡터 데이터베이스 모듈
"""

import os
import json
import pickle
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from pathlib import Path
import faiss
from sentence_transformers import SentenceTransformer


class VectorStore:
    """벡터 스토어 - FAISS 기반"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.embedding_model_name = config.get('embedding_model', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        self.index_path = Path('indexes/vector_index')
        self.metadata_path = Path('indexes/metadata.json')

        # 임베딩 모델 로드
        print(f"🔧 임베딩 모델 로드 중: {self.embedding_model_name}")
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self.dimension = self.embedding_model.get_sentence_embedding_dimension()

        # FAISS 인덱스 초기화
        self.index = None
        self.metadata = []
        self.doc_ids = []

        self._initialize_index()

    def _initialize_index(self):
        """인덱스 초기화"""
        # 저장된 인덱스가 있으면 로드
        if self.index_path.exists():
            self.load_index()
        else:
            # 새 인덱스 생성
            self.index = faiss.IndexFlatIP(self.dimension)  # Inner Product (코사인 유사도)
            print(f"✅ 새 벡터 인덱스 생성 (차원: {self.dimension})")

    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """텍스트 임베딩 생성"""
        if not texts:
            return np.array([])

        # 배치 처리로 임베딩 생성
        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,  # 정규화로 코사인 유사도 계산
            show_progress_bar=True,
            batch_size=32
        )

        return embeddings

    def add_documents(self, chunks: List['Chunk']) -> None:
        """문서 청크 추가"""
        if not chunks:
            return

        # 임베딩 수집
        embeddings = []
        for chunk in chunks:
            if chunk.embedding is not None:
                embeddings.append(chunk.embedding)
                self.doc_ids.append(chunk.id)
                self.metadata.append({
                    'chunk_id': chunk.id,
                    'doc_id': chunk.doc_id,
                    'metadata': chunk.metadata
                })

        if embeddings:
            embeddings_array = np.array(embeddings).astype('float32')

            # FAISS 인덱스에 추가
            self.index.add(embeddings_array)

            print(f"✅ {len(embeddings)}개 벡터 추가 (총: {self.index.ntotal}개)")

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """벡터 검색"""
        # 쿼리 임베딩
        query_embedding = self.create_embeddings([query])

        if self.index is None or self.index.ntotal == 0:
            print("⚠️ 인덱스가 비어있습니다")
            return []

        # FAISS 검색
        distances, indices = self.index.search(
            query_embedding.astype('float32'),
            min(top_k, self.index.ntotal)
        )

        # 결과 구성
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.metadata):
                result = {
                    'score': float(dist),
                    'chunk_id': self.doc_ids[idx],
                    'metadata': self.metadata[idx]
                }
                results.append(result)

        return results

    def save_index(self) -> None:
        """인덱스 저장"""
        # 디렉토리 생성
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # FAISS 인덱스 저장
        if self.index and self.index.ntotal > 0:
            faiss.write_index(self.index, str(self.index_path))

            # 메타데이터 저장
            metadata_to_save = {
                'doc_ids': self.doc_ids,
                'metadata': self.metadata,
                'dimension': self.dimension,
                'model_name': self.embedding_model_name
            }

            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_to_save, f, ensure_ascii=False, indent=2)

            print(f"✅ 인덱스 저장 완료: {self.index.ntotal}개 벡터")

    def load_index(self) -> None:
        """인덱스 로드"""
        try:
            # FAISS 인덱스 로드
            self.index = faiss.read_index(str(self.index_path))

            # 메타데이터 로드
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                self.doc_ids = saved_data['doc_ids']
                self.metadata = saved_data['metadata']

            print(f"✅ 인덱스 로드 완료: {self.index.ntotal}개 벡터")

        except Exception as e:
            print(f"⚠️ 인덱스 로드 실패, 새로 생성: {e}")
            self.index = faiss.IndexFlatIP(self.dimension)
            self.doc_ids = []
            self.metadata = []

    def clear(self) -> None:
        """인덱스 초기화"""
        self.index = faiss.IndexFlatIP(self.dimension)
        self.doc_ids = []
        self.metadata = []
        print("✅ 벡터 인덱스 초기화")

    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보"""
        return {
            'total_vectors': self.index.ntotal if self.index else 0,
            'dimension': self.dimension,
            'model': self.embedding_model_name,
            'index_type': 'FAISS FlatIP'
        }