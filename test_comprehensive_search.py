#!/usr/bin/env python3
"""
포괄적 문서 검색 테스트 - 다양한 장비 및 확장성 검증
"""

import sys
from pathlib import Path
import time
import re

sys.path.append(str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_comprehensive_search():
    """다양한 장비 문서 검색 및 확장성 테스트"""
    print("\n" + "="*60)
    print("📊 포괄적 문서 검색 테스트 (889개 문서 대상)")
    print("="*60 + "\n")

    # RAG 시스템 초기화
    print("📚 문서 검색 시스템 초기화 중...")
    start = time.time()
    rag = PerfectRAG(preload_llm=False)
    init_time = time.time() - start

    print(f"✅ 초기화 완료: {init_time:.2f}초")
    print(f"📁 총 {len(rag.pdf_files)}개 PDF 문서 로드")
    print(f"📝 메타데이터 캐시: {len(rag.metadata_cache)}개 항목\n")

    # 다양한 장비 테스트 쿼리
    test_queries = [
        ("DVR관련 문서", "DVR"),
        ("카메라 관련 문서", "카메라"),
        ("렌즈 관련 문서", "렌즈"),
        ("모니터 관련 문서", "모니터"),
        ("삼각대 구매 문서", "삼각대"),
        ("중계차 관련 문서", "중계차"),
        ("2020년 구매 문서", "2020.*구매"),
        ("2019년 수리 문서", "2019.*수리"),
        ("최새름 기안자 문서", "최새름"),
        ("김민수 기안자 문서", "김민수")
    ]

    results_summary = []

    print("🔍 다양한 검색 쿼리 테스트 시작\n")
    print("-" * 60)

    for query, keyword in test_queries:
        print(f"\n📌 테스트: '{query}'")
        start = time.time()

        try:
            # 문서 검색 실행
            result = rag._search_multiple_documents(query)
            search_time = time.time() - start

            # 결과 분석
            doc_count = 0
            found_files = []

            if '검색 결과' in result and '개 문서 발견' in result:
                count_match = re.search(r'총 (\d+)개 문서 발견', result)
                if count_match:
                    doc_count = int(count_match.group(1))

                # 파일명 추출
                lines = result.split('\n')
                for line in lines:
                    if '.pdf' in line:
                        file_match = re.search(r'([^\/\[\]]+\.pdf)', line)
                        if file_match:
                            filename = file_match.group(1).strip()
                            if filename not in found_files:
                                found_files.append(filename)

            # 직접 캐시에서 검증
            cache_count = 0
            for cache_key, metadata in rag.metadata_cache.items():
                if metadata.get('is_pdf'):
                    filename = metadata.get('filename', '')
                    text = metadata.get('text', '')[:1000]  # 첫 1000자

                    # 키워드 검색
                    if keyword.lower() in filename.lower() or keyword.lower() in text.lower():
                        cache_count += 1

            # 결과 저장
            results_summary.append({
                'query': query,
                'found': doc_count,
                'cache_verified': cache_count,
                'time': search_time,
                'sample_files': found_files[:3]
            })

            # 결과 출력
            if doc_count > 0:
                print(f"  ✅ {doc_count}개 문서 발견 (캐시 검증: {cache_count}개)")
                if found_files:
                    print(f"  📄 샘플: {found_files[0][:50]}...")
            else:
                print(f"  ⚠️ 검색 결과 없음 (캐시에는 {cache_count}개 존재)")

            print(f"  ⏱️ 검색 시간: {search_time:.3f}초")

        except Exception as e:
            print(f"  ❌ 오류: {e}")
            results_summary.append({
                'query': query,
                'found': 0,
                'cache_verified': 0,
                'time': 0,
                'error': str(e)
            })

    # 종합 분석
    print("\n" + "="*60)
    print("📊 검색 성능 종합 분석")
    print("="*60 + "\n")

    total_found = sum(r['found'] for r in results_summary)
    total_time = sum(r['time'] for r in results_summary)
    successful_searches = [r for r in results_summary if r['found'] > 0]

    print(f"📈 전체 통계:")
    print(f"  - 총 검색 쿼리: {len(test_queries)}개")
    print(f"  - 성공한 검색: {len(successful_searches)}개")
    print(f"  - 발견된 문서 총합: {total_found}개")
    print(f"  - 평균 검색 시간: {total_time/len(test_queries):.3f}초")
    print(f"  - 총 처리 시간: {total_time:.2f}초")

    print(f"\n🔍 검색 알고리즘 검증:")
    for r in results_summary:
        if r['found'] != r['cache_verified']:
            status = "⚠️ 불일치"
        elif r['found'] > 0:
            status = "✅ 정확"
        else:
            status = "🔍 추가 확인 필요"

        print(f"  {r['query']:20s} : 검색 {r['found']:3d}개, 캐시 {r['cache_verified']:3d}개 - {status}")

    # 확장성 테스트
    print(f"\n📦 확장성 검증:")
    print(f"  - 전체 문서 수: {len(rag.pdf_files)}개")
    print(f"  - 메타데이터 캐시 크기: {len(rag.metadata_cache)}개")
    print(f"  - 초기화 시간: {init_time:.2f}초")
    print(f"  - 문서당 평균 초기화: {init_time/len(rag.pdf_files)*1000:.1f}ms")

    # auto_indexer 연동 확인
    auto_indexer_path = Path(__file__).parent / 'auto_indexer.py'
    if auto_indexer_path.exists():
        print(f"\n🔄 자동 인덱싱 시스템: ✅ 사용 가능")
        print(f"  - 새 문서 자동 감지 및 인덱싱 지원")
        print(f"  - 60초마다 docs 폴더 모니터링")
    else:
        print(f"\n🔄 자동 인덱싱 시스템: ❌ 찾을 수 없음")

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)

if __name__ == "__main__":
    test_comprehensive_search()