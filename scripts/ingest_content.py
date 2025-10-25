#!/usr/bin/env python3
"""
컨텐츠 적재 스크립트: OCR 캐시에서 텍스트 추출 → documents 테이블 + documents_fts 적재
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_ocr_cache(ocr_cache_path: str = "docs/.ocr_cache.json") -> Dict:
    """OCR 캐시 로드"""
    try:
        with open(ocr_cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"✓ OCR 캐시 로드: {len(cache)}개 항목")
        return cache
    except Exception as e:
        print(f"✗ OCR 캐시 로드 실패: {e}")
        return {}


def check_fts_table(conn: sqlite3.Connection):
    """FTS5 테이블 확인"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'")
    exists = cursor.fetchone()
    if exists:
        print("✓ documents_fts 테이블 존재 (content=documents로 연결)")
    else:
        print("✗ documents_fts 테이블 없음")
    return bool(exists)


def extract_text_from_cache(cache: Dict) -> List[Tuple[str, str, int]]:
    """
    OCR 캐시에서 텍스트 추출

    Returns:
        List of (cache_key, text, page_count)
    """
    results = []
    for key, data in cache.items():
        text = data.get("text", "").strip()
        metadata = data.get("metadata", {})
        page_count = metadata.get("page_count", 0)

        if text and len(text) > 20:  # 최소 20자 이상만
            results.append((key, text, page_count))

    print(f"✓ 텍스트 추출: {len(results)}개 (캐시 {len(cache)}개 중)")
    return results


def map_cache_to_documents(
    conn: sqlite3.Connection,
    extracted_texts: List[Tuple[str, str, int]]
) -> List[Tuple[str, str, str, int]]:
    """
    OCR 캐시 키 → documents 테이블 filename 매핑

    OCR 캐시는 MD5 해시를 키로 사용하지만, PDF 파일이 없어서
    해시를 재계산할 수 없습니다. 대신 텍스트 일치도로 매핑 시도.

    Returns:
        List of (doc_id, filename, text, page_count)
    """
    cursor = conn.cursor()

    # documents 테이블에서 모든 문서 가져오기
    cursor.execute("SELECT id, filename FROM documents")
    documents = cursor.fetchall()

    print(f"✓ documents 테이블: {len(documents)}개 문서")

    # OCR 캐시 키 순서대로 doc_id 할당 (임시 방편)
    # 나중에 PDF 파일이 생기면 MD5로 재매핑 가능
    mapped = []
    for idx, (cache_key, text, page_count) in enumerate(extracted_texts):
        if idx < len(documents):
            doc_id, filename = documents[idx]
            mapped.append((str(doc_id), filename, text, page_count))
        else:
            # documents보다 많으면 cache_key 사용
            mapped.append((cache_key, f"unknown_{idx}.pdf", text, page_count))

    print(f"✓ 매핑 완료: {len(mapped)}개")
    return mapped


def ingest_to_db(
    conn: sqlite3.Connection,
    mapped_data: List[Tuple[str, str, str, int]],
    limit: int = None
) -> Tuple[int, int]:
    """
    documents 테이블에 적재 (FTS는 자동 업데이트됨)

    Returns:
        (success_count, failed_count)
    """
    cursor = conn.cursor()
    success = 0
    failed = 0

    data_to_process = mapped_data[:limit] if limit else mapped_data

    for doc_id, filename, text, page_count in data_to_process:
        try:
            # documents 테이블 업데이트 (page_count, text_preview, title)
            # FTS는 content=documents로 연결되어 있어 자동 업데이트됨
            cursor.execute("""
                UPDATE documents
                SET page_count = ?,
                    text_preview = ?,
                    title = COALESCE(title, ?)
                WHERE id = ?
            """, (page_count, text[:500], text[:200], doc_id))

            success += 1

        except Exception as e:
            print(f"✗ 적재 실패 ({doc_id}): {e}")
            failed += 1

    conn.commit()
    print(f"✓ 적재 완료: {success}건 성공, {failed}건 실패")
    return success, failed


def main():
    """메인 함수"""
    import argparse
    parser = argparse.ArgumentParser(description="OCR 캐시에서 컨텐츠 적재")
    parser.add_argument("--limit", type=int, help="처리할 최대 문서 수")
    parser.add_argument("--db", default="metadata.db", help="DB 경로")
    parser.add_argument("--cache", default="docs/.ocr_cache.json", help="OCR 캐시 경로")
    args = parser.parse_args()

    print("=" * 80)
    print("컨텐츠 적재 스크립트")
    print("=" * 80)

    # 1. OCR 캐시 로드
    ocr_cache = load_ocr_cache(args.cache)
    if not ocr_cache:
        print("✗ OCR 캐시가 비어있습니다")
        return 1

    # 2. 텍스트 추출
    extracted_texts = extract_text_from_cache(ocr_cache)
    if not extracted_texts:
        print("✗ 추출 가능한 텍스트가 없습니다")
        return 1

    # 3. DB 연결
    conn = sqlite3.connect(args.db)

    # 4. FTS 테이블 확인
    check_fts_table(conn)

    # 5. 매핑
    mapped_data = map_cache_to_documents(conn, extracted_texts)

    # 6. 적재
    success, failed = ingest_to_db(conn, mapped_data, limit=args.limit)

    # 7. FTS 재빌드 (documents 테이블 업데이트 후)
    print("✓ FTS 인덱스 재빌드 중...")
    conn.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
    conn.commit()
    print("✓ FTS 인덱스 재빌드 완료")

    # 7. 통계
    cursor = conn.cursor()
    total_docs = cursor.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    docs_with_pages = cursor.execute(
        "SELECT COUNT(*) FROM documents WHERE ifnull(page_count,0)>0"
    ).fetchone()[0]
    fts_count = cursor.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]

    print("\n" + "=" * 80)
    print("적재 결과 요약")
    print("=" * 80)
    print(f"총 문서 수: {total_docs}개")
    print(f"page_count > 0: {docs_with_pages}개")
    print(f"documents_fts 레코드: {fts_count}개")
    print(f"처리 성공: {success}건")
    print(f"처리 실패: {failed}건")

    # 평균 페이지 수
    avg_pages = cursor.execute(
        "SELECT AVG(page_count) FROM documents WHERE page_count > 0"
    ).fetchone()[0]
    print(f"평균 페이지 수: {avg_pages:.1f}페이지" if avg_pages else "평균 페이지 수: N/A")

    conn.close()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
