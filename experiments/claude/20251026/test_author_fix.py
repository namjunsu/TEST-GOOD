#!/usr/bin/env python3
"""저자 검색 수정 검증 테스트"""

import sys
sys.path.insert(0, "/home/wnstn4647/AI-CHAT")

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from app.rag.pipeline import RAGPipeline

print("=" * 80)
print("저자 검색 수정 검증 테스트")
print("=" * 80)

p = RAGPipeline()

# 테스트 쿼리: 스크린샷에서 보인 쿼리
test_queries = [
    "남준수 기안자",
    "남준수가 작성한 문서",
    "기안자 남준수",
]

for q in test_queries:
    print(f"\n질문: '{q}'")
    print("-" * 80)

    # 1. Retriever 검색 결과 확인
    retrieved = p.retriever.search(q, top_k=5)
    print(f"✅ Retriever: {len(retrieved)}개 문서 검색됨")

    if retrieved:
        for i, r in enumerate(retrieved[:3], 1):
            print(f"  {i}. {r.get('doc_id', 'unknown')}: {r.get('snippet', '')[:100]}...")

    # 2. Answer 생성 결과 확인
    result = p.answer(q, top_k=5)
    answer_text = result.get("text", "")
    evidence = result.get("evidence", [])

    print(f"\n✅ Evidence: {len(evidence)}개")
    print(f"✅ Answer 길이: {len(answer_text)}자")

    # 3. "없음" 메시지 체크
    has_no_doc_message = any(phrase in answer_text for phrase in [
        "제공된 문서가 없",
        "관련 문서를 찾을 수 없",
        "문서에서 찾을 수 없",
    ])

    if has_no_doc_message and len(retrieved) > 0:
        print(f"❌ 오류: 검색 성공({len(retrieved)}개)했지만 '없음' 메시지 출력!")
        print(f"   Answer: {answer_text[:200]}...")
    elif not has_no_doc_message and len(retrieved) > 0:
        print(f"✅ 정상: 검색 성공 + 답변 생성")
        print(f"   Answer: {answer_text[:200]}...")
    elif len(retrieved) == 0:
        print(f"⚠️  검색 실패 (결과 0개)")

    print("=" * 80)

print("\n테스트 완료")
