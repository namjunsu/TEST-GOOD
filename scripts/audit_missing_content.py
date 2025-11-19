#!/usr/bin/env python3
"""
결손 문서 점검 스크립트
content가 비어있거나 짧은 문서를 찾아서 재인덱싱 큐에 등록
"""

import argparse
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from app.data.metadata_db import MetadataDB
from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_args():
    """CLI 인자 파싱"""
    parser = argparse.ArgumentParser(description="결손 문서 점검 및 재인덱싱 큐 생성")
    parser.add_argument(
        "--min-len",
        type=int,
        default=int(os.getenv("RAG_MIN_CONTENT_LEN", "50")),
        help="content 최소 길이 임계값 (기본: 50자, 환경변수 RAG_MIN_CONTENT_LEN)",
    )
    return parser.parse_args()


def main():
    """결손 문서 점검 메인 함수"""
    args = parse_args()
    MIN_CONTENT_LEN = args.min_len

    print("=" * 80)
    print("결손 문서 점검")
    print("=" * 80)

    db = MetadataDB()
    missing = []
    total = 0

    print(f"\n문서 점검 중... (최소 길이: {MIN_CONTENT_LEN}자)")
    print("-" * 80)

    # 모든 문서 검사
    try:
        # MetadataDB에서 모든 doc_id 가져오기
        if hasattr(db, "get_all_metadata"):
            all_docs = db.get_all_metadata()
            for doc in all_docs:
                total += 1
                doc_id = doc.get("doc_id", "unknown")

                # content 조회
                content = None
                if hasattr(db, "get_content"):
                    content = db.get_content(doc_id)

                content_len = len(content or "")

                if content_len < MIN_CONTENT_LEN:
                    missing.append({
                        "doc_id": doc_id,
                        "filename": doc.get("filename", ""),
                        "content_len": content_len,
                    })
                    print(f"  ⚠️  {doc_id}: {content_len}자")

                if total % 100 == 0:
                    print(f"  진행: {total}개 문서 점검...")

        else:
            logger.warning("get_all_metadata 메서드 없음")
            print("\n⚠️  MetadataDB.get_all_metadata() 메서드가 구현되지 않았습니다.")
            print("다음 메서드를 app/data/metadata_db.py에 추가하세요:")
            print("""
    def get_all_metadata(self) -> list[dict]:
        '''모든 문서 메타데이터 조회'''
        with self._get_conn() as conn:
            cursor = conn.execute(
                '''
                SELECT doc_id, filename, pages, created_at
                FROM documents
                ORDER BY created_at DESC
                '''
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_content(self, doc_id: str) -> str | None:
        '''문서 전체 content 조회'''
        with self._get_conn() as conn:
            cursor = conn.execute(
                'SELECT content FROM documents WHERE doc_id = ?',
                (doc_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
            """)
            print("\n=" * 80)
            return

    except Exception as e:
        logger.error(f"점검 실패: {e}")
        import traceback
        traceback.print_exc()
        return

    print("-" * 80)
    print(f"\n점검 완료:")
    print(f"  총 문서 수: {total}개")

    # ZeroDivision 방지
    if total > 0:
        ratio = len(missing) / total * 100
        print(f"  결손 문서 수: {len(missing)}개 ({ratio:.1f}%)")
    else:
        print(f"  결손 문서 수: {len(missing)}개 (0.0%)")
        print("\n⚠️  문서가 하나도 없습니다. 인덱싱을 먼저 실행하세요.")
        print("=" * 80)
        return

    if missing:
        # 재인덱싱 큐 파일 생성
        queue_file = project_root / "data" / "reindex_queue.txt"
        queue_file.parent.mkdir(parents=True, exist_ok=True)

        with open(queue_file, "w") as f:
            for doc in missing:
                f.write(f"{doc['doc_id']}\t{doc['filename']}\t{doc['content_len']}\n")

        print(f"\n재인덱싱 큐 저장:")
        print(f"  파일: {queue_file}")
        print(f"  개수: {len(missing)}개")

        # 상위 10개만 출력
        print(f"\n결손 문서 샘플 (상위 10개):")
        for i, doc in enumerate(missing[:10], 1):
            print(f"  {i}. {doc['doc_id']}: {doc['filename']} ({doc['content_len']}자)")

        print(f"\n다음 단계:")
        print(f"  python3 scripts/rebuild_rag_indexes.py")
        print(f"  또는 특정 문서만:")
        print(f"  python3 scripts/rebuild_rag_indexes.py --doc-ids {missing[0]['doc_id']}")
    else:
        print("\n✅ 결손 문서 없음")

    print("=" * 80)

if __name__ == "__main__":
    main()
