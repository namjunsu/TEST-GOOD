#!/usr/bin/env python3
"""
기존 문서의 claimed_total 일괄 재추출 스크립트

DB에 저장된 문서 중 claimed_total이 NULL인 문서들을 대상으로
텍스트에서 금액을 재추출하여 업데이트합니다.

사용법:
    python scripts/ops/backfill_claimed_total.py              # 전체 재처리
    python scripts/ops/backfill_claimed_total.py --dry-run    # 테스트 모드 (DB 수정 안 함)
    python scripts/ops/backfill_claimed_total.py --limit 10   # 10개만 처리
    python scripts/ops/backfill_claimed_total.py --only "중계차*오버*"  # 특정 패턴만
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.parse.parse_tables import TableParser
from scripts.core.ingest_from_docs import extract_claimed_total_fallback

logger = get_logger(__name__)


class ClaimedTotalBackfiller:
    """claimed_total 재추출 처리기"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db = MetadataDB()
        self.table_parser = TableParser()
        self.stats = {
            "total": 0,
            "extracted": 0,
            "failed": 0,
            "skipped": 0,
        }

    def get_document_text(self, filename: str) -> Optional[str]:
        """문서 텍스트 가져오기

        우선순위:
        1. data/extracted/{filename}.txt (OCR 결과)
        2. DB의 text_preview (폴백)
        """
        # 1. extracted/*.txt 파일 시도
        txt_filename = filename.replace(".pdf", ".txt")
        txt_path = PROJECT_ROOT / "data" / "extracted" / txt_filename

        if txt_path.exists():
            try:
                text = txt_path.read_text(encoding="utf-8")
                if text.strip():
                    logger.debug(f"📄 텍스트 로드: {txt_path} ({len(text)} chars)")
                    return text
            except Exception as e:
                logger.warning(f"⚠️ {txt_path} 읽기 실패: {e}")

        # 2. DB의 text_preview 폴백
        doc = self.db.get_by_filename(filename)
        if doc and doc.get("text_preview"):
            logger.debug(f"📄 text_preview 사용: {filename} ({len(doc['text_preview'])} chars)")
            return doc["text_preview"]

        logger.warning(f"⚠️ 텍스트 없음: {filename}")
        return None

    def extract_claimed_total(self, text: str) -> Optional[int]:
        """텍스트에서 claimed_total 추출

        우선순위 변경 (표 파서 버그로 인해):
        1. extract_claimed_total_fallback() - 정규식 (신뢰성 높음)
        2. TableParser.extract_cost_table() - 표 기반 (폴백)
        """
        # 1. 정규식 추출 우선 (중간 합계 중복 문제 없음)
        claimed_total = extract_claimed_total_fallback(text)
        if claimed_total:
            logger.debug(f"💰 정규식 추출 성공: {claimed_total:,}원")
            return claimed_total

        # 2. 표 파싱 폴백 (정규식 실패 시에만)
        try:
            items, parse_success, status_msg = self.table_parser.extract_cost_table(text)
            if parse_success and items:
                # 항목들의 amount를 합산
                total = sum(item.get("amount", 0) for item in items if item.get("amount"))
                if total > 0:
                    logger.debug(f"💰 표 파싱 성공: {total:,}원 ({len(items)}개 항목)")
                    return total
        except Exception as e:
            logger.debug(f"표 파싱 실패: {e}")

        return None

    def process_document(self, filename: str) -> bool:
        """문서 1개 처리

        Returns:
            성공 여부
        """
        logger.info(f"처리 중: {filename}")

        # 1. 텍스트 가져오기
        text = self.get_document_text(filename)
        if not text:
            self.stats["skipped"] += 1
            return False

        # 2. 금액 추출
        claimed_total = self.extract_claimed_total(text)
        if not claimed_total:
            logger.info(f"❌ 금액 추출 실패: {filename}")
            self.stats["failed"] += 1
            return False

        # 3. DB 업데이트 (dry-run이 아닐 경우)
        if self.dry_run:
            logger.info(f"✅ [DRY-RUN] {filename} → ₩{claimed_total:,}")
        else:
            try:
                self.db.update_document(
                    filename=filename,
                    claimed_total=claimed_total,
                )
                logger.info(f"✅ DB 업데이트 완료: {filename} → ₩{claimed_total:,}")
            except Exception as e:
                logger.error(f"❌ DB 업데이트 실패: {filename} - {e}")
                self.stats["failed"] += 1
                return False

        self.stats["extracted"] += 1
        return True

    def run(self, limit: Optional[int] = None, pattern: Optional[str] = None):
        """재처리 실행

        Args:
            limit: 처리할 최대 문서 수 (None이면 전체)
            pattern: 파일명 패턴 (와일드카드 지원, 예: "중계차*오버*")
        """
        logger.info("=" * 80)
        logger.info("📦 claimed_total 재추출 시작")
        logger.info(f"모드: {'DRY-RUN (테스트)' if self.dry_run else '실제 실행'}")
        if limit:
            logger.info(f"제한: {limit}개 문서")
        if pattern:
            logger.info(f"패턴: {pattern}")
        logger.info("=" * 80)

        # DB에서 claimed_total IS NULL인 문서 조회
        with self.db._cursor() as cur:
            if pattern:
                # 와일드카드 패턴을 SQL LIKE로 변환
                sql_pattern = pattern.replace("*", "%")
                cur.execute(
                    "SELECT filename FROM documents WHERE claimed_total IS NULL AND filename LIKE ? ORDER BY filename",
                    (sql_pattern,),
                )
            else:
                cur.execute(
                    "SELECT filename FROM documents WHERE claimed_total IS NULL ORDER BY filename"
                )

            rows = cur.fetchall()

        if not rows:
            logger.info("✅ 모든 문서가 이미 claimed_total을 가지고 있습니다!")
            return

        total_candidates = len(rows)
        to_process = total_candidates if limit is None else min(limit, total_candidates)

        logger.info(f"\n📊 총 {total_candidates}개 문서가 claimed_total이 NULL 상태입니다.")
        logger.info(f"🔄 {to_process}개 문서를 처리합니다.\n")

        # 문서 처리
        for i, row in enumerate(rows[:to_process], 1):
            filename = row["filename"]
            self.stats["total"] += 1

            logger.info(f"\n[{i}/{to_process}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.process_document(filename)

        # 최종 통계
        self._print_stats(total_candidates)

    def _print_stats(self, total_candidates: int):
        """통계 출력"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 처리 결과")
        logger.info("=" * 80)
        logger.info(f"전체 후보: {total_candidates}개")
        logger.info(f"처리 완료: {self.stats['total']}개")
        logger.info(f"✅ 추출 성공: {self.stats['extracted']}개")
        logger.info(f"❌ 추출 실패: {self.stats['failed']}개")
        logger.info(f"⏭️  텍스트 없음: {self.stats['skipped']}개")

        if self.stats["total"] > 0:
            success_rate = (self.stats["extracted"] / self.stats["total"]) * 100
            logger.info(f"📈 성공률: {success_rate:.1f}%")

        if self.dry_run:
            logger.info("\n⚠️  DRY-RUN 모드: DB가 수정되지 않았습니다.")
            logger.info("실제 실행하려면 --dry-run 옵션을 제거하세요.")
        else:
            logger.info(f"\n✅ DB 업데이트 완료: {self.stats['extracted']}개 문서")

        logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="기존 문서의 claimed_total 재추출 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python scripts/ops/backfill_claimed_total.py              # 전체 재처리
  python scripts/ops/backfill_claimed_total.py --dry-run    # 테스트 모드
  python scripts/ops/backfill_claimed_total.py --limit 10   # 10개만
  python scripts/ops/backfill_claimed_total.py --only "중계차*오버*"  # 패턴 필터
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="테스트 모드 (DB 수정 안 함)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="처리할 최대 문서 수",
    )
    parser.add_argument(
        "--only",
        type=str,
        help="특정 파일명 패턴만 처리 (와일드카드 지원, 예: '중계차*오버*')",
    )

    args = parser.parse_args()

    # 백필러 실행
    backfiller = ClaimedTotalBackfiller(dry_run=args.dry_run)
    backfiller.run(limit=args.limit, pattern=args.only)


if __name__ == "__main__":
    main()
