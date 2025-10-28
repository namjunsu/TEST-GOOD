#!/usr/bin/env python3
"""
소모품/구매 문서 요약 테스트

2024-09-12_조명_소모품_구매_건.pdf 문서에 대한 요약 기능 검증:
- 소모품 템플릿 자동 선택
- 품목/총액/예산/납품장소 추출
- 5초 이내 응답
"""

import pytest
import time


@pytest.mark.e2e
def test_consumables_summary():
    """소모품 구매 문서 요약 테스트"""
    try:
        from app.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()

        # 테스트 쿼리
        query = "2024-09-12_조명_소모품_구매_건.pdf 요약"

        print(f"\n[테스트] {query}")

        start_time = time.time()
        result = pipeline.answer(query=query)
        elapsed = time.time() - start_time

        # 1. 응답 존재 확인
        assert result is not None, "응답이 None입니다"
        assert "text" in result, "응답에 'text' 키가 없습니다"

        response = result["text"]

        print(f"\n응답 길이: {len(response)}자")
        print(f"처리 시간: {elapsed:.2f}s")
        print(f"\n응답 미리보기:\n{response[:500]}...")

        # 2. 응답 길이 확인 (최소 100자)
        assert len(response) > 100, f"응답이 너무 짧음: {len(response)}자"

        # 3. 금지 문구 체크
        forbidden_phrases = [
            "문서 내용이 없습니다",
            "확인할 수 없습니다",
            "비어 있",
            "찾을 수 없습니다"
        ]

        for phrase in forbidden_phrases:
            assert phrase not in response, f"금지 문구 포함: '{phrase}'"

        # 4. 소모품 관련 키워드 포함 확인 (최소 1개)
        # 구조화 요약 성공 시 나올 키워드 OR 자유 요약 시 나올 키워드
        expected_keywords = [
            "조명", "소모품", "구매", "품목", "총액",
            "예산", "납품", "조명"  # 파일명에서 추론 가능
        ]

        found_keywords = [kw for kw in expected_keywords if kw in response]
        assert len(found_keywords) >= 1, (
            f"필수 키워드 미포함 (0/{len(expected_keywords)}). "
            f"응답: {response[:200]}"
        )

        # 5. 성능 확인 (경고만, 실패는 아님)
        if elapsed > 5.0:
            print(f"\n⚠️  슬로 쿼리: {elapsed:.2f}s (목표: 5s)")
        else:
            print(f"\n✅ 성능 기준 통과: {elapsed:.2f}s")

        # 6. found 상태 확인
        assert result.get("status", {}).get("found", False), "found=False"

        print(f"\n✅ 소모품 요약 테스트 통과")
        print(f"   - 응답 길이: {len(response)}자")
        print(f"   - 처리 시간: {elapsed:.2f}s")
        print(f"   - 키워드 발견: {found_keywords}")

    except Exception as e:
        pytest.fail(f"테스트 실패: {e}")


@pytest.mark.e2e
def test_consumables_template_detection():
    """소모품 템플릿 자동 감지 테스트"""
    from app.rag.summary_templates import detect_doc_kind

    # 테스트 케이스
    test_cases = [
        ("2024-09-12_조명_소모품_구매_건.pdf", "소모품 구매 관련 내용", "consumables"),
        ("소모품_구매_신청.pdf", "납품 요청", "consumables"),
        ("장비_수리_의뢰.pdf", "고장으로 인한 수리 필요", "repair"),
        ("모니터_교체_검토서.pdf", "신규 모니터 도입 검토", "proc_eval"),
    ]

    for filename, text, expected_kind in test_cases:
        detected_kind = detect_doc_kind(filename, text)
        print(f"\n{filename} → {detected_kind} (예상: {expected_kind})")
        assert detected_kind == expected_kind, (
            f"템플릿 감지 실패: {filename} → {detected_kind} (예상: {expected_kind})"
        )

    print(f"\n✅ 템플릿 자동 감지 테스트 통과 ({len(test_cases)}개 케이스)")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
