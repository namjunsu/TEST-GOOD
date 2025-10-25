#!/usr/bin/env python3
"""
테스트 질의 5건 정의
문서 기반으로 서로 다른 주제/카테고리를 고르게 택함
"""

TEST_QUERIES = [
    {
        "query": "2019년 ENG 카메라 수리 내역을 알려줘",
        "target_doc_id": "2019-01-30_ENG_카메라_수리_신청서.pdf",
        "expected_keywords": ["ENG", "카메라", "수리"],
        "acceptance": "evidence ≥ 1 이고 text에 expected_keywords 중 ≥1개 포함"
    },
    {
        "query": "트라이포드 발판 수리 건이 있었나?",
        "target_doc_id": "2019-01-14_카메라_트라이포트_발판_수리_건.pdf",
        "expected_keywords": ["트라이포드", "발판"],
        "acceptance": "evidence ≥ 1 이고 text에 expected_keywords 중 ≥1개 포함"
    },
    {
        "query": "무선 마이크 전원 스위치 고장 수리한 적 있어?",
        "target_doc_id": "2017-09-05_무선_마이크_전원_스위치_수리_건.pdf",
        "expected_keywords": ["무선", "마이크", "전원"],
        "acceptance": "evidence ≥ 1 이고 text에 expected_keywords 중 ≥1개 포함"
    },
    {
        "query": "2020년 3월에 스튜디오 지미짚 수리 건 찾아줘",
        "target_doc_id": "2020-03-11_영상카메라팀_스튜디오_지미짚_수리.pdf",
        "expected_keywords": ["스튜디오", "지미짚", "2020"],
        "acceptance": "evidence ≥ 1 이고 text에 expected_keywords 중 ≥1개 포함"
    },
    {
        "query": "LED조명 수리 관련 문서 검색",
        "target_doc_id": "2019-05-10_영상취재팀_LED조명_수리_건.pdf",
        "expected_keywords": ["LED", "조명"],
        "acceptance": "evidence ≥ 1 이고 text에 expected_keywords 중 ≥1개 포함"
    }
]


if __name__ == "__main__":
    print("=" * 120)
    print("테스트 질의 5건")
    print("=" * 120)
    print(f"\n{'#':<3} {'Query':<45} {'Target Doc':<40} {'Expected Keywords':<25}")
    print("-" * 120)

    for i, q in enumerate(TEST_QUERIES, 1):
        keywords_str = ", ".join(q["expected_keywords"])
        target_short = q["target_doc_id"][:38] + ".." if len(q["target_doc_id"]) > 40 else q["target_doc_id"]
        query_short = q["query"][:43] + ".." if len(q["query"]) > 45 else q["query"]
        print(f"{i:<3} {query_short:<45} {target_short:<40} {keywords_str:<25}")

    print("\n" + "=" * 120)
    print("\nAcceptance Criteria:")
    print("  - evidence ≥ 1")
    print("  - text에 expected_keywords 중 ≥1개 포함")
    print()
