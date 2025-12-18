#!/usr/bin/env python3
"""
벡터 DB 재구축 스크립트

임베딩 모델 변경 후 기존 벡터 DB를 새로운 모델로 재구축합니다.
- 기존: jhgan/ko-sroberta-multitask (768-dim)
- 신규: intfloat/multilingual-e5-large (1024-dim)
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_existing_db(db_dir: Path) -> Path:
    """기존 벡터 DB 백업

    Args:
        db_dir: 벡터 DB 디렉토리

    Returns:
        백업 디렉토리 경로
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db_dir.parent / f"db_backup_{timestamp}"

    logger.info(f"📦 기존 벡터 DB 백업 중...")
    logger.info(f"   원본: {db_dir}")
    logger.info(f"   백업: {backup_dir}")

    shutil.copytree(db_dir, backup_dir)
    logger.info(f"✅ 백업 완료!")

    return backup_dir


def rebuild_vector_db(data_dir: Path, force: bool = False):
    """벡터 DB 재구축

    Args:
        data_dir: 원본 문서 디렉토리
        force: 백업 없이 강제 재구축 (기본: False)
    """
    from rag_system.data.indexer import DocumentIndexer
    from rag_system.data.pdf_loader import PDFLoader

    db_dir = project_root / "docs" / "rag_system" / "db"

    logger.info("=" * 80)
    logger.info("벡터 DB 재구축 시작")
    logger.info("=" * 80)
    logger.info(f"문서 디렉토리: {data_dir}")
    logger.info(f"벡터 DB 디렉토리: {db_dir}")

    # 1. 백업 생성
    if db_dir.exists() and not force:
        backup_dir = backup_existing_db(db_dir)
        logger.info(f"\n💡 롤백이 필요한 경우:")
        logger.info(f"   rm -rf {db_dir}")
        logger.info(f"   mv {backup_dir} {db_dir}")

    # 2. 기존 DB 삭제
    if db_dir.exists():
        logger.info(f"\n🗑️  기존 벡터 DB 삭제 중...")
        shutil.rmtree(db_dir)
        logger.info(f"✅ 삭제 완료!")

    # 3. 새 벡터 DB 생성
    logger.info(f"\n🔨 새 벡터 DB 생성 중...")
    logger.info(f"   임베딩 모델: {os.getenv('EMBEDDING_MODEL', 'intfloat/multilingual-e5-large')}")

    # PDF 로더 초기화
    pdf_loader = PDFLoader()

    # 인덱서 초기화
    indexer = DocumentIndexer()

    # 4. 문서 로딩 및 인덱싱
    logger.info(f"\n📚 문서 로딩 및 인덱싱 시작...")

    pdf_files = list(data_dir.glob("**/*.pdf"))
    logger.info(f"   발견된 PDF 파일: {len(pdf_files)}개")

    if not pdf_files:
        logger.warning("⚠️  PDF 파일을 찾을 수 없습니다!")
        return

    # 문서 처리
    all_chunks = []
    for i, pdf_path in enumerate(pdf_files, 1):
        logger.info(f"   [{i}/{len(pdf_files)}] 처리 중: {pdf_path.name}")
        try:
            chunks = pdf_loader.load_pdf(str(pdf_path))
            all_chunks.extend(chunks)
            logger.info(f"      → {len(chunks)}개 청크 생성")
        except Exception as e:
            logger.error(f"      → 실패: {e}")

    logger.info(f"\n✅ 총 {len(all_chunks)}개 청크 생성됨")

    # 5. 벡터 DB 구축
    logger.info(f"\n🔧 벡터 DB 구축 중...")
    indexer.build_indexes(all_chunks)

    logger.info(f"\n✅ 벡터 DB 재구축 완료!")
    logger.info("=" * 80)

    # 6. 새 DB 정보 출력
    logger.info(f"\n📊 새 벡터 DB 정보:")
    for file in db_dir.glob("*"):
        size_mb = file.stat().st_size / 1024 / 1024
        logger.info(f"   - {file.name}: {size_mb:.1f} MB")


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="벡터 DB 재구축")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=project_root / "docs" / "rag_system" / "data",
        help="원본 문서 디렉토리 (기본: docs/rag_system/data)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="백업 없이 강제 재구축"
    )

    args = parser.parse_args()

    # 데이터 디렉토리 확인
    if not args.data_dir.exists():
        logger.error(f"❌ 데이터 디렉토리를 찾을 수 없습니다: {args.data_dir}")
        logger.error(f"💡 --data-dir 옵션으로 문서 디렉토리를 지정하세요.")
        sys.exit(1)

    try:
        rebuild_vector_db(args.data_dir, force=args.force)
    except Exception as e:
        logger.error(f"❌ 재구축 실패: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
