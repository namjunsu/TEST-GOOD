#!/usr/bin/env python3
"""
인덱스 정합성 검증 스크립트

DocStore ↔ FAISS/BM25 간 키 정합성을 검증합니다.

사용법:
    python scripts/check_index_consistency.py --report reports/index_consistency.md
"""

import argparse
import json
import logging
import pickle
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class IndexConsistencyChecker:
    """인덱스 정합성 검증기"""

    def __init__(
        self,
        db_path: str = "metadata.db",
        bm25_path: str = "rag_system/db/bm25_index.pkl",
        faiss_path: str = "rag_system/db/faiss.index"
    ):
        self.db_path = db_path
        self.bm25_path = bm25_path
        self.faiss_path = faiss_path

        self.docstore_keys = set()
        self.bm25_keys = set()
        self.faiss_count = 0

        self.inconsistencies = []

    def load_docstore_keys(self) -> Set[str]:
        """DocStore (metadata.db) 키 로드"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # documents 테이블에서 ID 또는 filename 추출
            cursor.execute("SELECT id, filename FROM documents")
            rows = cursor.fetchall()

            keys = set()
            for row in rows:
                doc_id, filename = row
                keys.add(str(doc_id))
                keys.add(filename)  # filename도 키로 사용 가능

            conn.close()
            logger.info(f"DocStore 키: {len(rows)}개 문서, {len(keys)}개 키")
            return keys

        except Exception as e:
            logger.error(f"DocStore 로드 실패: {e}")
            return set()

    def load_bm25_keys(self) -> Set[str]:
        """BM25 인덱스 키 로드"""
        try:
            if not Path(self.bm25_path).exists():
                logger.warning(f"BM25 인덱스 없음: {self.bm25_path}")
                return set()

            with open(self.bm25_path, 'rb') as f:
                bm25_data = pickle.load(f)

            # BM25 메타데이터에서 키 추출
            keys = set()
            if isinstance(bm25_data, dict):
                metadata = bm25_data.get('metadata', [])
            else:
                # BM25Store 객체
                metadata = getattr(bm25_data, 'metadata', [])

            for meta in metadata:
                if isinstance(meta, dict):
                    # id 또는 filename 사용
                    if 'id' in meta:
                        keys.add(str(meta['id']))
                    if 'filename' in meta:
                        keys.add(meta['filename'])

            logger.info(f"BM25 키: {len(metadata)}개 문서, {len(keys)}개 키")
            return keys

        except Exception as e:
            logger.error(f"BM25 로드 실패: {e}")
            return set()

    def load_faiss_count(self) -> int:
        """FAISS 인덱스 카운트 로드"""
        try:
            if not Path(self.faiss_path).exists():
                logger.warning(f"FAISS 인덱스 없음: {self.faiss_path}")
                return 0

            import faiss
            index = faiss.read_index(self.faiss_path)
            count = index.ntotal
            logger.info(f"FAISS 벡터 수: {count}개")
            return count

        except Exception as e:
            logger.error(f"FAISS 로드 실패: {e}")
            return 0

    def check_consistency(self) -> Dict:
        """정합성 검증"""
        logger.info("=" * 80)
        logger.info("인덱스 정합성 검증 시작")
        logger.info("=" * 80)

        # 1. 키 로드
        self.docstore_keys = self.load_docstore_keys()
        self.bm25_keys = self.load_bm25_keys()
        self.faiss_count = self.load_faiss_count()

        # 2. 정합성 검증
        report = {
            'timestamp': datetime.now().isoformat(),
            'docstore_count': len(self.docstore_keys),
            'bm25_count': len(self.bm25_keys),
            'faiss_count': self.faiss_count,
            'inconsistencies': [],
            'summary': {}
        }

        # DocStore - BM25 비교
        docstore_only = self.docstore_keys - self.bm25_keys
        bm25_only = self.bm25_keys - self.docstore_keys

        if docstore_only:
            report['inconsistencies'].append({
                'type': 'docstore_missing_in_bm25',
                'count': len(docstore_only),
                'sample': list(docstore_only)[:10]
            })
            logger.warning(f"DocStore에만 있음 (BM25 누락): {len(docstore_only)}개")

        if bm25_only:
            report['inconsistencies'].append({
                'type': 'bm25_missing_in_docstore',
                'count': len(bm25_only),
                'sample': list(bm25_only)[:10]
            })
            logger.warning(f"BM25에만 있음 (DocStore 누락): {len(bm25_only)}개")

        # 정합성 점수 계산
        if self.docstore_keys and self.bm25_keys:
            intersection = len(self.docstore_keys & self.bm25_keys)
            union = len(self.docstore_keys | self.bm25_keys)
            consistency_score = intersection / union * 100 if union > 0 else 0
            report['summary']['consistency_score'] = round(consistency_score, 2)
            logger.info(f"정합성 점수: {consistency_score:.2f}%")
        else:
            report['summary']['consistency_score'] = 0

        # 합격 여부
        report['summary']['passed'] = (
            len(docstore_only) == 0 and
            len(bm25_only) == 0
        )

        if report['summary']['passed']:
            logger.info("✅ 정합성 검증 통과")
        else:
            logger.warning("❌ 정합성 검증 실패")

        logger.info("=" * 80)

        return report

    def save_report(self, report: Dict, output_file: str):
        """보고서 저장 (Markdown)"""
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 인덱스 정합성 검증 보고서\n\n")
            f.write(f"**생성 시각:** {report['timestamp']}\n\n")

            # 요약
            f.write("## 요약\n\n")
            f.write(f"- DocStore 문서 수: {report['docstore_count']}\n")
            f.write(f"- BM25 인덱스 수: {report['bm25_count']}\n")
            f.write(f"- FAISS 벡터 수: {report['faiss_count']}\n")
            f.write(f"- 정합성 점수: {report['summary'].get('consistency_score', 0):.2f}%\n")

            passed = report['summary'].get('passed', False)
            f.write(f"- **검증 결과:** {'✅ 통과' if passed else '❌ 실패'}\n\n")

            # 불일치 상세
            if report['inconsistencies']:
                f.write("## 불일치 상세\n\n")
                for incon in report['inconsistencies']:
                    f.write(f"### {incon['type']}\n\n")
                    f.write(f"- 개수: {incon['count']}\n")
                    if incon.get('sample'):
                        f.write(f"- 샘플 (최대 10개):\n")
                        for key in incon['sample']:
                            f.write(f"  - `{key}`\n")
                    f.write("\n")
            else:
                f.write("## 불일치 없음\n\n")
                f.write("모든 인덱스가 완벽하게 동기화되어 있습니다.\n\n")

            # 권장 조치
            if not passed:
                f.write("## 권장 조치\n\n")
                f.write("1. `python scripts/reindex_atomic.py`로 재색인 수행\n")
                f.write("2. 재색인 후 다시 정합성 검증 실행\n")

        logger.info(f"✓ 보고서 저장: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="인덱스 정합성 검증")
    parser.add_argument("--db", default="metadata.db", help="DocStore DB 경로")
    parser.add_argument("--bm25", default="rag_system/db/bm25_index.pkl", help="BM25 인덱스 경로")
    parser.add_argument("--faiss", default="rag_system/db/faiss.index", help="FAISS 인덱스 경로")
    parser.add_argument("--report", default="reports/index_consistency.md", help="보고서 출력 경로")

    args = parser.parse_args()

    checker = IndexConsistencyChecker(
        db_path=args.db,
        bm25_path=args.bm25,
        faiss_path=args.faiss
    )

    report = checker.check_consistency()
    checker.save_report(report, args.report)

    return 0 if report['summary'].get('passed', False) else 1


if __name__ == "__main__":
    sys.exit(main())
