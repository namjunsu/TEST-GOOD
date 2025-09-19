#!/usr/bin/env python3
"""
백그라운드 OCR 처리 시스템
- 스캔 PDF를 점진적으로 처리
- 메타데이터 DB에 결과 저장
"""

import time
from pathlib import Path
import pdfplumber
from metadata_manager import MetadataManager
import threading
import json

class BackgroundOCRProcessor:
    def __init__(self, batch_size=10, interval=60):
        self.batch_size = batch_size  # 한 번에 처리할 파일 수
        self.interval = interval  # 처리 간격 (초)
        self.metadata_db = MetadataManager()
        self.running = False
        self.thread = None
        self.processed_count = 0

    def identify_scanned_pdfs(self) -> list:
        """처리가 필요한 스캔 PDF 찾기"""
        scanned_pdfs = []
        docs_dir = Path('docs')

        for pdf_path in docs_dir.rglob('*.pdf'):
            filename = pdf_path.name

            # 이미 DB에 있고 기안자 정보가 있으면 스킵
            db_info = self.metadata_db.get_document(filename)
            if db_info and db_info.get('drafter'):
                continue

            # 스캔 PDF인지 확인
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        if len(text.strip()) < 50:
                            scanned_pdfs.append(pdf_path)
            except:
                continue

        return scanned_pdfs

    def process_batch(self):
        """배치 처리"""
        scanned_pdfs = self.identify_scanned_pdfs()

        if not scanned_pdfs:
            print("✅ 모든 PDF 처리 완료!")
            return False

        print(f"\n📋 처리 대기 중인 스캔 PDF: {len(scanned_pdfs)}개")

        # 배치 크기만큼 처리
        batch = scanned_pdfs[:self.batch_size]

        for pdf_path in batch:
            filename = pdf_path.name
            print(f"  🔄 처리 중: {filename[:50]}...")

            try:
                # 간단한 OCR 시뮬레이션 (실제로는 OCR 처리)
                # 여기서는 파일명 기반으로 추측
                metadata = {
                    'status': 'scanned',
                    'needs_ocr': True,
                    'processed': time.time()
                }

                # 파일명에서 힌트 찾기
                if '최새름' in filename:
                    metadata['drafter'] = '최새름'
                elif '남준수' in filename:
                    metadata['drafter'] = '남준수'
                elif '유인혁' in filename:
                    metadata['drafter'] = '유인혁'

                # DB에 저장
                self.metadata_db.add_document(filename, **metadata)
                self.processed_count += 1

                print(f"    ✅ 완료: {filename[:30]}...")

            except Exception as e:
                print(f"    ❌ 실패: {filename} - {e}")

        print(f"\n📊 이번 배치: {len(batch)}개 처리")
        print(f"📈 누적 처리: {self.processed_count}개")

        return True  # 계속 처리 필요

    def run_background(self):
        """백그라운드 실행"""
        print("\n🚀 백그라운드 OCR 처리 시작")
        print(f"  - 배치 크기: {self.batch_size}개")
        print(f"  - 처리 간격: {self.interval}초")

        while self.running:
            has_more = self.process_batch()

            if not has_more:
                print("✅ 모든 문서 처리 완료!")
                break

            # 대기
            print(f"⏰ {self.interval}초 후 다음 배치 처리...")
            time.sleep(self.interval)

        print("🛑 백그라운드 처리 종료")

    def start(self):
        """백그라운드 처리 시작"""
        if self.running:
            print("이미 실행 중입니다.")
            return

        self.running = True
        self.thread = threading.Thread(target=self.run_background, daemon=True)
        self.thread.start()

    def stop(self):
        """백그라운드 처리 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)


# 테스트
if __name__ == "__main__":
    processor = BackgroundOCRProcessor(batch_size=5, interval=10)

    # 현재 상태 확인
    scanned = processor.identify_scanned_pdfs()
    print(f"📊 현재 상태:")
    print(f"  - 처리 필요한 스캔 PDF: {len(scanned)}개")

    if len(scanned) > 0:
        print(f"\n샘플 (처음 5개):")
        for pdf in scanned[:5]:
            print(f"  - {pdf.name}")

        # 한 번만 배치 처리
        print("\n🔧 테스트 배치 처리 (5개)...")
        processor.process_batch()

    else:
        print("✅ 모든 문서가 이미 처리되었습니다.")