#!/usr/bin/env python3
"""
BM25 검색 결과 중복 제거 테스트

조건:
- 동일 doc_id(DB PK), 서로 다른 chunk_id → 결과에서는 1개만 남아야 함
- id는 정수 DB PK 필수

2025-11-28: _resolve_doc_id 인터페이스 변경 반영 (id=DB PK 필수)
"""

import sys
import shutil
from pathlib import Path
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

import pytest
from rag_system.active.bm25_store import BM25Store


def _make_clean_store(tmp_path: Path) -> BM25Store:
    """임시 디렉터리에 깨끗한 BM25 인덱스 생성"""
    index_dir = tmp_path / "var" / "index"
    shutil.rmtree(index_dir, ignore_errors=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    index_path = index_dir / "bm25_dedup_test.pkl"
    store = BM25Store(index_path=str(index_path))
    return store


def _add_background_docs(bm25: BM25Store) -> None:
    """IDF 계산을 위한 배경 문서 추가 (희소성 확보)

    BM25 IDF는 log((N-df+0.5)/(df+0.5))로 계산됨.
    문서 수가 적으면 고빈도 토큰의 IDF가 0이 되어 검색 실패.
    최소 5개 이상의 배경 문서가 필요.
    """
    background_texts = [
        "서버실 냉각장치 점검 보고서입니다.",
        "네트워크 장비 교체 계획서입니다.",
        "보안 시스템 유지보수 안내문입니다.",
        "전력 설비 정기점검 결과입니다.",
        "통신 장비 업그레이드 제안서입니다.",
    ]
    background_metadatas = [
        {"id": 9001, "filename": "bg1.pdf"},
        {"id": 9002, "filename": "bg2.pdf"},
        {"id": 9003, "filename": "bg3.pdf"},
        {"id": 9004, "filename": "bg4.pdf"},
        {"id": 9005, "filename": "bg5.pdf"},
    ]
    bm25.add_documents(background_texts, background_metadatas)


def test_bm25_dedup_by_doc_id(tmp_path=Path("/tmp/bm25_test")):
    """동일 doc_id를 가진 결과가 중복으로 나오지 않는지 확인"""

    print("=" * 70)
    print("테스트 1: doc_id 기준 중복 제거")
    print("=" * 70)

    bm25 = _make_clean_store(tmp_path)
    _add_background_docs(bm25)  # IDF 희소성 확보

    texts = [
        "광화문 스튜디오 PGM 모니터 수리 검토입니다.",
        "광화문 스튜디오 PGM 모니터 교체 검토입니다.",  # 같은 문서의 다른 chunk라고 가정
        "데이터센터 NQC 모니터 교체 검토입니다.",
    ]

    # id는 정수 DB PK 필수
    metadatas = [
        {
            "id": 1001,  # DB PK (정수)
            "chunk_id": "chunk_1",
            "filename": "2025-03-01_PGM모니터_수리검토.pdf",
        },
        {
            "id": 1001,  # 동일 문서(동일 DB PK), 다른 chunk
            "chunk_id": "chunk_2",
            "filename": "2025-03-01_PGM모니터_수리검토.pdf",
        },
        {
            "id": 1002,  # 다른 문서
            "chunk_id": "chunk_1",
            "filename": "2025-03-02_NQC모니터_교체검토.pdf",
        },
    ]

    bm25.add_documents(texts, metadatas)
    results = bm25.search("PGM 모니터", top_k=10)

    print(f"검색 쿼리: 'PGM 모니터'")
    print(f"인덱싱된 문서: {len(texts)}개")
    print(f"검색 결과: {len(results)}개")

    # 결과 출력
    for i, r in enumerate(results, 1):
        doc_id = r.get("id", "없음")
        filename = r.get("filename", "없음")
        score = r.get("score", 0)
        print(f"  {i}. doc_id={doc_id}, score={score:.3f}, file={filename}")

    # 1) 결과 개수: id=1001은 1개만 나와야 함
    # Note: BM25Store는 내부적으로 id를 문자열로 정규화
    doc_ids = [r.get("id") for r in results]

    pgm_count = doc_ids.count("1001")  # 문자열로 비교

    if pgm_count == 1:
        print("✅ PASS: id=1001이 1개만 나옴 (중복 제거 성공)")
    else:
        print(f"❌ FAIL: id=1001이 {pgm_count}개 나옴 (중복 제거 실패)")

    assert pgm_count == 1, f"중복 제거 실패: id=1001이 {pgm_count}번 나옴"

    print()


def test_bm25_dedup_same_id_different_chunks(tmp_path=Path("/tmp/bm25_test2")):
    """동일 id(DB PK)를 가진 여러 청크가 1개로 중복 제거되는지 확인"""

    print("=" * 70)
    print("테스트 2: 동일 id, 다른 chunk 중복 제거")
    print("=" * 70)

    bm25 = _make_clean_store(tmp_path)
    _add_background_docs(bm25)  # IDF 희소성 확보

    texts = [
        "Livestream Studio 장비 수리 검토입니다.",
        "Livestream Studio 장비 교체 검토입니다.",  # 같은 파일의 다른 chunk
        "다른 스튜디오 장비 검토입니다.",
    ]

    # id는 정수 DB PK 필수
    metadatas = [
        {
            "id": 2001,
            "chunk_id": "chunk_1",
            "filename": "2025-03-03_LS_장비_수리_검토.pdf",
        },
        {
            "id": 2001,  # 동일 id
            "chunk_id": "chunk_2",
            "filename": "2025-03-03_LS_장비_수리_검토.pdf",
        },
        {
            "id": 2002,
            "chunk_id": "chunk_3",
            "filename": "2025-03-04_기타_장비_검토.pdf",
        },
    ]

    bm25.add_documents(texts, metadatas)
    results = bm25.search("Livestream Studio", top_k=10)

    print(f"검색 쿼리: 'Livestream Studio'")
    print(f"인덱싱된 문서: {len(texts)}개")
    print(f"검색 결과: {len(results)}개")

    # 결과 출력
    for i, r in enumerate(results, 1):
        doc_id = r.get("id", "없음")
        filename = r.get("filename", "없음")
        chunk_id = r.get("chunk_id", "없음")
        score = r.get("score", 0)
        print(f"  {i}. id={doc_id}, filename={filename}, chunk={chunk_id}, score={score:.3f}")

    doc_ids = [r.get("id") for r in results]
    ls_count = doc_ids.count("2001")  # 문자열로 비교

    if ls_count == 1:
        print("✅ PASS: id=2001이 1개만 나옴 (중복 제거 성공)")
    else:
        print(f"❌ FAIL: id=2001이 {ls_count}개 나옴 (중복 제거 실패)")

    assert ls_count == 1, f"중복 제거 실패: id=2001이 {ls_count}번 나옴"

    print()


def test_bm25_dedup_multiple_docs(tmp_path=Path("/tmp/bm25_test3")):
    """여러 문서의 중복 제거 테스트"""

    print("=" * 70)
    print("테스트 3: 여러 문서 중복 제거")
    print("=" * 70)

    bm25 = _make_clean_store(tmp_path)
    _add_background_docs(bm25)  # IDF 희소성 확보

    texts = [
        "DVR 시스템 교체 검토서 첫 번째 페이지",
        "DVR 시스템 교체 검토서 두 번째 페이지",  # 같은 id
        "DVR 백업 시스템 구축",
        "DVR 백업 시스템 상세",  # 같은 id
    ]

    # id는 정수 DB PK 필수
    metadatas = [
        {"id": 3001, "filename": "DVR_교체.pdf", "page": 1},
        {"id": 3001, "filename": "DVR_교체.pdf", "page": 2},
        {"id": 3002, "filename": "DVR_백업.pdf", "page": 1},
        {"id": 3002, "filename": "DVR_백업.pdf", "page": 2},
    ]

    bm25.add_documents(texts, metadatas)
    results = bm25.search("DVR", top_k=10)

    print(f"검색 쿼리: 'DVR'")
    print(f"인덱싱된 문서: {len(texts)}개")
    print(f"검색 결과: {len(results)}개")

    # 결과 출력
    for i, r in enumerate(results, 1):
        doc_id = r.get("id", "없음")
        filename = r.get("filename", "없음")
        page = r.get("page", "없음")
        score = r.get("score", 0)
        print(f"  {i}. id={doc_id}, file={filename}, page={page}, score={score:.3f}")

    # 예상: id=3001 1개, id=3002 1개 = 총 2개
    if len(results) == 2:
        print(f"✅ PASS: 중복 제거 후 2개 문서만 남음")
    else:
        print(f"❌ FAIL: 중복 제거 실패, {len(results)}개 남음")

    assert len(results) == 2, f"중복 제거 실패: {len(results)}개 남음"

    print()


if __name__ == "__main__":
    print("\n🧪 BM25 검색 결과 중복 제거 테스트\n")

    # pytest 없이도 실행 가능한 형태
    test_bm25_dedup_by_doc_id()
    test_bm25_dedup_same_id_different_chunks()
    test_bm25_dedup_multiple_docs()

    print("=" * 70)
    print("🎉 모든 테스트 통과!")
    print("=" * 70)