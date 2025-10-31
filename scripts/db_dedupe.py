#!/usr/bin/env python3
"""
데이터베이스 중복 제거 도구
content_hash 기준으로 중복 문서를 탐지하고 제거합니다.
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def find_duplicates(db: MetadataDB):
    """중복 문서 탐지 (content_hash 기준)"""
    conn = db._get_conn()
    cursor = conn.execute(
        """
        SELECT id, filename, content_hash, created_at
        FROM documents
        WHERE content_hash IS NOT NULL
        ORDER BY content_hash, created_at
        """
    )

    rows = cursor.fetchall()
    hash_groups = {}

    for row in rows:
        doc_id, filename, content_hash, created_at = row
        if content_hash not in hash_groups:
            hash_groups[content_hash] = []
        hash_groups[content_hash].append({
            "id": doc_id,
            "filename": filename,
            "created_at": created_at
        })

    # 중복 그룹 필터링 (2개 이상)
    duplicates = {k: v for k, v in hash_groups.items() if len(v) > 1}
    return duplicates


def remove_duplicates(db: MetadataDB, duplicates: dict, dry_run: bool = True):
    """중복 문서 제거 (가장 오래된 것 유지)"""
    removed = []

    for content_hash, docs in duplicates.items():
        # 가장 오래된 문서 유지
        docs_sorted = sorted(docs, key=lambda x: x["created_at"])
        keep = docs_sorted[0]
        to_remove = docs_sorted[1:]

        logger.info(f"중복 그룹 (content_hash: {content_hash[:8]}...)")
        logger.info(f"  유지: {keep['filename']} (id={keep['id']}, created={keep['created_at']})")

        for doc in to_remove:
            logger.info(f"  삭제: {doc['filename']} (id={doc['id']}, created={doc['created_at']})")
            removed.append(doc)

            if not dry_run:
                conn = db._get_conn()
                conn.execute("DELETE FROM documents WHERE id = ?", (doc["id"],))
                conn.commit()
                logger.info("    ✓ 삭제됨")

    return removed


def generate_report(duplicates: dict, removed: list, output_path: str):
    """보고서 생성"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 데이터베이스 중복 제거 보고서\n\n")
        f.write(f"중복 그룹 수: {len(duplicates)}\n")
        f.write(f"제거된 문서 수: {len(removed)}\n\n")

        if duplicates:
            f.write("## 중복 그룹 상세\n\n")
            for content_hash, docs in duplicates.items():
                f.write(f"### content_hash: {content_hash[:16]}...\n\n")
                for doc in docs:
                    f.write(f"- {doc['filename']} (id={doc['id']}, created={doc['created_at']})\n")
                f.write("\n")

        if removed:
            f.write("## 제거된 문서\n\n")
            for doc in removed:
                f.write(f"- {doc['filename']} (id={doc['id']})\n")

    logger.info(f"보고서 생성: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="데이터베이스 중복 제거")
    parser.add_argument("--db", default="metadata.db", help="DB 파일 경로")
    parser.add_argument("--report", default="reports/db_dedupe_report.md", help="보고서 출력 경로")
    parser.add_argument("--dry-run", action="store_true", help="드라이런 (실제 삭제 안 함)")
    parser.add_argument("--execute", action="store_true", help="실제 삭제 실행")

    args = parser.parse_args()

    # 기본값은 dry-run
    dry_run = not args.execute

    if dry_run:
        logger.warning("⚠️ DRY-RUN 모드 (실제 삭제 안 함). --execute 플래그로 실행하세요.")

    # DB 연결
    db = MetadataDB(db_path=args.db)

    # 중복 탐지
    logger.info("중복 문서 탐지 중...")
    duplicates = find_duplicates(db)

    if not duplicates:
        logger.info("✅ 중복 문서 없음")
        return

    logger.info(f"발견된 중복 그룹: {len(duplicates)}개")

    # 중복 제거
    removed = remove_duplicates(db, duplicates, dry_run=dry_run)

    # 보고서 생성
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    generate_report(duplicates, removed, args.report)

    if dry_run:
        logger.info("ℹ️ 드라이런 완료. --execute 플래그로 실제 삭제 가능")
    else:
        logger.info(f"✅ 중복 제거 완료: {len(removed)}개 문서 삭제")


if __name__ == "__main__":
    main()
