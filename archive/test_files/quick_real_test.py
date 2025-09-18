#!/usr/bin/env python3
"""
실제 빠른 테스트 - LLM 없이 검색 기능만 테스트
"""

from perfect_rag import PerfectRAG
import time

def test_basic_search():
    """기본 검색 기능 테스트"""
    print("🔍 기본 검색 기능 테스트")
    print("="*80)

    rag = PerfectRAG()
    print(f"✅ 시스템 로드 완료")
    print(f"  - PDF: {len(rag.pdf_files)}개")
    print(f"  - TXT: {len(rag.txt_files)}개")
    print(f"  - 캐시: {len(rag.metadata_cache)}개")
    print()

    # 테스트 1: 메타데이터 캐시 확인
    print("📌 테스트 1: 메타데이터 캐시 구조 확인")
    print("-"*40)
    sample_entries = list(rag.metadata_cache.items())[:3]
    for key, value in sample_entries:
        print(f"키: {key}")
        print(f"  파일명: {value.get('filename', 'N/A')}")
        print(f"  경로: {value.get('path')}")
        print(f"  연도: {value.get('year', 'N/A')}")
        print()

    # 테스트 2: 특정 연도 문서 검색
    print("📌 테스트 2: 2020년 문서 검색")
    print("-"*40)
    count_2020 = 0
    files_2020 = []
    for key, metadata in rag.metadata_cache.items():
        if metadata.get('year') == '2020':
            count_2020 += 1
            filename = metadata.get('filename', key)
            files_2020.append(filename)

    print(f"2020년 문서: {count_2020}개 발견")
    if files_2020:
        print("샘플 파일들:")
        for f in files_2020[:5]:
            print(f"  - {f}")
    print()

    # 테스트 3: 구매 관련 문서 검색
    print("📌 테스트 3: 구매 관련 문서 검색")
    print("-"*40)
    purchase_docs = []
    for key, metadata in rag.metadata_cache.items():
        filename = metadata.get('filename', key)
        if '구매' in filename or '구입' in filename:
            purchase_docs.append({
                'filename': filename,
                'year': metadata.get('year', 'N/A'),
                'path': str(metadata.get('path', ''))
            })

    print(f"구매 관련 문서: {len(purchase_docs)}개")
    if purchase_docs:
        print("최근 5개:")
        for doc in sorted(purchase_docs, key=lambda x: x['year'], reverse=True)[:5]:
            print(f"  - [{doc['year']}] {doc['filename']}")
    print()

    # 테스트 4: 자산 파일 존재 확인
    print("📌 테스트 4: 자산 파일 확인")
    print("-"*40)
    asset_files = []
    for key, metadata in rag.metadata_cache.items():
        if metadata.get('is_txt', False):
            filename = metadata.get('filename', key)
            if '자산' in filename or '7904' in filename:
                asset_files.append(filename)

    print(f"자산 파일: {len(asset_files)}개")
    for f in asset_files:
        print(f"  - {f}")
    print()

    # 테스트 5: find_best_document 함수 테스트
    print("📌 테스트 5: find_best_document 함수 테스트")
    print("-"*40)
    test_queries = [
        "2020년 카메라 구매",
        "중계차 수리",
        "스튜디오 조명"
    ]

    for query in test_queries:
        best_doc = rag.find_best_document(query)
        if best_doc:
            print(f"질문: '{query}'")
            print(f"  → 찾은 문서: {best_doc.name}")
        else:
            print(f"질문: '{query}'")
            print(f"  → 문서를 찾지 못함")
    print()

    # 테스트 6: 폴더별 파일 수 확인
    print("📌 테스트 6: 폴더별 파일 분포")
    print("-"*40)
    folder_stats = {}
    for key, metadata in rag.metadata_cache.items():
        # key가 상대 경로이므로 폴더 추출
        if '/' in key:
            folder = key.split('/')[0]
            folder_stats[folder] = folder_stats.get(folder, 0) + 1
        else:
            folder_stats['root'] = folder_stats.get('root', 0) + 1

    for folder, count in sorted(folder_stats.items()):
        print(f"  {folder}: {count}개")

    return True

def test_search_methods():
    """검색 메서드 테스트"""
    print("\n🔍 검색 메서드 테스트")
    print("="*80)

    rag = PerfectRAG()

    # _find_metadata_by_filename 테스트
    print("📌 _find_metadata_by_filename 테스트")
    print("-"*40)

    # 첫 번째 파일명 가져오기
    first_entry = next(iter(rag.metadata_cache.values()))
    if 'filename' in first_entry:
        test_filename = first_entry['filename']
        print(f"테스트 파일명: {test_filename}")

        metadata = rag._find_metadata_by_filename(test_filename)
        if metadata:
            print("  ✅ 메타데이터 찾기 성공")
            print(f"  경로: {metadata.get('path')}")
        else:
            print("  ❌ 메타데이터를 찾지 못함")
    else:
        print("  ⚠️ filename 필드가 없는 구 캐시 데이터")

    return True

if __name__ == "__main__":
    print("🚀 빠른 실제 테스트 시작\n")

    try:
        # 기본 검색 테스트
        test_basic_search()

        # 검색 메서드 테스트
        test_search_methods()

        print("\n✅ 모든 테스트 완료!")

    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()