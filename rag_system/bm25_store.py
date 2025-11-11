"""
한국어 BM25 검색 구현
kiwipiepy 기반 토크나이저 사용
"""

from app.core.logging import get_logger
import os
import json
import pickle
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
import math

# kiwipiepy 토크나이저 (한국어 특화)
# AVX-VNNI 문제로 인해 비활성화
KIWIPIEPY_AVAILABLE = False
print("⚠️  kiwipiepy disabled due to AVX-VNNI issue, using basic tokenization")

class KoreanTokenizer:
    """한국어 토크나이저"""
    
    # 토크나이저 상수
    MIN_TOKEN_LENGTH = 1
    VALID_POS_TAGS = ['N', 'V', 'A', 'M']  # 명사, 동사, 형용사, 수식언
    TOKEN_PATTERN = r'[^\w\s가-힣]'  # 한글, 영문, 숫자 외 제거
    CACHE_SIZE = 2048  # 토큰 캐시 크기

    def __init__(self):
        self.logger = get_logger(__name__)

        # 패턴 컴파일
        self._compiled_token_pattern = re.compile(self.TOKEN_PATTERN)

        # 성능 통계
        self.tokenize_count = 0
        self.cache_hits = 0

        if KIWIPIEPY_AVAILABLE:
            try:
                # AVX-VNNI 문제 해결을 위해 num_workers=0으로 설정
                self.kiwi = Kiwi(num_workers=0)
                self.use_kiwi = True
                self.logger.info("Kiwi 한국어 토크나이저 로드 완료")
            except Exception as e:
                self.logger.warning(f"Kiwi 초기화 실패, 기본 토크나이저 사용: {e}")
                self.use_kiwi = False
        else:
            self.use_kiwi = False
    
    @lru_cache(maxsize=CACHE_SIZE)
    def tokenize(self, text: str) -> List[str]:
        """텍스트를 토큰으로 분할 (캐시됨)"""
        self.tokenize_count += 1
        if text in self.tokenize.__wrapped__.__dict__.get('cache', {}):
            self.cache_hits += 1

        if not text or not text.strip():
            return []
        
        try:
            if self.use_kiwi:
                # Kiwi로 형태소 분석
                result = self.kiwi.analyze(text)
                tokens = []
                for token, pos, _, _ in result[0][0]:  # 첫 번째 분석 결과 사용
                    # 의미있는 품사만 선택
                    if pos[0] in self.VALID_POS_TAGS:
                        tokens.append(token.lower())
                return tokens
            else:
                # 기본 토크나이저 (공백 + 특수문자 기준)
                text = self._compiled_token_pattern.sub(' ', text)  # 한글, 영문, 숫자만 유지
                tokens = [t.lower() for t in text.split() if len(t) > self.MIN_TOKEN_LENGTH]
                return tokens

        except Exception as e:
            self.logger.error(f"토큰화 실패: {e}")
            # fallback
            text = self._compiled_token_pattern.sub(' ', text)
            return [t.lower() for t in text.split() if len(t) > self.MIN_TOKEN_LENGTH]

class BM25Store:
    """BM25 키워드 검색 구현"""
    
    # BM25 파라미터 기본값
    DEFAULT_K1 = 1.2  # 용어 빈도 포화 매개변수
    DEFAULT_B = 0.75  # 문서 길이 정규화 매개변수
    DEFAULT_INDEX_PATH = "rag_system/db/bm25_index.pkl"
    
    def __init__(self, index_path: str = None, k1: float = None, b: float = None):
        self.index_path = Path(index_path) if index_path else Path(self.DEFAULT_INDEX_PATH)
        self.k1 = k1 if k1 is not None else self.DEFAULT_K1
        self.b = b if b is not None else self.DEFAULT_B
        
        self.logger = get_logger(__name__)
        self.tokenizer = KoreanTokenizer()

        # BM25 인덱스
        self.documents = []  # 원본 문서들
        self.metadata = []   # 문서 메타데이터
        self.term_freqs = []  # 각 문서별 용어 빈도
        self.doc_freqs = defaultdict(int)  # 용어별 문서 빈도
        self.doc_lens = []   # 각 문서의 길이
        self.avg_doc_len = 0.0  # 평균 문서 길이
        self.vocab = set()   # 전체 어휘

        # 성능 통계
        self.search_count = 0
        self.total_search_time = 0.0
        self.index_time = 0.0
        
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """기존 인덱스 로드 또는 새 인덱스 생성"""
        if self.index_path.exists():
            try:
                self.load_index()
                self.logger.info(f"BM25 인덱스 로드 완료: {len(self.documents)}개 문서")
            except Exception as e:
                self.logger.error(f"BM25 인덱스 로드 실패: {e}")
                self._create_new_index()
        else:
            self._create_new_index()
    
    def _create_new_index(self):
        """새 인덱스 초기화"""
        self.documents = []
        self.metadata = []
        self.term_freqs = []
        self.doc_freqs = defaultdict(int)
        self.doc_lens = []
        self.avg_doc_len = 0.0
        self.vocab = set()
        self.logger.info("새 BM25 인덱스 생성")
    
    def save_index(self):
        """인덱스 저장"""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            
            index_data = {
                'documents': self.documents,
                'metadata': self.metadata,
                'term_freqs': self.term_freqs,
                'doc_freqs': dict(self.doc_freqs),
                'doc_lens': self.doc_lens,
                'avg_doc_len': self.avg_doc_len,
                'vocab': list(self.vocab),
                'k1': self.k1,
                'b': self.b
            }
            
            with open(self.index_path, 'wb') as f:
                pickle.dump(index_data, f)
            
            self.logger.info(f"BM25 인덱스 저장 완료: {self.index_path}")
            
        except Exception as e:
            self.logger.error(f"BM25 인덱스 저장 실패: {e}")
            raise
    
    def load_index(self):
        """저장된 인덱스 로드"""
        try:
            with open(self.index_path, 'rb') as f:
                index_data = pickle.load(f)

            self.documents = index_data['documents']
            self.metadata = index_data['metadata']
            self.term_freqs = index_data['term_freqs']
            self.doc_freqs = defaultdict(int, index_data['doc_freqs'])
            self.doc_lens = index_data['doc_lens']
            self.avg_doc_len = index_data['avg_doc_len']
            self.vocab = set(index_data['vocab'])
            self.k1 = index_data.get('k1', 1.2)
            self.b = index_data.get('b', 0.75)

            # 메타데이터 길이 보정 (IndexError 방지)
            N = len(self.documents)
            if len(self.metadata) < N:
                self.metadata += [{} for _ in range(N - len(self.metadata))]
                self.logger.warning(f"메타데이터 부족분 패딩: {N - len(self.metadata)}개")
            elif len(self.metadata) > N:
                self.metadata = self.metadata[:N]
                self.logger.warning(f"메타데이터 초과분 절단: {len(self.metadata) - N}개")

        except Exception as e:
            self.logger.error(f"BM25 인덱스 로드 실패: {e}")
            raise
    
    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]], batch_size: int = 100) -> None:
        """문서들을 인덱스에 추가 (배치 처리 최적화)"""
        if len(texts) != len(metadatas):
            raise ValueError("텍스트와 메타데이터 개수가 일치하지 않습니다")

        start_time = time.time()
        total_docs = len(texts)

        try:
            # 배치 처리 (메모리 효율성)
            for batch_start in range(0, total_docs, batch_size):
                batch_end = min(batch_start + batch_size, total_docs)
                batch_texts = texts[batch_start:batch_end]
                batch_metadatas = metadatas[batch_start:batch_end]

                for text, metadata in zip(batch_texts, batch_metadatas):
                    # 토큰화
                    tokens = self.tokenizer.tokenize(text)

                    # 문서 추가
                    self.documents.append(text)
                    self.metadata.append(metadata)

                    # 용어 빈도 계산
                    term_freq = defaultdict(int)
                    for token in tokens:
                        term_freq[token] += 1
                        self.vocab.add(token)

                    self.term_freqs.append(dict(term_freq))
                    self.doc_lens.append(len(tokens))

                    # 문서 빈도 업데이트
                    for token in set(tokens):
                        self.doc_freqs[token] += 1

                # 배치 로깅
                if (batch_end - batch_start) >= 10:
                    self.logger.debug(f"BM25 인덱싱 진행: {batch_end}/{total_docs}")

            # 평균 문서 길이 재계산
            if self.doc_lens:
                self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens)

            # 인덱싱 시간 기록
            self.index_time += time.time() - start_time

            self.logger.info(f"{total_docs}개 문서 BM25 인덱싱 완료 (총 {len(self.documents)}개, {time.time() - start_time:.2f}초)")
            
        except Exception as e:
            self.logger.error(f"BM25 문서 추가 실패: {e}")
            raise

    
    def search(self, query: str, top_k: int = 5, snippet_max: int = 5000, **kwargs) -> List[Dict[str, Any]]:
        """BM25 스코어로 문서 검색 (성능 추적 포함)

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            snippet_max: 스니펫 최대 길이 (기본: 5000자)
            **kwargs: 추가 옵션
        """
        if not self.documents:
            return []

        start_time = time.time()
        self.search_count += 1

        try:
            # 쿼리 토큰화 (빈 쿼리 방어)
            query_tokens = self.tokenizer.tokenize(query)
            if not query_tokens:
                return []
            
            # 각 문서별 BM25 스코어 계산
            scores = []
            N = len(self.documents)  # 총 문서 수
            
            for doc_idx in range(N):
                score = 0.0
                doc_len = self.doc_lens[doc_idx]
                
                for token in query_tokens:
                    if token in self.term_freqs[doc_idx]:
                        # 용어 빈도 (TF)
                        tf = self.term_freqs[doc_idx][token]
                        
                        # 문서 빈도 (DF)
                        df = self.doc_freqs.get(token, 0)
                        if df == 0:
                            continue
                        
                        # IDF 계산
                        idf = math.log((N - df + 0.5) / (df + 0.5))
                        
                        # BM25 스코어 계산
                        numerator = tf * (self.k1 + 1)
                        denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
                        
                        score += idf * (numerator / denominator)
                
                scores.append((score, doc_idx))
            
            # 스코어 기준 정렬
            scores.sort(key=lambda x: x[0], reverse=True)
            
            # 결과 구성
            results = []
            for i, (score, doc_idx) in enumerate(scores[:top_k]):
                if score > 0:  # 양의 스코어만
                    # 메타데이터 안전 접근 (IndexError 방지)
                    metadata = self.metadata[doc_idx] if doc_idx < len(self.metadata) else {}
                    # 스니펫 길이 제한 적용
                    content = self.documents[doc_idx]
                    snippet = content[:snippet_max] if snippet_max > 0 else content

                    result = {
                        'rank': i + 1,
                        'score': float(score),
                        'content': snippet,
                        'query_tokens': query_tokens,
                        **metadata
                    }
                    results.append(result)
            
            # 검색 시간 기록
            search_time = time.time() - start_time
            self.total_search_time += search_time

            if self.search_count % 100 == 0:
                self.logger.info(f"BM25 검색 통계: {self.search_count}회, 평균 {self.total_search_time/self.search_count:.3f}초")

            return results

        except Exception as e:
            self.logger.error(f"BM25 검색 실패: {e}")
            return []
        finally:
            self.total_search_time += time.time() - start_time
    
    def get_stats(self) -> Dict[str, Any]:
        """BM25 인덱스 통계 (확장된 메트릭)"""
        tokenizer_stats = {
            'type': 'kiwipiepy' if self.tokenizer.use_kiwi else 'basic',
            'tokenize_count': self.tokenizer.tokenize_count,
            'cache_hits': self.tokenizer.cache_hits,
            'cache_hit_rate': self.tokenizer.cache_hits / self.tokenizer.tokenize_count * 100 if self.tokenizer.tokenize_count > 0 else 0
        }

        return {
            'total_documents': len(self.documents),
            'vocab_size': len(self.vocab),
            'avg_doc_length': self.avg_doc_len,
            'avgdl': self.avg_doc_len,  # 호환성 alias
            'index_path': str(self.index_path),
            'bm25_index_path': str(self.index_path),  # 호환성 alias
            'bm25_index_docs': len(self.documents),  # 호환성 alias
            'has_tf': bool(self.term_freqs),
            'has_df': bool(self.doc_freqs),
            'parameters': {
                'k1': self.k1,
                'b': self.b
            },
            'tokenizer': tokenizer_stats,
            'performance': {
                'total_index_time': self.index_time,
                'search_count': self.search_count,
                'total_search_time': self.total_search_time,
                'avg_search_time': self.total_search_time / self.search_count if self.search_count > 0 else 0
            }
        }

# 테스트 함수
def test_bm25_store():
    """BM25 스토어 테스트"""
    print("🔍 BM25 스토어 테스트 시작")
    
    # 테스트 데이터
    test_texts = [
        "핀마이크 모델 ECM-77BC를 구매 검토합니다. 가격은 336,000원입니다.",
        "영상편집팀 워크스테이션 교체 비용은 179,300,000원입니다. HP Z8 모델입니다.",
        "광화문 스튜디오 모니터 교체 총액은 9,760,000원입니다. LG 모니터 3대입니다.",
        "카메라 장비 구매를 위한 예산 검토서입니다. 총 예산은 50,000,000원입니다.",
        "스튜디오 조명 시설 교체에 대한 기안서입니다. 필립스 LED 조명 20대를 구매합니다."
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
            'filename': '2023-07-15_카메라장비_예산검토.pdf',
            'content': test_texts[3],
            'metadata': {'doc_type': '예산서', 'amount': 50000000}
        },
        {
            'doc_id': 'doc5',
            'chunk_id': 'chunk5_1',
            'filename': '2024-03-20_조명시설_교체기안.pdf',
            'content': test_texts[4],
            'metadata': {'doc_type': '기안서', 'amount': 0}  # 금액 미상
        }
    ]
    
    try:
        # BM25 스토어 생성
        bm25 = BM25Store(index_path="rag_system/db/test_bm25_index.pkl")
        
        # 문서 추가
        print("📝 테스트 문서 추가 중...")
        bm25.add_documents(test_texts, test_metadatas)
        
        # 인덱스 저장
        bm25.save_index()
        
        # 검색 테스트
        test_queries = [
            "핀마이크 가격은 얼마인가요?",
            "워크스테이션 모델명은?",
            "모니터 개수는 몇 개인가요?",
            "카메라 예산",
            "조명 교체"
        ]
        
        for query in test_queries:
            print(f"\n🔍 BM25 검색: '{query}'")
            results = bm25.search(query, top_k=3)
            
            for result in results:
                print(f"  순위 {result['rank']}: {result['filename']}")
                print(f"    BM25 스코어: {result['score']:.3f}")
                print(f"    쿼리 토큰: {result['query_tokens']}")
                print(f"    내용: {result['content'][:50]}...")
        
        # 통계 출력
        stats = bm25.get_stats()
        print(f"\n📊 BM25 인덱스 통계:")
        print(f"  총 문서 수: {stats['total_documents']}")
        print(f"  어휘 크기: {stats['vocab_size']}")
        print(f"  평균 문서 길이: {stats['avg_doc_length']:.1f}")
        print(f"  토크나이저: {stats['tokenizer']['type']}")
        print(f"  토큰 캐시 히트율: {stats['tokenizer']['cache_hit_rate']:.1f}%")
        print(f"  파라미터: k1={stats['parameters']['k1']}, b={stats['parameters']['b']}")
        print(f"  평균 검색 시간: {stats['performance']['avg_search_time']:.3f}초")
        
        print("✅ BM25 스토어 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ BM25 스토어 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_bm25_store()