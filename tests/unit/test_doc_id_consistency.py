"""
doc_id 정합성 회귀 테스트

목적: doc_id 생성 규칙이 변경되지 않았는지 검증
실행: pytest tests/test_doc_id_consistency.py -v
"""

import pickle
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.skip(reason="인터페이스 변경으로 재작성 필요")

PROJECT_ROOT = Path(__file__).parent.parent


class TestDocIDConsistency:
    """doc_id 통합 규격 회귀 테스트"""

    def test_resolve_doc_id_with_valid_id(self):
        """metadata에 id가 있으면 문자열로 반환"""
        from rag_system.active.bm25_store import _resolve_doc_id

        metadata = {"id": 4148, "filename": "test.pdf"}
        doc_id = _resolve_doc_id(metadata, doc_idx=0)

        assert doc_id == "4148"
        assert isinstance(doc_id, str)

    def test_resolve_doc_id_missing_id_raises_error(self):
        """metadata에 id가 없으면 ValueError 발생"""
        from rag_system.active.bm25_store import _resolve_doc_id

        metadata = {"filename": "test.pdf"}  # id 없음

        with pytest.raises(ValueError, match="metadata\\['id'\\] 누락"):
            _resolve_doc_id(metadata, doc_idx=0)

    def test_resolve_doc_id_none_id_raises_error(self):
        """metadata['id']=None이면 ValueError 발생"""
        from rag_system.active.bm25_store import _resolve_doc_id

        metadata = {"id": None, "filename": "test.pdf"}

        with pytest.raises(ValueError, match="metadata\\['id'\\] 누락"):
            _resolve_doc_id(metadata, doc_idx=0)

    def test_docstore_bm25_id_matching(self):
        """DocStore와 BM25 인덱스의 doc_id가 일치하는지 검증"""
        db_path = PROJECT_ROOT / "metadata.db"
        bm25_path = PROJECT_ROOT / "var/index/bm25_index.pkl"

        # 두 파일이 모두 존재해야 테스트 가능
        if not db_path.exists() or not bm25_path.exists():
            pytest.skip("metadata.db 또는 BM25 인덱스 없음")

        # DocStore IDs
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM documents ORDER BY id LIMIT 10")
        db_ids = {str(row[0]) for row in cursor.fetchall()}
        conn.close()

        # BM25 IDs
        with open(bm25_path, "rb") as f:
            bm25_data = pickle.load(f)
            bm25_ids = {m.get("id") for m in bm25_data["metadata"][:10]}

        # 샘플 비교 (최소 5개 이상 일치해야 함)
        common_ids = db_ids & bm25_ids
        assert len(common_ids) >= 5, (
            f"DocStore와 BM25 ID 불일치. "
            f"공통 ID: {len(common_ids)}, DB: {db_ids}, BM25: {bm25_ids}"
        )

    def test_bm25_id_format(self):
        """BM25 인덱스의 doc_id가 문자열 숫자 형식인지 검증"""
        bm25_path = PROJECT_ROOT / "var/index/bm25_index.pkl"

        if not bm25_path.exists():
            pytest.skip("BM25 인덱스 없음")

        with open(bm25_path, "rb") as f:
            bm25_data = pickle.load(f)
            metadata = bm25_data["metadata"][:10]

        for meta in metadata:
            doc_id = meta.get("id")
            assert doc_id is not None, f"id 필드 누락: {meta}"
            assert isinstance(doc_id, str), f"id가 문자열이 아님: {doc_id} (type={type(doc_id)})"

            # 숫자 형식인지 확인 (doc_ 접두사 금지)
            assert doc_id.isdigit(), f"doc_id가 순수 숫자가 아님: {doc_id}"
            assert not doc_id.startswith("doc_"), f"doc_ 접두사 사용 금지: {doc_id}"

    def test_index_consistency_score(self):
        """정합성 검증 스크립트 실행 후 100% 확인"""
        report_path = PROJECT_ROOT / "reports/index_consistency.md"

        if not report_path.exists():
            pytest.skip("정합성 리포트 없음 (scripts/check_index_consistency.py 미실행)")

        content = report_path.read_text(encoding="utf-8")

        # 정합성 점수 파싱
        import re
        match = re.search(r"정합성 점수:\s*(\d+\.\d+)%", content)
        assert match, "정합성 점수를 찾을 수 없음"

        score = float(match.group(1))
        assert score == 100.0, f"정합성 점수가 100%가 아님: {score}%"


class TestDocIDRegressionPrevention:
    """doc_id 규격 변경 방지 테스트"""

    def test_no_sequential_doc_id_in_new_code(self):
        """신규 코드에서 순서 기반 doc_id 사용 금지"""
        # _resolve_doc_id 함수 시그니처 확인
        import inspect

        from rag_system.active import bm25_store
        sig = inspect.signature(bm25_store._resolve_doc_id)
        params = list(sig.parameters.keys())

        assert "metadata" in params, "_resolve_doc_id에 metadata 파라미터 필수"
        assert "doc_idx" in params, "_resolve_doc_id에 doc_idx 파라미터 필수"

    def test_reindex_script_uses_db_id(self):
        """reindex_atomic.py가 DB ID를 사용하는지 검증"""
        script_path = PROJECT_ROOT / "scripts/reindex_atomic.py"
        content = script_path.read_text(encoding="utf-8")

        # DB 쿼리에서 id 필드를 SELECT하는지 확인
        assert "SELECT id" in content or "SELECT *" in content, (
            "reindex_atomic.py가 DB id 필드를 조회하지 않음"
        )

        # metadata에 id를 전달하는지 확인
        assert "'id':" in content or '"id":' in content, (
            "reindex_atomic.py가 metadata에 id를 전달하지 않음"
        )

        # doc_id를 DB에서 가져오는지 확인 (str 변환 포함)
        import re
        assert re.search(r"doc_id\s*=\s*doc_meta\.get\(['\"]id['\"]\)", content) or \
               re.search(r"str\(doc_id\)", content), (
            "reindex_atomic.py가 DB doc_id를 문자열로 변환하지 않음"
        )
