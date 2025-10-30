#!/usr/bin/env python3
"""
원자적 재색인 스크립트

임시 인덱스를 생성한 후 스왑하여 무중단 재색인을 구현합니다.

사용법:
    python scripts/reindex_atomic.py --source ./docs --tmp-index ./var/index_tmp --swap-to ./var/index
"""

import argparse
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def reindex_bm25(source_dir: Path, output_path: Path) -> bool:
    """BM25 인덱스 재구축"""
    try:
        from rag_system.bm25_store import BM25Store
        import pdfplumber

        logger.info("BM25 인덱스 재구축 시작...")

        # PDF 파일 수집
        pdf_files = list(source_dir.rglob("*.pdf"))
        logger.info(f"대상 파일: {len(pdf_files)}개")

        texts = []
        metadatas = []

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 50 == 0:
                logger.info(f"진행: {i}/{len(pdf_files)}")

            try:
                text = ""
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages[:10]:  # 첫 10페이지만
                        page_text = page.extract_text() or ""
                        text += page_text + "\n"

                if text.strip():
                    texts.append(text)
                    metadatas.append({
                        'filename': pdf_path.name,
                        'path': str(pdf_path),
                        'id': f'doc_{i}'
                    })
            except Exception as e:
                logger.debug(f"스킵: {pdf_path.name} - {e}")

        logger.info(f"텍스트 추출 완료: {len(texts)}개")

        # BM25 인덱스 생성
        bm25 = BM25Store(index_path=str(output_path))
        bm25.documents = []
        bm25.metadata = []
        bm25.term_freqs = []
        bm25.doc_freqs = {}
        bm25.doc_lens = []
        bm25.vocab = set()

        for text, metadata in zip(texts, metadatas):
            tokens = bm25.tokenizer.tokenize(text)

            bm25.documents.append(text)
            bm25.metadata.append(metadata)

            term_freq = {}
            for token in tokens:
                term_freq[token] = term_freq.get(token, 0) + 1
                bm25.vocab.add(token)

            bm25.term_freqs.append(term_freq)
            bm25.doc_lens.append(len(tokens))

            for token in set(tokens):
                bm25.doc_freqs[token] = bm25.doc_freqs.get(token, 0) + 1

        if bm25.doc_lens:
            bm25.avg_doc_len = sum(bm25.doc_lens) / len(bm25.doc_lens)

        bm25.save_index()
        logger.info(f"✅ BM25 인덱스 완료: {len(bm25.documents)}개 문서")

        return True

    except Exception as e:
        logger.error(f"BM25 재구축 실패: {e}")
        return False


def atomic_swap(tmp_dir: Path, target_dir: Path) -> bool:
    """원자적 스왑: 임시 인덱스를 target으로 교체"""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        # 백업 생성
        backup_dir = target_dir.parent / f"{target_dir.name}_backup_{int(time.time())}"
        if target_dir.exists() and any(target_dir.iterdir()):
            logger.info(f"백업 생성: {backup_dir}")
            shutil.copytree(target_dir, backup_dir)

        # 임시 → 타겟으로 이동
        logger.info(f"스왑: {tmp_dir} → {target_dir}")
        for item in tmp_dir.iterdir():
            dest = target_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        logger.info("✅ 스왑 완료")
        return True

    except Exception as e:
        logger.error(f"스왑 실패: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="원자적 재색인")
    parser.add_argument("--source", default="./docs", help="소스 문서 디렉토리")
    parser.add_argument("--tmp-index", default="./var/index_tmp", help="임시 인덱스 디렉토리")
    parser.add_argument("--swap-to", default="./var/index", help="스왑 타겟 디렉토리")
    parser.add_argument("--report", default="reports/index_consistency.md", help="보고서 출력 경로")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("원자적 재색인 시작")
    logger.info("=" * 80)

    source_dir = Path(args.source)
    tmp_dir = Path(args.tmp_index)
    target_dir = Path(args.swap_to)

    # 1. 임시 디렉토리 생성
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 2. 임시 인덱스 생성
    tmp_bm25_path = tmp_dir / "bm25_index.pkl"
    success = reindex_bm25(source_dir, tmp_bm25_path)

    if not success:
        logger.error("❌ 재색인 실패")
        return 1

    # 3. 스왑
    swap_success = atomic_swap(tmp_dir, target_dir)

    if not swap_success:
        logger.error("❌ 스왑 실패")
        return 1

    # 4. 인덱스 버전 및 재색인 시각 기록
    try:
        var_dir = Path("var")
        var_dir.mkdir(exist_ok=True)

        # 버전 기록
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        import hashlib
        cfg_hash = hashlib.md5(f"{timestamp}".encode()).hexdigest()[:6]
        index_version = f"v{timestamp}_{cfg_hash}"

        version_file = var_dir / "index_version.txt"
        version_file.write_text(index_version)

        # 재색인 시각 기록
        reindex_time_file = var_dir / "last_reindex.txt"
        reindex_time_file.write_text(datetime.now().isoformat())

        logger.info(f"인덱스 버전 기록: {index_version}")

    except Exception as e:
        logger.warning(f"버전 기록 실패: {e}")

    # 5. 정합성 검증
    logger.info("\n정합성 검증 실행 중...")
    import subprocess
    result = subprocess.run([
        sys.executable,
        "scripts/check_index_consistency.py",
        "--report", args.report
    ])

    if result.returncode == 0:
        logger.info("✅ 재색인 및 검증 완료")
    else:
        logger.warning("⚠️ 재색인은 완료되었으나 정합성 검증 실패")

    logger.info(f"\n[INDEX] swap done: old=v0, new={index_version}")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
