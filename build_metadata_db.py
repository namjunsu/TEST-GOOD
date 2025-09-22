#!/usr/bin/env python3
"""
모든 PDF에서 메타데이터 자동 추출하여 DB 구축
- 텍스트 PDF: 즉시 추출
- 스캔 PDF: 나중에 처리 (표시만)
"""

import logging
import pdfplumber
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from metadata_manager import MetadataManager
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from functools import lru_cache
from tqdm import tqdm

logger = logging.getLogger(__name__)

class MetadataDBBuilder:
    """메타데이터 DB 구축 클래스"""

    # 상수 정의
    MIN_TEXT_LENGTH = 50  # 스캔 PDF 판단 기준
    MAX_WORKERS = 4  # 병렬 처리 워커 수
    MAX_FILENAME_DISPLAY = 50  # 파일명 표시 길이
    DEFAULT_BATCH_SIZE = 100  # 기본 배치 크기 (테스트용)

    def __init__(self, batch_size: Optional[int] = None):
        self.manager = MetadataManager()
        self.batch_size = batch_size

        # 통계
        self.text_count = 0
        self.scan_count = 0
        self.drafter_count = 0
        self.error_count = 0
        self.processing_times: List[float] = []

    def extract_metadata_from_pdf(self, pdf_path: Path) -> Dict:
        """PDF에서 메타데이터 추출 (성능 추적 포함)"""
        start_time = time.time()
        filename = pdf_path.name
        metadata = {'filename': filename, 'path': str(pdf_path)}

        try:
            if self._is_scanned_pdf(pdf_path):
                # 스캔 PDF
                metadata['status'] = 'scanned'
                metadata['needs_ocr'] = True
                display_name = self._truncate_filename(filename)
                logger.info(f"스캔 PDF 감지: {display_name}")
            else:
                # 텍스트 PDF - 메타데이터 추출
                metadata['status'] = 'text'

                with pdfplumber.open(pdf_path) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        # MetadataManager의 추출 함수 활용
                        extracted = self.manager.extract_from_text(text)
                        metadata.update(extracted)

                # 기안자 찾았으면 표시
                display_name = self._truncate_filename(filename)
                if metadata.get('drafter'):
                    logger.info(f"{display_name} → 기안자: {metadata['drafter']}")
                else:
                    logger.debug(f"{display_name} → 기안자 정보 없음")

        except Exception as e:
            metadata['status'] = 'error'
            metadata['error'] = str(e)
            self.error_count += 1
            logger.error(f"처리 오류: {filename} - {e}")

        # 처리 시간 기록
        processing_time = time.time() - start_time
        self.processing_times.append(processing_time)
        metadata['processing_time'] = processing_time

        return metadata

    @lru_cache(maxsize=512)
    def _is_scanned_pdf(self, pdf_path: Path) -> bool:
        """스캔 PDF인지 확인 (캐시됨)"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False

                # 첫 페이지만 빠르게 확인
                text = pdf.pages[0].extract_text() or ""
                return len(text.strip()) < self.MIN_TEXT_LENGTH

        except Exception:
            return False

    def _truncate_filename(self, filename: str) -> str:
        """파일명 길이 제한"""
        if len(filename) > self.MAX_FILENAME_DISPLAY:
            return filename[:self.MAX_FILENAME_DISPLAY] + "..."
        return filename

    def build_database(self, docs_dir: Path = None) -> Tuple[int, int, int]:
        """전체 문서 메타데이터 DB 구축 (병렬 처리)"""
        if docs_dir is None:
            docs_dir = Path('docs')

        logger.info("="*60)
        logger.info("메타데이터 DB 구축 시작")
        logger.info("="*60)

        # 모든 PDF 파일 찾기
        pdf_files = list(docs_dir.rglob('*.pdf'))

        # 배치 크기 적용
        if self.batch_size:
            pdf_files = pdf_files[:self.batch_size]
            logger.info(f"배치 모드: {self.batch_size}개만 처리")

        logger.info(f"총 {len(pdf_files)}개 PDF 파일 발견")

        # 통계 초기화
        self.text_count = 0
        self.scan_count = 0
        self.drafter_count = 0

        # 병렬 처리로 빠르게
        logger.info("메타데이터 추출 중...")

        # 프로그레스 바 사용 (tqdm 가능한 경우)
        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            use_tqdm = False

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.extract_metadata_from_pdf, pdf_path): pdf_path
                for pdf_path in pdf_files
            }

            # 프로그레스 바와 함께 처리
            completed_futures = tqdm(as_completed(futures), total=len(futures), desc="처리 중") if use_tqdm else as_completed(futures)

            for future in completed_futures:
                pdf_path = futures[future]
                try:
                    metadata = future.result()
                    filename = pdf_path.name

                    # DB에 저장 (filename은 metadata에서 제거)
                    if 'filename' in metadata:
                        del metadata['filename']
                    self.manager.add_document(filename, **metadata)

                    # 통계 업데이트
                    if metadata.get('status') == 'text':
                        self.text_count += 1
                    elif metadata.get('status') == 'scanned':
                        self.scan_count += 1

                    if metadata.get('drafter'):
                        self.drafter_count += 1

                except Exception as e:
                    logger.error(f"처리 실패: {pdf_path.name} - {e}")
                    self.error_count += 1

        # 저장
        self.manager.save_metadata()

        # 결과 로깅
        logger.info("="*60)
        logger.info("메타데이터 DB 구축 완료!")
        logger.info("="*60)

        self._print_statistics()

        return self.text_count, self.scan_count, self.drafter_count

    def _print_statistics(self):
        """통계 출력"""
        total_docs = self.text_count + self.scan_count

        print(f"\n📊 처리 결과:")
        print(f"  - 총 문서: {total_docs}개")
        print(f"  - 텍스트 PDF: {self.text_count}개")
        print(f"  - 스캔 PDF: {self.scan_count}개 (OCR 필요)")
        print(f"  - 기안자 확인: {self.drafter_count}개")
        print(f"  - 처리 오류: {self.error_count}개")

        # 성능 통계
        if self.processing_times:
            avg_time = sum(self.processing_times) / len(self.processing_times)
            print(f"\n⚡ 성능:")
            print(f"  - 평균 처리 시간: {avg_time:.3f}초/파일")
            print(f"  - 총 처리 시간: {sum(self.processing_times):.1f}초")

        # 기안자별 통계
        stats = self.manager.get_statistics()
        if stats['drafters']:
            print("\n👥 기안자별 문서 수:")
            for drafter, count in sorted(stats['drafters'].items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  - {drafter}: {count}개")

        print(f"\n💾 데이터베이스 파일: document_metadata.json")
        print(f"📝 {len(self.manager.metadata)}개 문서 정보 저장됨")

        # 캐시 통계 (MetadataManager에 있는 경우)
        if hasattr(self.manager, 'get_performance_stats'):
            perf_stats = self.manager.get_performance_stats()
            print(f"\n🔍 검색 성능:")
            print(f"  - 캐시 히트율: {perf_stats.get('cache_hit_rate', 0):.1f}%")

def main():
    """메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    import argparse
    parser = argparse.ArgumentParser(description='메타데이터 DB 구축')
    parser.add_argument('--batch-size', type=int, help='처리할 파일 수 제한')
    parser.add_argument('--docs-dir', type=str, default='docs', help='문서 디렉토리')
    args = parser.parse_args()

    start = time.time()

    builder = MetadataDBBuilder(batch_size=args.batch_size)
    text_count, scan_count, drafter_count = builder.build_database(Path(args.docs_dir))

    elapsed = time.time() - start
    print(f"\n⏱️ 전체 처리 시간: {elapsed:.1f}초")

    return 0

if __name__ == "__main__":
    exit(main())