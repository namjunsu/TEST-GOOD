#!/usr/bin/env python3
"""
자동 OCR 처리 활성화 스크립트
- 스캔된 PDF 자동 감지
- OCR 처리 및 텍스트 추출
- 메타데이터 DB 구축
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import re

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OCREnabler:
    """OCR 자동 처리 활성화 클래스"""

    # 상수 정의
    MIN_TEXT_LENGTH = 50  # 텍스트 PDF 판단 기준
    MAX_WORKERS = 4  # 병렬 처리 워커 수
    DPI_QUALITY = 300  # OCR용 DPI
    OCR_LANGUAGES = 'kor+eng'  # 한국어+영어 OCR
    CACHE_FILE = 'ocr_metadata.json'

    def __init__(self):
        self.docs_dir = Path('docs')
        self.cache_file = Path(self.CACHE_FILE)
        self.metadata = self.load_metadata()

        # 통계
        self.total_pdfs = 0
        self.text_pdfs = 0
        self.scanned_pdfs = 0
        self.ocr_success = 0
        self.ocr_failed = 0

    def load_metadata(self) -> Dict:
        """기존 메타데이터 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"메타데이터 로드 실패: {e}")
        return {}

    def save_metadata(self):
        """메타데이터 저장"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.info(f"메타데이터 저장 완료: {len(self.metadata)}개 문서")
        except Exception as e:
            logger.error(f"메타데이터 저장 실패: {e}")

    def is_scanned_pdf(self, pdf_path: Path) -> bool:
        """스캔 PDF인지 확인"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False

                # 첫 페이지 텍스트 확인
                text = pdf.pages[0].extract_text() or ""

                # 텍스트가 거의 없으면 스캔 PDF로 판단
                if len(text.strip()) < self.MIN_TEXT_LENGTH:
                    return True

                # 텍스트가 있어도 깨진 문자가 많으면 스캔 PDF
                # 한글/영어/숫자/기본 특수문자 외 문자 비율 확인
                normal_chars = re.findall(r'[가-힣a-zA-Z0-9\s\.,\-_()]+', text)
                normal_text = ''.join(normal_chars)

                if len(normal_text) < len(text) * 0.5:  # 정상 문자가 50% 미만
                    return True

        except Exception as e:
            logger.debug(f"PDF 확인 실패: {pdf_path.name} - {e}")

        return False

    def process_with_ocr(self, pdf_path: Path) -> Optional[str]:
        """OCR로 텍스트 추출"""
        try:
            logger.info(f"OCR 처리 시작: {pdf_path.name}")

            # PDF를 이미지로 변환
            images = convert_from_path(
                str(pdf_path),
                dpi=self.DPI_QUALITY,
                thread_count=2
            )

            # 각 페이지 OCR 처리
            extracted_texts = []
            for i, image in enumerate(images[:5], 1):  # 처음 5페이지만
                try:
                    # OCR 실행
                    text = pytesseract.image_to_string(
                        image,
                        lang=self.OCR_LANGUAGES,
                        config='--oem 3 --psm 6'
                    )

                    if text.strip():
                        extracted_texts.append(f"[페이지 {i}]\n{text}")

                except Exception as e:
                    logger.warning(f"페이지 {i} OCR 실패: {e}")

            if extracted_texts:
                full_text = "\n\n".join(extracted_texts)
                logger.info(f"OCR 성공: {pdf_path.name} ({len(full_text)}자)")
                return full_text
            else:
                logger.warning(f"OCR 텍스트 추출 실패: {pdf_path.name}")
                return None

        except Exception as e:
            logger.error(f"OCR 처리 실패: {pdf_path.name} - {e}")
            return None

    def extract_metadata(self, text: str, filename: str) -> Dict:
        """텍스트에서 메타데이터 추출"""
        metadata = {
            'filename': filename,
            'has_text': True,
            'extracted_at': time.time()
        }

        # 기안자 추출
        drafter_patterns = [
            r'기안자[:\s]*([가-힣]{2,4})',
            r'작성자[:\s]*([가-힣]{2,4})',
            r'담당[:\s]*([가-힣]{2,4})',
        ]
        for pattern in drafter_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['drafter'] = match.group(1)
                break

        # 날짜 추출
        date_pattern = r'(\d{4})[년\-./]\s*(\d{1,2})[월\-./]\s*(\d{1,2})'
        date_match = re.search(date_pattern, text)
        if date_match:
            metadata['date'] = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

        # 금액 추출
        amount_patterns = [
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'금액[:\s]*(\d{1,3}(?:,\d{3})*)',
            r'총[액계][:\s]*(\d{1,3}(?:,\d{3})*)'
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    metadata['amount'] = int(float(amount_str))
                except:
                    pass
                break

        return metadata

    def process_pdf(self, pdf_path: Path) -> Dict:
        """PDF 처리 (텍스트 추출 또는 OCR)"""
        filename = pdf_path.name

        # 이미 처리된 파일 확인
        if filename in self.metadata:
            logger.debug(f"이미 처리됨: {filename}")
            return self.metadata[filename]

        metadata = {'filename': filename, 'path': str(pdf_path)}

        if self.is_scanned_pdf(pdf_path):
            self.scanned_pdfs += 1
            metadata['is_scanned'] = True

            # OCR 처리
            extracted_text = self.process_with_ocr(pdf_path)
            if extracted_text:
                self.ocr_success += 1
                metadata['ocr_success'] = True
                metadata.update(self.extract_metadata(extracted_text, filename))

                # OCR 텍스트 저장 (선택사항)
                ocr_file = pdf_path.with_suffix('.ocr.txt')
                try:
                    with open(ocr_file, 'w', encoding='utf-8') as f:
                        f.write(extracted_text)
                    metadata['ocr_file'] = str(ocr_file)
                except:
                    pass
            else:
                self.ocr_failed += 1
                metadata['ocr_success'] = False
        else:
            self.text_pdfs += 1
            metadata['is_scanned'] = False

            # 일반 텍스트 추출
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        metadata.update(self.extract_metadata(text, filename))
            except:
                pass

        return metadata

    def analyze_documents(self) -> Tuple[List[Path], List[Path]]:
        """문서 분석 및 분류"""
        logger.info("문서 분석 시작...")

        text_pdfs = []
        scanned_pdfs = []

        # 모든 PDF 파일 찾기
        pdf_files = list(self.docs_dir.rglob('*.pdf'))
        self.total_pdfs = len(pdf_files)

        logger.info(f"총 {self.total_pdfs}개 PDF 발견")

        # 분류
        for pdf_path in tqdm(pdf_files, desc="PDF 분류"):
            if self.is_scanned_pdf(pdf_path):
                scanned_pdfs.append(pdf_path)
            else:
                text_pdfs.append(pdf_path)

        logger.info(f"텍스트 PDF: {len(text_pdfs)}개")
        logger.info(f"스캔 PDF: {len(scanned_pdfs)}개")

        return text_pdfs, scanned_pdfs

    def enable_ocr_processing(self):
        """OCR 처리 활성화 및 실행"""
        logger.info("="*60)
        logger.info("OCR 자동 처리 시작")
        logger.info("="*60)

        # 문서 분석
        text_pdfs, scanned_pdfs = self.analyze_documents()

        # 스캔 PDF 목록 출력
        if scanned_pdfs:
            logger.info(f"\n스캔 PDF 목록 ({len(scanned_pdfs)}개):")
            for pdf in scanned_pdfs[:10]:  # 처음 10개만 표시
                logger.info(f"  - {pdf.name}")
            if len(scanned_pdfs) > 10:
                logger.info(f"  ... 외 {len(scanned_pdfs)-10}개")

        # OCR 처리 자동 진행 (사용자 확인 없이)
        if not scanned_pdfs:
            logger.info("스캔 PDF가 없습니다.")
            return

        logger.info(f"\n{len(scanned_pdfs)}개 스캔 PDF 자동 처리 시작...")

        # 병렬 OCR 처리
        logger.info(f"\n병렬 OCR 처리 시작 (워커: {self.MAX_WORKERS}개)")

        with ProcessPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.process_pdf, pdf_path): pdf_path
                for pdf_path in scanned_pdfs
            }

            for future in tqdm(as_completed(futures), total=len(futures), desc="OCR 처리"):
                pdf_path = futures[future]
                try:
                    metadata = future.result(timeout=60)  # 1분 타임아웃
                    self.metadata[pdf_path.name] = metadata
                except Exception as e:
                    logger.error(f"처리 실패: {pdf_path.name} - {e}")

        # 메타데이터 저장
        self.save_metadata()

        # 결과 출력
        self.print_summary()

    def print_summary(self):
        """처리 결과 요약"""
        logger.info("\n" + "="*60)
        logger.info("OCR 처리 완료")
        logger.info("="*60)

        print(f"\n📊 처리 결과:")
        print(f"  총 PDF: {self.total_pdfs}개")
        print(f"  텍스트 PDF: {self.text_pdfs}개")
        print(f"  스캔 PDF: {self.scanned_pdfs}개")

        if self.scanned_pdfs > 0:
            success_rate = (self.ocr_success / self.scanned_pdfs) * 100
            print(f"\n🔍 OCR 결과:")
            print(f"  성공: {self.ocr_success}개 ({success_rate:.1f}%)")
            print(f"  실패: {self.ocr_failed}개")

        print(f"\n💾 메타데이터 파일: {self.CACHE_FILE}")
        print(f"   {len(self.metadata)}개 문서 정보 저장됨")

        # 추출된 정보 샘플
        if self.metadata:
            print("\n📝 추출된 메타데이터 샘플:")
            count = 0
            for filename, data in self.metadata.items():
                if data.get('drafter') or data.get('date') or data.get('amount'):
                    print(f"  • {filename[:50]}...")
                    if data.get('drafter'):
                        print(f"    기안자: {data['drafter']}")
                    if data.get('date'):
                        print(f"    날짜: {data['date']}")
                    if data.get('amount'):
                        print(f"    금액: {data['amount']:,}원")
                    count += 1
                    if count >= 3:
                        break

def main():
    """메인 함수"""
    enabler = OCREnabler()

    # Tesseract 설치 확인
    try:
        version = pytesseract.get_tesseract_version()
        logger.info(f"Tesseract 버전: {version}")
    except:
        logger.error("Tesseract가 설치되지 않았습니다!")
        logger.error("설치: sudo apt-get install tesseract-ocr tesseract-ocr-kor")
        return

    # OCR 처리 실행
    enabler.enable_ocr_processing()

if __name__ == "__main__":
    main()