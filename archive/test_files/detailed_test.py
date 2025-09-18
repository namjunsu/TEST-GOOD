#!/usr/bin/env python3
"""
AI-CHAT RAG 시스템 상세 테스트
모든 개선된 모듈들의 기능을 검증
"""

import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Any

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_separator(title: str):
    """테스트 구분선 출력"""
    print(f"\n{'='*80}")
    print(f"🧪 {title}")
    print('='*80)

def test_bm25_store():
    """BM25 스토어 테스트"""
    test_separator("BM25 스토어 테스트")
    
    try:
        from rag_system.bm25_store import BM25Store
        
        # 1. 인스턴스 생성
        print("1. BM25 인스턴스 생성...")
        bm25 = BM25Store(index_path="test_bm25.pkl")
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 상수 값 확인...")
        print(f"   - DEFAULT_K1: {bm25.DEFAULT_K1}")
        print(f"   - DEFAULT_B: {bm25.DEFAULT_B}")
        print(f"   - 실제 k1: {bm25.k1}")
        print(f"   - 실제 b: {bm25.b}")
        
        # 3. 문서 추가
        print("\n3. 문서 추가 테스트...")
        test_docs = [
            "AI 챗봇 시스템의 성능을 개선하는 방법",
            "한국어 자연어처리 기술의 발전",
            "딥러닝 모델의 최적화 기법"
        ]
        test_metadata = [
            {"doc_id": f"doc_{i}", "source": "test"} 
            for i in range(len(test_docs))
        ]
        
        bm25.add_documents(test_docs, test_metadata)
        print(f"   ✅ {len(test_docs)}개 문서 추가 완료")
        
        # 4. 검색 테스트
        print("\n4. 검색 테스트...")
        queries = ["AI 성능", "한국어 처리", "최적화"]
        for query in queries:
            results = bm25.search(query, top_k=2)
            print(f"   - '{query}' 검색: {len(results)}개 결과")
            if results:
                print(f"     최고 스코어: {results[0]['score']:.3f}")
        
        # 5. 통계
        print("\n5. 인덱스 통계...")
        stats = bm25.get_stats()
        print(f"   - 총 문서: {stats['total_documents']}")
        print(f"   - 어휘 크기: {stats['vocab_size']}")
        print(f"   - 평균 문서 길이: {stats['avg_doc_length']:.1f}")
        
        return True, "BM25 스토어 테스트 성공"
        
    except Exception as e:
        return False, f"BM25 테스트 실패: {str(e)}"

def test_document_compression():
    """문서 압축 테스트"""
    test_separator("문서 압축 테스트")
    
    try:
        from rag_system.document_compression import DocumentCompression
        
        # 1. 인스턴스 생성
        print("1. 압축기 인스턴스 생성...")
        compressor = DocumentCompression()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 상수 값 확인...")
        print(f"   - DEFAULT_TARGET_LENGTH: {compressor.DEFAULT_TARGET_LENGTH}")
        print(f"   - DEFAULT_COMPRESSION_RATIO: {compressor.DEFAULT_COMPRESSION_RATIO}")
        print(f"   - QUERY_MATCH_WEIGHT: {compressor.QUERY_MATCH_WEIGHT}")
        
        # 3. 문서 압축 테스트
        print("\n3. 문서 압축 테스트...")
        test_documents = [
            {
                'content': '이것은 매우 긴 문서입니다. ' * 50,  # 긴 문서
                'metadata': {'filename': 'long_doc.txt'}
            },
            {
                'content': '핵심 키워드를 포함한 문서. 중요한 정보가 여기 있습니다.',
                'metadata': {'filename': 'short_doc.txt'}
            }
        ]
        
        compressed = compressor.compress_documents(
            documents=test_documents,
            query='핵심 키워드',
            compression_ratio=0.5
        )
        
        print(f"   - 원본 문서 수: {len(test_documents)}")
        print(f"   - 압축 후 문서 수: {len(compressed)}")
        print(f"   - 첫 번째 문서 원본 길이: {len(test_documents[0]['content'])}")
        
        return True, "문서 압축 테스트 성공"
        
    except Exception as e:
        return False, f"문서 압축 테스트 실패: {str(e)}"

def test_query_optimizer():
    """쿼리 최적화 테스트"""
    test_separator("쿼리 최적화 테스트")
    
    try:
        from rag_system.query_optimizer import QueryOptimizer
        
        # 1. 인스턴스 생성
        print("1. 최적화기 인스턴스 생성...")
        optimizer = QueryOptimizer()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 가중치 상수 확인...")
        print(f"   - DEFAULT_VECTOR_WEIGHT: {optimizer.DEFAULT_VECTOR_WEIGHT}")
        print(f"   - DEFAULT_BM25_WEIGHT: {optimizer.DEFAULT_BM25_WEIGHT}")
        
        # 3. 쿼리 정제 테스트
        print("\n3. 쿼리 정제 테스트...")
        test_queries = [
            "뭐야 이거??",
            "~!@# 특수문자 $%^ 포함",
            "중계차는 어떤 장비를 가지고 있나요?"
        ]
        
        for query in test_queries:
            cleaned = optimizer.clean_query_for_search(query)
            print(f"   원본: '{query}'")
            print(f"   정제: '{cleaned}'")
        
        # 4. 가중치 결정 테스트
        print("\n4. 가중치 결정 테스트...")
        queries_for_weight = [
            "HD",  # 짧은 쿼리
            "중계차 장비 목록 상세",  # 중간 쿼리
            "2023년도에 구매한 방송 장비 중 1억원 이상 제품"  # 긴 쿼리
        ]
        
        for query in queries_for_weight:
            vector_weight, bm25_weight = optimizer.get_optimal_weights(query)
            print(f"   '{query[:20]}...'")
            print(f"     Vector: {vector_weight:.2f}, BM25: {bm25_weight:.2f}")
        
        return True, "쿼리 최적화 테스트 성공"
        
    except Exception as e:
        return False, f"쿼리 최적화 테스트 실패: {str(e)}"

def test_query_expansion():
    """쿼리 확장 테스트"""
    test_separator("쿼리 확장 테스트")
    
    try:
        from rag_system.query_expansion import QueryExpansion
        
        # 1. 인스턴스 생성
        print("1. 확장기 인스턴스 생성...")
        expander = QueryExpansion()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 확장 제한 상수 확인...")
        print(f"   - MAX_SYNONYMS_EXPANSIONS: {expander.MAX_SYNONYMS_EXPANSIONS}")
        print(f"   - MAX_PATTERN_EXPANSIONS: {expander.MAX_PATTERN_EXPANSIONS}")
        
        # 3. 쿼리 확장 테스트
        print("\n3. 쿼리 확장 테스트...")
        test_queries = [
            "HD 카메라",
            "모니터 구매",
            "LED 조명"
        ]
        
        for query in test_queries:
            expanded = expander.expand_query(query)
            print(f"   원본: '{query}'")
            print(f"   확장: {expanded['expanded_queries'][:3]}...")  # 처음 3개만
            print(f"   방법: {expanded['methods_used']}")
        
        return True, "쿼리 확장 테스트 성공"
        
    except Exception as e:
        return False, f"쿼리 확장 테스트 실패: {str(e)}"

def test_korean_reranker():
    """한국어 재순위 테스트"""
    test_separator("한국어 재순위 테스트")
    
    try:
        from rag_system.korean_reranker import KoreanReranker
        
        # 1. 인스턴스 생성
        print("1. 재순위기 인스턴스 생성...")
        reranker = KoreanReranker()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 가중치 상수 확인...")
        print(f"   - JACCARD_WEIGHT: {reranker.JACCARD_WEIGHT}")
        print(f"   - TF_WEIGHT: {reranker.TF_WEIGHT}")
        print(f"   - MAX_TOKEN_LENGTH: {reranker.MAX_TOKEN_LENGTH}")
        
        # 3. 재순위 테스트
        print("\n3. 재순위 테스트...")
        test_documents = [
            {'content': '중계차 HD 카메라 장비', 'metadata': {'score': 0.5}},
            {'content': 'HD 고화질 카메라 시스템', 'metadata': {'score': 0.6}},
            {'content': '방송용 카메라 장비 목록', 'metadata': {'score': 0.4}}
        ]
        
        reranked = reranker.rerank(
            query="HD 카메라",
            results=test_documents,
            top_k=2
        )
        
        print(f"   - 원본 문서: {len(test_documents)}개")
        print(f"   - 재순위 후: {len(reranked)}개")
        for i, doc in enumerate(reranked[:2]):
            print(f"   {i+1}. 스코어: {doc.get('rerank_score', 0):.3f}")
        
        return True, "한국어 재순위 테스트 성공"
        
    except Exception as e:
        return False, f"한국어 재순위 테스트 실패: {str(e)}"

def test_metadata_extractor():
    """메타데이터 추출 테스트"""
    test_separator("메타데이터 추출 테스트")
    
    try:
        from rag_system.metadata_extractor import MetadataExtractor
        
        # 1. 인스턴스 생성
        print("1. 추출기 인스턴스 생성...")
        extractor = MetadataExtractor()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 검증 상수 확인...")
        print(f"   - CONFIDENCE_HIGH: {extractor.CONFIDENCE_HIGH}")
        print(f"   - AUTHOR_MIN_LENGTH: {extractor.AUTHOR_MIN_LENGTH}")
        print(f"   - AUTHOR_MAX_LENGTH: {extractor.AUTHOR_MAX_LENGTH}")
        print(f"   - AMOUNT_MIN: {extractor.AMOUNT_MIN}")
        print(f"   - AMOUNT_MAX: {extractor.AMOUNT_MAX}")
        
        # 3. 메타데이터 추출 테스트
        print("\n3. 메타데이터 추출 테스트...")
        test_texts = [
            "작성자: 김철수 차장 / 날짜: 2024-03-15 / 금액: 1,500,000원",
            "담당: 이영희 대리 | 2023년 12월 | 총 350만원",
            "기안자: 박지성 / 결재일: 2024.01.20"
        ]
        
        for text in test_texts:
            metadata = extractor.extract_metadata(text)
            print(f"   텍스트: '{text[:30]}...'")
            if metadata.get('author'):
                print(f"     작성자: {metadata['author']}")
            if metadata.get('date'):
                print(f"     날짜: {metadata['date']}")
            if metadata.get('amount'):
                print(f"     금액: {metadata['amount']:,}원")
        
        return True, "메타데이터 추출 테스트 성공"
        
    except Exception as e:
        return False, f"메타데이터 추출 테스트 실패: {str(e)}"

def test_multilevel_filter():
    """다단계 필터링 테스트"""
    test_separator("다단계 필터링 테스트")
    
    try:
        from rag_system.multilevel_filter import MultilevelFilter
        
        # 1. 인스턴스 생성
        print("1. 필터 인스턴스 생성...")
        filter = MultilevelFilter()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 필터링 상수 확인...")
        print(f"   - PHASE1_MAX_CANDIDATES: {filter.PHASE1_MAX_CANDIDATES}")
        print(f"   - PHASE2_MAX_CANDIDATES: {filter.PHASE2_MAX_CANDIDATES}")
        print(f"   - PHASE3_TOP_K: {filter.PHASE3_TOP_K}")
        print(f"   - MIN_RELEVANCE_SCORE: {filter.MIN_RELEVANCE_SCORE}")
        
        # 3. 복잡도 분석 테스트
        print("\n3. 쿼리 복잡도 분석...")
        queries = [
            "HD 카메라",
            "2023년 구매한 장비 중 1억원 이상",
            "중계차와 스튜디오 장비 비교"
        ]
        
        for query in queries:
            complexity = filter.complexity_analyzer.analyze(query)
            print(f"   '{query}'")
            print(f"     복잡도: {complexity['complexity_level']}")
            print(f"     타입: {complexity['type']}")
        
        return True, "다단계 필터링 테스트 성공"
        
    except Exception as e:
        return False, f"다단계 필터링 테스트 실패: {str(e)}"

def test_hybrid_search():
    """하이브리드 검색 통합 테스트"""
    test_separator("하이브리드 검색 통합 테스트")
    
    try:
        from rag_system.hybrid_search import HybridSearch
        
        # 1. 인스턴스 생성
        print("1. 하이브리드 검색 인스턴스 생성...")
        search = HybridSearch()
        print("   ✅ 인스턴스 생성 성공")
        
        # 2. 상수 확인
        print("\n2. 검색 상수 확인...")
        print(f"   - DEFAULT_VECTOR_WEIGHT: {search.DEFAULT_VECTOR_WEIGHT}")
        print(f"   - DEFAULT_BM25_WEIGHT: {search.DEFAULT_BM25_WEIGHT}")
        print(f"   - DEFAULT_TOP_K: {search.DEFAULT_TOP_K}")
        
        # 3. 문서 추가 테스트
        print("\n3. 문서 인덱싱 테스트...")
        test_docs = [
            {
                'content': 'HD 카메라 시스템은 고화질 방송에 필수적입니다.',
                'doc_id': 'test1',
                'chunk_id': 'chunk1',
                'filename': 'camera.pdf'
            },
            {
                'content': '중계차는 실시간 방송을 위한 이동형 스튜디오입니다.',
                'doc_id': 'test2', 
                'chunk_id': 'chunk2',
                'filename': 'van.pdf'
            }
        ]
        
        search.add_documents(test_docs)
        print(f"   ✅ {len(test_docs)}개 문서 인덱싱 완료")
        
        # 4. 검색 테스트
        print("\n4. 하이브리드 검색 테스트...")
        results = search.search("HD 방송", top_k=2)
        print(f"   - 검색 결과: {len(results)}개")
        for i, result in enumerate(results):
            print(f"   {i+1}. {result['filename']} (스코어: {result.get('final_score', 0):.3f})")
        
        return True, "하이브리드 검색 테스트 성공"
        
    except Exception as e:
        return False, f"하이브리드 검색 테스트 실패: {str(e)}"

def test_memory_usage():
    """메모리 사용량 테스트"""
    test_separator("메모리 사용량 테스트")
    
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # 1. 초기 메모리
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        print(f"1. 초기 메모리 사용량: {initial_memory:.1f} MB")
        
        # 2. 모듈 로드 후
        from rag_system.bm25_store import BM25Store
        from rag_system.document_compression import DocumentCompression
        from rag_system.query_optimizer import QueryOptimizer
        
        loaded_memory = process.memory_info().rss / 1024 / 1024
        print(f"2. 모듈 로드 후: {loaded_memory:.1f} MB (+{loaded_memory-initial_memory:.1f} MB)")
        
        # 3. 인스턴스 생성 후
        bm25 = BM25Store()
        compressor = DocumentCompression()
        optimizer = QueryOptimizer()
        
        instance_memory = process.memory_info().rss / 1024 / 1024
        print(f"3. 인스턴스 생성 후: {instance_memory:.1f} MB (+{instance_memory-loaded_memory:.1f} MB)")
        
        # 4. 메모리 증가량 확인
        total_increase = instance_memory - initial_memory
        print(f"\n총 메모리 증가량: {total_increase:.1f} MB")
        
        if total_increase < 500:  # 500MB 미만이면 정상
            return True, f"메모리 사용량 정상 ({total_increase:.1f} MB)"
        else:
            return False, f"메모리 사용량 과다 ({total_increase:.1f} MB)"
            
    except Exception as e:
        return False, f"메모리 테스트 실패: {str(e)}"

def test_error_handling():
    """오류 처리 테스트"""
    test_separator("오류 처리 테스트")
    
    results = []
    
    # 1. 잘못된 파일 경로
    print("1. 잘못된 파일 경로 처리...")
    try:
        from rag_system.bm25_store import BM25Store
        bm25 = BM25Store(index_path="/invalid/path/index.pkl")
        bm25.load_index()
        results.append("❌ 예외가 발생하지 않음")
    except:
        results.append("✅ 예외 처리 성공")
    
    # 2. 빈 문서 처리
    print("2. 빈 문서 처리...")
    try:
        from rag_system.document_compression import DocumentCompression
        compressor = DocumentCompression()
        compressed = compressor.compress_documents([], "test", 0.5)
        results.append("✅ 빈 문서 처리 성공")
    except:
        results.append("❌ 빈 문서 처리 실패")
    
    # 3. None 쿼리 처리
    print("3. None 쿼리 처리...")
    try:
        from rag_system.query_optimizer import QueryOptimizer
        optimizer = QueryOptimizer()
        result = optimizer.clean_query_for_search(None) if hasattr(optimizer, 'clean_query_for_search') else ""
        if result == "":
            results.append("✅ None 처리 성공")
        else:
            results.append("❌ None 처리 실패")
    except:
        results.append("❌ 예외 발생")
    
    # 결과 집계
    success = all("✅" in r for r in results)
    return success, f"오류 처리 테스트: {results}"

def run_all_tests():
    """모든 테스트 실행"""
    print("🚀 AI-CHAT RAG 시스템 상세 테스트 시작")
    print(f"   시간: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 테스트 목록
    tests = [
        ("BM25 스토어", test_bm25_store),
        ("문서 압축", test_document_compression),
        ("쿼리 최적화", test_query_optimizer),
        ("쿼리 확장", test_query_expansion),
        ("한국어 재순위", test_korean_reranker),
        ("메타데이터 추출", test_metadata_extractor),
        ("다단계 필터링", test_multilevel_filter),
        ("하이브리드 검색", test_hybrid_search),
        ("메모리 사용량", test_memory_usage),
        ("오류 처리", test_error_handling)
    ]
    
    results = []
    failed = []
    
    for name, test_func in tests:
        try:
            success, message = test_func()
            if success:
                results.append(f"✅ {name}: {message}")
            else:
                results.append(f"❌ {name}: {message}")
                failed.append(name)
        except Exception as e:
            results.append(f"❌ {name}: 테스트 실행 실패 - {str(e)}")
            failed.append(name)
    
    # 최종 결과
    print("\n" + "="*80)
    print("📊 테스트 결과 요약")
    print("="*80)
    
    for result in results:
        print(result)
    
    print("\n" + "="*80)
    total = len(tests)
    passed = total - len(failed)
    print(f"✅ 성공: {passed}/{total}")
    print(f"❌ 실패: {len(failed)}/{total}")
    
    if failed:
        print(f"\n실패한 테스트: {', '.join(failed)}")
    else:
        print("\n🎉 모든 테스트 통과!")
    
    print("="*80)

if __name__ == "__main__":
    run_all_tests()