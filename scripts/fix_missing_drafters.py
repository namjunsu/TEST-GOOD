#!/usr/bin/env python3
"""누락된 기안자 정보 복구 스크립트

문서 텍스트에서 기안자 정보를 추출하여 DB 메타데이터를 복구합니다.
"""

import sqlite3
import re
from pathlib import Path
import sys

def extract_drafter_from_text(text: str) -> str:
    """텍스트에서 기안자 추출"""

    # 다양한 기안자 패턴
    patterns = [
        r'기안자\s*[:|]?\s*([가-힣]{2,4})',  # "기안자: 홍길동" 또는 "기안자 홍길동"
        r'기안자\s*\|\s*([가-힣]{2,4})',      # "기안자 | 홍길동"
        r'작성자\s*[:|]?\s*([가-힣]{2,4})',   # "작성자: 홍길동"
    ]

    for pattern in patterns:
        match = re.search(pattern, text[:3000])  # 처음 3000자만 검색
        if match:
            drafter = match.group(1).strip()
            # 잘못된 값 필터링
            if drafter and drafter not in ['기안자', '시행자', '보존기간', '문서번호', '신청구분']:
                return drafter

    return None

def main():
    """메인 실행 함수"""

    # DB 연결
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    # drafter가 없는 문서들 찾기
    cursor.execute("""
        SELECT id, filename
        FROM documents
        WHERE drafter IS NULL OR drafter = ''
    """)
    docs = cursor.fetchall()

    print(f"📊 전체 기안자 누락 문서: {len(docs)}개")
    print("=" * 60)

    fixed_count = 0
    failed_count = 0

    for doc_id, filename in docs:
        txt_file = Path('data/extracted') / filename.replace('.pdf', '.txt')

        if not txt_file.exists():
            print(f"⚠️  텍스트 파일 없음: {filename}")
            failed_count += 1
            continue

        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            drafter = extract_drafter_from_text(content)

            if drafter:
                # DB 업데이트
                cursor.execute(
                    "UPDATE documents SET drafter = ? WHERE id = ?",
                    (drafter, doc_id)
                )
                print(f"✅ 수정됨: {filename[:50]:<50} → {drafter}")
                fixed_count += 1
            else:
                print(f"❌ 추출 실패: {filename[:50]}")
                failed_count += 1

        except Exception as e:
            print(f"❌ 오류: {filename} - {e}")
            failed_count += 1

    # 변경사항 저장
    conn.commit()

    # 결과 요약
    print("=" * 60)
    print(f"📈 결과:")
    print(f"  - 수정됨: {fixed_count}개")
    print(f"  - 실패: {failed_count}개")
    print(f"  - 전체: {len(docs)}개")

    # 검증: 하승범 문서 개수 확인
    cursor.execute("SELECT COUNT(*) FROM documents WHERE drafter = '하승범'")
    hasung_count = cursor.fetchone()[0]
    print(f"\n🔍 하승범 문서: 총 {hasung_count}개")

    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        print("DRY RUN 모드는 아직 구현되지 않았습니다.")
    else:
        response = input("DB를 수정하시겠습니까? (y/n): ")
        if response.lower() == 'y':
            main()
        else:
            print("취소되었습니다.")