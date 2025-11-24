#!/usr/bin/env python3
"""2017년 기안자 누락 문서 OCR 재처리 스크립트

OCR 품질이 낮아 기안자 정보를 추출하지 못한 2017년 문서들을 재처리합니다.
"""

import sqlite3
import subprocess
from pathlib import Path
import re
import sys
import time
from typing import Optional, Tuple

# OCR 설정 개선
TESSERACT_CONFIG = '-l kor --oem 3 --psm 6'  # 한국어, LSTM OCR 엔진, 균일한 블록 텍스트

def extract_drafter_from_ocr_text(text: str) -> Optional[str]:
    """개선된 기안자 추출 로직"""

    # 다양한 패턴 시도
    patterns = [
        # 표준 패턴
        r'기안자\s*[:|]?\s*([가-힣]{2,4})',
        r'기안자\s*\|\s*([가-힣]{2,4})',
        # 공백/줄바꿈 처리
        r'기\s*안\s*자\s*[:|]?\s*([가-힣]{2,4})',
        # OCR 오류 보정
        r'기안차\s*[:|]?\s*([가-힣]{2,4})',  # 자→차
        r'기인자\s*[:|]?\s*([가-힣]{2,4})',  # 안→인
        # 영문 혼재
        r'기안자.*?([가-힣]{2,4})\s*(?:보존|시행)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text[:3000])
        if match:
            drafter = match.group(1).strip()
            # 유효성 검증
            if drafter and len(drafter) >= 2 and len(drafter) <= 4:
                if drafter not in ['보존기간', '시행자', '기안일자', '문서번호']:
                    return drafter

    return None

def reprocess_with_ocr(pdf_path: Path) -> Tuple[bool, Optional[str], str]:
    """PDF를 OCR로 재처리하여 기안자 추출"""

    try:
        # 1. PDF를 이미지로 변환 (첫 페이지만)
        img_path = Path('/tmp') / f"{pdf_path.stem}_page1.png"
        cmd = [
            'pdftoppm', '-png', '-f', '1', '-l', '1',
            '-r', '300',  # 높은 해상도
            str(pdf_path), str(img_path.with_suffix(''))
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return False, None, f"PDF 변환 실패: {result.stderr}"

        # 실제 생성된 파일명 찾기
        img_files = list(Path('/tmp').glob(f"{pdf_path.stem}_page1*.png"))
        if not img_files:
            return False, None, "이미지 파일 생성 실패"

        actual_img_path = img_files[0]

        # 2. OCR 수행
        ocr_cmd = f'tesseract {actual_img_path} stdout {TESSERACT_CONFIG}'
        result = subprocess.run(ocr_cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            actual_img_path.unlink()
            return False, None, f"OCR 실패: {result.stderr}"

        ocr_text = result.stdout

        # 3. 기안자 추출
        drafter = extract_drafter_from_ocr_text(ocr_text)

        # 4. 정리
        actual_img_path.unlink()

        if drafter:
            return True, drafter, "OCR 성공"
        else:
            # 디버깅을 위해 일부 텍스트 반환
            sample = ocr_text[:500].replace('\n', ' ')
            return False, None, f"기안자 추출 실패. 샘플: {sample[:100]}..."

    except Exception as e:
        return False, None, f"오류: {str(e)}"

def main():
    """메인 실행 함수"""

    print("=" * 60)
    print("📝 2017년 문서 OCR 재처리")
    print("=" * 60)

    # Tesseract 설치 확인
    try:
        subprocess.run(['tesseract', '--version'], capture_output=True, check=True)
    except:
        print("❌ Tesseract OCR이 설치되지 않았습니다.")
        print("설치: sudo apt-get install tesseract-ocr tesseract-ocr-kor")
        return

    # pdftoppm 설치 확인
    try:
        subprocess.run(['pdftoppm', '-v'], capture_output=True, check=True)
    except:
        print("❌ pdftoppm이 설치되지 않았습니다.")
        print("설치: sudo apt-get install poppler-utils")
        return

    # DB 연결
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    # 2017년 기안자 누락 문서 조회
    cursor.execute("""
        SELECT id, filename
        FROM documents
        WHERE (drafter IS NULL OR drafter = '')
        AND filename LIKE '2017-%'
        ORDER BY filename
    """)

    docs = cursor.fetchall()
    print(f"\n📊 처리 대상: {len(docs)}개 문서\n")

    if len(docs) == 0:
        print("✅ 처리할 문서가 없습니다.")
        conn.close()
        return

    # 처리
    success_count = 0
    failed_count = 0
    results = []

    for i, (doc_id, filename) in enumerate(docs, 1):
        pdf_path = Path('docs') / f"year_{filename[:4]}" / filename

        if not pdf_path.exists():
            print(f"[{i}/{len(docs)}] ❌ 파일 없음: {filename}")
            failed_count += 1
            continue

        print(f"[{i}/{len(docs)}] 처리 중: {filename[:50]}...", end='')

        # OCR 재처리
        success, drafter, message = reprocess_with_ocr(pdf_path)

        if success and drafter:
            # DB 업데이트
            cursor.execute(
                "UPDATE documents SET drafter = ? WHERE id = ?",
                (drafter, doc_id)
            )
            print(f" ✅ {drafter}")
            success_count += 1
            results.append((filename, drafter, "성공"))
        else:
            print(f" ❌ {message[:50]}")
            failed_count += 1
            results.append((filename, None, message))

        # 과부하 방지
        if i % 5 == 0:
            time.sleep(1)

    # 커밋
    conn.commit()

    # 결과 요약
    print("\n" + "=" * 60)
    print("📈 처리 결과:")
    print(f"  ✅ 성공: {success_count}개")
    print(f"  ❌ 실패: {failed_count}개")
    print(f"  📊 전체: {len(docs)}개")

    # 성공 사례 출력
    if success_count > 0:
        print("\n✅ 복구 성공:")
        for filename, drafter, status in results:
            if drafter:
                print(f"  - {filename[:50]}: {drafter}")

    # 실패 사례 분석
    if failed_count > 0:
        print(f"\n❌ 실패 사례 ({min(5, failed_count)}개만 표시):")
        fail_count = 0
        for filename, drafter, message in results:
            if not drafter and fail_count < 5:
                print(f"  - {filename[:30]}: {message[:50]}")
                fail_count += 1

    conn.close()
    print("\n✅ OCR 재처리 완료")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 테스트 모드: 첫 3개만 처리
        print("🧪 테스트 모드: 3개 문서만 처리")
    else:
        response = input("45개 문서를 OCR 재처리하시겠습니까? (y/n): ")
        if response.lower() == 'y':
            main()
        else:
            print("취소되었습니다.")