#!/usr/bin/env python3
"""
벡터(임베딩) 인덱스 재빌드 스크립트

metadata.db의 문서들을 기반으로 FAISS 벡터 인덱스를 재생성합니다.

GPU 메모리가 부족한 경우 자동으로 CPU 모드로 전환합니다.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def check_gpu_memory() -> tuple[bool, float]:
    """GPU 메모리 여유 확인

    Returns:
        tuple[bool, float]: (사용 가능 여부, 여유 GB)
    """
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            free_mb = float(result.stdout.strip().split('\n')[0])
            free_gb = free_mb / 1024
            # 최소 2GB 여유 필요 (임베딩 모델 + 작업 메모리)
            has_enough = free_gb >= 2.0
            logger.info(f"GPU 여유 메모리: {free_gb:.2f}GB (필요: 2.0GB)")
            return has_enough, free_gb
    except Exception as e:
        logger.warning(f"GPU 메모리 확인 실패: {e}")

    return False, 0.0


def force_cpu_mode():
    """CPU 모드 강제 설정"""
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    logger.info("⚙️  CPU 모드로 전환됨 (GPU 메모리 부족)")


def rebuild_vector_index():
    """벡터 인덱스 재빌드"""

    # GPU 메모리 체크 및 자동 CPU 모드 전환
    if "CUDA_VISIBLE_DEVICES" not in os.environ:
        has_gpu_memory, free_gb = check_gpu_memory()
        if not has_gpu_memory:
            force_cpu_mode()

    # 경로 설정
    index_path = os.getenv("VECTOR_INDEX_PATH", "data/vector_index")
    db_path = os.getenv("METADB_PATH", "metadata.db")

    logger.info(f"DB 경로: {db_path}")
    logger.info(f"인덱스 경로: {index_path}")

    # DB에서 문서 로드
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, filename, text_preview
        FROM documents
        WHERE text_preview IS NOT NULL AND text_preview != ''
    """)
    rows = cursor.fetchall()
    conn.close()

    logger.info(f"{len(rows)}개 문서 로드됨")

    if not rows:
        logger.warning("문서가 없습니다. 인덱스를 생성하지 않습니다.")
        return False

    # VectorStore 및 Chunk 임포트
    from app.rag.chunking import Chunk
    from app.rag.embeddings import VectorStore

    # 기존 인덱스 삭제
    index_path_obj = Path(index_path)
    if index_path_obj.exists():
        import shutil
        shutil.rmtree(index_path_obj)
        logger.info("기존 인덱스 삭제됨")

    # VectorStore 초기화
    vector_store = VectorStore(index_path=index_path)
    vector_store.clear()

    # 청크 생성 (문서당 하나의 청크로 단순화)
    chunks = []
    for row in rows:
        doc_id = row["filename"]
        text = row["text_preview"] or ""

        if len(text) < 50:  # 너무 짧은 문서 스킵
            continue

        chunk = Chunk(
            doc_id=doc_id,
            chunk_id=f"{doc_id}_0",
            text=text[:5000],  # 최대 5000자
            chunk_index=0,
            start_char=0,
            end_char=min(len(text), 5000),
            metadata={"filename": doc_id},
        )
        chunks.append(chunk)

    logger.info(f"{len(chunks)}개 청크 생성됨")

    if not chunks:
        logger.warning("유효한 청크가 없습니다.")
        return False

    # 배치로 임베딩 및 저장
    batch_size = 32
    total_added = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        added = vector_store.add_chunks(batch, show_progress=False)
        total_added += added
        logger.info(f"진행: {min(i + batch_size, len(chunks))}/{len(chunks)} ({total_added}개 추가됨)")

    # 저장
    vector_store.save()

    logger.info(f"벡터 인덱스 생성 완료: {total_added}개 청크")

    return True


if __name__ == "__main__":
    try:
        success = rebuild_vector_index()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"인덱싱 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
