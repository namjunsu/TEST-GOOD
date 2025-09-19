#!/usr/bin/env python3
"""
기안자 검색 개선 - 스캔 PDF 문제 해결
"""

import json
from pathlib import Path

# 알려진 기안자 정보 매핑 (수동으로 관리)
# 스캔 PDF의 경우 여기에 수동으로 추가
KNOWN_DRAFTERS = {
    # 2025년 문서
    "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf": "최새름",
    "2025-01-14_채널A_불용_방송_장비_폐기_요청의_건.pdf": "남준수",
    "2025-01-09_광화문_스튜디오_모니터_&_스탠드_교체_검토서.pdf": "김민수",

    # 2024년 문서 (예시)
    "2024-11-14_뉴스_스튜디오_지미집_Control_Box_수리_건.pdf": "남준수",

    # 2023년 문서
    "2023-12-06_오픈스튜디오_무선마이크_수신_장애_조치_기안서.pdf": "최새름",
    "2023-11-02_영상취재팀_트라이포드_수리_건.pdf": "유인혁",

    # 2019년 문서
    "2019-05-31_Audio_Patch_Cable_구매.pdf": "유인혁",

    # 더 많은 문서 추가 가능...
}

# JSON 파일로 저장
drafter_db_path = Path("drafter_database.json")

def save_drafter_database():
    """기안자 데이터베이스 저장"""
    with open(drafter_db_path, 'w', encoding='utf-8') as f:
        json.dump(KNOWN_DRAFTERS, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(KNOWN_DRAFTERS)}개 문서의 기안자 정보를 저장했습니다.")
    print(f"   파일: {drafter_db_path}")

def load_drafter_database():
    """기안자 데이터베이스 로드"""
    if drafter_db_path.exists():
        with open(drafter_db_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def search_by_drafter(drafter_name: str):
    """기안자로 문서 검색"""
    db = load_drafter_database()
    found_docs = []

    for filename, drafter in db.items():
        if drafter_name in drafter:
            found_docs.append(filename)

    return found_docs

if __name__ == "__main__":
    # 데이터베이스 생성
    save_drafter_database()

    # 테스트 검색
    print("\n🔍 테스트 검색:")
    for name in ["최새름", "남준수", "유인혁"]:
        docs = search_by_drafter(name)
        print(f"\n{name} 기안자 문서: {len(docs)}개")
        for doc in docs:
            print(f"  - {doc}")