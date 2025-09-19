#!/usr/bin/env python3
"""
DVR 문서 검색 테스트 - 단순 버전
"""

import sys
from pathlib import Path
import time
import re

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_dvr_document_search():
    """문서 검색 기능만 테스트 (LLM 없이)"""
    print("\n" + "="*50)
    print("🔍 DVR 문서 검색 테스트")
    print("="*50 + "\n")

    # RAG 시스템 초기화 (LLM 로드하지 않음)
    print("📚 문서 검색 시스템 초기화 중...")
    rag = PerfectRAG(preload_llm=False)  # LLM 로드하지 않음
    print(f"✅ {len(rag.pdf_files)}개 PDF 문서 로드 완료\n")

    # DVR 관련 문서 검색 테스트
    print("\n🔍 DVR 관련 문서 검색 중...")
    query = "DVR관련 문서 찾아줘"

    # _search_multiple_documents 메소드 직접 호출
    try:
        result = rag._search_multiple_documents(query)

        # 결과 분석
        if '검색 결과' in result and '개 문서 발견' in result:
            # 문서 개수 추출
            count_match = re.search(r'총 (\d+)개 문서 발견', result)
            if count_match:
                doc_count = int(count_match.group(1))
                print(f"\n✅ 성공: {doc_count}개 DVR 관련 문서 발견")

                # 발견된 파일명 추출
                lines = result.split('\n')
                dvr_files = []
                for line in lines:
                    # 파일명 패턴 찾기
                    if '.pdf' in line and 'DVR' in line.upper():
                        # 파일명을 추출
                        file_match = re.search(r'([^\/]+\.pdf)', line)
                        if file_match:
                            filename = file_match.group(1)
                            if filename not in dvr_files:
                                dvr_files.append(filename)

                if dvr_files:
                    print(f"\n📄 발견된 DVR 문서 파일들:")
                    for i, filename in enumerate(dvr_files[:10], 1):
                        print(f"   {i}. {filename}")
                else:
                    print("\n⚠️ DVR이 파일명에 직접 표시되지 않았지만 관련 문서를 찾았습니다.")

        elif "관련 문서를 찾을 수 없습니다" in result:
            print("\n❌ 실패: DVR 관련 문서를 찾지 못함")
            print("🔍 문서 검색 기준이 너무 엄격할 수 있습니다.")
        else:
            print("\n⚠️ 예상과 다른 응답 형식")
            print(result[:300] + "...")  # 처음 300자만 출력

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")

    # 메타데이터 캐시에서 DVR 파일 직접 검색
    print("\n" + "="*50)
    print("📝 메타데이터 캐시에서 DVR 문서 검색")
    print("="*50)

    dvr_docs = []
    for cache_key, metadata in rag.metadata_cache.items():
        if metadata.get('is_pdf'):
            filename = metadata.get('filename', '')
            if 'DVR' in filename.upper():
                dvr_docs.append(filename)

    if dvr_docs:
        print(f"\n✅ 메타데이터 캐시에서 {len(dvr_docs)}개 DVR 문서 발견:")
        for i, doc in enumerate(dvr_docs[:10], 1):
            print(f"   {i}. {doc}")
    else:
        print("\n⚠️ 메타데이터 캐시에 DVR 문서가 없습니다.")
        print("🔍 다른 키워드로 검색해야 할 수 있습니다.")

    print("\n" + "="*50)
    print("테스트 종료")
    print("="*50)

if __name__ == "__main__":
    test_dvr_document_search()