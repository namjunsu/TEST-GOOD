"""임베딩 모델 v1.1

sentence-transformers를 사용한 텍스트 임베딩 생성.

특징:
- 한국어 특화 모델 지원 (jhgan/ko-sroberta-multitask)
- 배치 처리로 효율적인 임베딩
- GPU/CPU 자동 감지
- 싱글톤 패턴으로 메모리 효율화

2025-12-21 v1.1 변경사항:
- 배치 크기를 EmbeddingsConfig로 외부화
- H100 GPU 환경 최적화
"""

import os
import threading
from typing import Optional, Union

import numpy as np

from app.core.logging import get_logger
from config.constants import EmbeddingsConfig

logger = get_logger(__name__)


class EmbeddingModel:
    """임베딩 모델 클래스

    sentence-transformers를 래핑하여 텍스트 임베딩을 생성합니다.

    Args:
        model_name: 사용할 모델명 (기본: jhgan/ko-sroberta-multitask)
        device: 사용할 디바이스 ("cuda", "cpu", None=자동)
        normalize: 임베딩 정규화 여부
    """

    # 추천 한국어 모델
    DEFAULT_MODEL = "jhgan/ko-sroberta-multitask"
    # 대안 모델들
    ALTERNATIVE_MODELS = [
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "intfloat/multilingual-e5-small",
    ]

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        normalize: bool = True,
    ):
        self.model_name = model_name or os.getenv(
            "EMBEDDING_MODEL", self.DEFAULT_MODEL
        )
        self.normalize = normalize
        self._model = None
        self._lock = threading.Lock()
        self._dimension: Optional[int] = None

        # 디바이스 설정
        if device:
            self.device = device
        else:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            f"✅ EmbeddingModel 초기화: model={self.model_name}, device={self.device}"
        )

    def _load_model(self):
        """모델 Lazy Loading"""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer

                        logger.info(f"🔄 모델 로딩 중: {self.model_name}")
                        self._model = SentenceTransformer(
                            self.model_name,
                            device=self.device,
                        )
                        self._dimension = self._model.get_sentence_embedding_dimension()
                        logger.info(
                            f"✅ 모델 로드 완료: dim={self._dimension}"
                        )
                    except Exception as e:
                        logger.error(f"❌ 모델 로드 실패: {e}")
                        raise

    @property
    def dimension(self) -> int:
        """임베딩 차원 수 반환"""
        self._load_model()
        return self._dimension

    def encode(
        self,
        texts: Union[str, list[str]],
        batch_size: int = EmbeddingsConfig.ENCODE_BATCH_SIZE,
        show_progress: bool = False,
    ) -> np.ndarray:
        """텍스트를 벡터로 인코딩

        Args:
            texts: 단일 텍스트 또는 텍스트 리스트
            batch_size: 배치 크기
            show_progress: 진행률 표시 여부

        Returns:
            임베딩 벡터 (numpy array)
            - 단일 텍스트: shape (dimension,)
            - 리스트: shape (n_texts, dimension)
        """
        self._load_model()

        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        # 빈 텍스트 필터링
        texts = [t if t.strip() else " " for t in texts]

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
        )

        if single_input:
            return embeddings[0]

        return embeddings

    def encode_query(self, query: str) -> np.ndarray:
        """쿼리 임베딩 (단일 텍스트 최적화)

        Args:
            query: 검색 쿼리

        Returns:
            쿼리 임베딩 벡터
        """
        return self.encode(query)

    def encode_documents(
        self,
        documents: list[str],
        batch_size: int = EmbeddingsConfig.DOCUMENT_BATCH_SIZE,
        show_progress: bool = True,
    ) -> np.ndarray:
        """문서 임베딩 (대량 처리 최적화)

        Args:
            documents: 문서 텍스트 리스트
            batch_size: 배치 크기
            show_progress: 진행률 표시

        Returns:
            문서 임베딩 행렬 (n_docs, dimension)
        """
        return self.encode(
            documents,
            batch_size=batch_size,
            show_progress=show_progress,
        )

    def similarity(
        self,
        query_embedding: np.ndarray,
        doc_embeddings: np.ndarray,
    ) -> np.ndarray:
        """코사인 유사도 계산

        Args:
            query_embedding: 쿼리 벡터 (dimension,)
            doc_embeddings: 문서 벡터 행렬 (n_docs, dimension)

        Returns:
            유사도 점수 배열 (n_docs,)
        """
        # 정규화된 벡터면 내적 = 코사인 유사도
        if self.normalize:
            return np.dot(doc_embeddings, query_embedding)

        # 정규화 안 된 경우
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = doc_embeddings / np.linalg.norm(
            doc_embeddings, axis=1, keepdims=True
        )
        return np.dot(doc_norms, query_norm)


# 싱글톤 인스턴스
_embedding_model: Optional[EmbeddingModel] = None
_model_lock = threading.Lock()


def get_embedding_model(
    model_name: Optional[str] = None,
    force_reload: bool = False,
) -> EmbeddingModel:
    """EmbeddingModel 싱글톤 인스턴스 반환

    Args:
        model_name: 모델명 (첫 호출 시에만 적용)
        force_reload: 강제 재로드 여부

    Returns:
        EmbeddingModel 인스턴스
    """
    global _embedding_model

    with _model_lock:
        if _embedding_model is None or force_reload:
            _embedding_model = EmbeddingModel(model_name=model_name)

    return _embedding_model
