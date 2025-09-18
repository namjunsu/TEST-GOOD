#!/usr/bin/env python3
"""
PDF 문서들을 RAG 시스템에 인덱싱하는 스크립트
"""

import os
import sys
import warnings
import logging
from pathlib import Path
from typing import List
import time

# 프로젝트 루트를 동적으로 찾기
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

# 설정 파일 import
import config

# PDF 관련 경고 메시지 필터링
warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfplumber")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")

from rag_system.hybrid_search import HybridSearch
from rag_system.metadata_extractor import MetadataExtractor
from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor  # OCR 프로세서

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# pdfminer/pdfplumber의 불필요한 경고 숨기기
logging.getLogger('pdfminer').setLevel(logging.ERROR)
logging.getLogger('pdfminer.pdffont').setLevel(logging.ERROR)
logging.getLogger('pdfminer.pdfinterp').setLevel(logging.ERROR)
logging.getLogger('pdfplumber').setLevel(logging.ERROR)

def clean_extracted_text(text: str) -> str:
    """추출된 텍스트 정리 - OCR 오류 패턴 기반 동적 처리"""
    import re
    
    # 1. 분리된 모델명 패턴 복원 (XXX-999XX 형식)
    # 대문자들이 공백으로 분리된 후 하이픈과 숫자가 오는 패턴
    text = re.sub(r'([A-Z])\s+([A-Z])\s+([A-Z])\s*-?\s*(\d+)\s*([A-Z]+)', r'\1\2\3-\4\5', text)
    
    # 2. 숫자 분리 복원 (천단위 콤마가 있는 숫자)
    # 3 , 0 0 0 -> 3,000 형식 복원
    text = re.sub(r'(\d)\s*,\s*(\d)\s*(\d)\s*(\d)', r'\1,\2\3\4', text)
    text = re.sub(r'(\d)\s+(\d)\s+(\d)\s+(\d)', r'\1\2\3\4', text)  # 4자리
    text = re.sub(r'(\d)\s+(\d)\s+(\d)', r'\1\2\3', text)  # 3자리
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)  # 2자리
    
    # 3. OCR로 분리된 한글 복원 (일반 패턴)
    # 2-4글자 한글이 공백으로 분리된 경우 합치기
    def merge_korean(match):
        parts = match.group(0).split()
        merged = ''.join(parts)
        # 일반적인 한글 단어 길이인 2-5자면 합치기
        if 2 <= len(merged) <= 5:
            return merged
        return match.group(0)
    
    text = re.sub(r'([가-힣])\s+([가-힣])(?:\s+([가-힣]))?(?:\s+([가-힣]))?', merge_korean, text)
    
    # 4. 영문 브랜드명 복원 (대문자+숫자 조합)
    text = re.sub(r'([A-Z]{2,})\s+([A-Z]*\d+)', r'\1\2', text)
    
    # 5. 불필요한 다중 공백 제거
    text = re.sub(r'\s+', ' ', text)
    
    return text

def extract_text_from_txt(txt_path: str) -> List[str]:
    """TXT 파일에서 텍스트 추출"""
    chunks = []
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
        
        # 텍스트를 청크로 분할
        chunk_size = 2048
        overlap = 256
        
        for i in range(0, len(full_text), chunk_size - overlap):
            chunk = full_text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
    except Exception as e:
        logger.error(f"TXT 텍스트 추출 실패 {txt_path}: {e}")
        return []

def extract_text_from_pdf(pdf_path: str, use_enhanced_ocr: bool = True) -> List[str]:
    """PDF에서 텍스트 추출 - 향상된 OCR 포함"""
    try:
        chunks = []
        full_text = ""
        
        if use_enhanced_ocr:
            # 향상된 OCR 프로세서 사용 (Tesseract 포함)
            try:
                enhanced_ocr = EnhancedOCRProcessor()
                full_text, metadata = enhanced_ocr.extract_text_with_ocr(pdf_path)
                
                # 메타데이터 로깅
                if metadata.get('ocr_performed'):
                    logger.info(f"  OCR 수행: {metadata['image_count']}개 이미지, {metadata['ocr_text_length']}자 추출")
            except Exception as e:
                logger.warning(f"향상된 OCR 실패, 기본 모드로 전환: {e}")
                use_enhanced_ocr = False
        
        # 기본 방식 폴백 또는 향상된 OCR 실패 시
        if not use_enhanced_ocr or not full_text:
            import pdfplumber
            # EnhancedOCRProcessor의 후처리 메서드 사용
            enhanced_ocr = EnhancedOCRProcessor()
            
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        # OCR 후처리 적용 (HP Z8, 금액 등 수정)
                        corrected_text = enhanced_ocr._post_process_ocr(page_text)
                        # 추가 텍스트 정리 적용
                        cleaned_text = clean_extracted_text(corrected_text)
                        full_text += f"\n[페이지 {page_num + 1}]\n{cleaned_text}\n"
                    
            # PyPDF2로 fallback 시도 (OCR 검출기 포함)
            if not full_text.strip():
                logger.warning(f"pdfplumber 추출 실패, PyPDF2로 재시도: {pdf_path}")
                import PyPDF2
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages):
                        page_text = page.extract_text()
                        if page_text.strip():
                            # OCR 후처리 적용 (HP Z8, 금액 등 수정)
                            corrected_text = enhanced_ocr._post_process_ocr(page_text)
                            cleaned_text = clean_extracted_text(corrected_text)
                            full_text += f"\n[페이지 {page_num + 1}]\n{cleaned_text}\n"
            
        # 텍스트를 청크로 분할 (더 큰 청크로 개선)
        chunk_size = 2048  # 1024 -> 2048로 증가 (더 많은 컨텍스트 포함)
        overlap = 256      # 128 -> 256으로 증가 (문맥 연결성 향상)
        
        for i in range(0, len(full_text), chunk_size - overlap):
            chunk = full_text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
        
    except Exception as e:
        logger.error(f"PDF 텍스트 추출 실패 {pdf_path}: {e}")
        return []

def main():
    """메인 실행 함수"""
    
    print("RAG System Index Building Started")
    print("=" * 50)
    
    try:
        # 하이브리드 검색 시스템 초기화
        hybrid_search = HybridSearch()
        
        # 메타데이터 추출기 초기화
        metadata_extractor = MetadataExtractor()
        
        # PDF와 TXT 파일들 찾기 - config 사용
        docs_dir = Path(config.DOCS_DIR)
        pdf_files = list(docs_dir.glob('*.pdf'))
        txt_files = list(docs_dir.glob('*.txt'))
        all_files = pdf_files + txt_files
        
        print(f"📄 발견된 문서 파일: {len(all_files)}개 (PDF: {len(pdf_files)}, TXT: {len(txt_files)})")
        
        total_chunks = 0
        processed_files = 0
        
        for doc_file in all_files:
            print(f"\n🔄 처리 중: {doc_file.name}")
            
            try:
                # 파일 형식에 따라 텍스트 추출
                if doc_file.suffix.lower() == '.pdf':
                    chunks = extract_text_from_pdf(str(doc_file))
                elif doc_file.suffix.lower() == '.txt':
                    chunks = extract_text_from_txt(str(doc_file))
                else:
                    continue
                
                if chunks:
                    # 전체 텍스트로 메타데이터 추출
                    full_text = ' '.join(chunks)
                    extracted_metadata = metadata_extractor.extract_metadata(full_text, str(doc_file))
                    
                    # 검색 가능한 청크 생성 (메타데이터 포함)
                    enhanced_chunks = []
                    metadatas = []
                    
                    for i, chunk in enumerate(chunks):
                        # 메타데이터를 검색 텍스트에 포함 (핵심!)
                        metadata_text = f"\n[메타데이터] 파일명: {extracted_metadata.filename}"
                        if extracted_metadata.author:
                            metadata_text += f" 기안자: {extracted_metadata.author}"
                        if extracted_metadata.date:
                            metadata_text += f" 작성일: {extracted_metadata.date}"
                        if extracted_metadata.amount:
                            metadata_text += f" 금액: {extracted_metadata.amount:,}원"
                        if extracted_metadata.department:
                            metadata_text += f" 부서: {extracted_metadata.department}"
                        
                        # 청크에 메타데이터 텍스트 추가
                        enhanced_chunk = chunk + metadata_text
                        enhanced_chunks.append(enhanced_chunk)
                        
                        # 메타데이터 딕셔너리 생성
                        chunk_metadata = {
                            'source': extracted_metadata.filename,  # source 필드 추가 (중요!)
                            'filename': extracted_metadata.filename,
                            'file_path': extracted_metadata.file_path,
                            'doc_type': extracted_metadata.doc_type,
                            'date': extracted_metadata.date,
                            'author': extracted_metadata.author,
                            'department': extracted_metadata.department,
                            'amount': extracted_metadata.amount,
                            'chunk_id': f"{doc_file.stem}_{i}",
                            'chunk_index': i,
                            'content': chunk
                        }
                        metadatas.append(chunk_metadata)
                    
                    # 하이브리드 검색에 추가 (메타데이터가 포함된 텍스트 사용)
                    hybrid_search.add_documents(enhanced_chunks, metadatas)
                    
                    total_chunks += len(chunks)
                    processed_files += 1
                    
                    print(f"   ✅ {len(chunks)}개 청크 추가됨")
                else:
                    print(f"   ⚠️  텍스트 추출 실패")
                    
            except Exception as e:
                print(f"   ❌ 파일 처리 실패: {e}")
        
        print(f"\n📊 인덱싱 완료!")
        print(f"   - 처리된 파일: {processed_files}/{len(all_files)}개")
        print(f"   - 총 청크 수: {total_chunks}개")
        
        # 인덱스 저장
        print(f"\n💾 인덱스 저장 중...")
        hybrid_search.save_indexes()
        print(f"   ✅ 인덱스 저장 완료")
        
        # 테스트 검색
        print(f"\n🧪 테스트 검색...")
        test_results = hybrid_search.search("핀마이크 가격", top_k=3)
        print(f"   ✅ 테스트 검색 결과: {len(test_results.get('fused_results', []))}개")
        
        if test_results.get('fused_results'):
            first_result = test_results['fused_results'][0]
            print(f"   📄 첫 번째 결과: {first_result.get('filename', 'N/A')}")
        
        print(f"\n🎉 인덱스 구축이 성공적으로 완료되었습니다!")
        
    except Exception as e:
        print(f"\n❌ 인덱스 구축 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()