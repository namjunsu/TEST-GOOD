#!/usr/bin/env python3
"""
기안자 검색 테스트
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from perfect_rag import PerfectRAG

def test_drafter_search():
    """기안자 검색 기능 테스트"""
    print("\n" + "="*50)
    print("🔍 기안자 검색 테스트")
    print("="*50 + "\n")

    # RAG 시스템 초기화
    print("📚 문서 검색 시스템 초기화 중...")
    rag = PerfectRAG(preload_llm=False)
    print(f"✅ {len(rag.pdf_files)}개 PDF 문서 로드 완료\n")

    # 테스트할 기안자들
    test_drafters = ["최새름", "김민수", "이철수", "박영희"]

    for drafter_name in test_drafters:
        print(f"\n🔍 '{drafter_name} 기안자' 검색 중...")
        query = f"{drafter_name} 기안자 문서 찾아줘"

        try:
            result = rag._search_multiple_documents(query)

            # 결과 분석
            if '검색 결과' in result and '개 문서 발견' in result:
                # 문서 개수 추출
                import re
                count_match = re.search(r'총 (\d+)개 문서 발견', result)
                if count_match:
                    doc_count = int(count_match.group(1))
                    print(f"✅ {doc_count}개 문서 발견")

                    # 발견된 파일 표시
                    lines = result.split('\n')
                    found_files = []
                    for line in lines:
                        if '.pdf' in line:
                            # 파일명 추출
                            file_match = re.search(r'([^/\[\]]+\.pdf)', line)
                            if file_match:
                                filename = file_match.group(1).strip()
                                if filename not in found_files:
                                    found_files.append(filename)

                    if found_files:
                        print(f"📄 발견된 문서:")
                        for i, filename in enumerate(found_files[:5], 1):
                            # 실제 기안자 확인을 위해 PDF에서 추출
                            for cache_key, metadata in rag.metadata_cache.items():
                                if metadata.get('filename') == filename:
                                    pdf_path = metadata['path']
                                    pdf_info = rag._extract_pdf_info(pdf_path)
                                    actual_drafter = pdf_info.get('기안자', '미확인')
                                    print(f"   {i}. {filename[:50]}...")
                                    print(f"      -> 기안자: {actual_drafter}")
                                    break
                else:
                    print("⚠️ 문서 개수를 파싱할 수 없습니다.")

            elif "관련 문서를 찾을 수 없습니다" in result:
                print(f"❌ {drafter_name} 기안자 문서를 찾지 못함")
            else:
                print("⚠️ 예상과 다른 응답 형식")
                print(result[:300] + "...")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")

    print("\n" + "="*50)

    # 실제 PDF에서 기안자 정보 직접 확인
    print("\n📝 실제 문서의 기안자 정보 확인")
    print("="*50)

    sample_files = list(rag.pdf_files)[:5]  # 처음 5개 파일만
    for pdf_path in sample_files:
        try:
            pdf_info = rag._extract_pdf_info(pdf_path)
            drafter = pdf_info.get('기안자', '')
            if drafter:
                print(f"• {pdf_path.name[:50]}...")
                print(f"  기안자: {drafter}")
        except:
            pass

    print("\n" + "="*50)
    print("테스트 완료")
    print("="*50)

if __name__ == "__main__":
    test_drafter_search()