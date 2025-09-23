"""
BM25 검색 모듈
==============

BM25 알고리즘 기반 한국어 문서 검색을 제공합니다.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from rank_bm25 import BM25Okapi
from konlpy.tag import Okt
import re

from ..config import RAGConfig
from ..exceptions import SearchException, handle_errors

logger = logging.getLogger(__name__)


class BM25Search:
    """BM25 검색 엔진 클래스"""

    def __init__(self, config: RAGConfig):
        """
        Args:
            config: RAG 설정 객체
        """
        self.config = config
        self.tokenizer = Okt()
        self.bm25 = None
        self.documents = []
        self.document_ids = []
        self.index_path = config.cache_dir / "bm25_index.pkl"

        # BM25 파라미터
        self.k1 = 1.2
        self.b = 0.75

        # 한국어 불용어
        self.stop_words = {
            '의', '가', '이', '은', '들', '는', '좀', '잘', '걍', '과',
            '도', '를', '으로', '자', '에', '와', '한', '하다', '을'
        }

    def _tokenize(self, text: str) -> List[str]:
        """
        한국어 텍스트 토큰화

        Args:
            text: 입력 텍스트

        Returns:
            토큰 리스트
        """
        # 소문자 변환
        text = text.lower()

        # 특수문자 제거
        text = re.sub(r'[^\w\s]', ' ', text)

        # 형태소 분석
        tokens = []
        try:
            morphs = self.tokenizer.morphs(text)
            tokens = [
                token for token in morphs
                if token not in self.stop_words and len(token) > 1
            ]
        except Exception as e:
            logger.warning(f"Tokenization failed: {e}")
            # Fallback to simple split
            tokens = text.split()

        return tokens

    @handle_errors(default_return=[])
    def build_index(self, documents: List[Dict]) -> None:
        """
        BM25 인덱스 구축

        Args:
            documents: 문서 딕셔너리 리스트
                      각 문서는 'id', 'text', 'metadata' 필드 포함
        """
        logger.info(f"Building BM25 index for {len(documents)} documents")

        self.documents = documents
        self.document_ids = [doc['id'] for doc in documents]

        # 문서 토큰화
        tokenized_docs = []
        for doc in documents:
            tokens = self._tokenize(doc.get('text', ''))
            tokenized_docs.append(tokens)

        # BM25 인덱스 생성
        self.bm25 = BM25Okapi(
            tokenized_docs,
            k1=self.k1,
            b=self.b
        )

        # 인덱스 저장
        self.save_index()

        logger.info("BM25 index built successfully")

    def save_index(self) -> None:
        """인덱스를 파일로 저장"""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            index_data = {
                'bm25': self.bm25,
                'documents': self.documents,
                'document_ids': self.document_ids,
                'k1': self.k1,
                'b': self.b
            }

            with open(self.index_path, 'wb') as f:
                pickle.dump(index_data, f)

            logger.info(f"Index saved to {self.index_path}")

        except Exception as e:
            logger.error(f"Failed to save index: {e}")

    def load_index(self) -> bool:
        """저장된 인덱스 로드"""
        try:
            if not self.index_path.exists():
                return False

            with open(self.index_path, 'rb') as f:
                index_data = pickle.load(f)

            self.bm25 = index_data['bm25']
            self.documents = index_data['documents']
            self.document_ids = index_data['document_ids']
            self.k1 = index_data.get('k1', 1.2)
            self.b = index_data.get('b', 0.75)

            logger.info(f"Index loaded from {self.index_path}")
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
        BM25 검색 수행

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            min_score: 최소 점수 임계값

        Returns:
            검색 결과 리스트
        """
        if not self.bm25:
            raise SearchException("BM25 index not built")

        # 쿼리 토큰화
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # BM25 점수 계산
        scores = self.bm25.get_scores(query_tokens)

        # 상위 k개 결과 선택
        top_indices = np.argsort(scores)[::-1][:top_k]

        # 결과 생성
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < min_score:
                break

            result = {
                'id': self.document_ids[idx],
                'score': score,
                'text': self.documents[idx].get('text', ''),
                'metadata': self.documents[idx].get('metadata', {}),
                'type': 'bm25'
            }
            results.append(result)

        logger.info(f"BM25 search returned {len(results)} results for query: {query[:50]}")
        return results

    def update_document(self, doc_id: str, text: str) -> bool:
        """
        단일 문서 업데이트

        Args:
            doc_id: 문서 ID
            text: 새로운 텍스트

        Returns:
            성공 여부
        """
        try:
            # 문서 찾기
            idx = self.document_ids.index(doc_id)

            # 문서 업데이트
            self.documents[idx]['text'] = text

            # 인덱스 재구축
            self.build_index(self.documents)

            return True

        except ValueError:
            logger.error(f"Document {doc_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to update document: {e}")
            return False

    def delete_document(self, doc_id: str) -> bool:
        """
        문서 삭제

        Args:
            doc_id: 삭제할 문서 ID

        Returns:
            성공 여부
        """
        try:
            # 문서 찾기
            idx = self.document_ids.index(doc_id)

            # 문서 제거
            del self.documents[idx]
            del self.document_ids[idx]

            # 인덱스 재구축
            if self.documents:
                self.build_index(self.documents)
            else:
                self.bm25 = None

            return True

        except ValueError:
            logger.error(f"Document {doc_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            return False

    def get_stats(self) -> Dict:
        """
        인덱스 통계 반환

        Returns:
            통계 정보
        """
        if not self.bm25:
            return {'status': 'not_built'}

        return {
            'status': 'ready',
            'num_documents': len(self.documents),
            'avg_doc_length': self.bm25.avgdl if hasattr(self.bm25, 'avgdl') else 0,
            'k1': self.k1,
            'b': self.b,
            'index_size': self.index_path.stat().st_size if self.index_path.exists() else 0
        }