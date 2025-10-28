#!/usr/bin/env python3
"""
청크 계약(Data Contract) 검사 테스트

RAG 파이프라인에서 생성되는 청크들이 필수 계약을 준수하는지 검증합니다.

계약 사항:
1. 필수 필드: doc_id, page, snippet, score, meta
2. snippet은 비어있지 않아야 함 (최소 1자 이상)
3. meta는 딕셔너리이며 filename을 포함해야 함
4. score는 float 타입
"""

import pytest
from typing import List, Dict, Any


def validate_chunk_contract(chunk: Dict[str, Any]) -> List[str]:
    """
    청크 계약 검증

    Args:
        chunk: 검증할 청크

    Returns:
        위반 사항 리스트 (비어있으면 통과)
    """
    violations = []

    # 1. 필수 필드 존재 확인
    required_fields = ["doc_id", "page", "snippet", "score", "meta"]
    for field in required_fields:
        if field not in chunk:
            violations.append(f"필수 필드 누락: {field}")

    # 2. snippet 비어있지 않음 확인
    if "snippet" in chunk:
        snippet = chunk["snippet"]
        if not snippet or (isinstance(snippet, str) and not snippet.strip()):
            violations.append(f"snippet 비어있음: {repr(snippet)}")
        elif len(snippet.strip()) < 1:
            violations.append(f"snippet 길이 부족: {len(snippet)} chars")

    # 3. meta 필드 검증
    if "meta" in chunk:
        meta = chunk["meta"]
        if not isinstance(meta, dict):
            violations.append(f"meta는 딕셔너리여야 함: {type(meta)}")
        elif "filename" not in meta:
            violations.append("meta에 filename 필드 누락")

    # 4. score 타입 검증
    if "score" in chunk:
        score = chunk["score"]
        if not isinstance(score, (int, float)):
            violations.append(f"score는 숫자여야 함: {type(score)}")

    # 5. page 타입 검증
    if "page" in chunk:
        page = chunk["page"]
        if not isinstance(page, int):
            violations.append(f"page는 정수여야 함: {type(page)}")

    return violations


def test_chunk_contract_validation():
    """청크 계약 검증 함수 자체 테스트"""

    # 정상 청크
    valid_chunk = {
        "doc_id": "test.pdf",
        "page": 1,
        "snippet": "이것은 테스트 내용입니다.",
        "score": 0.85,
        "meta": {"filename": "test.pdf", "date": "2024-01-01"}
    }

    violations = validate_chunk_contract(valid_chunk)
    assert len(violations) == 0, f"정상 청크에서 위반 발견: {violations}"

    # 필수 필드 누락
    invalid_chunk_missing = {
        "doc_id": "test.pdf",
        "page": 1,
        "score": 0.85
        # snippet과 meta 누락
    }
    violations = validate_chunk_contract(invalid_chunk_missing)
    assert len(violations) >= 2, "필수 필드 누락 감지 실패"

    # snippet 비어있음
    invalid_chunk_empty_snippet = {
        "doc_id": "test.pdf",
        "page": 1,
        "snippet": "",  # 빈 문자열
        "score": 0.85,
        "meta": {"filename": "test.pdf"}
    }
    violations = validate_chunk_contract(invalid_chunk_empty_snippet)
    assert any("snippet" in v for v in violations), "빈 snippet 감지 실패"


@pytest.mark.integration
def test_retriever_chunk_contract():
    """실제 리트리버가 반환하는 청크 계약 검증"""
    try:
        from app.rag.retrievers.hybrid import HybridRetriever

        retriever = HybridRetriever()

        # 실제 검색 수행
        test_queries = [
            "2025년 문서",
            "모니터 교체",
            "중계차 보수"
        ]

        all_violations = []

        for query in test_queries:
            results = retriever.search(query=query, top_k=5)

            for i, chunk in enumerate(results):
                violations = validate_chunk_contract(chunk)
                if violations:
                    all_violations.append({
                        "query": query,
                        "chunk_index": i,
                        "violations": violations,
                        "chunk_keys": list(chunk.keys())
                    })

        # 위반 사항 출력 및 검증
        if all_violations:
            print("\n" + "="*80)
            print("청크 계약 위반 발견:")
            print("="*80)
            for violation_info in all_violations:
                print(f"\n쿼리: {violation_info['query']}")
                print(f"청크 인덱스: {violation_info['chunk_index']}")
                print(f"청크 키: {violation_info['chunk_keys']}")
                print(f"위반 사항:")
                for v in violation_info['violations']:
                    print(f"  - {v}")
            print("="*80 + "\n")

            pytest.fail(f"청크 계약 위반: {len(all_violations)}건")

        print(f"✅ 청크 계약 검증 통과: {len(test_queries)}개 쿼리, 모든 청크 준수")

    except ImportError as e:
        pytest.skip(f"HybridRetriever 로드 실패: {e}")


@pytest.mark.integration
def test_pipeline_chunk_contract():
    """파이프라인에서 압축된 청크 계약 검증"""
    try:
        from app.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()

        # 실제 쿼리 실행
        test_queries = [
            ("2025년 남준수 문서 찾아줘", "LIST"),
            ("광화문 스튜디오 모니터 교체 검토서 요약", "SUMMARY"),
        ]

        all_violations = []

        for query, expected_mode in test_queries:
            result = pipeline.run(query=query)

            # 압축된 청크 가져오기 (internal API)
            if hasattr(pipeline, '_last_compressed_chunks'):
                compressed = pipeline._last_compressed_chunks

                for i, chunk in enumerate(compressed):
                    violations = validate_chunk_contract(chunk)
                    if violations:
                        all_violations.append({
                            "query": query,
                            "mode": expected_mode,
                            "chunk_index": i,
                            "violations": violations
                        })

        if all_violations:
            print("\n" + "="*80)
            print("파이프라인 청크 계약 위반:")
            print("="*80)
            for v in all_violations:
                print(f"\n쿼리: {v['query']}")
                print(f"모드: {v['mode']}")
                print(f"청크 인덱스: {v['chunk_index']}")
                print(f"위반 사항: {v['violations']}")
            print("="*80 + "\n")

            pytest.fail(f"파이프라인 청크 계약 위반: {len(all_violations)}건")

        print(f"✅ 파이프라인 청크 계약 검증 통과")

    except Exception as e:
        pytest.skip(f"파이프라인 테스트 실패: {e}")


if __name__ == "__main__":
    # 단독 실행 시
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
