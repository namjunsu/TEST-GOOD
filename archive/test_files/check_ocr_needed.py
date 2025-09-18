#!/usr/bin/env python3
"""
OCR이 필요한 스캔 문서 빠른 식별 스크립트
"""

import fitz  # PyMuPDF
from pathlib import Path
import time
from typing import List, Tuple
import sys

def check_pdf_has_text(pdf_path: Path, sample_pages: int = 3) -> bool:
    """
    PDF에 추출 가능한 텍스트가 있는지 빠르게 확인
    처음 몇 페이지만 샘플링하여 확인
    """
    try:
        doc = fitz.open(str(pdf_path))
        pages_to_check = min(sample_pages, len(doc))
        
        for page_num in range(pages_to_check):
            page = doc[page_num]
            text = page.get_text().strip()
            
            # 의미있는 텍스트가 있으면 (공백 제외 20자 이상)
            if len(text.replace(' ', '').replace('\n', '')) > 20:
                doc.close()
                return True
        
        doc.close()
        return False
        
    except Exception as e:
        print(f"  ⚠️ {pdf_path.name} 확인 실패: {e}")
        return None

def scan_documents() -> Tuple[List[Path], List[Path], List[Path]]:
    """
    모든 PDF 문서를 스캔하여 분류
    """
    docs_dir = Path('docs')
    
    # 모든 PDF 파일 수집 (archive 제외)
    pdf_files = []
    for pdf_path in docs_dir.rglob('*.pdf'):
        if 'archive' not in str(pdf_path).lower():
            pdf_files.append(pdf_path)
    
    pdf_files.sort()
    
    text_extractable = []  # 텍스트 추출 가능
    ocr_needed = []        # OCR 필요 (스캔 문서)
    check_failed = []      # 확인 실패
    
    print(f"\n📄 총 {len(pdf_files)}개 PDF 문서 분석 시작...")
    print("="*60)
    
    start_time = time.time()
    
    for i, pdf_path in enumerate(pdf_files, 1):
        if i % 20 == 0:
            elapsed = time.time() - start_time
            print(f"\n⏳ 진행 중: {i}/{len(pdf_files)} ({i/len(pdf_files)*100:.1f}%) - {elapsed:.1f}초")
        
        result = check_pdf_has_text(pdf_path)
        
        if result is True:
            text_extractable.append(pdf_path)
            sys.stdout.write('.')
        elif result is False:
            ocr_needed.append(pdf_path)
            sys.stdout.write('X')
        else:
            check_failed.append(pdf_path)
            sys.stdout.write('?')
        
        sys.stdout.flush()
    
    print("\n")
    elapsed_total = time.time() - start_time
    
    return text_extractable, ocr_needed, check_failed, elapsed_total

def main():
    print("🔍 OCR 필요 문서 식별 스크립트")
    print("="*60)
    
    text_docs, ocr_docs, failed_docs, elapsed = scan_documents()
    
    print("\n" + "="*60)
    print("📊 분석 결과")
    print("="*60)
    
    print(f"\n✅ 텍스트 추출 가능: {len(text_docs)}개")
    print(f"🔍 OCR 필요 (스캔): {len(ocr_docs)}개")
    print(f"⚠️ 확인 실패: {len(failed_docs)}개")
    print(f"⏱️ 소요 시간: {elapsed:.1f}초")
    
    if ocr_docs:
        print("\n" + "="*60)
        print(f"🔍 OCR이 필요한 스캔 문서 목록 ({len(ocr_docs)}개)")
        print("="*60)
        
        # 연도별로 그룹화
        year_groups = {}
        for pdf_path in ocr_docs:
            year = pdf_path.parent.name
            if year not in year_groups:
                year_groups[year] = []
            year_groups[year].append(pdf_path)
        
        # 연도 순으로 정렬하여 출력
        for year in sorted(year_groups.keys()):
            docs = year_groups[year]
            print(f"\n📁 {year} ({len(docs)}개):")
            for doc in sorted(docs):
                # 파일명만 출력 (가독성)
                print(f"  • {doc.name}")
    
    if failed_docs:
        print("\n" + "="*60)
        print(f"⚠️ 확인 실패한 문서 ({len(failed_docs)}개)")
        print("="*60)
        for doc in failed_docs:
            print(f"  • {doc.name}")
    
    # 통계 요약
    total = len(text_docs) + len(ocr_docs) + len(failed_docs)
    ocr_ratio = (len(ocr_docs) / total * 100) if total > 0 else 0
    
    print("\n" + "="*60)
    print("📈 요약 통계")
    print("="*60)
    print(f"  • 전체 문서: {total}개")
    print(f"  • OCR 필요 비율: {ocr_ratio:.1f}%")
    print(f"  • 평균 처리 시간: {elapsed/total:.2f}초/문서")

if __name__ == "__main__":
    main()