#!/usr/bin/env python3
"""
text_preview 동기화 스크립트

문제: DB의 text_preview가 오래된 OCR 결과로, 실제 텍스트 파일과 불일치
해결: data/extracted/*.txt 파일에서 최신 텍스트를 읽어 DB 업데이트

사용법:
    python scripts/ops/sync_text_preview.py          # dry-run (변경사항 확인)
    python scripts/ops/sync_text_preview.py --apply  # 실제 적용

2025-12-16: 초기 구현
"""

import argparse
import sqlite3
from pathlib import Path


def get_text_preview(txt_path: Path, max_len: int = 1500) -> str | None:
    """텍스트 파일에서 미리보기 추출"""
    if not txt_path.exists():
        return None

    try:
        text = txt_path.read_text(encoding="utf-8")
        # 앞 1500자, 줄바꿈 → 공백
        preview = text[:max_len].replace("\n", " ").strip()
        return preview if preview else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="text_preview 동기화")
    parser.add_argument("--apply", action="store_true", help="실제 적용 (없으면 dry-run)")
    parser.add_argument("--db", default="metadata.db", help="DB 경로")
    parser.add_argument("--txt-dir", default="data/extracted", help="텍스트 파일 디렉토리")
    args = parser.parse_args()

    db_path = Path(args.db)
    txt_dir = Path(args.txt_dir)

    if not db_path.exists():
        print(f"❌ DB 없음: {db_path}")
        return

    conn = sqlite3.connect(db_path)

    # 모든 문서 조회
    rows = conn.execute("SELECT filename, text_preview FROM documents").fetchall()
    print(f"📊 전체 문서: {len(rows)}건")

    updated = 0
    skipped = 0
    no_txt = 0

    for filename, old_preview in rows:
        # 텍스트 파일 경로 (확장자 제거 후 .txt)
        base_name = filename.replace(".pdf", "")
        txt_path = txt_dir / f"{base_name}.txt"

        new_preview = get_text_preview(txt_path)

        if new_preview is None:
            no_txt += 1
            continue

        # 비교 (정규화)
        old_norm = (old_preview or "").strip()[:200]
        new_norm = new_preview.strip()[:200]

        if old_norm == new_norm:
            skipped += 1
            continue

        # 업데이트 필요
        if args.apply:
            conn.execute(
                "UPDATE documents SET text_preview = ? WHERE filename = ?",
                (new_preview, filename)
            )

        updated += 1
        if updated <= 10:  # 처음 10개만 출력
            print(f"\n📄 {filename}")
            print(f"   이전: {old_norm[:60]}...")
            print(f"   이후: {new_norm[:60]}...")

    if args.apply:
        conn.commit()
        print(f"\n✅ 업데이트 완료: {updated}건")
    else:
        print("\n🔍 Dry-run 결과:")
        print(f"   업데이트 필요: {updated}건")
        print(f"   변경 없음: {skipped}건")
        print(f"   텍스트 없음: {no_txt}건")
        print(f"\n실제 적용하려면: python {__file__} --apply")

    conn.close()


if __name__ == "__main__":
    main()
