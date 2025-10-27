#!/usr/bin/env python3
"""
Doctype 재분류 스크립트 (백필)

목적:
- 기존 DB에 저장된 전체 문서의 doctype을 룰 기반으로 재계산
- doctype 기능 추가 전 인덱싱된 문서들의 'proposal' 편중 해소

안전 절차:
- metadata.db 백업 필수
- 실행 전 dry-run 모드로 영향 범위 확인 가능

사용법:
    python scripts/reclassify_doctype.py                # 전체 재분류
    python scripts/reclassify_doctype.py --dry-run      # 실행 미리보기
    python scripts/reclassify_doctype.py --limit 100    # 100건만 처리

작성일: 2025-10-27
"""

import sqlite3
import pathlib
import sys
import argparse
from collections import Counter

# 프로젝트 루트를 sys.path에 추가
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

from app.rag.parse.doctype import classify_document

DB_PATH = "metadata.db"


def main(dry_run: bool = False, limit: int = None):
    """메인 재분류 로직"""

    print("=" * 60)
    print("📋 Doctype 재분류 스크립트 시작")
    print("=" * 60)

    if dry_run:
        print("⚠️  DRY-RUN 모드: DB 변경 없이 미리보기만 수행\n")
    else:
        print("🔥 실행 모드: DB가 실제로 업데이트됩니다\n")

    # DB 연결
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 현재 doctype 분포 확인
    print("📊 재분류 전 doctype 분포:")
    cur.execute("SELECT doctype, COUNT(*) FROM documents GROUP BY doctype")
    before_stats = dict(cur.fetchall())
    for doctype, count in before_stats.items():
        print(f"   {doctype or '(NULL)'}: {count}건")
    print()

    # 재분류 대상 문서 조회
    query = "SELECT id, filename, text_preview FROM documents"
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query)
    rows = cur.fetchall()
    total_docs = len(rows)

    print(f"🎯 재분류 대상: {total_docs}건\n")

    # 재분류 수행
    updated_count = 0
    changed_count = 0
    new_stats = Counter()
    changed_samples = []  # 변경된 문서 샘플 (최대 20건)

    for doc_id, filename, text_preview in rows:
        # 텍스트 샘플 준비 (처음 4000자)
        text_sample = (text_preview or "")[:4000]

        # 기존 doctype 조회
        cur.execute("SELECT doctype FROM documents WHERE id = ?", (doc_id,))
        old_doctype = cur.fetchone()[0]

        # 룰 기반 재분류
        result = classify_document(text_sample, filename)
        new_doctype = result["doctype"]
        confidence = result["confidence"]
        reasons = result["reasons"]

        # 통계 수집
        new_stats[new_doctype] += 1

        # 변경 여부 확인
        if old_doctype != new_doctype:
            changed_count += 1

            # 샘플 수집 (최대 20건)
            if len(changed_samples) < 20:
                changed_samples.append({
                    "id": doc_id,
                    "filename": filename,
                    "old": old_doctype,
                    "new": new_doctype,
                    "confidence": confidence,
                    "reasons": reasons
                })

            # Dry-run이 아니면 DB 업데이트
            if not dry_run:
                cur.execute(
                    "UPDATE documents SET doctype = ? WHERE id = ?",
                    (new_doctype, doc_id)
                )

        updated_count += 1

        # 진행 상황 표시 (100건마다)
        if updated_count % 100 == 0:
            print(f"   처리 중... {updated_count}/{total_docs}건")

    # DB 커밋 (dry-run이 아닐 때만)
    if not dry_run:
        conn.commit()

    conn.close()

    # 결과 보고
    print("\n" + "=" * 60)
    print("✅ 재분류 완료")
    print("=" * 60)
    print(f"처리 건수: {updated_count}/{total_docs}건")
    print(f"변경 건수: {changed_count}건 ({changed_count/total_docs*100:.1f}%)\n")

    print("📊 재분류 후 doctype 분포:")
    for doctype in sorted(new_stats.keys()):
        count = new_stats[doctype]
        pct = count / total_docs * 100
        print(f"   {doctype}: {count}건 ({pct:.1f}%)")

    # 변경 샘플 표시
    if changed_samples:
        print(f"\n📝 변경 샘플 (최대 20건):")
        for i, sample in enumerate(changed_samples[:20], 1):
            print(f"\n{i}. {sample['filename'][:60]}")
            print(f"   변경: {sample['old']} → {sample['new']}")
            print(f"   신뢰도: {sample['confidence']:.2f}")
            if sample['reasons']:
                print(f"   매칭 키워드: {', '.join(sample['reasons'][:5])}")

    # AC 평가
    print("\n" + "=" * 60)
    print("🎯 AC (Acceptance Criteria) 평가")
    print("=" * 60)

    # AC1: proposal 편중 해소
    proposal_ratio = new_stats.get('proposal', 0) / total_docs * 100
    other_ratio = 100 - proposal_ratio
    ac1_pass = other_ratio > 10

    print(f"AC1: 'proposal' 단일값 편중 해소 (타 라벨 > 10%)")
    print(f"     proposal: {proposal_ratio:.1f}%, 타 라벨 합계: {other_ratio:.1f}%")
    print(f"     결과: {'✅ PASS' if ac1_pass else '❌ FAIL'}")

    # 권장 조치
    if dry_run:
        print("\n💡 다음 단계:")
        print("   1. 위 결과를 확인 후 실행 모드로 재실행:")
        print("      python scripts/reclassify_doctype.py")
        print("   2. 검토서/폐기문서 표본 수동 점검 (각 10건)")
    else:
        print("\n💡 다음 단계:")
        print("   1. DB 재분류 완료 ✅")
        print("   2. 검증 쿼리 실행:")
        print("      sqlite3 metadata.db \"SELECT doctype, COUNT(*) FROM documents GROUP BY doctype;\"")
        print("   3. 검토서/폐기문서 표본 수동 점검 (각 10건):")
        print("      sqlite3 metadata.db \"SELECT id, filename, doctype FROM documents WHERE doctype='review' LIMIT 10;\"")
        print("      sqlite3 metadata.db \"SELECT id, filename, doctype FROM documents WHERE doctype='disposal' LIMIT 10;\"")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Doctype 재분류 스크립트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 DB 변경 없이 미리보기만 수행"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="처리할 문서 수 제한 (테스트용)"
    )

    args = parser.parse_args()

    try:
        main(dry_run=args.dry_run, limit=args.limit)
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
