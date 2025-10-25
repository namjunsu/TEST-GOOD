#!/usr/bin/env python3
"""
결손 문서 점검 스크립트
content가 비어있거나 짧은 문서를 찾아서 재인덱싱 큐에 등록
"""

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

from app.data.metadata.db import MetadataDB
from app.core.logging import get_logger

logger = get_logger(__name__)

def main():
    """결손 문서 점검 메인 함수"""
    print("=" * 80)
    print("결손 문서 점검")
    print("=" * 80)

    db = MetadataDB()
    missing = []
    total = 0

    # 임계값
    MIN_CONTENT_LEN = 50

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
            return

    except Exception as e:
        logger.error(f"점검 실패: {e}")
        import traceback
        traceback.print_exc()
        return

    print("-" * 80)
    print(f"\n점검 완료:")
    print(f"  총 문서 수: {total}개")
    print(f"  결손 문서 수: {len(missing)}개 ({len(missing)/total*100:.1f}%)")

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
        print(f"  python3 rebuild_rag_indexes.py")
        print(f"  또는 특정 문서만:")
        print(f"  python3 rebuild_rag_indexes.py --doc-ids {missing[0]['doc_id']}")
    else:
        print("\n✅ 결손 문서 없음")

    print("=" * 80)

if __name__ == "__main__":
    main()
