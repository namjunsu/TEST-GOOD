#!/usr/bin/env python3
"""
기존 문서 메타데이터 재파싱 스크립트

metadata.db의 text_preview에서 메타데이터를 다시 추출하여 업데이트합니다.

사용법:
    python scripts/ops/reparse_metadata.py              # 전체 재파싱
    python scripts/ops/reparse_metadata.py --dry-run    # 미리보기만
    python scripts/ops/reparse_metadata.py --limit 10   # 10개만 처리
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def extract_metadata_from_text(text: str, filename: str) -> dict:
    """텍스트에서 메타데이터 추출

    Args:
        text: 문서 전체 텍스트
        filename: 파일명

    Returns:
        추출된 메타데이터 딕셔너리
    """
    result = {}

    # === 날짜 추출 (우선순위: 시행일자 > 기안일자 > 작성일자 > 작성일 > 파일명) ===

    # 시행일자 (기안서)
    action_date_match = re.search(r"시행일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2})", text)
    if action_date_match:
        result["date"] = normalize_date(action_date_match.group(1))

    # 기안일자 (기안서)
    if "date" not in result:
        draft_date_match = re.search(r"기안일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2})", text)
        if draft_date_match:
            result["date"] = normalize_date(draft_date_match.group(1))

    # 작성일자 (보고서)
    if "date" not in result:
        created_date_match = re.search(r"작성일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2})", text)
        if created_date_match:
            result["date"] = normalize_date(created_date_match.group(1))

    # 작성일 (검토서: "작성일 2021. 06. 21.")
    if "date" not in result:
        review_date_patterns = [
            r"작성일\s*[:\s]\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)",
            r"작성일\s*[:\s]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        ]
        for pattern in review_date_patterns:
            review_date_match = re.search(pattern, text)
            if review_date_match:
                result["date"] = normalize_date(review_date_match.group(1))
                break

    # 보고일 (보고서)
    if "date" not in result:
        report_date_match = re.search(r"보고일\s*[:\s]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})", text)
        if report_date_match:
            result["date"] = normalize_date(report_date_match.group(1))

    # 파일명에서 날짜 폴백
    if "date" not in result:
        filename_date_match = re.match(r"^(\d{4})[-_]?(\d{1,2})[-_]?(\d{1,2})", filename)
        if filename_date_match:
            y, m, d = filename_date_match.groups()
            result["date"] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    # === 작성자 추출 (우선순위: 기안자 > 작성자 > 검토자 > 담당자) ===

    stopwords = {"정보", "없음", "기타", "미상", "해당", "합계", "비용", "내용"}

    # 기안자 (기안서)
    drafter_match = re.search(r"기안자[\s\|\ㅣ:：\t]*([가-힣]{2,4})", text)
    if drafter_match:
        name = drafter_match.group(1)
        if name not in stopwords:
            result["drafter"] = name

    # 작성자 (검토서/보고서)
    if "drafter" not in result:
        author_match = re.search(r"작성자[\s\|\ㅣ:：\t]*([가-힣]{2,4})", text)
        if author_match:
            name = author_match.group(1)
            if name not in stopwords:
                result["drafter"] = name

    # 검토자 (검토서)
    if "drafter" not in result:
        reviewer_match = re.search(r"검토자[\s\|\ㅣ:：\t]*([가-힣]{2,4})", text)
        if reviewer_match:
            name = reviewer_match.group(1)
            if name not in stopwords:
                result["drafter"] = name

    # 담당자 (폴백)
    if "drafter" not in result:
        manager_match = re.search(r"담당자[\s\|\ㅣ:：\t]*([가-힣]{2,4})", text)
        if manager_match:
            name = manager_match.group(1)
            if name not in stopwords:
                result["drafter"] = name

    return result


def normalize_date(date_str: str) -> str:
    """날짜 문자열 정규화 (YYYY-MM-DD)"""
    if not date_str:
        return ""

    # 공백, 점, 슬래시 → 대시
    s = date_str.strip()
    s = re.sub(r"[./]", "-", s)
    s = re.sub(r"\s+", "", s)

    # YYYY-M-D → YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mm, dd = m.groups()
        return f"{y}-{mm.zfill(2)}-{dd.zfill(2)}"

    return s


def main():
    parser = argparse.ArgumentParser(description="기존 문서 메타데이터 재파싱")
    parser.add_argument("--dry-run", action="store_true", help="실제 업데이트 없이 미리보기만")
    parser.add_argument("--limit", type=int, help="처리할 최대 문서 수")
    parser.add_argument("--db-path", default="metadata.db", help="DB 경로")
    parser.add_argument("--extracted-dir", default="data/extracted", help="추출된 텍스트 디렉토리")
    parser.add_argument("--force", action="store_true", help="기존 값이 있어도 강제 업데이트")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("기존 문서 메타데이터 재파싱 시작")
    logger.info(f"dry_run: {args.dry_run}, force: {args.force}")
    logger.info("=" * 60)

    conn = sqlite3.connect(args.db_path)
    cursor = conn.cursor()

    extracted_dir = Path(args.extracted_dir)

    # 모든 문서 조회
    query = "SELECT id, filename, text_preview, date, drafter FROM documents"
    if args.limit:
        query += f" LIMIT {args.limit}"

    cursor.execute(query)
    rows = cursor.fetchall()

    logger.info(f"대상 문서: {len(rows)}개")

    stats = {
        "total": 0,
        "date_updated": 0,
        "drafter_updated": 0,
        "skipped": 0,
    }

    for row in rows:
        doc_id, filename, text_preview, current_date, current_drafter = row
        stats["total"] += 1

        # 1순위: data/extracted/ 파일에서 텍스트 읽기
        txt_filename = filename.replace(".pdf", ".txt").replace(".PDF", ".txt")
        txt_path = extracted_dir / txt_filename

        if txt_path.exists():
            try:
                text = txt_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"파일 읽기 실패: {txt_path} - {e}")
                text = text_preview or ""
        else:
            # 2순위: DB의 text_preview 사용
            text = text_preview or ""

        if not text:
            stats["skipped"] += 1
            continue

        # 메타데이터 추출
        extracted = extract_metadata_from_text(text, filename)

        updates = []
        update_values = []

        # 날짜 업데이트 조건: force 또는 (현재 값이 없거나 "정보 없음")
        date_needs_update = args.force or (not current_date or current_date == "정보 없음")
        if extracted.get("date") and date_needs_update:
            updates.append("date = ?")
            update_values.append(extracted["date"])

            # year, month도 업데이트
            if len(extracted["date"]) >= 7:
                updates.append("year = ?")
                update_values.append(extracted["date"][:4])
                updates.append("month = ?")
                update_values.append(extracted["date"][:7])

            stats["date_updated"] += 1
            if current_date != extracted["date"]:
                logger.info(f"[날짜] {filename}: {current_date} → {extracted['date']}")

        # 작성자 업데이트 조건: force 또는 (현재 값이 없거나 "정보 없음")
        drafter_needs_update = args.force or (not current_drafter or current_drafter == "정보 없음")
        if extracted.get("drafter") and drafter_needs_update:
            updates.append("drafter = ?")
            update_values.append(extracted["drafter"])
            stats["drafter_updated"] += 1
            if current_drafter != extracted["drafter"]:
                logger.info(f"[작성자] {filename}: {current_drafter} → {extracted['drafter']}")

        # 업데이트 실행
        if updates and not args.dry_run:
            update_values.append(doc_id)
            update_sql = f"UPDATE documents SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(update_sql, update_values)

    if not args.dry_run:
        conn.commit()

    conn.close()

    logger.info("=" * 60)
    logger.info("재파싱 완료")
    logger.info(f"  총 문서: {stats['total']}개")
    logger.info(f"  날짜 업데이트: {stats['date_updated']}개")
    logger.info(f"  작성자 업데이트: {stats['drafter_updated']}개")
    logger.info(f"  스킵 (텍스트 없음): {stats['skipped']}개")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
