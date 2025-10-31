#!/usr/bin/env python3
"""
데이터베이스 무결성 검증 도구
- 파일 존재 여부 검증
- content_hash 무결성 검증
- 임시 파일명 패턴 검증 (_1, _2 등)
- 메타데이터 필수 필드 검증
"""

import argparse
import hashlib
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """파일 SHA256 해시 계산"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_file_existence(db: MetadataDB):
    """파일 존재 여부 검증"""
    logger.info("파일 존재 여부 검증 중...")
    conn = db._get_conn()
    cursor = conn.execute("SELECT id, filename, path FROM documents")

    missing_files = []
    for row in cursor.fetchall():
        doc_id, filename, path = row
        file_path = Path(path)

        if not file_path.exists():
            missing_files.append({
                "id": doc_id,
                "filename": filename,
                "path": str(path)
            })
            logger.warning(f"파일 없음: {filename} (id={doc_id})")

    return missing_files


def verify_content_hash(db: MetadataDB):
    """content_hash 무결성 검증 (파일 해시와 DB 해시 비교)"""
    logger.info("content_hash 무결성 검증 중...")
    conn = db._get_conn()
    cursor = conn.execute(
        "SELECT id, filename, path, content_hash FROM documents WHERE content_hash IS NOT NULL"
    )

    mismatches = []
    for row in cursor.fetchall():
        doc_id, filename, path, stored_hash = row
        file_path = Path(path)

        if not file_path.exists():
            continue  # 파일 존재 검증에서 이미 처리됨

        try:
            actual_hash = compute_file_hash(file_path)
            if actual_hash != stored_hash:
                mismatches.append({
                    "id": doc_id,
                    "filename": filename,
                    "stored_hash": stored_hash[:16] + "...",
                    "actual_hash": actual_hash[:16] + "..."
                })
                logger.warning(f"해시 불일치: {filename} (id={doc_id})")
        except Exception as e:
            logger.error(f"해시 계산 실패: {filename} - {e}")

    return mismatches


def verify_temp_filenames(db: MetadataDB):
    """임시 파일명 패턴 검증 (_1, _2 등)"""
    logger.info("임시 파일명 패턴 검증 중...")
    conn = db._get_conn()
    cursor = conn.execute(
        "SELECT id, filename FROM documents WHERE filename GLOB '*_[0-9].pdf'"
    )

    temp_files = []
    for row in cursor.fetchall():
        doc_id, filename = row
        temp_files.append({
            "id": doc_id,
            "filename": filename
        })
        logger.warning(f"임시 파일명: {filename} (id={doc_id})")

    return temp_files


def verify_required_fields(db: MetadataDB):
    """필수 필드 검증"""
    logger.info("필수 필드 검증 중...")
    conn = db._get_conn()
    cursor = conn.execute(
        """
        SELECT id, filename, date, drafter, doctype
        FROM documents
        WHERE date IS NULL OR date = ''
           OR drafter IS NULL OR drafter = ''
           OR doctype IS NULL OR doctype = ''
        """
    )

    missing_fields = []
    for row in cursor.fetchall():
        doc_id, filename, date, drafter, doctype = row
        missing = []
        if not date:
            missing.append("date")
        if not drafter:
            missing.append("drafter")
        if not doctype:
            missing.append("doctype")

        missing_fields.append({
            "id": doc_id,
            "filename": filename,
            "missing": ", ".join(missing)
        })
        logger.warning(f"필수 필드 누락: {filename} - {', '.join(missing)}")

    return missing_fields


def generate_report(results: dict, output_path: str):
    """검증 보고서 생성"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 데이터베이스 무결성 검증 보고서\n\n")

        f.write("## 검증 요약\n\n")
        f.write(f"- 파일 없음: {len(results['missing_files'])}개\n")
        f.write(f"- 해시 불일치: {len(results['hash_mismatches'])}개\n")
        f.write(f"- 임시 파일명: {len(results['temp_files'])}개\n")
        f.write(f"- 필수 필드 누락: {len(results['missing_fields'])}개\n\n")

        if results["missing_files"]:
            f.write("## 파일 없음\n\n")
            for item in results["missing_files"]:
                f.write(f"- {item['filename']} (id={item['id']}, path={item['path']})\n")
            f.write("\n")

        if results["hash_mismatches"]:
            f.write("## 해시 불일치\n\n")
            for item in results["hash_mismatches"]:
                f.write(f"- {item['filename']} (id={item['id']})\n")
                f.write(f"  - stored: {item['stored_hash']}\n")
                f.write(f"  - actual: {item['actual_hash']}\n")
            f.write("\n")

        if results["temp_files"]:
            f.write("## 임시 파일명\n\n")
            for item in results["temp_files"]:
                f.write(f"- {item['filename']} (id={item['id']})\n")
            f.write("\n")

        if results["missing_fields"]:
            f.write("## 필수 필드 누락\n\n")
            for item in results["missing_fields"]:
                f.write(f"- {item['filename']} (id={item['id']}) - {item['missing']}\n")

    logger.info(f"보고서 생성: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="데이터베이스 무결성 검증")
    parser.add_argument("--db", default="metadata.db", help="DB 파일 경로")
    parser.add_argument("--report", default="reports/db_verify_report.md", help="보고서 출력 경로")

    args = parser.parse_args()

    # DB 연결
    db = MetadataDB(db_path=args.db)

    # 검증 실행
    results = {
        "missing_files": verify_file_existence(db),
        "hash_mismatches": verify_content_hash(db),
        "temp_files": verify_temp_filenames(db),
        "missing_fields": verify_required_fields(db)
    }

    # 보고서 생성
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    generate_report(results, args.report)

    # 요약 출력
    total_issues = sum(len(v) for v in results.values())
    if total_issues == 0:
        logger.info("✅ 무결성 검증 완료: 문제 없음")
    else:
        logger.warning(f"⚠️ 무결성 검증 완료: {total_issues}개 문제 발견")


if __name__ == "__main__":
    main()
