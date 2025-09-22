#!/usr/bin/env python3
"""
백그라운드 OCR 처리 시스템
- 스캔 PDF를 점진적으로 처리
- 메타데이터 DB에 결과 저장
"""

import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
import pdfplumber
from metadata_manager import MetadataManager
import threading
import json
from functools import lru_cache

logger = logging.getLogger(__name__)

class BackgroundOCRProcessor:
    # 상수 정의
    DEFAULT_BATCH_SIZE = 10
    DEFAULT_INTERVAL = 60  # 초
    MIN_TEXT_LENGTH = 50  # 스캔 PDF 판단 기준
    THREAD_JOIN_TIMEOUT = 5  # 초
    MAX_FILENAME_DISPLAY = 50  # 파일명 표시 길이

    # 기안자 매핑 (실제로는 설정 파일에서 로드해야 함)
    DRAFTER_HINTS = {
        '최새름': '최새름',
        '남준수': '남준수',
        '유인혁': '유인혁'
    }

    def __init__(self, batch_size: int = None, interval: int = None):
        self.batch_size = batch_size if batch_size is not None else self.DEFAULT_BATCH_SIZE
        self.interval = interval if interval is not None else self.DEFAULT_INTERVAL
        self.metadata_db = MetadataManager()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.processed_count = 0

        # 성능 메트릭
        self._start_time: Optional[float] = None
        self._total_processing_time = 0.0
        self._error_count = 0
        self._processed_files: Set[str] = set()  # 중복 처리 방지

    def identify_scanned_pdfs(self) -> List[Path]:
        """처리가 필요한 스캔 PDF 찾기 (성능 최적화)"""
        scanned_pdfs: List[Path] = []
        docs_dir = Path('docs')

        if not docs_dir.exists():
            logger.warning(f"docs 디렉토리가 존재하지 않음")
            return scanned_pdfs

        for pdf_path in docs_dir.rglob('*.pdf'):
            filename = pdf_path.name

            # 이미 처리된 파일 스킵
            if filename in self._processed_files:
                continue

            # 이미 DB에 있고 기안자 정보가 있으면 스킵
            db_info = self.metadata_db.get_document(filename)
            if db_info and db_info.get('drafter'):
                self._processed_files.add(filename)
                continue

            # 스캔 PDF인지 확인
            if self._is_scanned_pdf(pdf_path):
                scanned_pdfs.append(pdf_path)

        return scanned_pdfs

    @lru_cache(maxsize=256)
    def _is_scanned_pdf(self, pdf_path: Path) -> bool:
        """스캔 PDF인지 확인 (캐시됨)"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ""
                    return len(text.strip()) < self.MIN_TEXT_LENGTH
        except Exception as e:
            logger.debug(f"PDF 확인 실패: {pdf_path.name} - {e}")
        return False

    def process_batch(self) -> bool:
        """배치 처리 (성능 추적 포함)"""
        batch_start_time = time.time()
        scanned_pdfs = self.identify_scanned_pdfs()

        if not scanned_pdfs:
            logger.info("모든 PDF 처리 완료!")
            return False

        logger.info(f"처리 대기 중인 스캔 PDF: {len(scanned_pdfs)}개")

        # 배치 크기만큼 처리
        batch = scanned_pdfs[:self.batch_size]

        for pdf_path in batch:
            filename = pdf_path.name
            display_name = filename[:self.MAX_FILENAME_DISPLAY] + ('...' if len(filename) > self.MAX_FILENAME_DISPLAY else '')
            logger.debug(f"처리 중: {display_name}")

            try:
                # OCR 시뮬레이션 (실제로는 OCR 처리)
                metadata = self._extract_metadata(filename)

                # DB에 저장
                self.metadata_db.add_document(filename, **metadata)
                self.processed_count += 1
                self._processed_files.add(filename)

                logger.debug(f"완료: {display_name}")

            except Exception as e:
                self._error_count += 1
                logger.error(f"처리 실패: {filename} - {e}")

        # 배치 처리 시간 기록
        batch_time = time.time() - batch_start_time
        self._total_processing_time += batch_time

        logger.info(f"이번 배치: {len(batch)}개 처리 ({batch_time:.2f}초)")
        logger.info(f"누적 처리: {self.processed_count}개, 오류: {self._error_count}개")

        return True  # 계속 처리 필요

    def _extract_metadata(self, filename: str) -> Dict[str, any]:
        """파일명에서 메타데이터 추출"""
        metadata = {
            'status': 'scanned',
            'needs_ocr': True,
            'processed': time.time()
        }

        # 파일명에서 기안자 힌트 찾기
        for hint, drafter in self.DRAFTER_HINTS.items():
            if hint in filename:
                metadata['drafter'] = drafter
                break

        return metadata

    def run_background(self) -> None:
        """백그라운드 실행"""
        logger.info("백그라운드 OCR 처리 시작")
        logger.info(f"배치 크기: {self.batch_size}개, 처리 간격: {self.interval}초")
        self._start_time = time.time()

        while self.running:
            has_more = self.process_batch()

            if not has_more:
                logger.info("모든 문서 처리 완료!")
                break

            # 대기
            logger.debug(f"{self.interval}초 후 다음 배치 처리...")
            time.sleep(self.interval)

        logger.info("백그라운드 처리 종료")

    def start(self) -> None:
        """백그라운드 처리 시작"""
        if self.running:
            logger.warning("이미 실행 중입니다.")
            return

        self.running = True
        self.thread = threading.Thread(target=self.run_background, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """백그라운드 처리 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=self.THREAD_JOIN_TIMEOUT)

    def get_stats(self) -> Dict[str, any]:
        """통계 정보 반환"""
        uptime = time.time() - self._start_time if self._start_time else 0
        avg_time_per_file = (self._total_processing_time / self.processed_count
                            if self.processed_count > 0 else 0)

        return {
            'processed_count': self.processed_count,
            'error_count': self._error_count,
            'uptime_seconds': uptime,
            'total_processing_time': self._total_processing_time,
            'avg_time_per_file': avg_time_per_file,
            'cached_files': len(self._processed_files),
            'batch_size': self.batch_size,
            'interval': self.interval
        }


# 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
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

        # 통계 출력
        stats = processor.get_stats()
        print("\n⚡ 처리 통계:")
        print(f"  - 처리된 파일: {stats['processed_count']}개")
        print(f"  - 평균 처리 시간: {stats['avg_time_per_file']:.3f}초/파일")

    else:
        print("✅ 모든 문서가 이미 처리되었습니다.")