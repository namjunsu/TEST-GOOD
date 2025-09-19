#!/usr/bin/env python3
"""
간단한 기안자 검색 테스트
"""

import sys
from pathlib import Path
import re

sys.path.append(str(Path(__file__).parent))

# 샘플 PDF 파일 1개만 테스트
test_pdf = Path("docs/year_2025/2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf")

if test_pdf.exists():
    # PDF에서 텍스트 추출
    try:
        import pdfplumber
        with pdfplumber.open(test_pdf) as pdf:
            if pdf.pages:
                text = pdf.pages[0].extract_text()
                if text:
                    print("📄 PDF 파일:", test_pdf.name)
                    print("="*60)

                    # 기안자 패턴 찾기
                    patterns = [
                        r'기안자[\s:：]*([가-힣]+)',
                        r'작성자[\s:：]*([가-힣]+)',
                        r'담당자[\s:：]*([가-힣]+)'
                    ]

                    drafter_found = False
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            drafter = match.group(1).strip()
                            print(f"✅ 기안자 발견: {drafter}")
                            drafter_found = True
                            break

                    if not drafter_found:
                        print("❌ 기안자 정보를 찾을 수 없음")
                        print("\n처음 500자 확인:")
                        print(text[:500])

                    print("\n" + "="*60)

                    # RAG 시스템에서 검색 테스트
                    from perfect_rag import PerfectRAG

                    print("\n🔍 RAG 시스템 검색 테스트")
                    print("="*60)

                    rag = PerfectRAG(preload_llm=False)

                    # 최새름 기안자 검색
                    query = "최새름 기안자 문서 찾아줘"
                    print(f"\n검색어: {query}")

                    result = rag._search_multiple_documents(query)

                    # 결과 분석
                    if '검색 결과' in result and '개 문서 발견' in result:
                        count_match = re.search(r'총 (\d+)개 문서 발견', result)
                        if count_match:
                            doc_count = int(count_match.group(1))
                            print(f"✅ {doc_count}개 문서 발견")

                            # 처음 몇 줄 표시
                            lines = result.split('\n')
                            for line in lines[:10]:
                                if line.strip():
                                    print(f"  {line}")
                    else:
                        print("❌ 문서를 찾을 수 없습니다.")
                        print(f"응답: {result[:500]}")

    except Exception as e:
        print(f"오류: {e}")
else:
    print(f"테스트 파일이 없습니다: {test_pdf}")