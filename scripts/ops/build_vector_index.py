#!/usr/bin/env python3
"""벡터 인덱스 빌드 스크립트

MetadataDB의 문서를 청킹하고 벡터 인덱스를 생성합니다.

사용법:
    python scripts/ops/build_vector_index.py [--chunk-size 512] [--overlap 128]
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.chunking import Chunk, TextChunker
from app.rag.embeddings import get_vector_store

logger = get_logger(__name__)


def build_index(
    chunk_size: int = 512,
    overlap: int = 128,
    batch_size: int = 32,
    force_rebuild: bool = False,
) -> dict:
    """벡터 인덱스 빌드

    Args:
        chunk_size: 청크 크기
        overlap: 오버랩 크기
        batch_size: 임베딩 배치 크기
        force_rebuild: 기존 인덱스 삭제 후 재빌드

    Returns:
        빌드 통계
    """
    logger.info("🚀 벡터 인덱스 빌드 시작")

    # 1. MetadataDB에서 문서 로드
    logger.info("📄 문서 로딩 중...")
    db = MetadataDB()

    # 전체 문서 수 확인
    total_count = db.count_documents()
    logger.info(f"📄 총 {total_count}개 문서 존재")

    # 모든 문서 로드 (limit을 충분히 크게)
    documents = db.search_documents(limit=total_count + 100)

    if not documents:
        logger.warning("⚠️ 인덱싱할 문서가 없습니다")
        return {"status": "no_documents"}

    logger.info(f"📄 {len(documents)}개 문서 로드됨")

    # 2. 텍스트 청킹
    logger.info(f"✂️ 청킹 중... (size={chunk_size}, overlap={overlap})")
    chunker = TextChunker(
        chunk_size=chunk_size,
        overlap=overlap,
    )

    all_chunks: list[Chunk] = []
    for doc in documents:
        filename = doc.get("filename", "")
        text = doc.get("text_preview", "")

        if not text or len(text.strip()) < 50:
            logger.debug(f"⏭️ {filename}: 텍스트 너무 짧음, 스킵")
            continue

        # 문서 메타데이터
        metadata = {
            "title": doc.get("title", ""),
            "drafter": doc.get("drafter", ""),
            "draft_date": doc.get("draft_date", ""),
            "page_count": doc.get("page_count", 1),
        }

        chunks = chunker.chunk(text, filename, metadata)
        all_chunks.extend(chunks)

    logger.info(f"✂️ 총 {len(all_chunks)}개 청크 생성됨")

    if not all_chunks:
        logger.warning("⚠️ 생성된 청크가 없습니다")
        return {"status": "no_chunks"}

    # 3. 벡터 스토어에 추가
    logger.info("🔢 벡터 인덱싱 중...")
    vector_store = get_vector_store()

    if force_rebuild:
        logger.info("🗑️ 기존 인덱스 삭제")
        vector_store.clear()

    added = vector_store.add_chunks(
        chunks=all_chunks,
        batch_size=batch_size,
        show_progress=True,
    )

    # 4. 저장
    vector_store.save()

    stats = vector_store.get_stats()
    logger.info(
        f"✅ 벡터 인덱스 빌드 완료!\n"
        f"   - 문서: {len(documents)}개\n"
        f"   - 청크: {added}개\n"
        f"   - 벡터 차원: {stats['dimension']}\n"
        f"   - 저장 경로: {stats['index_path']}"
    )

    return {
        "status": "success",
        "documents": len(documents),
        "chunks": added,
        "dimension": stats["dimension"],
        "index_path": stats["index_path"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="벡터 인덱스 빌드",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="청크 크기 (문자 수)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=128,
        help="오버랩 크기 (문자 수)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="임베딩 배치 크기",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 인덱스 삭제 후 재빌드",
    )

    args = parser.parse_args()

    try:
        result = build_index(
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            batch_size=args.batch_size,
            force_rebuild=args.force,
        )

        if result["status"] == "success":
            print(f"\n✅ 빌드 완료: {result['chunks']}개 청크 인덱싱됨")
            sys.exit(0)
        else:
            print(f"\n⚠️ 빌드 실패: {result['status']}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ 빌드 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
