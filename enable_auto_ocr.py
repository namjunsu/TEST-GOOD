#!/usr/bin/env python3
"""
자동 OCR 활성화 스크립트
- 스캔 PDF 문서를 자동 감지하고 OCR 처리
- 처리된 텍스트를 캐시에 저장
"""

import sys
import json
from pathlib import Path
import time
from typing import Dict, List, Tuple
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/wnstn4647/AI-CHAT')
from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor

def identify_scanned_pdfs(docs_dir: Path) -> List[Path]:
    """스캔 PDF 파일 식별"""
    scanned_pdfs = []
    all_pdfs = list(docs_dir.glob('**/*.pdf'))
    
    logger.info(f"🔍 전체 {len(all_pdfs)}개 PDF 검사 시작...")
    
    for pdf_path in all_pdfs:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if pdf.pages:
                    # 처음 2페이지만 검사
                    total_text = ""
                    for page in pdf.pages[:2]:
                        text = page.extract_text() or ""
                        total_text += text
                    
                    # 텍스트가 50자 미만이면 스캔 문서로 간주
                    if len(total_text.strip()) < 50:
                        scanned_pdfs.append(pdf_path)
        except Exception as e:
            # 오류 발생 시도 스캔으로 간주
            scanned_pdfs.append(pdf_path)
    
    logger.info(f"❌ 스캔 PDF {len(scanned_pdfs)}개 발견 ({len(scanned_pdfs)*100//len(all_pdfs)}%)")
    return scanned_pdfs

def process_single_pdf(pdf_path: Path, ocr_processor: EnhancedOCRProcessor) -> Tuple[Path, bool, str]:
    """단일 PDF OCR 처리"""
    try:
        logger.info(f"🔄 OCR 처리: {pdf_path.name}")
        text, metadata = ocr_processor.extract_text_with_ocr(str(pdf_path))
        
        if metadata.get('ocr_performed') and len(text) > 100:
            return pdf_path, True, text
        else:
            return pdf_path, False, ""
    except Exception as e:
        logger.error(f"❌ OCR 실패: {pdf_path.name} - {e}")
        return pdf_path, False, ""

def batch_ocr_processing(scanned_pdfs: List[Path], max_workers: int = 4) -> Dict[str, str]:
    """병렬 OCR 처리"""
    ocr_results = {}
    ocr_processor = EnhancedOCRProcessor()
    
    logger.info(f"🚀 {max_workers}개 워커로 병렬 OCR 시작...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_single_pdf, pdf_path, ocr_processor)
            for pdf_path in scanned_pdfs[:10]  # 먼저 10개만 테스트
        ]
        
        for future in as_completed(futures):
            pdf_path, success, text = future.result()
            if success:
                ocr_results[str(pdf_path)] = text
                logger.info(f"✅ OCR 성공: {pdf_path.name} ({len(text)}자)")
    
    return ocr_results

def save_ocr_cache(ocr_results: Dict[str, str], cache_file: Path):
    """처리된 OCR 결과 캐시에 저장"""
    cache_data = {
        'version': '1.0',
        'created_at': time.time(),
        'total_processed': len(ocr_results),
        'ocr_texts': ocr_results
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"💾 OCR 캐시 저장: {cache_file}")

def main():
    """메인 실행"""
    docs_dir = Path('docs')
    cache_file = Path('ocr_cache.json')
    
    print("\n" + "="*60)
    print("🤖 자동 OCR 처리 시스템")
    print("="*60)
    
    # 1. 스캔 PDF 식별
    scanned_pdfs = identify_scanned_pdfs(docs_dir)
    
    if not scanned_pdfs:
        print("✅ 모든 PDF가 텍스트 추출 가능합니다!")
        return
    
    print(f"\n📋 스캔 문서 예시:")
    for pdf in scanned_pdfs[:5]:
        print(f"  - {pdf.name}")
    
    # 2. OCR 처리
    print(f"\n🔄 OCR 처리 시작 (처음 10개만 테스트)...")
    start_time = time.time()
    
    ocr_results = batch_ocr_processing(scanned_pdfs)
    
    elapsed = time.time() - start_time
    print(f"\n✅ OCR 처리 완료!")
    print(f"  - 성공: {len(ocr_results)}개")
    print(f"  - 시간: {elapsed:.1f}초")
    print(f"  - 평균: {elapsed/len(ocr_results):.1f}초/문서" if ocr_results else "")
    
    # 3. 캐시 저장
    if ocr_results:
        save_ocr_cache(ocr_results, cache_file)
        print(f"\n💾 캐시 파일: {cache_file}")
        
        # 예시 출력
        example_path = list(ocr_results.keys())[0]
        example_text = ocr_results[example_path]
        print(f"\n📄 OCR 결과 예시 ({Path(example_path).name}):")
        print(f"{example_text[:200]}..." if len(example_text) > 200 else example_text)

if __name__ == "__main__":
    main()