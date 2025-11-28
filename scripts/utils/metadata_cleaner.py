#!/usr/bin/env python3
"""
metadata.db Cleaner - Stale 레코드 정리 유틸리티
물리적으로 존재하지 않는 파일의 메타데이터를 정리합니다.
"""

import sqlite3
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


def purge_missing_files_from_metadata(
    db_path: str = "metadata.db",
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """metadata.db에서 물리적으로 존재하지 않는 파일 레코드 삭제

    Args:
        db_path: metadata.db 경로
        dry_run: True면 실제로 삭제하지 않고 대상만 출력

    Returns:
        (삭제된 레코드 수, 삭제된 파일명 리스트)
    """
    if not Path(db_path).exists():
        logger.error(f"DB 파일이 존재하지 않습니다: {db_path}")
        return 0, []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 모든 문서 조회
        cursor.execute("""
            SELECT id, filename, path
            FROM documents
            WHERE LOWER(filename) LIKE '%.pdf' OR LOWER(filename) LIKE '%.txt'
        """)

        all_docs = cursor.fetchall()
        stale_ids = []
        stale_filenames = []

        # 파일 존재 여부 확인
        for row in all_docs:
            doc_id = row["id"]
            filename = row["filename"]
            path = row["path"]

            # 경로 확인 (path 필드가 있으면 사용, 없으면 docs/ + filename)
            if path:
                file_path = Path(path)
            else:
                file_path = Path("docs") / filename

            # 파일이 존재하지 않으면 stale 목록에 추가
            if not file_path.exists():
                stale_ids.append(doc_id)
                stale_filenames.append(filename)

        # 결과 로깅
        logger.info(f"전체 문서: {len(all_docs)}개")
        logger.info(f"Stale 레코드: {len(stale_ids)}개")

        if dry_run:
            logger.info("DRY RUN 모드 - 삭제하지 않음")
            for filename in stale_filenames[:10]:  # 처음 10개만 출력
                logger.info(f"  - {filename}")
            if len(stale_filenames) > 10:
                logger.info(f"  ... 외 {len(stale_filenames) - 10}개")
        # 실제 삭제 실행
        elif stale_ids:
            # documents 테이블에서 삭제 (트리거로 documents_fts도 자동 삭제됨)
            placeholders = ",".join(["?"] * len(stale_ids))
            cursor.execute(f"""
                    DELETE FROM documents
                    WHERE id IN ({placeholders})
                """, stale_ids)

            conn.commit()
            logger.info(f"✅ {len(stale_ids)}개 stale 레코드 삭제 완료")

            # 삭제된 파일명 로깅 (처음 10개만)
            for filename in stale_filenames[:10]:
                logger.info(f"  - {filename}")
            if len(stale_filenames) > 10:
                logger.info(f"  ... 외 {len(stale_filenames) - 10}개")

        conn.close()
        return len(stale_ids), stale_filenames

    except Exception as e:
        logger.error(f"metadata.db 정리 실패: {e}")
        return 0, []


def verify_sync(metadata_db: str = "metadata.db", index_db: str = "everything_index.db") -> dict:
    """두 DB 간의 동기화 상태 확인

    Args:
        metadata_db: metadata.db 경로
        index_db: everything_index.db 경로

    Returns:
        동기화 상태 딕셔너리
    """
    result = {
        "metadata_count": 0,
        "index_count": 0,
        "diff": 0,
        "missing_in_index": [],
        "stale_in_index": [],
        "synced": False,
    }

    try:
        # metadata.db 카운트
        metadata_conn = sqlite3.connect(metadata_db)
        metadata_conn.row_factory = sqlite3.Row
        cursor = metadata_conn.execute("""
            SELECT COUNT(DISTINCT filename) as count
            FROM documents
            WHERE LOWER(filename) LIKE '%.pdf' OR LOWER(filename) LIKE '%.txt'
        """)
        result["metadata_count"] = cursor.fetchone()["count"]

        # 모든 파일명 가져오기
        cursor = metadata_conn.execute("""
            SELECT DISTINCT filename
            FROM documents
            WHERE LOWER(filename) LIKE '%.pdf' OR LOWER(filename) LIKE '%.txt'
        """)
        metadata_files = {row["filename"] for row in cursor.fetchall()}
        metadata_conn.close()

        # everything_index.db 카운트
        if Path(index_db).exists():
            index_conn = sqlite3.connect(index_db)
            index_conn.row_factory = sqlite3.Row
            cursor = index_conn.execute("""
                SELECT COUNT(DISTINCT filename) as count
                FROM files
            """)
            result["index_count"] = cursor.fetchone()["count"]

            # 모든 파일명 가져오기
            cursor = index_conn.execute("""
                SELECT DISTINCT filename
                FROM files
            """)
            index_files = {row["filename"] for row in cursor.fetchall()}
            index_conn.close()

            # 차이 계산
            result["missing_in_index"] = list(metadata_files - index_files)
            result["stale_in_index"] = list(index_files - metadata_files)

        result["diff"] = result["metadata_count"] - result["index_count"]
        result["synced"] = (result["diff"] == 0 and
                           len(result["missing_in_index"]) == 0 and
                           len(result["stale_in_index"]) == 0)

        return result

    except Exception as e:
        logger.error(f"동기화 확인 실패: {e}")
        return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="metadata.db Cleaner")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상만 출력")
    parser.add_argument("--verify", action="store_true", help="동기화 상태만 확인")
    parser.add_argument("--db", default="metadata.db", help="DB 경로")

    args = parser.parse_args()

    if args.verify:
        print("🔍 동기화 상태 확인 중...")
        result = verify_sync(args.db)
        print("\n📊 동기화 상태:")
        print(f"  - metadata.db: {result['metadata_count']}개")
        print(f"  - everything_index.db: {result['index_count']}개")
        print(f"  - 차이: {result['diff']}개")
        print(f"  - 동기화 상태: {'✅ 정상' if result['synced'] else '⚠️ 불일치'}")

        if result["missing_in_index"]:
            print(f"\n⚠️ 라이브러리에만 존재 (인덱스에 없음): {len(result['missing_in_index'])}개")
            for filename in result["missing_in_index"][:5]:
                print(f"  - {filename}")

        if result["stale_in_index"]:
            print(f"\n⚠️ 인덱스에만 존재 (라이브러리에 없음): {len(result['stale_in_index'])}개")
            for filename in result["stale_in_index"][:5]:
                print(f"  - {filename}")
    else:
        print(f"🧹 metadata.db 정리 시작... (DRY_RUN={args.dry_run})")
        count, filenames = purge_missing_files_from_metadata(args.db, args.dry_run)

        if args.dry_run:
            print(f"\n📋 삭제 대상: {count}개 (실제로 삭제하지 않음)")
            print("실제로 삭제하려면 --dry-run 옵션 없이 실행하세요.")
        else:
            print(f"\n✅ 정리 완료: {count}개 stale 레코드 삭제")
