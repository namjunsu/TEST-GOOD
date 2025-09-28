"""
Document Compression (문서 압축) 모듈
Advanced RAG 기법 중 하나로, 검색된 문서에서 중요한 정보만 추출하여 LLM 컨텍스트 효율성 향상
"""

import logging
import time
import re
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Tuple
from collections import Counter, defaultdict
import numpy as np

class DocumentCompression:
    """문서 압축 모듈"""
    
    # 압축 설정 상수
    DEFAULT_TARGET_LENGTH = 1000
    DEFAULT_COMPRESSION_RATIO = 0.7
    MIN_SENTENCE_LENGTH = 10
    SHORT_SENTENCE_LENGTH = 20
    LONG_SENTENCE_LENGTH = 200
    
    # 점수 가중치 상수
    QUERY_MATCH_WEIGHT = 5.0
    PATTERN_MATCH_WEIGHT = 2.0
    FIRST_SENTENCE_BONUS = 1.0
    LAST_SENTENCE_BONUS = 0.5
    SHORT_SENTENCE_PENALTY = 0.5
    LONG_SENTENCE_PENALTY = 0.8
    
    # 정규식 패턴
    WORD_PATTERN = r'[가-힣a-zA-Z0-9]+'
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 성능 통계
        self.compression_count = 0
        self.total_compression_time = 0.0
        self.total_original_chars = 0
        self.total_compressed_chars = 0

        # 중요 키워드 패턴 (방송기술 도메인)
        self.important_patterns = [
            # 금액/수량 패턴
            r'(\d{1,3}(?:,\d{3})*)\s*원',
            r'(\d+)\s*개',
            r'(\d+)\s*대',
            r'(\d+)\s*식',
            r'총\s*(\d{1,3}(?:,\d{3})*)\s*원',
            
            # 날짜 패턴
            r'20\d{2}[.-]\d{1,2}[.-]\d{1,2}',
            r'20\d{2}년\s*\d{1,2}월',
            
            # 장비명 패턴
            r'[A-Z]+-[A-Z0-9]+',  # 모델명
            r'[A-Z]{2,}\s*\d+[A-Z]*',  # HP Z8, LG55 등
            
            # 기술 용어
            r'워크스테이션|모니터|카메라|마이크|케이블|삼각대|드론|조명',
            r'교체|구매|수리|설치|업그레이드|갱신',
            r'검토|기안|계획|보고|요청'
        ]
        
        # 문장 중요도 계산용 키워드
        self.high_value_keywords = {
            # 금액 관련 (높은 가중치)
            '금액': 3.0, '가격': 3.0, '비용': 3.0, '총액': 3.0, '예산': 3.0,
            '원': 2.5,
            
            # 장비명 (높은 가중치)  
            'HP': 2.8, 'LG': 2.8, 'Sony': 2.8, 'Canon': 2.8, 'TVLogic': 2.8,
            'Z8': 2.5, '워크스테이션': 2.5, '모니터': 2.5, '카메라': 2.5,
            
            # 행동 관련
            '교체': 2.0, '구매': 2.0, '수리': 2.0, '설치': 2.0,
            '검토': 1.8, '기안': 1.8, '계획': 1.8, '요청': 1.8,
            
            # 일반 용어
            '장비': 1.5, '기기': 1.5, '도구': 1.5, '시설': 1.5,
            '문서': 1.2, '보고서': 1.2, '기안서': 1.2
        }
        
        # 불필요한 문구 패턴
        self.noise_patterns = [
            r'php\?mode=getPrint.*',
            r'gw\.channela-mt\.com.*',
            r'\[페이지\s+\d+\]',
            r'^\s*-+\s*$',
            r'^\s*=+\s*$',
            r'^\s*\d+\s*$'
        ]

        # 패턴 컴파일
        self._compile_patterns()

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        # 중요 패턴 컴파일
        self.compiled_important = [re.compile(p, re.IGNORECASE) for p in self.important_patterns]

        # 노이즈 패턴 컴파일
        self.compiled_noise = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.noise_patterns]

        # 단어 추출 패턴 컴파일
        self.compiled_word_pattern = re.compile(self.WORD_PATTERN)

        # 문장 분할 패턴 컴파일
        self.sentence_split_patterns = [
            re.compile(r'[.!?。]+\s+'),
            re.compile(r'다\.\s+'),
            re.compile(r'습니다\.\s+'),
            re.compile(r'입니다\.\s+'),
            re.compile(r'요\.\s+'),
            re.compile(r'니다\.\s+')
        ]

        self.logger.info(f"패턴 컴파일 완료: {len(self.compiled_important)}개 중요 패턴, {len(self.compiled_noise)}개 노이즈 패턴")

    def compress_documents(
        self, 
        documents: List[Dict[str, Any]], 
        query: str,
        target_length: int = None,
        compression_ratio: float = None
    ) -> Dict[str, Any]:
        """문서 압축 수행"""
        start_time = time.time()
        
        compression_result = {
            'original_documents': documents,
            'compressed_documents': [],
            'compression_stats': {},
            'processing_time': 0.0
        }
        
        try:
            if not documents:
                return compression_result
            
            # 기본값 설정
            if target_length is None:
                target_length = self.DEFAULT_TARGET_LENGTH
            if compression_ratio is None:
                compression_ratio = self.DEFAULT_COMPRESSION_RATIO
            
            # 각 문서별로 압축 수행
            for doc in documents:
                compressed_doc = self._compress_single_document(
                    doc, query, target_length, compression_ratio
                )
                compression_result['compressed_documents'].append(compressed_doc)
            
            # 압축 통계 계산
            compression_result['compression_stats'] = self._calculate_compression_stats(
                documents, compression_result['compressed_documents']
            )
            
            compression_result['processing_time'] = time.time() - start_time

            # 통계 업데이트
            self.compression_count += len(documents)
            self.total_compression_time += compression_result['processing_time']
            self.total_original_chars += compression_result['compression_stats']['original_total_chars']
            self.total_compressed_chars += compression_result['compression_stats']['compressed_total_chars']

            self.logger.info(
                f"문서 압축 완료: {len(documents)}개 문서 "
                f"(원본: {compression_result['compression_stats']['original_total_chars']}자 "
                f"→ 압축: {compression_result['compression_stats']['compressed_total_chars']}자, "
                f"비율: {compression_result['compression_stats']['compression_ratio']:.2f})"
            )

            return compression_result
            
        except Exception as e:
            self.logger.error(f"문서 압축 실패: {e}")
            compression_result['processing_time'] = time.time() - start_time
            return compression_result
    
    def _compress_single_document(
        self, 
        document: Dict[str, Any], 
        query: str,
        target_length: int,
        compression_ratio: float
    ) -> Dict[str, Any]:
        """단일 문서 압축"""
        
        content = document.get('content', '')
        if not content:
            return document
        
        # 1. 노이즈 제거
        cleaned_content = self._remove_noise(content)
        
        # 2. 문장 분할 및 중요도 계산
        sentences = self._split_into_sentences(cleaned_content)
        sentence_scores = self._calculate_sentence_importance(sentences, query)
        
        # 3. 중요한 문장 선택
        target_sentences = max(1, int(len(sentences) * compression_ratio))
        selected_sentences = self._select_important_sentences(
            sentences, sentence_scores, target_sentences, target_length
        )
        
        # 4. 압축된 문서 생성
        compressed_doc = document.copy()
        compressed_doc['content'] = ' '.join(selected_sentences)
        compressed_doc['original_length'] = len(content)
        compressed_doc['compressed_length'] = len(compressed_doc['content'])
        compressed_doc['compression_ratio'] = compressed_doc['compressed_length'] / len(content) if content else 1.0
        compressed_doc['sentences_kept'] = len(selected_sentences)
        compressed_doc['sentences_total'] = len(sentences)
        
        return compressed_doc
    
    def _remove_noise(self, content: str) -> str:
        """노이즈 패턴 제거 (컴파일된 패턴 사용)"""
        cleaned = content

        for pattern in self.compiled_noise:
            cleaned = pattern.sub('', cleaned)

        # 연속된 공백 정리
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned
    
    def _split_into_sentences(self, content: str) -> List[str]:
        """문장 분할 (컴파일된 패턴 사용)"""
        sentences = [content]

        for pattern in self.sentence_split_patterns:
            new_sentences = []
            for sentence in sentences:
                parts = pattern.split(sentence)
                new_sentences.extend([p.strip() for p in parts if p.strip()])
            sentences = new_sentences
        
        # 너무 짧은 문장 제거
        sentences = [s for s in sentences if len(s) >= self.MIN_SENTENCE_LENGTH]
        
        return sentences
    
    def _calculate_sentence_importance(self, sentences: List[str], query: str) -> List[float]:
        """문장별 중요도 계산 (최적화)"""
        scores = []
        query_words = set(self.compiled_word_pattern.findall(query.lower()))

        for idx, sentence in enumerate(sentences):
            score = 0.0
            sentence_lower = sentence.lower()

            # 1. 쿼리 단어 매칭 점수
            sentence_words = set(self.compiled_word_pattern.findall(sentence_lower))
            query_match_score = len(query_words.intersection(sentence_words)) / len(query_words) if query_words else 0
            score += query_match_score * self.QUERY_MATCH_WEIGHT

            # 2. 중요 패턴 점수 (컴파일된 패턴 사용)
            for pattern in self.compiled_important:
                matches = pattern.findall(sentence)
                score += len(matches) * self.PATTERN_MATCH_WEIGHT

            # 3. 고가치 키워드 점수
            for keyword, weight in self.high_value_keywords.items():
                if keyword.lower() in sentence_lower:
                    score += weight

            # 4. 문장 위치 점수 (인덱스 직접 사용)
            position_score = 0.0
            if idx == 0:  # 첫 문장
                position_score = self.FIRST_SENTENCE_BONUS
            elif idx == len(sentences) - 1:  # 마지막 문장
                position_score = self.LAST_SENTENCE_BONUS
            score += position_score
            
            # 5. 문장 길이 정규화 (너무 짧거나 긴 문장 페널티)
            length_score = 1.0
            if len(sentence) < self.SHORT_SENTENCE_LENGTH:
                length_score = self.SHORT_SENTENCE_PENALTY
            elif len(sentence) > self.LONG_SENTENCE_LENGTH:
                length_score = self.LONG_SENTENCE_PENALTY
            score *= length_score
            
            scores.append(score)
        
        return scores
    
    def _select_important_sentences(
        self, 
        sentences: List[str], 
        scores: List[float], 
        target_count: int,
        target_length: int
    ) -> List[str]:
        """중요한 문장 선택"""
        
        if not sentences:
            return []
        
        # 점수 기준으로 정렬
        sentence_score_pairs = list(zip(sentences, scores, range(len(sentences))))
        sentence_score_pairs.sort(key=lambda x: x[1], reverse=True)
        
        selected_sentences = []
        selected_indices = []
        total_length = 0
        
        # 점수 순으로 문장 선택
        for sentence, score, idx in sentence_score_pairs:
            if len(selected_sentences) >= target_count:
                break
            if total_length + len(sentence) > target_length:
                break
            
            selected_sentences.append(sentence)
            selected_indices.append(idx)
            total_length += len(sentence)
        
        # 원본 순서대로 재정렬
        selected_indices.sort()
        ordered_sentences = [sentences[i] for i in selected_indices]
        
        return ordered_sentences if ordered_sentences else sentences[:1]  # 최소 1개는 반환
    
    def _calculate_compression_stats(
        self, 
        original_docs: List[Dict[str, Any]], 
        compressed_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """압축 통계 계산"""
        
        original_total = sum(len(doc.get('content', '')) for doc in original_docs)
        compressed_total = sum(len(doc.get('content', '')) for doc in compressed_docs)
        
        stats = {
            'total_documents': len(original_docs),
            'original_total_chars': original_total,
            'compressed_total_chars': compressed_total,
            'compression_ratio': compressed_total / original_total if original_total > 0 else 1.0,
            'average_compression_per_doc': compressed_total / len(compressed_docs) if compressed_docs else 0,
            'sentences_stats': {
                'original_total': sum(doc.get('sentences_total', 0) for doc in compressed_docs),
                'kept_total': sum(doc.get('sentences_kept', 0) for doc in compressed_docs),
                'kept_ratio': 0.0
            }
        }
        
        if stats['sentences_stats']['original_total'] > 0:
            stats['sentences_stats']['kept_ratio'] = (
                stats['sentences_stats']['kept_total'] / stats['sentences_stats']['original_total']
            )
        
        return stats

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        avg_compression_ratio = (self.total_compressed_chars / self.total_original_chars * 100
                                if self.total_original_chars > 0 else 0.0)

        stats = {
            'compression_count': self.compression_count,
            'total_compression_time': self.total_compression_time,
            'avg_compression_time': self.total_compression_time / self.compression_count if self.compression_count > 0 else 0.0,
            'total_original_chars': self.total_original_chars,
            'total_compressed_chars': self.total_compressed_chars,
            'overall_compression_ratio': avg_compression_ratio,
            'compiled_patterns': {
                'important': len(self.compiled_important),
                'noise': len(self.compiled_noise),
                'sentence_split': len(self.sentence_split_patterns)
            }
        }
        return stats

# 테스트 함수
def test_document_compression():
    """문서 압축 테스트"""
    print("📄 문서 압축 테스트 시작")
    
    try:
        # 문서 압축기 초기화
        compressor = DocumentCompression()
        
        # 테스트 문서들
        test_documents = [
            {
                'content': """
                HP Z8 워크스테이션 총 금액은 179,300,000원입니다. 이 장비는 영상편집팀의 기존 장비 교체를 위해 검토되었습니다.
                기존 워크스테이션의 노후화로 인한 안정성 저하 문제가 있었습니다. 새로운 워크스테이션은 고성능 영상 편집 작업에 적합합니다.
                php?mode=getPrint&idx=214683&menu_depth=001004003&is_mark=&is_comm... 이런 불필요한 정보도 포함되어 있습니다.
                gw.channela-mt.com/groupware/approval/approval_form_popup 같은 URL도 있습니다.
                [페이지 1] 이런 페이지 정보도 있습니다.
                """,
                'filename': 'hp_workstation.pdf',
                'score': 5.2
            },
            {
                'content': """
                광화문 스튜디오 모니터 교체 검토 결과입니다. 총 예산은 9,760,000원으로 계획되었습니다.
                모니터 3대와 관련 부품들을 포함한 견적입니다. LG 55인치 모니터를 선정하였습니다.
                설치 작업은 2025년 1월에 진행될 예정입니다. 기존 모니터는 폐기 처리됩니다.
                아주 짧은 문장. 이런 문장들은 제거될 수 있습니다.
                매우 길고 불필요한 내용이 포함된 문장으로서 실제 의미있는 정보는 별로 없지만 길이만 긴 문장입니다 이런 경우에는 압축 과정에서 페널티를 받을 수 있습니다.
                """,
                'filename': 'monitor_replacement.pdf',
                'score': 4.8
            }
        ]
        
        # 테스트 쿼리
        test_query = "HP Z8 워크스테이션 가격"
        
        print(f"\n🔍 테스트 쿼리: '{test_query}'")
        print(f"📄 문서 수: {len(test_documents)}")
        
        # 문서 압축 수행
        result = compressor.compress_documents(
            documents=test_documents,
            query=test_query,
            target_length=300,
            compression_ratio=0.6
        )
        
        # 결과 출력
        print(f"\n📊 압축 결과:")
        print(f"  처리 시간: {result['processing_time']:.3f}초")
        print(f"  원본 총 글자 수: {result['compression_stats']['original_total_chars']}자")
        print(f"  압축 후 글자 수: {result['compression_stats']['compressed_total_chars']}자")
        print(f"  압축 비율: {result['compression_stats']['compression_ratio']:.2f}")
        
        print(f"\n📄 문서별 압축 결과:")
        for i, compressed_doc in enumerate(result['compressed_documents']):
            print(f"  문서 {i+1}: {compressed_doc['filename']}")
            print(f"    원본: {compressed_doc['original_length']}자 → 압축: {compressed_doc['compressed_length']}자")
            print(f"    문장: {compressed_doc['sentences_total']}개 → {compressed_doc['sentences_kept']}개")
            print(f"    압축 내용: {compressed_doc['content'][:100]}...")
            print()
        
        print("✅ 문서 압축 테스트 완료")
        return True
        
    except Exception as e:
        print(f"❌ 문서 압축 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_document_compression()