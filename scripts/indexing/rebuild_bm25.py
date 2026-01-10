#!/usr/bin/env python3
"""
BM25 인덱스 재빌드 스크립트

metadata.db의 문서들을 기반으로 BM25 인덱스를 재생성합니다.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from rag_system.active.bm25_store import BM25Store

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def rebuild_bm25_index():
    """BM25 인덱스 재빌드 (전문 텍스트 기반)

    개선사항:
    - text_preview 대신 data/extracted/*.txt 파일의 전문 사용
    - 전문이 없으면 text_preview로 폴백
    """

    # 경로 설정
    index_path = os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
    db_path = os.getenv("METADB_PATH", "metadata.db")
    extracted_dir = Path(os.getenv("EXTRACTED_DIR", "data/extracted"))

    logger.info(f"📂 DB 경로: {db_path}")
    logger.info(f"📂 인덱스 경로: {index_path}")
    logger.info(f"📂 추출 텍스트 디렉토리: {extracted_dir}")

    # DB에서 문서 로드
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, filename, text_preview, year, drafter
        FROM documents
    """)
    rows = cursor.fetchall()
    conn.close()

    logger.info(f"📄 {len(rows)}개 문서 로드됨")

    if not rows:
        logger.warning("⚠️ 문서가 없습니다. 인덱스를 생성하지 않습니다.")
        return False

    # 문서 포맷팅
    documents = []
    metadata_list = []
    full_text_count = 0
    fallback_count = 0

    for row in rows:
        doc_id, filename, text_preview, year, drafter = row

        # 1순위: data/extracted/*.txt 파일에서 전문 로드
        extracted_file = extracted_dir / filename.replace(".pdf", ".txt")

        if extracted_file.exists():
            try:
                full_text = extracted_file.read_text(encoding="utf-8")
                if full_text.strip():
                    documents.append(full_text)
                    full_text_count += 1
                else:
                    # 빈 파일이면 text_preview 사용
                    documents.append(text_preview or "")
                    fallback_count += 1
            except Exception as e:
                logger.warning(f"⚠️ 전문 로드 실패 ({filename}): {e}")
                documents.append(text_preview or "")
                fallback_count += 1
        else:
            # 전문 파일이 없으면 text_preview 사용
            documents.append(text_preview or "")
            fallback_count += 1

        metadata_list.append({
            "id": doc_id,  # BM25Store._resolve_doc_id()가 "id" 필드를 요구
            "filename": filename,
            "year": year,
            "drafter": drafter,
        })

    logger.info(f"📊 전문 사용: {full_text_count}개, text_preview 폴백: {fallback_count}개")

    # BM25 인덱스 생성
    logger.info("🔨 BM25 인덱스 생성 중...")

    # 인덱스 디렉토리 생성
    index_path_obj = Path(index_path)
    index_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # 기존 인덱스 삭제 (재빌드이므로 초기화 필요)
    if index_path_obj.exists():
        index_path_obj.unlink()
        logger.info("🗑️ 기존 인덱스 삭제됨")

    # BM25Store로 인덱싱 (빈 인덱스에서 시작)
    bm25_store = BM25Store(index_path=index_path)
    bm25_store.add_documents(documents, metadata_list)
    bm25_store.save_index()

    logger.info(f"✅ BM25 인덱스 생성 완료: {len(documents)}개 문서")

    return True


if __name__ == "__main__":
    try:
        success = rebuild_bm25_index()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ 인덱싱 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
