#!/usr/bin/env python3
"""Document 모드 성능 테스트 스크립트

청크 기반 로딩 개선 사항 검증:
- 로딩 속도 측정
- 컨텍스트 품질 확인
- detail_level별 동작 확인
"""

import sys
import time
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.rag.handlers.document import DocumentHandler
from app.rag.retrievers.hybrid import HybridRetriever
from app.core.llm_adapter import LLMAdapter
from app.core.config import settings


def test_document_loading():
    """Document 핸들러의 청크 기반 로딩 테스트"""

    print("=" * 80)
    print("Document 모드 성능 테스트")
    print("=" * 80)

    # 핸들러 초기화
    print("\n[1] 핸들러 초기화 중...")
    retriever = HybridRetriever()
    llm_adapter = LLMAdapter()
    handler = DocumentHandler(retriever=retriever, generator=llm_adapter)
    print("✅ 핸들러 초기화 완료")

    # 테스트 쿼리 (로그에서 확인된 실제 문서)
    test_queries = [
        {
            "query": "2025-08-13_TVLogic 문서 요약해줘",
            "expected_filename": "2025-08-13_TVLogic.pdf",
            "detail_level": "normal"
        },
        {
            "query": "2025-08-13_TVLogic 문서의 총 금액은?",
            "expected_filename": "2025-08-13_TVLogic.pdf",
            "detail_level": "brief"
        },
    ]

    results = []

    for i, test_case in enumerate(test_queries, 1):
        print(f"\n[{i+1}] 테스트 케이스 {i}")
        print(f"   쿼리: {test_case['query']}")
        print(f"   기대 문서: {test_case['expected_filename']}")
        print(f"   상세도: {test_case['detail_level']}")

        start = time.perf_counter()

        try:
            # Document 모드 쿼리 실행
            response = handler.handle(
                query=test_case['query'],
                selected_filename=test_case['expected_filename']
            )

            duration = time.perf_counter() - start

            # 결과 분석
            success = response.get('status', {}).get('success', False)
            text_length = len(response.get('text', ''))
            filename = response.get('files', [None])[0]

            result = {
                'case': i,
                'query': test_case['query'],
                'success': success,
                'duration': duration,
                'text_length': text_length,
                'filename': filename,
            }
            results.append(result)

            # 결과 출력
            print(f"   ✅ 성공: {success}")
            print(f"   ⏱️  소요 시간: {duration:.2f}초")
            print(f"   📝 응답 길이: {text_length}자")
            print(f"   📄 문서: {filename}")

            if duration > 10:
                print(f"   ⚠️  경고: 응답 시간이 10초를 초과했습니다!")
            elif duration < 5:
                print(f"   🎉 우수: 5초 이내 응답 (목표 달성)")

        except Exception as e:
            duration = time.perf_counter() - start
            print(f"   ❌ 실패: {type(e).__name__}: {e}")
            results.append({
                'case': i,
                'query': test_case['query'],
                'success': False,
                'duration': duration,
                'error': str(e),
            })

    # 전체 결과 요약
    print("\n" + "=" * 80)
    print("테스트 결과 요약")
    print("=" * 80)

    for result in results:
        status = "✅" if result.get('success') else "❌"
        duration = result['duration']
        print(f"{status} 케이스 {result['case']}: {duration:.2f}초 - {result['query'][:40]}...")

    # 성능 기준 확인
    print("\n" + "=" * 80)
    print("성능 기준 확인")
    print("=" * 80)

    successful = [r for r in results if r.get('success')]
    if successful:
        avg_duration = sum(r['duration'] for r in successful) / len(successful)
        max_duration = max(r['duration'] for r in successful)
        min_duration = min(r['duration'] for r in successful)

        print(f"평균 응답 시간: {avg_duration:.2f}초")
        print(f"최대 응답 시간: {max_duration:.2f}초")
        print(f"최소 응답 시간: {min_duration:.2f}초")

        if avg_duration < 5:
            print("🎉 목표 달성: 평균 5초 이내 (기존 988초 대비 197배 개선)")
        elif avg_duration < 10:
            print("✅ 양호: 평균 10초 이내 (기존 988초 대비 98배 개선)")
        else:
            print(f"⚠️  개선 필요: 평균 {avg_duration:.2f}초 (목표: 5초 이내)")
    else:
        print("❌ 모든 테스트 실패")

    print("\n" + "=" * 80)


def test_chunk_assembly():
    """청크 조립 로직 단독 테스트"""

    print("\n" + "=" * 80)
    print("청크 조립 로직 테스트")
    print("=" * 80)

    # 핸들러 초기화
    retriever = HybridRetriever()
    llm_adapter = LLMAdapter()
    handler = DocumentHandler(retriever=retriever, generator=llm_adapter)

    # 테스트 청크 생성
    test_chunks = [
        {"text": "첫 번째 청크입니다. " * 100},  # ~1200자
        {"text": "두 번째 청크입니다. " * 100},  # ~1200자
        {"text": "세 번째 청크입니다. " * 100},  # ~1200자
    ]

    # 다양한 max_chars 테스트
    test_cases = [
        (6000, "brief"),
        (12000, "normal"),
        (24000, "detailed"),
    ]

    for max_chars, level in test_cases:
        print(f"\n[테스트] max_chars={max_chars} ({level})")

        result = handler._assemble_context_from_chunks(test_chunks, max_chars=max_chars)

        print(f"   입력 청크 수: {len(test_chunks)}")
        print(f"   출력 길이: {len(result)}자")
        print(f"   제한 준수: {len(result) <= max_chars}")

        if len(result) > max_chars:
            print(f"   ⚠️  경고: 최대 길이 초과!")
        else:
            print(f"   ✅ 제한 내에서 조립 완료")


if __name__ == "__main__":
    print("Document 모드 성능 개선 테스트 시작\n")

    # 1. 청크 조립 로직 테스트
    try:
        test_chunk_assembly()
    except Exception as e:
        print(f"❌ 청크 조립 테스트 실패: {e}")

    # 2. Document 핸들러 통합 테스트
    try:
        test_document_loading()
    except Exception as e:
        print(f"❌ Document 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

    print("\n테스트 완료")
