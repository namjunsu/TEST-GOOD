#!/usr/bin/env python3
"""
고급 OCR 자동 처리 시스템

주요 기능:
- 스캔 PDF 자동 감지 및 분류
- 병렬 OCR 처리 with 진행률 표시
- 재시도 메커니즘 및 오류 복구
- 증분 처리 (이미 처리된 파일 건너뛰기)
- 상세한 통계 및 리포트 생성
- 메모리 효율적인 배치 처리
"""

import os
import sys
import json
import hashlib
import argparse
import psutil
import pickle
from pathlib import Path
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
import logging
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

# 프로젝트 경로 동적 설정
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    class tqdm:  # Fallback
        def __init__(self, iterable=None, total=None, desc="", **kwargs):
            self.iterable = iterable or []
            self.total = total or len(self.iterable)
            self.desc = desc
        def __iter__(self):
            return iter(self.iterable)
        def update(self, n=1):
            pass
        def close(self):
            pass

# 설정 상수
DEFAULT_CACHE_FILE = "ocr_cache.json"
DEFAULT_STATE_FILE = "ocr_state.pkl"
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_WORKERS = 4
MIN_TEXT_LENGTH = 50  # 스캔 PDF 판별 기준
MAX_RETRIES = 3
MEMORY_THRESHOLD_MB = 500
CACHE_VERSION = "2.0"

# 로깅 설정
class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR

def setup_logging(level: str = "INFO", log_file: Optional[Path] = None):
    """향상된 로깅 설정"""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )
    return logging.getLogger(__name__)

@dataclass
class PDFInfo:
    """PDF 파일 정보"""
    path: Path
    size_mb: float
    page_count: int
    text_length: int
    is_scanned: bool
    hash: str
    error: Optional[str] = None
    processing_time: float = 0.0
    ocr_success: bool = False
    extracted_text: str = ""

@dataclass
class OCRStats:
    """OCR 처리 통계"""
    total_files: int = 0
    scanned_files: int = 0
    processed_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_time: float = 0.0
    total_size_mb: float = 0.0
    errors: List[str] = field(default_factory=list)

    def get_summary(self) -> Dict:
        """통계 요약 반환"""
        return {
            "total_files": self.total_files,
            "scanned_files": self.scanned_files,
            "processed_files": self.processed_files,
            "success_rate": f"{(self.successful_files/self.processed_files*100):.1f}%" if self.processed_files else "0%",
            "average_time": f"{self.total_time/self.processed_files:.1f}s" if self.processed_files else "0s",
            "total_size_mb": f"{self.total_size_mb:.1f}MB",
            "errors_count": len(self.errors)
        }

class OCRProcessor:
    """향상된 OCR 처리기"""

    def __init__(self, cache_file: Path, state_file: Path,
                 batch_size: int = DEFAULT_BATCH_SIZE,
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 verbose: bool = True):
        self.cache_file = cache_file
        self.state_file = state_file
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.verbose = verbose
        self.logger = logging.getLogger(self.__class__.__name__)

        # OCR 프로세서 초기화
        self.ocr_processor = EnhancedOCRProcessor()

        # 캐시 및 상태 로드
        self.cache = self.load_cache()
        self.processed_hashes = self.load_state()

        # 통계
        self.stats = OCRStats()

    def load_cache(self) -> Dict:
        """기존 캐시 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if cache_data.get('version') == CACHE_VERSION:
                        self.logger.info(f"✅ 캐시 로드: {len(cache_data.get('ocr_texts', {}))}개 항목")
                        return cache_data
            except Exception as e:
                self.logger.warning(f"⚠️ 캐시 로드 실패: {e}")
        return {'version': CACHE_VERSION, 'ocr_texts': {}, 'metadata': {}}

    def load_state(self) -> Set[str]:
        """처리 상태 로드"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'rb') as f:
                    state = pickle.load(f)
                    self.logger.info(f"✅ 상태 로드: {len(state)}개 처리 완료")
                    return state
            except Exception as e:
                self.logger.warning(f"⚠️ 상태 로드 실패: {e}")
        return set()

    def save_cache(self):
        """캐시 저장"""
        self.cache['updated_at'] = datetime.now().isoformat()
        self.cache['stats'] = asdict(self.stats)

        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
        self.logger.info(f"💾 캐시 저장: {self.cache_file}")

    def save_state(self):
        """처리 상태 저장"""
        with open(self.state_file, 'wb') as f:
            pickle.dump(self.processed_hashes, f)
        self.logger.info(f"💾 상태 저장: {self.state_file}")

    def get_file_hash(self, file_path: Path) -> str:
        """파일 해시 계산"""
        hash_md5 = hashlib.md5()
        hash_md5.update(str(file_path).encode())
        hash_md5.update(str(file_path.stat().st_mtime).encode())
        return hash_md5.hexdigest()

    def analyze_pdf(self, pdf_path: Path) -> PDFInfo:
        """PDF 분석 및 스캔 여부 판별"""
        try:
            file_hash = self.get_file_hash(pdf_path)
            size_mb = pdf_path.stat().st_size / (1024 * 1024)

            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)

                # 처음 3페이지 검사
                total_text = ""
                for page in pdf.pages[:3]:
                    text = page.extract_text() or ""
                    total_text += text

                text_length = len(total_text.strip())
                is_scanned = text_length < MIN_TEXT_LENGTH

                return PDFInfo(
                    path=pdf_path,
                    size_mb=size_mb,
                    page_count=page_count,
                    text_length=text_length,
                    is_scanned=is_scanned,
                    hash=file_hash
                )

        except Exception as e:
            return PDFInfo(
                path=pdf_path,
                size_mb=0,
                page_count=0,
                text_length=0,
                is_scanned=True,  # 오류 시 스캔으로 간주
                hash=self.get_file_hash(pdf_path),
                error=str(e)
            )

    def identify_scanned_pdfs(self, docs_dir: Path, skip_processed: bool = True) -> List[PDFInfo]:
        """스캔 PDF 파일 식별 및 분석"""
        all_pdfs = list(docs_dir.glob('**/*.pdf'))
        self.stats.total_files = len(all_pdfs)

        self.logger.info(f"🔍 전체 {len(all_pdfs)}개 PDF 분석 시작...")

        pdf_infos = []
        scanned_count = 0

        # 진행률 표시
        with tqdm(total=len(all_pdfs), desc="PDF 분석", disable=not self.verbose) as pbar:
            for pdf_path in all_pdfs:
                info = self.analyze_pdf(pdf_path)

                # 이미 처리된 파일 건너뛰기
                if skip_processed and info.hash in self.processed_hashes:
                    self.stats.skipped_files += 1
                    pbar.update(1)
                    continue

                pdf_infos.append(info)
                if info.is_scanned:
                    scanned_count += 1

                pbar.update(1)
                pbar.set_postfix(scanned=scanned_count)

        self.stats.scanned_files = scanned_count

        scanned_pdfs = [info for info in pdf_infos if info.is_scanned]
        self.logger.info(f"📊 결과: {len(scanned_pdfs)}개 스캔 PDF 발견 ({scanned_count*100//len(all_pdfs)}%)")

        return scanned_pdfs

    def process_single_pdf(self, pdf_info: PDFInfo, retry_count: int = 0) -> PDFInfo:
        """단일 PDF OCR 처리 with 재시도"""
        start_time = time.time()

        try:
            if self.verbose:
                self.logger.info(f"🔄 OCR 처리: {pdf_info.path.name}")

            text, metadata = self.ocr_processor.extract_text_with_ocr(str(pdf_info.path))

            if metadata.get('ocr_performed') and len(text) > 100:
                pdf_info.ocr_success = True
                pdf_info.extracted_text = text
                pdf_info.processing_time = time.time() - start_time

                # 캐시 업데이트
                self.cache['ocr_texts'][str(pdf_info.path)] = text
                self.cache['metadata'][str(pdf_info.path)] = {
                    'hash': pdf_info.hash,
                    'processing_time': pdf_info.processing_time,
                    'text_length': len(text),
                    'timestamp': datetime.now().isoformat()
                }

                # 처리 완료 표시
                self.processed_hashes.add(pdf_info.hash)

            else:
                pdf_info.ocr_success = False
                pdf_info.error = "OCR 텍스트 부족"

        except Exception as e:
            pdf_info.error = str(e)
            pdf_info.ocr_success = False

            # 재시도
            if retry_count < MAX_RETRIES:
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self.process_single_pdf(pdf_info, retry_count + 1)

            self.logger.error(f"❌ OCR 실패 ({retry_count+1}/{MAX_RETRIES}): {pdf_info.path.name} - {e}")

        pdf_info.processing_time = time.time() - start_time
        return pdf_info

    def check_memory(self) -> bool:
        """메모리 사용량 체크"""
        memory = psutil.Process().memory_info().rss / 1024 / 1024
        if memory > MEMORY_THRESHOLD_MB:
            self.logger.warning(f"⚠️ 메모리 사용량 높음: {memory:.1f}MB")
            return False
        return True

    def process_batch(self, pdf_infos: List[PDFInfo]) -> List[PDFInfo]:
        """배치 단위 병렬 OCR 처리"""
        processed_infos = []

        # 메모리 체크
        if not self.check_memory():
            import gc
            gc.collect()

        # 병렬 처리 실행기 선택 (파일 크기에 따라)
        total_size_mb = sum(info.size_mb for info in pdf_infos)
        use_process = total_size_mb > 100  # 100MB 이상이면 프로세스 사용

        executor_class = ProcessPoolExecutor if use_process else ThreadPoolExecutor
        executor_name = "프로세스" if use_process else "스레드"

        with executor_class(max_workers=self.max_workers) as executor:
            if self.verbose:
                self.logger.info(f"🚀 {self.max_workers}개 {executor_name}로 병렬 처리 시작...")

            futures = {
                executor.submit(self.process_single_pdf, pdf_info): pdf_info
                for pdf_info in pdf_infos
            }

            # 진행률 표시
            with tqdm(total=len(futures), desc="OCR 처리", disable=not self.verbose) as pbar:
                for future in as_completed(futures):
                    pdf_info = futures[future]

                    try:
                        result = future.result(timeout=60)
                        processed_infos.append(result)

                        # 통계 업데이트
                        self.stats.processed_files += 1
                        if result.ocr_success:
                            self.stats.successful_files += 1
                            status = "✅"
                        else:
                            self.stats.failed_files += 1
                            status = "❌"
                            if result.error:
                                self.stats.errors.append(f"{result.path.name}: {result.error}")

                        self.stats.total_time += result.processing_time
                        self.stats.total_size_mb += result.size_mb

                        pbar.update(1)
                        pbar.set_postfix(
                            success=self.stats.successful_files,
                            failed=self.stats.failed_files
                        )

                        if self.verbose:
                            self.logger.info(
                                f"{status} {result.path.name}: "
                                f"{len(result.extracted_text)}자, "
                                f"{result.processing_time:.1f}초"
                            )

                    except Exception as e:
                        self.logger.error(f"❌ 처리 오류: {pdf_info.path.name} - {e}")
                        self.stats.failed_files += 1
                        self.stats.errors.append(f"{pdf_info.path.name}: {e}")
                        pbar.update(1)

        return processed_infos

    def process_all(self, pdf_infos: List[PDFInfo], save_interval: int = 10) -> List[PDFInfo]:
        """전체 PDF 배치 처리"""
        all_results = []
        total_batches = (len(pdf_infos) + self.batch_size - 1) // self.batch_size

        self.logger.info(f"📦 총 {total_batches}개 배치로 처리 시작...")

        for i in range(0, len(pdf_infos), self.batch_size):
            batch = pdf_infos[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1

            self.logger.info(f"\n🔄 배치 {batch_num}/{total_batches} 처리 중...")

            results = self.process_batch(batch)
            all_results.extend(results)

            # 주기적 저장
            if batch_num % save_interval == 0:
                self.save_cache()
                self.save_state()
                self.logger.info(f"💾 중간 저장 완료 (배치 {batch_num})")

        # 최종 저장
        self.save_cache()
        self.save_state()

        return all_results

    def generate_report(self, output_file: Optional[Path] = None) -> str:
        """처리 결과 리포트 생성"""
        stats = self.stats.get_summary()

        report = []
        report.append("\n" + "="*60)
        report.append("📊 OCR 처리 결과 리포트")
        report.append("="*60)
        report.append(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("📈 통계:")
        for key, value in stats.items():
            report.append(f"  - {key}: {value}")

        if self.stats.errors:
            report.append("\n❌ 오류 목록:")
            for error in self.stats.errors[:10]:  # 최대 10개만
                report.append(f"  - {error}")
            if len(self.stats.errors) > 10:
                report.append(f"  ... 외 {len(self.stats.errors)-10}개")

        report.append("\n💾 파일 정보:")
        report.append(f"  - 캐시 파일: {self.cache_file}")
        report.append(f"  - 상태 파일: {self.state_file}")

        report_text = "\n".join(report)

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            self.logger.info(f"📄 리포트 저장: {output_file}")

        return report_text

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description="AI-CHAT OCR 자동 처리 시스템",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  %(prog)s --batch-size 20 --workers 8  # 대량 처리
  %(prog)s --limit 10 --verbose        # 테스트 모드
  %(prog)s --skip-processed            # 증분 처리
  %(prog)s --report report.txt         # 리포트 생성
        """
    )

    parser.add_argument(
        "--docs-dir", type=Path, default=Path("docs"),
        help="문서 디렉토리 경로 (기본: docs)"
    )
    parser.add_argument(
        "--cache-file", type=Path, default=Path(DEFAULT_CACHE_FILE),
        help=f"캐시 파일 경로 (기본: {DEFAULT_CACHE_FILE})"
    )
    parser.add_argument(
        "--state-file", type=Path, default=Path(DEFAULT_STATE_FILE),
        help=f"상태 파일 경로 (기본: {DEFAULT_STATE_FILE})"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"배치 크기 (기본: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_MAX_WORKERS,
        help=f"워커 수 (기본: {DEFAULT_MAX_WORKERS})"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="처리할 최대 파일 수 (테스트용)"
    )
    parser.add_argument(
        "--skip-processed", action="store_true",
        help="이미 처리된 파일 건너뛰기"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="모든 파일 강제 재처리"
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="리포트 파일 경로"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="자세한 출력"
    )
    parser.add_argument(
        "--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO', help="로그 레벨"
    )
    parser.add_argument(
        "--log-file", type=Path, default=None,
        help="로그 파일 경로"
    )

    args = parser.parse_args()

    # 로깅 설정
    logger = setup_logging(args.log_level, args.log_file)

    print("\n" + "="*60)
    print("🤖 AI-CHAT OCR 자동 처리 시스템 v2.0")
    print("="*60)

    # OCR 프로세서 초기화
    processor = OCRProcessor(
        cache_file=args.cache_file,
        state_file=args.state_file,
        batch_size=args.batch_size,
        max_workers=args.workers,
        verbose=args.verbose
    )

    # 문서 디렉토리 확인
    if not args.docs_dir.exists():
        logger.error(f"❌ 문서 디렉토리를 찾을 수 없습니다: {args.docs_dir}")
        return 1

    # 1. 스캔 PDF 식별
    print(f"\n📁 디렉토리: {args.docs_dir}")

    skip_processed = args.skip_processed and not args.force
    scanned_pdfs = processor.identify_scanned_pdfs(args.docs_dir, skip_processed)

    if not scanned_pdfs:
        print("\n✅ 처리할 스캔 PDF가 없습니다!")
        if processor.stats.skipped_files > 0:
            print(f"   (이미 처리됨: {processor.stats.skipped_files}개)")
        return 0

    # 처리 대상 제한
    if args.limit:
        scanned_pdfs = scanned_pdfs[:args.limit]
        print(f"\n⚠️ 테스트 모드: {args.limit}개 파일만 처리")

    print(f"\n📋 처리 대상: {len(scanned_pdfs)}개 스캔 PDF")

    # 크기별 정렬 (작은 파일부터)
    scanned_pdfs.sort(key=lambda x: x.size_mb)

    # 예시 출력
    print(f"\n📄 처리할 파일 예시:")
    for info in scanned_pdfs[:5]:
        print(f"  - {info.path.name} ({info.size_mb:.1f}MB, {info.page_count}페이지)")
    if len(scanned_pdfs) > 5:
        print(f"  ... 외 {len(scanned_pdfs)-5}개")

    # 사용자 확인
    if not args.force and len(scanned_pdfs) > 50:
        response = input(f"\n⚠️ {len(scanned_pdfs)}개 파일을 처리합니다. 계속하시겠습니까? (y/n): ")
        if response.lower() != 'y':
            print("취소되었습니다.")
            return 0

    # 2. OCR 처리
    print(f"\n🚀 OCR 처리 시작...")
    start_time = time.time()

    try:
        results = processor.process_all(scanned_pdfs)

        elapsed = time.time() - start_time

        # 3. 결과 리포트
        print("\n" + "="*60)
        print("✅ OCR 처리 완료!")
        print("="*60)

        # 리포트 생성 및 출력
        report = processor.generate_report(args.report)
        print(report)

        # 성공 예시 출력
        successful_results = [r for r in results if r.ocr_success and r.extracted_text]
        if successful_results:
            example = successful_results[0]
            print(f"\n📄 OCR 성공 예시 ({example.path.name}):")
            text_preview = example.extracted_text[:300]
            print(f"{text_preview}..." if len(example.extracted_text) > 300 else text_preview)

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 중단됨")
        processor.save_cache()
        processor.save_state()
        print("💾 진행 상황이 저장되었습니다. 다시 실행하면 이어서 처리됩니다.")
        return 1

    except Exception as e:
        logger.error(f"❌ 처리 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())