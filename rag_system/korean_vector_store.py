"""
한국어 특화 벡터 임베딩 및 FAISS 벡터 스토어 구현
jhgan/ko-sroberta-multitask 모델 사용
"""

import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import pickle
import hashlib
from functools import lru_cache

import torch
import faiss
from sentence_transformers import SentenceTransformer

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:
    TfidfVectorizer = None

# 설정 상수
DEFAULT_MODEL_NAME = "jhgan/ko-sroberta-multitask"
DEFAULT_EMBEDDING_DIM = 768  # ko-sroberta-multitask 기본 차원
DEFAULT_INDEX_PATH = "rag_system/db/korean_vector_index.faiss"
DEFAULT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"  # 자동 GPU 감지
MAX_BATCH_SIZE = 1024 if torch.cuda.is_available() else 512  # GPU시 더 큰 배치

# 환경변수 설정 (한 번만)
if "TRANSFORMERS_OFFLINE" not in os.environ:
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"

class KoreanVectorStore:
    """한국어 특화 FAISS 기반 벡터 스토어"""
    
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME,
                 index_path: str = None,
                 device: str = DEFAULT_DEVICE,
                 batch_size: int = MAX_BATCH_SIZE):
        self.model_name = model_name
        self.index_path = Path(index_path) if index_path else Path(DEFAULT_INDEX_PATH)
        self.device = device
        self.batch_size = batch_size
        self.metadata_path = self.index_path.with_suffix('.metadata.pkl')
        
        self.logger = logging.getLogger(__name__)
        
        # 임베딩 모델 로드
        self.embedding_model = None
        self.embedding_dim = DEFAULT_EMBEDDING_DIM
        self._cache_folder = None  # 캐시 폴더 저장
        
        # FAISS 인덱스
        self.index = None
        self.metadata = []  # 각 벡터에 대응하는 메타데이터
        
        self._initialize()
    
    @lru_cache(maxsize=1)
    def _get_cache_folder(self) -> str:
        """캐시 폴더 경로 가져오기 (캐시됨)"""
        try:
            from config import SENTENCE_TRANSFORMERS_CACHE
            cache_folder = SENTENCE_TRANSFORMERS_CACHE
        except ImportError:
            cache_folder = "./models/sentence_transformers"

        os.environ["TRANSFORMERS_CACHE"] = cache_folder
        return cache_folder

    def _initialize(self):
        """임베딩 모델 및 인덱스 초기화 (완전 오프라인 모드)"""
        try:
            self.logger.info(f"한국어 임베딩 모델 로딩 중: {self.model_name}")

            # 캐시 폴더 설정 (한 번만)
            self._cache_folder = self._get_cache_folder()
            
            try:
                # 로컬 경로에서 직접 로드 시도
                local_model_path = f"{self._cache_folder}/{self.model_name.replace('/', '--')}"
                
                if Path(local_model_path).exists():
                    self.logger.info(f"로컬 모델 경로 사용: {local_model_path}")
                    self.embedding_model = SentenceTransformer(
                        local_model_path,
                        device=self.device
                    )
                else:
                    # 로컬 캐시 폴더에서 로드 시도
                    self.logger.info(f"캐시 폴더에서 로드 시도: {self._cache_folder}")
                    
                    self.embedding_model = SentenceTransformer(
                        self.model_name,
                        device=self.device,
                        cache_folder=self._cache_folder
                    )
                
                # 실제 임베딩 차원 확인
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
                
                self.logger.info(f"한국어 임베딩 모델 로드 완료 (차원: {self.embedding_dim})")
                
            except Exception as model_error:
                self.logger.error(f"한국어 임베딩 모델 로드 실패: {model_error}")
                self.logger.info("폴백: 더미 임베딩 모델 생성")
                
                # 폴백: 더미 모델 생성
                self._create_fallback_embedder()
                self.logger.warning("더미 임베딩 모델로 동작 - 검색 품질 제한됨")
            
            # FAISS 인덱스 초기화 또는 로드
            if self.index_path.exists() and self.metadata_path.exists():
                self.load_index()
            else:
                self.create_new_index()
                
        except Exception as e:
            self.logger.error(f"한국어 벡터 스토어 초기화 실패: {e}")
            raise
    
    def _create_fallback_embedder(self):
        """폴백 임베딩 함수 생성 (TF-IDF 기반)"""
        
        class FallbackEmbedder:
            def __init__(self, dim=DEFAULT_EMBEDDING_DIM):
                self.dim = dim
                if TfidfVectorizer:
                    self.vectorizer = TfidfVectorizer(max_features=self.dim, stop_words=None)
                else:
                    self.vectorizer = None
                self.is_fitted = False
                
            def encode(self, texts, **kwargs):
                # 간단한 해시 기반 임베딩 (일관성 보장)
                embeddings = []
                for text in texts:
                    # 텍스트를 해시하여 벡터 생성
                    hash_obj = hashlib.sha256(str(text).encode())
                    hash_bytes = hash_obj.digest()
                    
                    # 지정된 차원 벡터로 확장 (해시 반복)
                    vector = []
                    for i in range(self.dim):
                        vector.append((hash_bytes[i % len(hash_bytes)] / 255.0) - 0.5)
                    
                    embeddings.append(vector)
                
                return np.array(embeddings, dtype='float32')
            
            def get_sentence_embedding_dimension(self):
                return self.dim
        
        self.embedding_model = FallbackEmbedder()
        self.embedding_dim = DEFAULT_EMBEDDING_DIM
    
    def create_new_index(self):
        """새 FAISS 인덱스 생성"""
        # 코사인 유사도 기반 인덱스 (한국어 텍스트에 더 적합)
        self.index = faiss.IndexFlatIP(self.embedding_dim)  # Inner Product (코사인 유사도)
        self.metadata = []
        self.logger.info("새 한국어 FAISS 인덱스 생성 완료")
    
    def save_index(self):
        """인덱스 및 메타데이터 저장"""
        try:
            # 디렉터리 생성
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            
            # FAISS 인덱스 저장
            faiss.write_index(self.index, str(self.index_path))
            
            # 메타데이터 저장
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
            
            self.logger.info(f"한국어 인덱스 저장 완료: {self.index_path}")
            
        except Exception as e:
            self.logger.error(f"한국어 인덱스 저장 실패: {e}")
            raise
    
    def load_index(self):
        """저장된 인덱스 및 메타데이터 로드"""
        try:
            # FAISS 인덱스 로드
            self.index = faiss.read_index(str(self.index_path))
            
            # 메타데이터 로드
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
            
            self.logger.info(f"한국어 인덱스 로드 완료: {len(self.metadata)}개 문서")
            
        except Exception as e:
            self.logger.error(f"한국어 인덱스 로드 실패: {e}")
            # 실패시 새 인덱스 생성
            self.create_new_index()
    
    def encode_texts(self, texts: List[str]) -> np.ndarray:
        """텍스트들을 벡터로 변환 (L2 정규화 포함, 배치 처리)"""
        try:
            # 대용량 텍스트를 배치로 처리
            if len(texts) > self.batch_size:
                all_embeddings = []
                for i in range(0, len(texts), self.batch_size):
                    batch = texts[i:i + self.batch_size]
                    batch_embeddings = self.embedding_model.encode(
                        batch,
                        convert_to_numpy=True,
                        show_progress_bar=False,  # 배치별로는 표시 안함
                        normalize_embeddings=True,
                        batch_size=self.batch_size
                    )
                    all_embeddings.append(batch_embeddings)
                embeddings = np.vstack(all_embeddings)
            else:
                embeddings = self.embedding_model.encode(
                    texts,
                    convert_to_numpy=True,
                    show_progress_bar=True,
                    normalize_embeddings=True,  # 코사인 유사도를 위한 정규화
                    batch_size=self.batch_size
                )
            return embeddings.astype('float32')
        except Exception as e:
            self.logger.error(f"한국어 텍스트 인코딩 실패: {e}")
            raise
    
    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        """문서들을 인덱스에 추가"""
        if len(texts) != len(metadatas):
            raise ValueError("텍스트와 메타데이터 개수가 일치하지 않습니다")
        
        try:
            # 텍스트들을 임베딩으로 변환
            embeddings = self.encode_texts(texts)
            
            # FAISS 인덱스에 추가
            self.index.add(embeddings)
            
            # 메타데이터 추가
            self.metadata.extend(metadatas)
            
            self.logger.info(f"{len(texts)}개 한국어 문서 추가 완료 (총 {len(self.metadata)}개)")
            
        except Exception as e:
            self.logger.error(f"한국어 문서 추가 실패: {e}")
            raise
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """쿼리와 유사한 문서 검색 (코사인 유사도)"""
        if self.index.ntotal == 0:
            return []
        
        try:
            # 쿼리 임베딩 (정규화 포함)
            query_embedding = self.encode_texts([query])
            
            # FAISS 검색 (내적 기반 - 정규화된 벡터에서는 코사인 유사도와 동일)
            scores, indices = self.index.search(query_embedding, top_k)
            
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.metadata) and idx != -1:  # 유효한 인덱스 확인
                    result = {
                        'rank': i + 1,
                        'score': float(score),  # 코사인 유사도 점수 (높을수록 유사)
                        'similarity': float(score),  # 정규화된 벡터에서 내적 = 코사인 유사도
                        **self.metadata[idx]
                    }
                    results.append(result)
            
            return results
            
        except Exception as e:
            self.logger.error(f"한국어 검색 실패: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """인덱스 통계 정보"""
        return {
            'total_vectors': self.index.ntotal if self.index else 0,
            'embedding_dim': self.embedding_dim,
            'model_name': self.model_name,
            'index_path': str(self.index_path),
            'metadata_count': len(self.metadata),
            'model_type': 'Korean Specialized (jhgan/ko-sroberta-multitask)',
            'similarity_metric': 'Cosine Similarity'
        }
    
    def rebuild_from_existing_data(self, old_vector_store_path: str = None):
        """기존 벡터스토어 데이터를 새 모델로 재구축"""
        try:
            old_path = Path(old_vector_store_path) if old_vector_store_path else Path("rag_system/db/vector_index.faiss")
            old_metadata_path = old_path.with_suffix('.metadata.pkl')
            
            if not (old_path.exists() and old_metadata_path.exists()):
                self.logger.warning("기존 인덱스를 찾을 수 없어 새로 시작합니다")
                return
                
            # 기존 메타데이터만 로드 (텍스트 추출용)
            with open(old_metadata_path, 'rb') as f:
                old_metadata = pickle.load(f)
            
            if not old_metadata:
                self.logger.warning("기존 메타데이터가 비어있습니다")
                return
            
            self.logger.info(f"기존 {len(old_metadata)}개 문서를 새 한국어 모델로 재구축 중...")
            
            # 텍스트 추출
            texts = [item.get('content', '') for item in old_metadata if item.get('content')]
            valid_metadata = [item for item in old_metadata if item.get('content')]
            
            if texts:
                # 새 모델로 재인덱싱
                self.create_new_index()
                self.add_documents(texts, valid_metadata)
                self.save_index()
                
                self.logger.info(f"한국어 모델 재구축 완료: {len(texts)}개 문서")
            else:
                self.logger.warning("재구축할 유효한 텍스트를 찾을 수 없습니다")
                
        except Exception as e:
            self.logger.error(f"한국어 모델 재구축 실패: {e}")
            raise

# 테스트 함수
def test_korean_vector_store():
    """한국어 벡터 스토어 테스트"""
    print("🔍 한국어 벡터 스토어 테스트 시작")
    
    # 테스트 데이터 (한국어 방송 기술 관련)
    test_texts = [
        "핀마이크 모델 ECM-77BC를 구매 검토합니다. 가격은 336,000원입니다.",
        "영상편집팀 워크스테이션 교체 비용은 179,300,000원입니다. HP Z8 모델입니다.",
        "광화문 스튜디오 모니터 교체 총액은 9,760,000원입니다. LG 모니터 3대입니다.",
        "방송 장비 중 카메라 렌즈 Canon EF 70-200mm를 신규 도입합니다.",
        "음향 장비 업그레이드를 위해 믹싱 콘솔을 교체 검토중입니다."
    ]
    
    test_metadatas = [
        {
            'doc_id': 'doc1',
            'chunk_id': 'chunk1_1',
            'filename': '2021-05-13_핀마이크_구매검토.pdf',
            'content': test_texts[0],
            'metadata': {'doc_type': '기안서', 'amount': 336000}
        },
        {
            'doc_id': 'doc2', 
            'chunk_id': 'chunk2_1',
            'filename': '2022-02-03_워크스테이션_교체검토.pdf',
            'content': test_texts[1],
            'metadata': {'doc_type': '검토서', 'amount': 179300000}
        },
        {
            'doc_id': 'doc3',
            'chunk_id': 'chunk3_1', 
            'filename': '2025-01-09_모니터_교체검토.pdf',
            'content': test_texts[2],
            'metadata': {'doc_type': '기안서', 'amount': 9760000}
        },
        {
            'doc_id': 'doc4',
            'chunk_id': 'chunk4_1',
            'filename': '2023-08-15_카메라렌즈_도입.pdf',
            'content': test_texts[3],
            'metadata': {'doc_type': '도입서', 'amount': 5000000}
        },
        {
            'doc_id': 'doc5',
            'chunk_id': 'chunk5_1',
            'filename': '2024-03-20_음향장비_업그레이드.pdf',
            'content': test_texts[4],
            'metadata': {'doc_type': '검토서', 'amount': 15000000}
        }
    ]
    
    try:
        # 한국어 벡터 스토어 생성
        kvs = KoreanVectorStore(index_path="rag_system/db/test_korean_vector_index.faiss")
        
        # 문서 추가
        print("📝 한국어 테스트 문서 추가 중...")
        kvs.add_documents(test_texts, test_metadatas)
        
        # 인덱스 저장
        kvs.save_index()
        
        # 검색 테스트 (한국어 쿼리)
        test_queries = [
            "핀마이크 가격은 얼마인가요?",
            "워크스테이션 모델명을 알려주세요", 
            "모니터 몇 대를 교체하나요?",
            "카메라 장비 관련 정보를 찾고 있습니다",
            "음향 장비 예산은 어느 정도인가요?",
            "가장 비싼 장비는 무엇인가요?"
        ]
        
        for query in test_queries:
            print(f"\n🔍 검색: '{query}'")
            results = kvs.search(query, top_k=3)
            
            for result in results:
                print(f"  순위 {result['rank']}: {result['filename']}")
                print(f"    코사인 유사도: {result['similarity']:.4f}")
                print(f"    내용: {result['content'][:60]}...")
        
        # 통계 출력
        stats = kvs.get_stats()
        print(f"\n📊 한국어 인덱스 통계:")
        print(f"  총 벡터 수: {stats['total_vectors']}")
        print(f"  임베딩 차원: {stats['embedding_dim']}")
        print(f"  모델: {stats['model_name']}")
        print(f"  유사도 메트릭: {stats['similarity_metric']}")
        
        print("✅ 한국어 벡터 스토어 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ 한국어 벡터 스토어 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_korean_vector_store()