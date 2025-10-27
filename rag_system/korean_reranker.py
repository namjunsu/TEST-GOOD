"""
한국어 Reranker 모듈
Dongjin-kr/ko-reranker 모델을 사용한 문서 재정렬
"""

from app.core.logging import get_logger
import torch
import time
import re
import hashlib
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional
from functools import lru_cache
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np

try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Reranker 설정 상수
DEFAULT_MODEL_NAME = "Dongjin-kr/ko-reranker"
MAX_TOKEN_LENGTH = 512  # 토큰 최대 길이
JACCARD_WEIGHT = 0.7  # Jaccard 유사도 가중치
TF_WEIGHT = 0.3  # Term Frequency 가중치
CACHE_SIZE = 1024  # 캐시 크기
BATCH_SIZE = 32  # 배치 처리 크기

class KoreanReranker:
    """한국어 문서 재정렬 모델"""
    
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME,
                 fallback_mode: bool = True,
                 device: Optional[str] = None,
                 batch_size: int = BATCH_SIZE):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self.logger = get_logger(__name__)
        self.fallback_mode = fallback_mode
        
        # 오프라인 환경이므로 바로 키워드 기반 스코어링 사용
        self.use_keyword_scoring = True
        self.logger.info("오프라인 모드: 키워드 기반 스코어링 사용")

        # 성능 통계
        self.rerank_count = 0
        self.total_rerank_time = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
    
    def load_model(self):
        """Reranker 모델 로드"""
        try:
            self.logger.info(f"Reranker 모델 로딩 중: {self.model_name}")
            
            # 토크나이저 로드
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # 모델 로드
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None
            )
            
            if self.device == "cpu":
                self.model = self.model.to(self.device)
            
            self.model.eval()
            self.logger.info(f"Reranker 모델 로드 완료 (device: {self.device})")
            
        except Exception as e:
            self.logger.error(f"Reranker 모델 로드 실패: {e}")
            raise
    
    def load_fallback_model(self):
        """대안 모델 로드 (로컬 sentence-transformer 기반)"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            self.logger.error("sentence-transformers가 설치되지 않음")
            self.use_keyword_scoring = True
            self.logger.info("키워드 기반 스코어링으로 폴백")
            return
        
        try:
            self.logger.info("대안 Reranker 모델 로딩 중: sentence-transformers 기반")
            
            # 다국어 모델 사용 (한국어 지원)
            self.sentence_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.use_sentence_transformer = True
            
            self.logger.info("대안 Reranker 모델 로드 완료")
            
        except Exception as e:
            self.logger.error(f"대안 모델 로드 실패: {e}")
            # 최후의 수단: 키워드 기반 스코어링
            self.use_keyword_scoring = True
            self.logger.info("키워드 기반 스코어링으로 폴백")
    
    def _get_cache_key(self, query: str, document: str) -> str:
        """캐시 키 생성"""
        combined = f"{query}::{document[:200]}"  # 문서는 처음 200자만
        return hashlib.md5(combined.encode()).hexdigest()

    @lru_cache(maxsize=CACHE_SIZE)
    def _cached_score(self, cache_key: str, query: str, document: str) -> float:
        """캐시된 점수 계산"""
        return self._compute_score_internal(query, document)

    def compute_score(self, query: str, document: str) -> float:
        """쿼리와 문서 간 관련도 점수 계산 (캐시 적용)"""
        cache_key = self._get_cache_key(query, document)

        # 캐시 통계 업데이트
        if cache_key in self._cached_score.__wrapped__.__dict__.get('cache', {}):
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        return self._cached_score(cache_key, query, document)

    def _compute_score_internal(self, query: str, document: str) -> float:
        """실제 점수 계산 로직"""
        try:
            # 원본 cross-encoder 모델 사용
            if hasattr(self, 'model') and self.model is not None:
                return self._compute_cross_encoder_score(query, document)
            
            # 대안 sentence transformer 모델 사용
            elif hasattr(self, 'use_sentence_transformer'):
                return self._compute_sentence_transformer_score(query, document)
            
            # 키워드 기반 스코어링 사용
            elif hasattr(self, 'use_keyword_scoring'):
                return self._compute_keyword_score(query, document)
            
            else:
                return 0.0
                
        except Exception as e:
            self.logger.error(f"점수 계산 실패: {e}")
            return 0.0
    
    def _compute_cross_encoder_score(self, query: str, document: str) -> float:
        """Cross-encoder 모델로 점수 계산"""
        # 입력 텍스트 준비
        pair = [query, document]
        
        # 토크나이징
        inputs = self.tokenizer(
            pair,
            padding=True,
            truncation=True,
            max_length=MAX_TOKEN_LENGTH,
            return_tensors="pt"
        ).to(self.device)
        
        # 점수 계산
        with torch.no_grad():
            outputs = self.model(**inputs)
            score = torch.sigmoid(outputs.logits).cpu().numpy()[0][0]
        
        return float(score)
    
    def _compute_sentence_transformer_score(self, query: str, document: str) -> float:
        """Sentence Transformer로 점수 계산 (cosine similarity)"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            return self._compute_keyword_score(query, document)
        
        # 임베딩 생성
        query_embedding = self.sentence_model.encode([query])
        doc_embedding = self.sentence_model.encode([document])
        
        # 코사인 유사도 계산
        similarity = util.pytorch_cos_sim(query_embedding, doc_embedding)
        score = float(similarity[0][0])
        
        # 0-1 범위로 정규화
        return (score + 1.0) / 2.0
    
    def _compute_keyword_score(self, query: str, document: str) -> float:
        """키워드 기반 점수 계산 (최후의 수단)"""
        # 한글과 영어, 숫자만 추출
        query_words = re.findall(r'[가-힣a-zA-Z0-9]+', query.lower())
        doc_words = re.findall(r'[가-힣a-zA-Z0-9]+', document.lower())
        
        if not query_words:
            return 0.0
        
        # 교집합 단어 개수
        query_set = set(query_words)
        doc_set = set(doc_words)
        intersection = len(query_set.intersection(doc_set))
        
        # Jaccard 유사도 계산
        union = len(query_set.union(doc_set))
        jaccard_score = intersection / union if union > 0 else 0.0
        
        # TF 가중치 추가
        doc_counter = Counter(doc_words)
        tf_score = sum(doc_counter.get(word, 0) for word in query_words)
        if len(doc_words) > 0:
            tf_score = tf_score / len(doc_words)
        else:
            tf_score = 0.0
        
        # 최종 점수 (Jaccard + TF)
        final_score = JACCARD_WEIGHT * jaccard_score + TF_WEIGHT * tf_score
        
        return min(max(final_score, 0.0), 1.0)
    
    def compute_batch_scores(self, query: str, documents: List[str]) -> List[float]:
        """배치로 여러 문서의 점수를 계산"""
        try:
            # 각 문서에 대해 개별 점수 계산
            all_scores = []
            for doc in documents:
                score = self.compute_score(query, doc)
                all_scores.append(score)
            
            return all_scores
            
        except Exception as e:
            self.logger.error(f"배치 점수 계산 실패: {e}")
            return [0.0] * len(documents)
    
    def rerank(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """검색 결과를 재정렬 (rerank_documents의 별칭)"""
        return self.rerank_documents(query, search_results, top_k)
    
    def rerank_documents(
        self, 
        query: str, 
        search_results: List[Dict[str, Any]], 
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """검색 결과를 재정렬"""
        if not search_results:
            return search_results
        
        start_time = time.time()
        
        try:
            # 문서 텍스트 추출
            documents = [result.get('content', '') for result in search_results]
            
            # 배치 점수 계산
            rerank_scores = self.compute_batch_scores(query, documents)
            
            # 원본 결과에 rerank 점수 추가
            for i, result in enumerate(search_results):
                result['rerank_score'] = rerank_scores[i]
                result['original_rank'] = i + 1
            
            # rerank 점수로 재정렬
            reranked_results = sorted(
                search_results, 
                key=lambda x: x['rerank_score'], 
                reverse=True
            )
            
            # 새로운 순위 부여
            for i, result in enumerate(reranked_results):
                result['rerank_rank'] = i + 1
            
            # 상위 K개만 반환
            if top_k is not None:
                reranked_results = reranked_results[:top_k]
            
            rerank_time = time.time() - start_time

            # 통계 업데이트
            self.rerank_count += 1
            self.total_rerank_time += rerank_time

            self.logger.info(
                f"문서 재정렬 완료: {len(search_results)}개 → {len(reranked_results)}개 "
                f"(시간: {rerank_time:.3f}초, 캐시 히트율: {self.cache_hits/(self.cache_hits+self.cache_misses)*100:.1f}%)"
            )
            
            return reranked_results
            
        except Exception as e:
            self.logger.error(f"문서 재정렬 실패: {e}")
            return search_results

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        stats = {
            'rerank_count': self.rerank_count,
            'total_rerank_time': self.total_rerank_time,
            'avg_rerank_time': self.total_rerank_time / self.rerank_count if self.rerank_count > 0 else 0.0,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) * 100 if (self.cache_hits + self.cache_misses) > 0 else 0.0,
            'cached_score_info': self._cached_score.cache_info() if hasattr(self._cached_score, 'cache_info') else None
        }
        return stats

    def get_reranking_analysis(self, reranked_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """재정렬 분석 정보 제공"""
        if not reranked_results:
            return {}
        
        # 순위 변동 분석
        rank_changes = []
        for result in reranked_results:
            original_rank = result.get('original_rank', 0)
            rerank_rank = result.get('rerank_rank', 0)
            change = original_rank - rerank_rank  # 양수면 순위 상승
            rank_changes.append(change)
        
        # 점수 통계
        rerank_scores = [r.get('rerank_score', 0.0) for r in reranked_results]
        
        analysis = {
            'total_documents': len(reranked_results),
            'rank_changes': {
                'improved': len([c for c in rank_changes if c > 0]),
                'degraded': len([c for c in rank_changes if c < 0]),
                'unchanged': len([c for c in rank_changes if c == 0]),
                'max_improvement': max(rank_changes) if rank_changes else 0,
                'max_degradation': min(rank_changes) if rank_changes else 0
            },
            'score_stats': {
                'mean_score': np.mean(rerank_scores) if rerank_scores else 0.0,
                'max_score': max(rerank_scores) if rerank_scores else 0.0,
                'min_score': min(rerank_scores) if rerank_scores else 0.0,
                'std_score': np.std(rerank_scores) if rerank_scores else 0.0
            }
        }
        
        return analysis

# 테스트 함수
def test_korean_reranker():
    """한국어 Reranker 테스트"""
    print("🔄 한국어 Reranker 테스트 시작")
    
    try:
        # Reranker 초기화
        reranker = KoreanReranker()
        
        # 테스트 쿼리와 문서들
        test_query = "HP Z8 워크스테이션 가격"
        test_documents = [
            {
                'content': '광화문 스튜디오 모니터 교체 총액은 9,760,000원입니다.',
                'filename': '2025-01-09_광화문스튜디오모니터교체.pdf',
                'score': 5.2
            },
            {
                'content': 'HP Z8 워크스테이션 총 금액은 179,300,000원입니다. 영상편집용입니다.',
                'filename': '2022-02-03_HP워크스테이션교체.pdf', 
                'score': 4.8
            },
            {
                'content': '핀마이크 모델 ECM-77BC 가격은 336,000원입니다.',
                'filename': '2021-05-13_핀마이크구매.pdf',
                'score': 3.1
            }
        ]
        
        print(f"🔍 테스트 쿼리: '{test_query}'")
        print(f"📄 문서 수: {len(test_documents)}")
        
        # 재정렬 수행
        reranked = reranker.rerank_documents(test_query, test_documents.copy())
        
        # 결과 출력
        print("\n📊 재정렬 결과:")
        for i, result in enumerate(reranked):
            print(f"  {i+1}위: {result['filename']}")
            print(f"      원본 순위: {result['original_rank']} → 재정렬: {result['rerank_rank']}")
            print(f"      원본 점수: {result['score']:.2f} → Rerank 점수: {result['rerank_score']:.4f}")
            print(f"      내용: {result['content'][:50]}...")
            print()
        
        # 분석 정보
        analysis = reranker.get_reranking_analysis(reranked)
        print("📈 재정렬 분석:")
        print(f"  순위 개선: {analysis['rank_changes']['improved']}개")
        print(f"  순위 하락: {analysis['rank_changes']['degraded']}개") 
        print(f"  평균 점수: {analysis['score_stats']['mean_score']:.4f}")
        print(f"  최고 점수: {analysis['score_stats']['max_score']:.4f}")
        
        print("✅ 한국어 Reranker 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ 한국어 Reranker 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_korean_reranker()