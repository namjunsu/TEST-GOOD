#!/usr/bin/env python3
"""
모든 PDF에서 메타데이터 자동 추출하여 DB 구축
- 텍스트 PDF: 즉시 추출
- 스캔 PDF: 나중에 처리 (표시만)
"""

import pdfplumber
from pathlib import Path
from metadata_manager import MetadataManager
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def extract_metadata_from_pdf(pdf_path: Path, manager: MetadataManager) -> dict:
    """PDF에서 메타데이터 추출"""
    filename = pdf_path.name
    metadata = {'filename': filename, 'path': str(pdf_path)}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                metadata['status'] = 'empty'
                return metadata

            # 첫 페이지만 빠르게 확인
            text = pdf.pages[0].extract_text() or ""

            if len(text.strip()) < 50:
                # 스캔 PDF
                metadata['status'] = 'scanned'
                metadata['needs_ocr'] = True
                print(f"  ❌ 스캔 PDF: {filename[:50]}...")
            else:
                # 텍스트 PDF - 메타데이터 추출
                metadata['status'] = 'text'

                # MetadataManager의 추출 함수 활용
                extracted = manager.extract_from_text(text)
                metadata.update(extracted)

                # 기안자 찾았으면 표시
                if metadata.get('drafter'):
                    print(f"  ✅ {filename[:50]}... → 기안자: {metadata['drafter']}")
                else:
                    print(f"  ⚠️ {filename[:50]}... → 기안자 정보 없음")

    except Exception as e:
        metadata['status'] = 'error'
        metadata['error'] = str(e)
        print(f"  ❌ 오류: {filename} - {e}")

    return metadata


def build_database():
    """전체 문서 메타데이터 DB 구축"""
    print("\n" + "="*60)
    print("📚 메타데이터 DB 구축 시작")
    print("="*60 + "\n")

    manager = MetadataManager()

    # 모든 PDF 파일 찾기
    docs_dir = Path('docs')
    pdf_files = list(docs_dir.rglob('*.pdf'))

    print(f"📁 총 {len(pdf_files)}개 PDF 파일 발견\n")

    # 통계
    text_count = 0
    scan_count = 0
    drafter_count = 0

    # 병렬 처리로 빠르게
    print("🔍 메타데이터 추출 중...\n")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(extract_metadata_from_pdf, pdf_path, manager): pdf_path
            for pdf_path in pdf_files[:100]  # 일단 100개만 처리 (테스트)
        }

        for future in as_completed(futures):
            pdf_path = futures[future]
            try:
                metadata = future.result()
                filename = pdf_path.name

                # DB에 저장 (filename은 metadata에서 제거)
                if 'filename' in metadata:
                    del metadata['filename']
                manager.add_document(filename, **metadata)

                # 통계 업데이트
                if metadata.get('status') == 'text':
                    text_count += 1
                elif metadata.get('status') == 'scanned':
                    scan_count += 1

                if metadata.get('drafter'):
                    drafter_count += 1

            except Exception as e:
                print(f"  ❌ 처리 실패: {pdf_path.name} - {e}")

    # 저장
    manager.save_metadata()

    # 결과 출력
    print("\n" + "="*60)
    print("✅ 메타데이터 DB 구축 완료!")
    print("="*60 + "\n")

    print(f"📊 처리 결과:")
    print(f"  - 총 문서: {text_count + scan_count}개")
    print(f"  - 텍스트 PDF: {text_count}개")
    print(f"  - 스캔 PDF: {scan_count}개 (OCR 필요)")
    print(f"  - 기안자 확인: {drafter_count}개\n")

    # 기안자별 통계
    stats = manager.get_statistics()
    if stats['drafters']:
        print("👥 기안자별 문서 수:")
        for drafter, count in sorted(stats['drafters'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {drafter}: {count}개")

    print(f"\n💾 데이터베이스 파일: document_metadata.json")
    print(f"📝 {len(manager.metadata)}개 문서 정보 저장됨")


if __name__ == "__main__":
    start = time.time()
    build_database()
    elapsed = time.time() - start
    print(f"\n⏱️ 처리 시간: {elapsed:.1f}초")