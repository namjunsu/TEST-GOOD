#!/usr/bin/env python3
"""
RAG 시스템 진단 스크립트
문제점을 체계적으로 파악
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

def check_environment():
    """환경 변수 확인"""
    print("=" * 80)
    print("1. 환경 변수 설정 확인")
    print("=" * 80)

    env_vars = [
        'USE_V2_RETRIEVER',
        'SEARCH_VECTOR_WEIGHT',
        'SEARCH_BM25_WEIGHT',
        'DIAG_RAG',
        'DIAG_LOG_LEVEL',
    ]

    for var in env_vars:
        value = os.getenv(var, 'NOT SET')
        print(f"  {var}: {value}")
    print()

def check_indexes():
    """인덱스 파일 확인"""
    print("=" * 80)
    print("2. 인덱스 파일 상태 확인")
    print("=" * 80)

    # V1 인덱스
    print("  [V1 인덱스]")
    v1_files = [
        'rag_system/db/bm25_index.pkl',
        'rag_system/db/korean_vector_index.faiss',
        'rag_system/db/korean_vector_index.metadata.pkl',
    ]

    for file_path in v1_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size / (1024 * 1024)  # MB
            print(f"    ✓ {file_path}: {size:.2f} MB")
        else:
            print(f"    ✗ {file_path}: 없음")

    # V2 인덱스
    print("\n  [V2 인덱스]")
    v2_dirs = [
        'indexes_v2/bm25',
        'indexes_v2/faiss',
    ]

    for dir_path in v2_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            files = list(path.glob('*'))
            print(f"    ✓ {dir_path}: {len(files)}개 파일")
            for f in files[:3]:  # 처음 3개만
                size = f.stat().st_size / (1024 * 1024)  # MB
                print(f"      - {f.name}: {size:.2f} MB")
        else:
            print(f"    ✗ {dir_path}: 없음")
    print()

def check_retriever():
    """Retriever 초기화 테스트"""
    print("=" * 80)
    print("3. Retriever 초기화 테스트")
    print("=" * 80)

    try:
        from app.rag.pipeline import RAGPipeline

        print("  RAGPipeline 초기화 중...")
        pipeline = RAGPipeline()
        print("  ✓ RAGPipeline 초기화 성공")

        # Retriever 타입 확인
        retriever = pipeline.retriever
        print(f"  Retriever 타입: {type(retriever).__name__}")

        # V2 어댑터인지 확인
        if hasattr(retriever, '_impl'):
            impl_type = type(retriever._impl).__name__ if retriever._impl else "None"
            print(f"  내부 구현 타입: {impl_type}")

        return pipeline
    except Exception as e:
        print(f"  ✗ RAGPipeline 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_search(pipeline):
    """검색 테스트"""
    print("\n" + "=" * 80)
    print("4. 검색 기능 테스트")
    print("=" * 80)

    if not pipeline:
        print("  Pipeline이 없어서 테스트 불가")
        return

    test_queries = [
        "카메라",
        "DVR",
        "워크스테이션",
    ]

    for query in test_queries:
        print(f"\n  테스트 질문: '{query}'")
        print("  " + "-" * 76)

        try:
            # 검색만 수행 (LLM 생성 제외)
            results = pipeline.retriever.search(query, top_k=3)

            print(f"  검색 결과: {len(results)}개")

            if results:
                for i, result in enumerate(results[:3], 1):
                    doc_id = result.get('doc_id', 'unknown')
                    score = result.get('score', 0.0)
                    snippet = result.get('snippet', '')[:100]
                    print(f"    {i}. {doc_id}")
                    print(f"       점수: {score:.4f}")
                    print(f"       미리보기: {snippet}...")
            else:
                print("    ⚠️ 검색 결과 없음!")

        except Exception as e:
            print(f"  ✗ 검색 실패: {e}")
            import traceback
            traceback.print_exc()

def test_full_rag(pipeline):
    """전체 RAG 파이프라인 테스트"""
    print("\n" + "=" * 80)
    print("5. 전체 RAG 파이프라인 테스트")
    print("=" * 80)

    if not pipeline:
        print("  Pipeline이 없어서 테스트 불가")
        return

    test_query = "카메라 수리"
    print(f"\n  테스트 질문: '{test_query}'")
    print("  " + "-" * 76)

    try:
        # answer() 메서드 사용 (검색 + 생성)
        result = pipeline.answer(test_query, top_k=3)

        print(f"  답변 생성 성공")
        print(f"  답변 길이: {len(result.get('text', ''))} 글자")
        print(f"  Evidence 개수: {len(result.get('evidence', []))} 개")

        # 진단 정보 출력
        if result.get('diagnostics'):
            diag = result['diagnostics']
            print(f"\n  [진단 정보]")
            print(f"    모드: {diag.get('mode', 'unknown')}")
            print(f"    검색 문서 수: {diag.get('retrieved_k', 0)}")
            print(f"    압축 후 문서 수: {diag.get('after_compress_k', 0)}")
            print(f"    Evidence 개수: {diag.get('evidence_count', 0)}")
            print(f"    Evidence 강제 주입: {diag.get('evidence_injected', False)}")

        print(f"\n  답변 미리보기:")
        print(f"  {result.get('text', '')[:300]}...")

        print(f"\n  Evidence:")
        for i, ev in enumerate(result.get('evidence', [])[:3], 1):
            doc_id = ev.get('doc_id', 'unknown')
            snippet = ev.get('snippet', '')[:100]
            print(f"    {i}. {doc_id}")
            print(f"       {snippet}...")

    except Exception as e:
        print(f"  ✗ RAG 파이프라인 실패: {e}")
        import traceback
        traceback.print_exc()

def check_metadata_db():
    """메타데이터 DB 확인"""
    print("\n" + "=" * 80)
    print("6. 메타데이터 DB 확인")
    print("=" * 80)

    try:
        from app.data.metadata.db import MetadataDB

        db = MetadataDB()
        print("  ✓ MetadataDB 초기화 성공")

        # 문서 개수 확인
        count = db.count_all()
        print(f"  총 문서 개수: {count}개")

        # 샘플 문서 확인
        if count > 0:
            sample_docs = db.get_all_metadata(limit=3)
            print(f"\n  샘플 문서:")
            for doc in sample_docs:
                print(f"    - {doc.get('doc_id', 'unknown')}: {doc.get('filename', 'unknown')}")

    except Exception as e:
        print(f"  ✗ MetadataDB 확인 실패: {e}")
        import traceback
        traceback.print_exc()

def main():
    """메인 함수"""
    print("\n")
    print("█" * 80)
    print("  RAG 시스템 진단")
    print("█" * 80)
    print()

    # 1. 환경 변수 확인
    check_environment()

    # 2. 인덱스 파일 확인
    check_indexes()

    # 3. Retriever 초기화 테스트
    pipeline = check_retriever()

    # 4. 검색 테스트
    test_search(pipeline)

    # 5. 전체 RAG 파이프라인 테스트
    test_full_rag(pipeline)

    # 6. 메타데이터 DB 확인
    check_metadata_db()

    print("\n" + "=" * 80)
    print("진단 완료")
    print("=" * 80)

if __name__ == "__main__":
    main()
