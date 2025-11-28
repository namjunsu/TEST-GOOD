#!/usr/bin/env python3
"""
자동 인덱싱 감시 시스템
docs/ 폴더에 신규 PDF가 추가되면 자동으로 인덱싱

사용법:
    python3 auto_index_watcher.py  # 계속 실행 (백그라운드 권장)
"""

import hashlib
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/auto_indexer.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# 프로젝트 루트
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import pdfplumber
from rag_system.korean_vector_store import KoreanVectorStore

from rag_system.active.bm25_store import BM25Store


class AutoIndexWatcher:
    """자동 인덱싱 감시자"""

    def __init__(self, docs_dir: str = "docs", check_interval: int = 60):
        """
        Args:
            docs_dir: 감시할 문서 디렉토리
            check_interval: 체크 간격 (초)
        """
        self.docs_dir = Path(docs_dir)
        self.check_interval = check_interval

        # 이미 인덱싱된 파일 추적
        self.indexed_files: set[str] = set()
        self.file_hashes = {}  # 파일 해시 저장 (변경 감지용)

        # RAG 스토어 초기화
        self.bm25_store = None
        self.vector_store = None

        # 로그 디렉토리 생성
        Path("logs").mkdir(exist_ok=True)

    def _load_stores(self):
        """RAG 스토어 로드 (지연 로딩)"""
        if self.bm25_store is None:
            logger.info("BM25Store 로드 중...")
            self.bm25_store = BM25Store(index_path="var/index/bm25_index.pkl")

        if self.vector_store is None:
            logger.info("KoreanVectorStore 로드 중...")
            self.vector_store = KoreanVectorStore(
                index_path="var/index/korean_vector_index.faiss",
            )

    def _get_file_hash(self, file_path: Path) -> str:
        """파일 해시 계산 (변경 감지용)"""
        try:
            with Path(file_path).open("rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"해시 계산 실패 {file_path.name}: {e}")
            return ""

    def _scan_files(self) -> set[str]:
        """현재 존재하는 모든 PDF 파일 스캔"""
        pdf_files = set()
        for pdf_path in self.docs_dir.rglob("*.pdf"):
            pdf_files.add(str(pdf_path))
        return pdf_files

    def _index_new_file(self, pdf_path: Path) -> bool:
        """신규 파일 인덱싱"""
        try:
            logger.info(f"📄 신규 파일 인덱싱: {pdf_path.name}")

            # PDF 텍스트 추출
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:10]:  # 최대 10페이지
                    page_text = page.extract_text() or ""
                    text += page_text + "\n"

            if not text.strip():
                logger.warning(f"⚠️  텍스트 추출 실패: {pdf_path.name}")
                return False

            # RAG 스토어 로드
            self._load_stores()

            # 문서 ID 생성
            doc_id = f"doc_{hashlib.md5(str(pdf_path).encode()).hexdigest()[:12]}"

            # BM25 인덱스에 추가
            self.bm25_store.add_document(
                doc_id=doc_id,
                content=text,
                metadata={
                    "filename": pdf_path.name,
                    "path": str(pdf_path),
                    "indexed_at": datetime.now().isoformat(),
                },
            )

            # Vector 인덱스에 추가
            content_chunk = text[:5000]  # 최대 5000자
            self.vector_store.add_document(
                doc_id=doc_id,
                content=content_chunk,
                metadata={
                    "filename": pdf_path.name,
                    "path": str(pdf_path),
                    "indexed_at": datetime.now().isoformat(),
                },
            )

            # 인덱스 저장
            self.bm25_store.save_index()
            self.vector_store.save_index()

            # 추적에 추가
            self.indexed_files.add(str(pdf_path))
            self.file_hashes[str(pdf_path)] = self._get_file_hash(pdf_path)

            logger.info(f"✅ 인덱싱 완료: {pdf_path.name}")
            return True

        except Exception as e:
            logger.error(f"❌ 인덱싱 실패 {pdf_path.name}: {e}")
            return False

    def _check_for_changes(self):
        """신규/변경된 파일 체크 및 인덱싱"""
        current_files = self._scan_files()

        # 신규 파일 감지
        new_files = current_files - self.indexed_files

        if new_files:
            logger.info(f"🔍 신규 파일 {len(new_files)}개 발견")

            for file_path_str in new_files:
                file_path = Path(file_path_str)
                self._index_new_file(file_path)

        # 변경된 파일 감지 (선택적)
        for file_path_str in current_files & self.indexed_files:
            file_path = Path(file_path_str)
            current_hash = self._get_file_hash(file_path)

            if current_hash != self.file_hashes.get(file_path_str):
                logger.info(f"🔄 파일 변경 감지: {file_path.name}")
                self._index_new_file(file_path)

        # 삭제된 파일 감지 (로그만)
        deleted_files = self.indexed_files - current_files
        if deleted_files:
            logger.warning(f"🗑️  삭제된 파일 {len(deleted_files)}개 감지")
            for file_path_str in deleted_files:
                logger.warning(f"   - {Path(file_path_str).name}")
                self.indexed_files.remove(file_path_str)
                self.file_hashes.pop(file_path_str, None)

    def start(self):
        """감시 시작"""
        logger.info("🚀 자동 인덱싱 감시 시작")
        logger.info(f"📂 감시 디렉토리: {self.docs_dir}")
        logger.info(f"⏱️  체크 간격: {self.check_interval}초")
        logger.info("=" * 60)

        # 초기 파일 목록 로드
        logger.info("초기 파일 스캔 중...")
        self.indexed_files = self._scan_files()
        logger.info(f"📊 현재 파일: {len(self.indexed_files)}개")

        # 파일 해시 초기화
        for file_path_str in self.indexed_files:
            file_path = Path(file_path_str)
            self.file_hashes[file_path_str] = self._get_file_hash(file_path)

        # 감시 루프
        try:
            while True:
                self._check_for_changes()
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("\n⏹️  감시 중지됨")
        except Exception as e:
            logger.error(f"❌ 오류 발생: {e}")
            raise


def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="RAG 자동 인덱싱 감시")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="체크 간격 (초, 기본: 60)",
    )
    parser.add_argument(
        "--docs-dir",
        type=str,
        default="docs",
        help="감시할 문서 디렉토리 (기본: docs)",
    )

    args = parser.parse_args()

    watcher = AutoIndexWatcher(
        docs_dir=args.docs_dir,
        check_interval=args.interval,
    )

    watcher.start()


if __name__ == "__main__":
    main()
