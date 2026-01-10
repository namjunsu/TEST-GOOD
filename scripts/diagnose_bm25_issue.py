#!/usr/bin/env python3
"""BM25 인덱스 상태 진단 스크립트

Document 모드에서 BM25 청크 로딩이 제대로 작동하는지 확인합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_system.active.bm25_store import BM25Store
from config.constants import HybridRetrieverConfig


def diagnose_bm25():
    """BM25 인덱스 상태 진단"""

    print("=" * 80)
    print("BM25 인덱스 진단")
    print("=" * 80)

    # 1. 인덱스 파일 존재 확인
    index_path = HybridRetrieverConfig.DEFAULT_BM25_INDEX_PATH
    index_file = Path(index_path)

    print(f"\n[1] 인덱스 파일 확인")
    print(f"   경로: {index_path}")
    print(f"   존재: {index_file.exists()}")

    if index_file.exists():
        size_mb = index_file.stat().st_size / (1024 * 1024)
        print(f"   크기: {size_mb:.2f} MB")
    else:
        print("   ❌ 인덱스 파일이 존재하지 않습니다!")
        print(f"   생성 방법: python scripts/indexing/rebuild_bm25.py")
        return

    # 2. BM25Store 로드
    print(f"\n[2] BM25Store 로드")
    try:
        bm25_store = BM25Store(index_path=index_path)
        print(f"   ✅ 로드 성공")
        print(f"   총 문서 수: {len(bm25_store.documents)}")
        print(f"   총 메타데이터 수: {len(bm25_store.metadata)}")
    except Exception as e:
        print(f"   ❌ 로드 실패: {e}")
        return

    # 3. 메타데이터 구조 분석
    print(f"\n[3] 메타데이터 구조 분석")

    if not bm25_store.metadata:
        print("   ❌ 메타데이터가 비어있습니다!")
        return

    # 첫 5개 메타데이터 샘플
    print(f"   샘플 메타데이터 (처음 5개):")
    for i, meta in enumerate(bm25_store.metadata[:5]):
        print(f"\n   [{i}]")
        print(f"      filename: {meta.get('filename', 'N/A')}")
        print(f"      doc_id: {meta.get('doc_id', 'N/A')}")
        print(f"      page: {meta.get('page', 'N/A')}")
        print(f"      keys: {list(meta.keys())}")

    # 4. filename 필드 확인
    print(f"\n[4] filename 필드 통계")

    filenames = set()
    has_filename = 0

    for meta in bm25_store.metadata:
        if meta.get("filename"):
            has_filename += 1
            filenames.add(meta.get("filename"))

    print(f"   filename 있는 청크: {has_filename}/{len(bm25_store.metadata)} ({has_filename/len(bm25_store.metadata)*100:.1f}%)")
    print(f"   고유 파일 수: {len(filenames)}")

    # 상위 10개 파일
    filename_counts = {}
    for meta in bm25_store.metadata:
        fn = meta.get("filename")
        if fn:
            filename_counts[fn] = filename_counts.get(fn, 0) + 1

    print(f"\n   상위 10개 파일 (청크 수):")
    for fn, count in sorted(filename_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"      {fn}: {count}개 청크")

    # 5. 특정 문서 테스트 (로그에서 확인된 문서)
    print(f"\n[5] 특정 문서 청크 검색 테스트")

    test_filenames = [
        "2025-08-13_TVLogic.pdf",
        "2025-08-13_TVLogic.txt",
    ]

    for test_fn in test_filenames:
        print(f"\n   테스트: {test_fn}")

        chunks = []
        for i, meta in enumerate(bm25_store.metadata):
            if meta.get("filename") == test_fn:
                content = bm25_store.documents[i]
                if content and len(content.strip()) > 0:
                    chunks.append({
                        "index": i,
                        "length": len(content),
                        "preview": content[:100]
                    })

        print(f"      발견된 청크: {len(chunks)}개")

        if chunks:
            print(f"      첫 번째 청크 미리보기:")
            print(f"         길이: {chunks[0]['length']}자")
            print(f"         내용: {chunks[0]['preview']}...")
        else:
            print(f"      ⚠️  청크를 찾지 못했습니다!")

    # 6. Document 핸들러의 _make_chunks_for_doc() 시뮬레이션
    print(f"\n[6] _make_chunks_for_doc() 로직 시뮬레이션")

    target_filename = "2025-08-13_TVLogic.pdf"
    print(f"   대상 파일: {target_filename}")

    # 핸들러 로직 복제
    chunks = []
    for i, meta in enumerate(bm25_store.metadata):
        if meta.get("filename") == target_filename:
            content = bm25_store.documents[i]
            if content and len(content.strip()) > 0:
                chunks.append({
                    "doc_id": target_filename,
                    "page": 1,
                    "text": content,
                    "score": 1.0,
                    "filename": target_filename,
                })

    print(f"   결과: {len(chunks)}개 청크")

    if chunks:
        total_chars = sum(len(c["text"]) for c in chunks)
        print(f"   총 문자 수: {total_chars:,}자")
        print(f"   평균 청크 크기: {total_chars/len(chunks):.0f}자")

        # 조립 시뮬레이션
        max_chars = 12000
        parts = []
        total_len = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            if total_len + len(text) > max_chars:
                remaining = max_chars - total_len
                if remaining > 0:
                    parts.append(text[:remaining])
                break
            parts.append(text)
            total_len += len(text)

        result = "\n\n".join(parts)
        print(f"   조립 후 길이: {len(result)}자 (제한: {max_chars}자)")
        print(f"   사용된 청크: {len(parts)}/{len(chunks)}개")
        print(f"   ✅ 청크 기반 로딩 가능!")
    else:
        print(f"   ❌ 청크를 찾지 못했습니다!")
        print(f"   가능한 원인:")
        print(f"      - filename 필드 불일치 (.pdf vs .txt)")
        print(f"      - BM25 인덱스 재구축 필요")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        diagnose_bm25()
    except Exception as e:
        print(f"\n❌ 진단 실패: {e}")
        import traceback
        traceback.print_exc()
