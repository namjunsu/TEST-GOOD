#!/usr/bin/env python3
"""
원자적 재색인 스크립트

임시 인덱스를 생성한 후 스왑하여 무중단 재색인을 구현합니다.

사용법:
    python scripts/reindex_atomic.py --source ./docs --tmp-index ./var/index_tmp --swap-to ./var/index
"""

import argparse
import logging
import os
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

# 전체 텍스트 추출 디렉토리 (환경변수 or 기본값)
EXTRACTED_DIR = Path(os.getenv("EXTRACTED_DIR", "data/extracted"))


def _load_fulltext_from_extracted(pdf_filename: str) -> str | None:
    """data/extracted에서 전체 텍스트 로드 (1순위)

    Args:
        pdf_filename: PDF 파일명 (예: "file.pdf")

    Returns:
        전체 텍스트 또는 None
    """
    stem = pdf_filename[:-4] if pdf_filename.lower().endswith(".pdf") else pdf_filename
    txt_path = EXTRACTED_DIR / f"{stem}.txt"

    if txt_path.exists():
        try:
            return txt_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"추출 파일 읽기 실패: {txt_path.name} - {e}")

    return None


def _load_text_from_metadata_db(filename: str, db_conn) -> str | None:
    """metadata.db에서 text_preview 로드 (2순위)

    Args:
        filename: PDF 파일명
        db_conn: SQLite 연결 객체

    Returns:
        text_preview 또는 None
    """
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT text_preview FROM documents WHERE filename = ?",
            (filename,)
        )
        result = cursor.fetchone()
        if result and result[0]:
            return result[0]
    except Exception as e:
        logger.debug(f"metadata.db 조회 실패: {filename} - {e}")

    return None


def reindex_bm25(source_dir: Path, output_path: Path) -> bool:
    """BM25 인덱스 재구축 (metadata.db 기반)"""
    try:
        from rag_system.bm25_store import BM25Store
        from modules.metadata_db import MetadataDB
        import pdfplumber

        logger.info("BM25 인덱스 재구축 시작...")

        # metadata.db에서 모든 문서 가져오기 (단일 진실원)
        db = MetadataDB()
        all_docs = []
        db_conn = None  # text_preview 조회용 연결 유지
        try:
            import sqlite3
            db_conn = db._get_conn()
            cursor = db_conn.cursor()
            cursor.execute("SELECT filename, date, drafter, category FROM documents")
            for row in cursor.fetchall():
                all_docs.append({
                    'filename': row[0],
                    'date': row[1],
                    'drafter': row[2],
                    'category': row[3]
                })
        except Exception as e:
            logger.error(f"metadata.db 읽기 실패: {e}")
            # 폴백: 파일 시스템 스캔
            pdf_files = list(source_dir.rglob("*.pdf"))
            all_docs = [{'filename': p.name, 'date': '', 'drafter': '', 'category': 'pdf'} for p in pdf_files]

        logger.info(f"대상 문서: {len(all_docs)}개 (metadata.db 기준)")

        texts = []
        metadatas = []
        fulltext_count = 0
        preview_count = 0  # metadata.db text_preview 사용
        fallback_count = 0
        missing_count = 0

        for i, doc_meta in enumerate(all_docs, 1):
            if i % 50 == 0:
                logger.info(f"진행: {i}/{len(all_docs)} (전체: {fulltext_count}, preview: {preview_count}, 폴백: {fallback_count}, 누락: {missing_count})")

            filename = doc_meta['filename']
            # 파일을 재귀적으로 검색 (서브디렉토리 포함)
            pdf_path = source_dir / filename
            if not pdf_path.exists():
                # 파일명만으로 검색 (서브디렉토리에서 찾기)
                search_results = list(source_dir.rglob(filename))
                if search_results:
                    pdf_path = search_results[0]

            try:
                # 1순위: data/extracted에서 전체 텍스트 로드
                text = _load_fulltext_from_extracted(filename)

                if text and len(text) >= 1000:  # 임계값: 1000자 이상
                    fulltext_count += 1
                else:
                    # 2순위: metadata.db에서 text_preview 로드 (임계값 상향: 1000자)
                    if db_conn and (not text or len(text) < 100):
                        preview_text = _load_text_from_metadata_db(filename, db_conn)
                        # preview가 충분히 길면 사용 (1000자 이상), 아니면 pdfplumber 폴백
                        if preview_text and len(preview_text) >= 1000:
                            text = preview_text
                            preview_count += 1
                        else:
                            # 3순위: pdfplumber로 추출 (폴백)
                            if text:
                                logger.warning(f"[short-text-fallback] {filename} - extracted={len(text)}자")

                            text = ""
                            if pdf_path.exists():
                                with pdfplumber.open(pdf_path) as pdf:
                                    for page in pdf.pages:  # 전체 페이지
                                        page_text = page.extract_text() or ""
                                        text += page_text + "\n"
                                fallback_count += 1
                            else:
                                logger.warning(f"⚠️ 파일 없음: {filename}")
                    else:
                        # text_preview도 없으면 pdfplumber 시도
                        if text:
                            logger.warning(f"[short-text-fallback] {filename} - extracted={len(text)}자")

                        text = ""
                        if pdf_path.exists():
                            with pdfplumber.open(pdf_path) as pdf:
                                for page in pdf.pages:  # 전체 페이지
                                    page_text = page.extract_text() or ""
                                    text += page_text + "\n"
                            fallback_count += 1
                        else:
                            logger.warning(f"⚠️ 파일 없음: {filename}")

                # 텍스트 없어도 파일명으로라도 검색 가능하게 (근본 해결)
                if not text.strip():
                    text = f"[파일명: {filename}] (텍스트 추출 실패)"
                    missing_count += 1

                texts.append(text)
                metadatas.append({
                    'filename': filename,
                    'path': str(pdf_path),
                    'id': f'doc_{i}',
                    'date': doc_meta.get('date', ''),
                    'drafter': doc_meta.get('drafter', ''),
                    'category': doc_meta.get('category', 'pdf')
                })
            except Exception as e:
                logger.warning(f"처리 실패: {filename} - {e}")
                # 실패해도 파일명으로 인덱싱
                texts.append(f"[파일명: {filename}] (처리 실패: {e})")
                metadatas.append({
                    'filename': filename,
                    'path': str(pdf_path),
                    'id': f'doc_{i}'
                })
                missing_count += 1

        logger.info(f"텍스트 추출 완료: {len(texts)}개")
        logger.info(f"  전체 텍스트 사용: {fulltext_count}개 ({fulltext_count*100//max(len(texts),1)}%)")
        logger.info(f"  metadata.db preview: {preview_count}개 ({preview_count*100//max(len(texts),1)}%)")
        logger.info(f"  폴백 (pdfplumber): {fallback_count}개 ({fallback_count*100//max(len(texts),1)}%)")
        logger.info(f"  텍스트 누락 (파일명만): {missing_count}개 ({missing_count*100//max(len(texts),1)}%)")

        if fallback_count > len(texts) * 0.05:  # 5% 초과
            logger.warning(f"⚠️ 폴백 비율 높음: {fallback_count*100//max(len(texts),1)}% (권장: ≤5%)")

        if missing_count > 0:
            logger.warning(f"⚠️ {missing_count}개 문서는 텍스트 추출 실패 (파일명으로만 검색 가능)")

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
