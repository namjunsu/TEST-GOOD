#!/usr/bin/env python3
"""
새 PDF 자동 감지 및 OCR 처리 모니터
- 새 PDF 추가 시 자동으로 OCR 처리
- 백그라운드 상시 실행
"""

import time
import logging
from pathlib import Path
from metadata_manager import MetadataManager
from background_ocr_processor import BackgroundOCRProcessor
import threading

logger = logging.getLogger(__name__)

class AutoOCRMonitor:
    def __init__(self):
        self.manager = MetadataManager()
        self.processor = BackgroundOCRProcessor(batch_size=5, interval=10)
        self.running = False
        self.check_interval = 60  # 60초마다 확인

    def check_new_pdfs(self):
        """새로운 스캔 PDF 확인"""
        docs_dir = Path('docs')
        new_scanned = []

        for pdf_path in docs_dir.rglob('*.pdf'):
            filename = pdf_path.name

            # DB에 없는 새 파일 확인
            if not self.manager.get_document(filename):
                # 스캔 PDF인지 확인
                if self.processor._is_scanned_pdf(pdf_path):
                    new_scanned.append(pdf_path)
                    logger.info(f"새 스캔 PDF 발견: {filename}")

        return new_scanned

    def run_monitor(self):
        """모니터링 실행"""
        logger.info("자동 OCR 모니터 시작")
        logger.info(f"체크 간격: {self.check_interval}초")

        while self.running:
            # 새 파일 확인
            new_pdfs = self.check_new_pdfs()

            if new_pdfs:
                logger.info(f"{len(new_pdfs)}개 새 스캔 PDF 발견!")
                # OCR 처리
                self.processor.process_batch()
            else:
                logger.debug("새 파일 없음")

            # 대기
            time.sleep(self.check_interval)

    def start(self):
        """백그라운드 모니터 시작"""
        self.running = True
        self.thread = threading.Thread(target=self.run_monitor, daemon=True)
        self.thread.start()
        logger.info("자동 OCR 모니터가 백그라운드에서 실행 중입니다")

    def stop(self):
        """모니터 중지"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=5)

# 웹 인터페이스와 통합하려면:
# web_interface.py에 추가:
# from auto_ocr_monitor import AutoOCRMonitor
# ocr_monitor = AutoOCRMonitor()
# ocr_monitor.start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = AutoOCRMonitor()

    print("🔄 자동 OCR 모니터")
    print("- 60초마다 새 PDF 확인")
    print("- 스캔 PDF 자동 처리")
    print("- Ctrl+C로 중지\n")

    try:
        monitor.running = True
        monitor.run_monitor()
    except KeyboardInterrupt:
        print("\n모니터 중지됨")