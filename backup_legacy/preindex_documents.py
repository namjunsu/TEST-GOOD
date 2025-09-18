#!/usr/bin/env python3
"""
문서 메타데이터 사전 인덱싱 스크립트
웹 인터페이스 실행 전에 실행하여 초기 로딩 속도 개선
"""

import sys
from pathlib import Path
from datetime import datetime
import time
import re
import html

# 프로젝트 루트 경로 추가
sys.path.append(str(Path(__file__).parent))

from document_metadata_cache import DocumentMetadataCache
import config

def preindex_all_documents():
    """모든 문서를 사전 인덱싱"""
    print("📚 문서 메타데이터 사전 인덱싱 시작...")
    start_time = time.time()

    docs_path = Path(config.DOCS_DIR)
    cache = DocumentMetadataCache()

    # 모든 PDF 파일 목록
    pdf_files = list(docs_path.glob("*.pdf"))
    total_files = len(pdf_files)

    print(f"📄 총 {total_files}개 PDF 파일 발견")

    indexed_count = 0
    skipped_count = 0
    error_count = 0

    for i, pdf_file in enumerate(pdf_files, 1):
        # 진행 상황 표시
        if i % 10 == 0:
            print(f"  진행중... {i}/{total_files} ({i*100//total_files}%)")

        # 이미 캐시되어 있고 최신이면 스킵
        if cache.is_cached(pdf_file):
            skipped_count += 1
            continue

        try:
            # 메타데이터 추출
            stat = pdf_file.stat()
            name_parts = pdf_file.stem.split('_', 1)
            doc_date = name_parts[0] if len(name_parts) > 0 else ""
            doc_title = name_parts[1] if len(name_parts) > 1 else pdf_file.stem
            doc_title = html.unescape(doc_title)

            # 연도 추출
            year = doc_date[:4] if len(doc_date) >= 4 else "연도없음"
            month = doc_date[5:7] if len(doc_date) >= 7 else ""

            # 카테고리 분류
            category = "기타"
            if "구매" in pdf_file.name:
                category = "구매"
            elif "폐기" in pdf_file.name:
                category = "폐기"
            elif "수리" in pdf_file.name or "보수" in pdf_file.name:
                category = "수리"
            elif "소모품" in pdf_file.name:
                category = "소모품"

            # 기안자 추출 (비용이 큰 작업)
            drafter = "미상"
            try:
                import pdfplumber
                with pdfplumber.open(pdf_file) as pdf:
                    if pdf.pages:
                        first_page_text = pdf.pages[0].extract_text() or ""

                        drafter_patterns = [
                            r'기안자[\s:：]*([가-힣]{2,4})',
                            r'작성자[\s:：]*([가-힣]{2,4})',
                            r'담당[\s:：]*([가-힣]{2,4})',
                            r'기안[\s:：]*([가-힣]{2,4})',
                            r'담당자[\s:：]*([가-힣]{2,4})',
                            r'성명[\s:：]*([가-힣]{2,4})',
                        ]

                        for pattern in drafter_patterns:
                            match = re.search(pattern, first_page_text)
                            if match:
                                drafter = match.group(1).strip()
                                if 2 <= len(drafter) <= 4:
                                    break
                                else:
                                    drafter = "미상"
            except Exception as e:
                print(f"  ⚠️ {pdf_file.name}: 기안자 추출 실패 - {str(e)[:50]}")

            # 메타데이터 생성
            metadata = {
                'title': doc_title,
                'filename': pdf_file.name,
                'path': str(pdf_file),
                'category': category,
                'date': doc_date,
                'year': year,
                'month': month,
                'drafter': drafter,
                'modified': datetime.fromtimestamp(stat.st_mtime)
            }

            # 캐시에 저장
            cache.save_metadata(pdf_file, metadata)
            indexed_count += 1

        except Exception as e:
            print(f"  ❌ {pdf_file.name}: 인덱싱 실패 - {str(e)}")
            error_count += 1

    # 완료 통계
    elapsed_time = time.time() - start_time
    stats = cache.get_stats()

    print("\n" + "="*50)
    print("✅ 사전 인덱싱 완료!")
    print(f"  - 소요 시간: {elapsed_time:.2f}초")
    print(f"  - 신규 인덱싱: {indexed_count}개")
    print(f"  - 스킵 (이미 캐시됨): {skipped_count}개")
    print(f"  - 오류: {error_count}개")
    print(f"  - 전체 캐시된 문서: {stats['total_cached']}개")
    print("\n카테고리별:")
    for category, count in stats['by_category'].items():
        print(f"  - {category}: {count}개")

    return indexed_count > 0 or skipped_count > 0

if __name__ == "__main__":
    success = preindex_all_documents()
    sys.exit(0 if success else 1)