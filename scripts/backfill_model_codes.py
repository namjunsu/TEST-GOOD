#!/usr/bin/env python3
"""기존 documents에서 model_codes 백필

data/extracted/*.txt에서 텍스트를 읽어 model_codes 테이블을 채웁니다.
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트 추가
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.textproc.normalizer import extract_codes, normalize_code

logger = get_logger(__name__)

EXTRACTED_DIR = BASE_DIR / "data" / "extracted"


def backfill_model_codes(limit: int | None = None, dry_run: bool = False):
    """기존 documents에서 model_codes 백필

    Args:
        limit: 처리할 최대 문서 수 (None=전체)
        dry_run: 시뮬레이션 모드
    """
    db = MetadataDB()
    conn = db._get_conn()

    print("=" * 70)
    print("Model Codes Backfill (기존 문서 코드 추출)")
    print("=" * 70)
    print(f"Project root: {BASE_DIR}")
    print(f"Extracted dir: {EXTRACTED_DIR}")

    # 1. documents 조회 (filename과 id 매핑)
    query = "SELECT id, filename FROM documents"
    if limit is not None:
        if limit <= 0:
            print(f"\n⚠️  limit={limit}이므로 처리할 문서가 없습니다.")
            return
        cursor = conn.execute(f"{query} LIMIT ?", (limit,))
    else:
        cursor = conn.execute(query)

    documents = cursor.fetchall()

    print(f"\n📄 처리 대상: {len(documents)}개 문서")

    if dry_run:
        print("⚠️  DRY-RUN 모드 (실제 저장 없음)\n")

    # 2. 각 문서에서 코드 추출 및 저장
    total_codes = 0
    doc_with_codes = 0
    errors = 0
    skipped = 0
    batch_count = 0

    for doc_id, filename in documents:
        try:
            # 텍스트 파일 경로 (PDF → TXT)
            txt_filename = Path(filename).with_suffix(".txt")
            txt_path = EXTRACTED_DIR / txt_filename

            if not txt_path.exists():
                skipped += 1
                logger.debug(f"텍스트 파일 없음: {txt_filename}")
                continue

            # 텍스트 읽기
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            if not text.strip():
                continue

            # 코드 추출 (원본 + 정규화)
            raw_codes = extract_codes(text, normalize_result=False)

            if not raw_codes:
                continue

            # 정규화
            code_pairs = []
            for raw in raw_codes:
                norm = normalize_code(raw, uppercase=True)
                code_pairs.append((raw, norm))

            doc_with_codes += 1
            print(f"\n📌 {filename}")
            print(f"   doc_id={doc_id}, 코드 {len(code_pairs)}개")
            if code_pairs[:3]:
                for raw, norm in code_pairs[:3]:
                    print(f"     {raw} → {norm}")
                if len(code_pairs) > 3:
                    print(f"     ... 외 {len(code_pairs)-3}개")

            if not dry_run:
                # model_codes 테이블에 삽입 (executemany로 배치 처리)
                rows = [(doc_id, raw, norm) for raw, norm in code_pairs]
                try:
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO model_codes (doc_id, raw_code, norm_code)
                        VALUES (?, ?, ?)
                        """,
                        rows,
                    )
                    total_codes += len(rows)
                except Exception as e:
                    logger.warning(f"코드 삽입 실패 (doc_id={doc_id}): {e}")

                conn.commit()
                batch_count += 1

                # 진행 상황 표시 (50개마다)
                if batch_count % 50 == 0:
                    print(f"\n  💾 커밋: {batch_count}개 문서 처리...")
            else:
                total_codes += len(code_pairs)

        except Exception as e:
            errors += 1
            logger.error(f"문서 처리 실패 ({filename}): {e}", exc_info=True)

    # 3. 결과 출력
    print("\n" + "=" * 70)
    print("백필 완료")
    print("=" * 70)
    print(f"✓ 처리된 문서: {len(documents)}개")
    print(f"✓ 코드 발견 문서: {doc_with_codes}개")
    print(f"✓ 추출된 총 코드: {total_codes}개")
    print(f"✓ 스킵: {skipped}개 (텍스트 파일 없음)")
    print(f"✓ 에러: {errors}개")

    if not dry_run:
        # 검증
        cursor = conn.execute("SELECT COUNT(DISTINCT doc_id) FROM model_codes")
        unique_docs = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM model_codes")
        total_rows = cursor.fetchone()[0]

        print(f"\n📊 DB 상태:")
        print(f"   - model_codes 총 레코드: {total_rows}개")
        print(f"   - 고유 문서: {unique_docs}개")

        # 샘플 확인 (padded_norm 컬럼 존재 여부 체크)
        try:
            cursor = conn.execute(
                "SELECT raw_code, norm_code, padded_norm FROM model_codes LIMIT 10"
            )
            samples = cursor.fetchall()
            print(f"\n   샘플 (10개):")
            for raw, norm, padded in samples:
                print(f"     {raw:20s} → {norm:20s} → [{padded}]")
        except Exception as e:
            # padded_norm 컬럼이 없거나 다른 스키마 이슈
            print("\n   샘플 조회 중 오류 (padded_norm 컬럼 없음?):")
            print(f"   {e}")
            # 대신 raw_code, norm_code만 조회
            cursor = conn.execute(
                "SELECT raw_code, norm_code FROM model_codes LIMIT 10"
            )
            samples = cursor.fetchall()
            print(f"\n   샘플 (10개, raw → norm):")
            for raw, norm in samples:
                print(f"     {raw:20s} → {norm}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Model Codes Backfill")
    parser.add_argument("--limit", type=int, help="처리할 최대 문서 수 (기본: 전체)")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션 모드")
    args = parser.parse_args()

    backfill_model_codes(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
