#!/usr/bin/env python3
"""
메타데이터 DB 초기 설정 및 확장
한 번 실행으로 모든 PDF의 기안자 정보 추출
"""

import pdfplumber
from pathlib import Path
from metadata_manager import MetadataManager
import time

def setup_metadata_db():
    """모든 PDF에서 메타데이터 추출하여 DB 구축"""
    print("\n" + "="*60)
    print("🚀 메타데이터 DB 구축 시작")
    print("="*60 + "\n")

    manager = MetadataManager()
    docs_dir = Path('docs')
    pdf_files = list(docs_dir.rglob('*.pdf'))

    print(f"📁 총 {len(pdf_files)}개 PDF 파일 발견\n")

    # 통계
    text_count = 0
    scan_count = 0
    drafter_found = 0
    processed = 0

    print("🔍 문서 처리 중... (시간이 걸릴 수 있습니다)\n")

    # 테스트를 위해 처음 50개만 처리
    for i, pdf_path in enumerate(pdf_files[:50], 1):
        filename = pdf_path.name

        # 진행 상황 표시
        if i % 10 == 0:
            print(f"  진행: {i}/{len(pdf_files)} ({i*100//len(pdf_files)}%)")

        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    continue

                # 첫 페이지만 빠르게 확인
                text = pdf.pages[0].extract_text() or ""

                metadata = {
                    'path': str(pdf_path),
                    'filename': filename
                }

                if len(text.strip()) < 50:
                    # 스캔 PDF
                    metadata['status'] = 'scanned'
                    metadata['needs_ocr'] = True
                    scan_count += 1
                else:
                    # 텍스트 PDF - 메타데이터 추출
                    metadata['status'] = 'text'
                    text_count += 1

                    # 기안자 추출
                    extracted = manager.extract_from_text(text)
                    metadata.update(extracted)

                    if metadata.get('drafter'):
                        drafter_found += 1
                        print(f"  ✅ {filename[:40]}... → 기안자: {metadata['drafter']}")

                # DB에 저장 (filename 키 제거)
                if 'filename' in metadata:
                    del metadata['filename']
                manager.add_document(filename, **metadata)
                processed += 1

        except Exception as e:
            print(f"  ❌ 오류: {filename[:30]}... - {str(e)[:30]}")

    # 결과 출력
    print("\n" + "="*60)
    print("✅ 메타데이터 DB 구축 완료!")
    print("="*60 + "\n")

    print(f"📊 처리 결과:")
    print(f"  - 총 처리: {processed}개")
    print(f"  - 텍스트 PDF: {text_count}개")
    print(f"  - 스캔 PDF: {scan_count}개 (OCR 필요)")
    print(f"  - 기안자 확인: {drafter_found}개\n")

    # 기안자별 통계
    stats = manager.get_statistics()
    if stats['drafters']:
        print("👥 기안자별 문서 수:")
        for drafter, count in sorted(stats['drafters'].items(),
                                    key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {drafter}: {count}개")

    print(f"\n💾 데이터베이스 저장 완료: document_metadata.json")
    print(f"📝 총 {len(manager.metadata)}개 문서 정보 저장됨")

    # 권장사항
    print("\n" + "="*60)
    print("💡 다음 단계:")
    print("="*60)
    if scan_count > 0:
        print(f"⚠️ {scan_count}개의 스캔 PDF가 있습니다.")
        print("   OCR이 필요하지만, 현재 시스템은 텍스트 PDF도 잘 처리합니다.")
    print("\n✅ 이제 웹 인터페이스에서 기안자 검색을 사용할 수 있습니다!")
    print("   예: '최새름 기안자 문서 찾아줘'")

if __name__ == "__main__":
    start = time.time()
    setup_metadata_db()
    elapsed = time.time() - start
    print(f"\n⏱️ 총 처리 시간: {elapsed:.1f}초")