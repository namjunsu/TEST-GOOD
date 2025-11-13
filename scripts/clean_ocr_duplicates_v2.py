#!/usr/bin/env python3
"""
clean_ocr_duplicates_v2.py
- backup/extracted_20251113 기준으로
  [OCR 추출 텍스트] 이후의 OCR 본문을 완전히 제거하고
  data/extracted에 정제된 텍스트를 재생성한다.
"""

from pathlib import Path

# 백업(원본)과 타깃 경로 정의
BACKUP_DIR = Path("backup/extracted_20251113")
TARGET_DIR = Path("data/extracted")

MARKERS = [
    "[OCR 추출 텍스트]",    # 기본 마커
    "[ OCR 추출 텍스트 ]",  # 혹시 공백 변형
]

def clean_text(text: str) -> str:
    """
    [OCR 추출 텍스트] 마커 이후 전체를 제거한다.
    마커가 없으면 원문 그대로 반환.
    """
    idx = -1
    for m in MARKERS:
        pos = text.find(m)
        if pos != -1:
            # 여러 마커가 있다면 가장 앞에 나온 것 기준
            idx = pos if idx == -1 else min(idx, pos)

    if idx == -1:
        # 마커 없음 → 그대로 반환
        return text

    cleaned = text[:idx].rstrip() + "\n"
    return cleaned


def main():
    if not BACKUP_DIR.exists():
        raise SystemExit(f"백업 디렉터리가 존재하지 않습니다: {BACKUP_DIR}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(BACKUP_DIR.glob("*.txt"))
    print(f"[INFO] 대상 파일 수: {len(txt_files)}개")

    changed = 0
    no_marker = 0

    for src in txt_files:
        raw = src.read_text(encoding="utf-8", errors="ignore")
        cleaned = clean_text(raw)

        # 간단한 통계용
        if cleaned != raw:
            changed += 1
        else:
            no_marker += 1

        dst = TARGET_DIR / src.name
        dst.write_text(cleaned, encoding="utf-8")

    print(f"[INFO] OCR 블록 제거된 파일: {changed}개")
    print(f"[INFO] 마커 미검출(그대로 유지): {no_marker}개")
    print(f"[INFO] 출력 디렉터리: {TARGET_DIR.resolve()}")


if __name__ == "__main__":
    main()
