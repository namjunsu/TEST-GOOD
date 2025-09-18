#!/usr/bin/env python3
"""
성능 개선 검증 테스트
모든 최적화 적용 후 성능 측정
"""

import time
from perfect_rag import PerfectRAG

def test_performance():
    print("="*60)
    print("🚀 RAG 시스템 성능 개선 검증 테스트")
    print("="*60)
    
    # 시스템 초기화
    print("\n📦 시스템 로딩...")
    start = time.time()
    rag = PerfectRAG()
    load_time = time.time() - start
    
    print(f"✅ 시스템 로드 완료: {load_time:.1f}초")
    print(f"  - PDF 파일: {len(rag.pdf_files)}개")
    print(f"  - TXT 파일: {len(rag.txt_files)}개")
    print(f"  - 메타데이터: {len(rag.metadata_cache)}개")
    
    # 테스트 쿼리들
    test_queries = [
        ("2020년 구매 문서", "document"),
        ("중계차 장비 현황", "asset"),
        ("카메라 수리 내역", "document"),
        ("광화문 장비", "asset"),
        ("2020년에 구매한 문서", "document"),  # 캐시 테스트용 유사 쿼리
    ]
    
    results = []
    
    print("\n📊 성능 테스트 시작...")
    print("-"*60)
    
    for i, (query, mode) in enumerate(test_queries, 1):
        print(f"\n테스트 {i}: {query} (모드: {mode})")
        
        start = time.time()
        result = rag.answer(query, mode=mode)
        elapsed = time.time() - start
        
        # 결과 저장
        results.append({
            'query': query,
            'mode': mode, 
            'time': elapsed,
            'length': len(result),
            'cached': elapsed < 1.0
        })
        
        # 출력
        print(f"  ⏱️ 응답 시간: {elapsed:.1f}초")
        print(f"  📝 응답 길이: {len(result):,} 글자")
        
        if elapsed < 1.0:
            print("  ✅ 캐시 히트!")
        elif elapsed < 30:
            print("  ⚡ 빠른 응답 (<30초)")
        elif elapsed < 60:
            print("  🔄 보통 응답 (30-60초)")
        else:
            print("  ⏳ 느린 응답 (>60초)")
    
    # 통계 출력
    print("\n" + "="*60)
    print("📈 성능 통계")
    print("="*60)
    
    avg_time = sum(r['time'] for r in results) / len(results)
    cached_count = sum(1 for r in results if r['cached'])
    
    print(f"\n총 테스트: {len(results)}개")
    print(f"평균 응답 시간: {avg_time:.1f}초")
    print(f"캐시 히트: {cached_count}/{len(results)} ({cached_count/len(results)*100:.0f}%)")
    
    # 모드별 통계
    doc_results = [r for r in results if r['mode'] == 'document']
    asset_results = [r for r in results if r['mode'] == 'asset']
    
    if doc_results:
        doc_avg = sum(r['time'] for r in doc_results) / len(doc_results)
        print(f"\n문서 모드 평균: {doc_avg:.1f}초")
    
    if asset_results:
        asset_avg = sum(r['time'] for r in asset_results) / len(asset_results)
        print(f"자산 모드 평균: {asset_avg:.1f}초")
    
    # 캐시 통계
    cache_stats = rag.get_cache_stats()
    print(f"\n캐시 통계:")
    print(f"  - 응답 캐시: {cache_stats['response_cache_size']}개")
    print(f"  - 전체 캐시: {cache_stats['total_cache_size']}개")
    print(f"  - 총 히트: {cache_stats['hits']}회")
    print(f"  - 총 미스: {cache_stats['misses']}회")
    if cache_stats['hits'] + cache_stats['misses'] > 0:
        hit_rate = cache_stats['hits'] / (cache_stats['hits'] + cache_stats['misses'])
        print(f"  - 히트율: {hit_rate:.1%}")
    
    # 성능 개선 평가
    print("\n" + "="*60)
    print("🎯 성능 개선 평가")
    print("="*60)
    
    improvements = []
    
    # 응답 시간 개선
    if avg_time < 30:
        improvements.append("✅ 평균 응답 시간 30초 이하 달성")
    elif avg_time < 60:
        improvements.append("⚡ 평균 응답 시간 60초 이하")
    else:
        improvements.append("⚠️ 응답 시간 추가 개선 필요")
    
    # 캐시 효율성
    if cached_count >= len(results) * 0.3:
        improvements.append("✅ 캐시 히트율 30% 이상 달성")
    else:
        improvements.append("⚠️ 캐시 히트율 개선 필요")
    
    # LLM 로딩
    if load_time < 10:
        improvements.append("✅ 시스템 로딩 10초 이하")
    else:
        improvements.append("⚠️ 시스템 로딩 시간 개선 필요")
    
    for imp in improvements:
        print(f"  {imp}")
    
    print("\n✨ 테스트 완료!")
    return results

if __name__ == "__main__":
    results = test_performance()
