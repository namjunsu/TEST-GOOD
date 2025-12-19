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
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from rag_system.active.bm25_store import BM25Store

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def rebuild_bm25_index():
    """BM25 인덱스 재빌드"""

    # 경로 설정
    index_path = os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
    db_path = os.getenv("METADB_PATH", "metadata.db")

    logger.info(f"📂 DB 경로: {db_path}")
    logger.info(f"📂 인덱스 경로: {index_path}")

    # DB에서 문서 로드
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, filename, content, year, drafter
        FROM documents
        WHERE content IS NOT NULL AND content != ''
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

    for row in rows:
        doc_id, filename, content, year, drafter = row
        documents.append(content)
        metadata_list.append({
            "doc_id": doc_id,
            "filename": filename,
            "year": year,
            "drafter": drafter,
        })

    # BM25 인덱스 생성
    logger.info("🔨 BM25 인덱스 생성 중...")

    # 인덱스 디렉토리 생성
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)

    # BM25Store로 인덱싱
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
