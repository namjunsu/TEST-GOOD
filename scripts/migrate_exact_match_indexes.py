#!/usr/bin/env python3
"""ExactMatchRetriever v2.0 인덱스 마이그레이션

2025-11-11

실행 항목:
1. padded_norm 컬럼 추가 (model_codes)
2. 인덱스 생성 (COLLATE NOCASE, padded_norm)
3. 기존 데이터 마이그레이션
4. 검증

Usage:
    python scripts/migrate_exact_match_indexes.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.metadata_db import MetadataDB
from app.core.logging import get_logger

logger = get_logger(__name__)


def check_column_exists(db: MetadataDB, table: str, column: str) -> bool:
    """컬럼 존재 여부 확인"""
    try:
        conn = db._get_conn()
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1].lower() for row in cursor.fetchall()]
        return column.lower() in columns
    except Exception as e:
        logger.error(f"컬럼 확인 실패: {e}")
        return False


def check_index_exists(db: MetadataDB, index_name: str) -> bool:
    """인덱스 존재 여부 확인"""
    try:
        conn = db._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"인덱스 확인 실패: {e}")
        return False


def check_table_exists(db: MetadataDB, table: str) -> bool:
    """테이블 존재 여부 확인"""
    try:
        conn = db._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"테이블 확인 실패: {e}")
        return False


def migrate_model_codes_padded_norm(db: MetadataDB, dry_run: bool = False) -> bool:
    """model_codes 테이블에 padded_norm 컬럼 추가 및 마이그레이션 (트랜잭션 안전)

    Args:
        db: MetadataDB 인스턴스
        dry_run: 시뮬레이션 모드

    Returns:
        성공 여부
    """
    conn = None
    try:
        conn = db._get_conn()

        # 0. 테이블 존재 확인
        if not check_table_exists(db, 'model_codes'):
            logger.warning("⚠️ model_codes 테이블 없음 - 스킵 (향후 ingest 시 자동 생성)")
            return True

        # 1. 컬럼 존재 확인
        if check_column_exists(db, 'model_codes', 'padded_norm'):
            logger.info("✓ padded_norm 컬럼 이미 존재")
            return True

        if dry_run:
            # Dry-run 모드: 트랜잭션 없이 시뮬레이션만
            logger.info("[DRY-RUN] ALTER TABLE model_codes ADD COLUMN padded_norm TEXT")
            cursor = conn.execute("SELECT COUNT(*) FROM model_codes WHERE norm_code IS NOT NULL")
            total_count = cursor.fetchone()[0]
            logger.info(f"[DRY-RUN] UPDATE model_codes SET padded_norm = ' ' || norm_code || ' ' ({total_count}건)")
            return True

        # === 트랜잭션 시작 ===
        logger.info("🔄 트랜잭션 시작...")
        conn.execute("BEGIN TRANSACTION")

        try:
            # 2. 컬럼 추가
            logger.info("padded_norm 컬럼 추가 중...")
            conn.execute("ALTER TABLE model_codes ADD COLUMN padded_norm TEXT")
            logger.info("✓ padded_norm 컬럼 추가 완료")

            # 3. 기존 데이터 마이그레이션
            cursor = conn.execute("SELECT COUNT(*) FROM model_codes WHERE norm_code IS NOT NULL")
            total_count = cursor.fetchone()[0]
            logger.info(f"기존 데이터 마이그레이션 중... ({total_count}건)")

            # 배치 업데이트 (norm_code → ' ' || norm_code || ' ')
            conn.execute("""
                UPDATE model_codes
                SET padded_norm = ' ' || norm_code || ' '
                WHERE norm_code IS NOT NULL
            """)

            # 검증
            cursor = conn.execute("SELECT COUNT(*) FROM model_codes WHERE padded_norm IS NOT NULL")
            migrated_count = cursor.fetchone()[0]

            if migrated_count != total_count:
                logger.error(f"❌ 마이그레이션 불일치: {migrated_count} != {total_count}")
                raise ValueError(f"Migration count mismatch: {migrated_count} != {total_count}")

            # === 트랜잭션 커밋 ===
            conn.commit()
            logger.info(f"✅ 트랜잭션 커밋 완료: {migrated_count}/{total_count}건")
            return True

        except Exception as inner_e:
            # === 트랜잭션 롤백 ===
            conn.rollback()
            logger.error(f"❌ 트랜잭션 롤백: {inner_e}", exc_info=True)
            raise

    except Exception as e:
        logger.error(f"❌ padded_norm 마이그레이션 실패: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                logger.info("🔄 안전 롤백 완료")
            except Exception:
                pass
        return False


def create_indexes(db: MetadataDB, dry_run: bool = False) -> bool:
    """인덱스 생성

    Args:
        db: MetadataDB 인스턴스
        dry_run: 시뮬레이션 모드

    Returns:
        성공 여부
    """
    try:
        conn = db._get_conn()

        indexes = [
            # model_codes 인덱스
            ("idx_model_codes_norm", "CREATE INDEX IF NOT EXISTS idx_model_codes_norm ON model_codes(norm_code)"),
            ("idx_model_codes_padded", "CREATE INDEX IF NOT EXISTS idx_model_codes_padded ON model_codes(padded_norm)"),
            ("idx_model_codes_doc", "CREATE INDEX IF NOT EXISTS idx_model_codes_doc ON model_codes(doc_id)"),
            # documents 인덱스 (COLLATE NOCASE)
            ("idx_documents_filename_nocase", "CREATE INDEX IF NOT EXISTS idx_documents_filename_nocase ON documents(filename COLLATE NOCASE)"),
        ]

        for index_name, create_sql in indexes:
            if check_index_exists(db, index_name):
                logger.info(f"✓ 인덱스 '{index_name}' 이미 존재")
                continue

            logger.info(f"인덱스 '{index_name}' 생성 중...")
            if not dry_run:
                conn.execute(create_sql)
                conn.commit()
                logger.info(f"✓ 인덱스 '{index_name}' 생성 완료")
            else:
                logger.info(f"[DRY-RUN] {create_sql}")

        return True

    except Exception as e:
        logger.error(f"❌ 인덱스 생성 실패: {e}", exc_info=True)
        return False


def verify_migration(db: MetadataDB) -> bool:
    """마이그레이션 검증

    Args:
        db: MetadataDB 인스턴스

    Returns:
        검증 성공 여부
    """
    try:
        conn = db._get_conn()

        logger.info("\n=== 마이그레이션 검증 ===")

        # 1. model_codes 테이블 검증 (존재 시만)
        if check_table_exists(db, 'model_codes'):
            # padded_norm 컬럼 존재 확인
            if not check_column_exists(db, 'model_codes', 'padded_norm'):
                logger.warning("⚠️ padded_norm 컬럼 없음 (향후 ingest 시 생성)")
            else:
                # 데이터 무결성 확인
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM model_codes
                    WHERE norm_code IS NOT NULL AND padded_norm IS NULL
                """)
                null_count = cursor.fetchone()[0]

                if null_count > 0:
                    logger.error(f"❌ padded_norm NULL 데이터 {null_count}건 발견")
                    return False
                else:
                    logger.info("✓ padded_norm 데이터 무결성 확인")

                # 샘플 쿼리 테스트
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM model_codes WHERE padded_norm LIKE '% XRN1620 %'
                """)
                sample_count = cursor.fetchone()[0]
                logger.info(f"✓ 샘플 쿼리 (padded_norm LIKE '% XRN1620 %'): {sample_count}건")
        else:
            logger.warning("⚠️ model_codes 테이블 없음 - 검증 스킵")

        # 2. 인덱스 확인
        required_indexes = {
            'idx_model_codes_norm': check_table_exists(db, 'model_codes'),
            'idx_model_codes_padded': check_table_exists(db, 'model_codes'),
            'idx_model_codes_doc': check_table_exists(db, 'model_codes'),
            'idx_documents_filename_nocase': True  # documents 테이블은 항상 존재
        }

        missing_indexes = [
            idx for idx, should_exist in required_indexes.items()
            if should_exist and not check_index_exists(db, idx)
        ]

        if missing_indexes:
            logger.error(f"❌ 누락된 인덱스: {missing_indexes}")
            return False
        else:
            logger.info("✓ 모든 필수 인덱스 존재")

        # 3. documents 테이블 샘플 쿼리 테스트
        cursor = conn.execute("""
            SELECT COUNT(*) FROM documents WHERE filename COLLATE NOCASE LIKE '%pdf%'
        """)
        sample_count2 = cursor.fetchone()[0]
        logger.info(f"✓ 샘플 쿼리 (filename COLLATE NOCASE LIKE '%pdf%'): {sample_count2}건")

        logger.info("\n✅ 마이그레이션 검증 완료")
        return True

    except Exception as e:
        logger.error(f"❌ 검증 실패: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="ExactMatchRetriever v2.0 인덱스 마이그레이션")
    parser.add_argument('--dry-run', action='store_true', help="시뮬레이션 모드 (실제 변경 없음)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ExactMatchRetriever v2.0 인덱스 마이그레이션")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("⚠️ DRY-RUN 모드 (시뮬레이션)")

    db = MetadataDB()

    # 1. padded_norm 컬럼 마이그레이션
    if not migrate_model_codes_padded_norm(db, dry_run=args.dry_run):
        logger.error("❌ 마이그레이션 실패")
        return 1

    # 2. 인덱스 생성
    if not create_indexes(db, dry_run=args.dry_run):
        logger.error("❌ 인덱스 생성 실패")
        return 1

    # 3. 검증 (실제 실행 시만)
    if not args.dry_run:
        if not verify_migration(db):
            logger.error("❌ 검증 실패")
            return 1

    logger.info("\n" + "=" * 60)
    if args.dry_run:
        logger.info("✅ DRY-RUN 완료 (실제 변경 없음)")
    else:
        logger.info("✅ 마이그레이션 완료")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
