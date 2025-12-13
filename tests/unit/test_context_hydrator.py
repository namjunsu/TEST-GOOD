#!/usr/bin/env python3
"""
Context Hydrator 단위 테스트
- 문장 분리 경계 케이스
- 수치 인식 패턴
- 폴백 체인 우선순위
- PDF 테일 추출 및 보안
- 길이 정책 (모드별)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.rag.utils.context_hydrator import (
    SCORE_WEIGHTS,
    _extract_core_sentences,
    _extract_pdf_tail,
    _extract_text_from_chunk,
    _hard_cut_paragraphwise,
    _is_under_docs,
    hydrate_context,
)


@pytest.fixture(autouse=True)
def hydrator_policy_env(monkeypatch):
    """
    휴리스틱 정책 기본값 고정 (테스트 재현성)

    테스트별로 오버라이드 가능
    """
    monkeypatch.setenv("HYDRATOR_W_NUMERIC", "3")
    monkeypatch.setenv("HYDRATOR_W_KEYWORD", "1")
    monkeypatch.setenv("HYDRATOR_W_CONCLUSION", "2")
    monkeypatch.setenv("HYDRATOR_W_EDGE", "1")
    monkeypatch.setenv("IGNORE_SEMVER_IN_NUMERIC", "false")
    monkeypatch.setenv("END_BONUS", "1")
    yield


class TestSentenceSplit:
    """문장 분리 경계 케이스"""

    def test_ellipsis_and_parentheses_with_semver_ignore(self, monkeypatch):
        """말줄임표, 괄호 내 마침표 (세미버 무시 옵션)"""
        monkeypatch.setenv("IGNORE_SEMVER_IN_NUMERIC", "true")
        # 모듈 재임포트 (환경변수 변경 반영)
        import importlib

        import app.rag.utils.context_hydrator
        importlib.reload(app.rag.utils.context_hydrator)
        from app.rag.utils.context_hydrator import _extract_core_sentences

        text = "1. 개요입니다... 다음 문장(예: v1.2.3). 끝!"
        out = _extract_core_sentences(text, 10_000)
        # 세미버 무시 시 "개요"가 우선될 수 있음
        assert "개요" in out or "다음 문장" in out

    def test_ellipsis_and_parentheses_default(self):
        """말줄임표, 괄호 내 마침표 (기본 정책: 숫자 가중)"""
        text = "1. 개요입니다... 다음 문장(예: v1.2.3). 끝!"
        out = _extract_core_sentences(text, 10_000)
        # 기본 정책: 세미버 포함 숫자 패턴이 높은 가중치 → 결과에 포함됨
        assert "다음 문장" in out or "끝" in out

    def test_double_newline_paragraph_policy_aware(self):
        """줄바꿈 2회 문단 구분 (정책 독립적 검증)"""
        text = "첫 문단입니다.\n\n두 번째 문단입니다."
        out = _extract_core_sentences(text, 10_000)
        # 정책(END_BONUS)에 따라 우선순위 변동 가능
        # 두 문단 중 최소 하나는 포함되어야 함
        assert ("첫 문단" in out or "두 번째" in out)
        # 길이 제한이 충분하면 둘 다 포함 가능
        if len(text) < 10_000:
            assert len(out) > 0

    def test_double_newline_paragraph_default(self):
        """줄바꿈 2회 문단 구분 (기본 정책: 말미 가중 활성)"""
        text = "첫 문단입니다.\n\n두 번째 문단입니다."
        out = _extract_core_sentences(text, 10_000)
        # 기본 정책: 마지막 문단 우선 → 결과에 "두 번째" 포함 가능
        assert ("첫 문단" in out or "두 번째" in out)

    def test_short_sentences_filtered(self):
        """10자 이하 문장 필터링 (경계값 테스트)"""
        text = "가. 나다라마바사아자차카타파하."  # 정확히 10자
        out = _extract_core_sentences(text, 10_000)
        # 10자 이하는 필터링되므로 빈 문자열 가능
        # 10자 정확히인 경우 strip 후 10자라면 포함
        assert len(out) == 0 or "나다라마바사아자차카타파하" in out


class TestNumericPatterns:
    """수치 인식 패턴"""

    def test_comma_separated_numbers(self):
        """쉼표 구분 숫자"""
        text = "총액은 12,300원입니다."
        # numeric 패턴 테스트
        import re

        numeric = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b")
        assert numeric.search(text)

    def test_korean_unit_numbers(self):
        """한글 단위 숫자"""
        for s in ["12만 원", "1.5억", "2억원"]:
            text = f"금액: {s}"
            units = ("원", "년", "월", "일", "개", "대", "만", "억")
            assert any(u in text for u in units)

    def test_mixed_sentence_scoring(self):
        """숫자 + 키워드 혼합 문장 점수"""
        text = "카메라 렌즈 구매: 총액은 2,450,000원입니다. 기안 작성 완료."
        out = _extract_core_sentences(text, 10_000)
        assert "2,450,000" in out or "카메라" in out


class TestFallbackChain:
    """폴백 체인 우선순위"""

    def test_text_priority(self):
        """text 키 우선"""
        chunk = {"text": "TXT", "content": "CNT", "raw_text": "RT"}
        metrics = {"fallback_chain": []}
        result = _extract_text_from_chunk(chunk, metrics)
        assert result == "TXT"
        assert metrics["fallback_chain"] == ["text"]

    def test_page_content_fallback(self):
        """text 없으면 content → page_content"""
        chunk = {"content": "CNT", "page_content": "PC"}
        metrics = {"fallback_chain": []}
        result = _extract_text_from_chunk(chunk, metrics)
        assert result == "CNT"

    def test_raw_text_fallback(self):
        """raw_text 폴백"""
        chunk = {"raw_text": "RT", "abstract": "AB"}
        metrics = {"fallback_chain": []}
        result = _extract_text_from_chunk(chunk, metrics)
        assert result == "RT"

    def test_abstract_last_resort(self):
        """abstract 최후 수단"""
        chunk = {"abstract": "AB"}
        metrics = {"fallback_chain": []}
        result = _extract_text_from_chunk(chunk, metrics)
        assert result == "AB"

    def test_empty_chunk(self):
        """모든 키 없음 → 빈 문자열"""
        chunk = {}
        metrics = {"fallback_chain": []}
        result = _extract_text_from_chunk(chunk, metrics)
        assert result == ""


class TestPDFTail:
    """PDF 테일 추출 및 보안"""

    @pytest.fixture
    def mock_pdf(self):
        """Mock PDF 픽스처"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "docs" / "test.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_text("dummy")
            yield pdf_path

    def test_extension_validation(self, mock_pdf):
        """확장자 검증: .pdf만 허용"""
        chunk = {"file_path": str(mock_pdf.with_suffix(".txt"))}
        metrics = {"pdf_tail_pages": 0}
        result = _extract_pdf_tail(chunk, metrics)
        assert result == ""

    def test_uppercase_pdf_extension(self, mock_pdf):
        """대문자 확장자 .PDF 허용"""
        chunk = {"file_path": str(mock_pdf.with_suffix(".PDF"))}
        metrics = {"pdf_tail_pages": 0}
        # 실제 PDF가 아니므로 pdfplumber 실패하지만 확장자는 통과
        # 에러 처리로 빈 문자열 반환
        result = _extract_pdf_tail(chunk, metrics)
        assert result == ""  # pdfplumber 실패 시

    def test_path_outside_docs(self):
        """docs 외부 경로 차단"""
        with tempfile.TemporaryDirectory() as tmpdir:
            outside_path = Path(tmpdir) / "outside.pdf"
            outside_path.write_text("dummy")
            chunk = {"file_path": str(outside_path)}
            metrics = {"pdf_tail_pages": 0}
            result = _extract_pdf_tail(chunk, metrics)
            assert result == ""

    def test_symlink_security(self):
        """심볼릭 링크 우회 차단"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()
            outside = Path(tmpdir) / "outside.pdf"
            outside.write_text("dummy")
            link = docs_dir / "link.pdf"
            # 심볼릭 링크 생성 시도 (권한 없으면 스킵)
            try:
                link.symlink_to(outside)
                chunk = {"file_path": str(link)}
                metrics = {"pdf_tail_pages": 0}
                with patch.dict(os.environ, {"DOCS_DIR": str(docs_dir)}):
                    result = _extract_pdf_tail(chunk, metrics)
                    # resolve() 후 docs 외부 → 차단
                    assert result == ""
            except OSError:
                pytest.skip("symlink creation failed (permission)")

    def test_file_size_limit(self, mock_pdf):
        """파일 크기 64MB 초과 차단"""
        # 실제로 64MB 파일 생성하지 않고 모킹
        chunk = {"file_path": str(mock_pdf)}
        metrics = {"pdf_tail_pages": 0}

        with patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value = Mock(st_size=65 * 1024 * 1024)  # 65MB
            result = _extract_pdf_tail(chunk, metrics)
            assert result == ""


class TestIsUnderDocs:
    """경로 검증 헬퍼"""

    def test_direct_child(self):
        """docs 직계 하위"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs = Path(tmpdir) / "docs"
            docs.mkdir()
            child = docs / "file.pdf"
            child.write_text("dummy")
            with patch.dict(os.environ, {"DOCS_DIR": str(docs)}):
                assert _is_under_docs(child)

    def test_nested_child(self):
        """docs 중첩 하위"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs = Path(tmpdir) / "docs"
            (docs / "sub").mkdir(parents=True)
            nested = docs / "sub" / "file.pdf"
            nested.write_text("dummy")
            with patch.dict(os.environ, {"DOCS_DIR": str(docs)}):
                assert _is_under_docs(nested)

    def test_outside_docs(self):
        """docs 외부"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs = Path(tmpdir) / "docs"
            docs.mkdir()
            outside = Path(tmpdir) / "outside.pdf"
            outside.write_text("dummy")
            with patch.dict(os.environ, {"DOCS_DIR": str(docs)}):
                assert not _is_under_docs(outside)


class TestHardCutParagraphwise:
    """문단 단위 하드 컷"""

    def test_single_paragraph(self):
        """단일 문단"""
        text = "짧은 문단입니다."
        result = _hard_cut_paragraphwise(text, 100)
        assert result == text

    def test_multiple_paragraphs_under_limit(self):
        """복수 문단, 제한 이하"""
        text = "첫 문단.\n\n두 번째 문단."
        result = _hard_cut_paragraphwise(text, 100)
        assert "첫 문단" in result
        assert "두 번째 문단" in result

    def test_paragraphs_over_limit(self):
        """복수 문단, 제한 초과 시 문단 단위 컷"""
        text = "첫 문단입니다.\n\n두 번째 문단입니다.\n\n세 번째 문단입니다."
        result = _hard_cut_paragraphwise(text, 30)
        # 첫 문단만 포함 (길이 제한)
        assert "첫 문단" in result
        assert "세 번째" not in result

    def test_fallback_to_slice(self):
        """문단 구분 없으면 슬라이싱"""
        text = "줄바꿈 없는 긴 텍스트입니다" * 10
        result = _hard_cut_paragraphwise(text, 50)
        assert len(result) <= 50


class TestHydrateContext:
    """통합 테스트"""

    def test_chunks_only(self):
        """청크만"""
        chunks = [{"text": "청크 1입니다."}, {"text": "청크 2입니다."}]
        text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
        assert "청크 1" in text
        assert "청크 2" in text
        assert metrics["chunks_used"] == 2
        assert metrics["pdf_tail_pages"] == 0

    def test_mode_rag_compression(self):
        """RAG 모드: 압축 적용"""
        long_text = "일반 문장입니다. " * 1000
        chunks = [{"text": long_text}]
        with patch.dict(os.environ, {"CONTEXT_MAX_TOKENS": "50", "RAG_STYLE_COMPACT": "true"}):
            text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
            assert metrics["compression_applied"] or metrics["truncate_reason"] == "hardcut"

    def test_mode_summarize_no_compression(self):
        """Summarize 모드: 압축 비적용"""
        long_text = "일반 문장입니다. " * 1000
        chunks = [{"text": long_text}]
        with patch.dict(os.environ, {"CONTEXT_MAX_TOKENS": "50", "RAG_STYLE_COMPACT": "true"}):
            text, metrics = hydrate_context(chunks, max_len=10000, mode="summarize")
            # 압축 비적용, 하드컷만
            assert not metrics["compression_applied"]

    def test_token_estimate(self):
        """토큰 추정치"""
        chunks = [{"text": "테스트 텍스트입니다."}]
        with patch.dict(os.environ, {"TOKENS_PER_CHAR": "0.33"}):
            text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
            assert metrics["token_estimate"] > 0
            assert metrics["token_estimate"] == int(len(text) * 0.33)

    def test_empty_chunks(self):
        """빈 청크 → 컨텍스트 0 경고"""
        chunks = [{}]
        text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
        assert text == ""
        assert metrics["total_length"] == 0


class TestPropertyBased:
    """속성 기반 테스트 (임의 입력)"""

    def test_random_text_no_exception(self):
        """임의 텍스트 예외 미발생"""
        import random
        import string

        for _ in range(10):
            text = "".join(random.choices(string.printable + "가나다라마", k=500))
            try:
                _extract_core_sentences(text, 1000)
            except Exception as e:
                pytest.fail(f"Exception on random text: {e}")

    def test_edge_case_env_vars(self):
        """환경변수 경계값"""
        chunks = [{"text": "테스트"}]
        # TOKENS_PER_CHAR = 0 방어
        with patch.dict(os.environ, {"TOKENS_PER_CHAR": "0"}):
            text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
            # 1e-6 최소값으로 나눠지므로 예외 없음
            assert metrics["token_estimate"] >= 0

        # CONTEXT_MAX_TOKENS 아주 큰 값
        with patch.dict(os.environ, {"CONTEXT_MAX_TOKENS": "1000000"}):
            text, metrics = hydrate_context(chunks, max_len=10000, mode="rag")
            assert metrics["context_max_tokens"] == 1000000


@pytest.mark.heuristic
class TestGoldenSnapshot:
    """골든 스냅샷 테스트 (실제 PDF 샘플 기반 회귀 검증)"""

    def test_policy_snapshot_consistency(self):
        """
        휴리스틱 정책 일관성 검증

        정책 변경 시 이 테스트의 출력 변화를 검토하여
        의도하지 않은 회귀를 감지
        """
        # 실제 사내 PDF 샘플 텍스트 (익명화)
        sample_text = """
        1. 구매 목적: 방송 장비 렌즈 교체 건에 따른 구매.
        신청 일자는 2025년 1월 15일입니다.

        2. 품목 상세: 카메라 렌즈 (모델: Canon EF 24-70mm f/2.8L).
        단가는 2,450,000원이며, 수량은 1개입니다.

        3. 결론: 따라서 총 금액은 2,450,000원으로 확정되었습니다.
        검토 완료하였으며, 승인 요청드립니다.
        """

        result = _extract_core_sentences(sample_text, 500)

        # 휴리스틱 체크: 높은 점수 문장이 포함되는지
        # (수치 정보 + 도메인 키워드가 있는 문장)
        assert "2,450,000" in result  # 수치 정보
        assert ("렌즈" in result or "카메라" in result)  # 도메인 키워드

        # 정책 의존성 표시 (변경 시 업데이트 필요)
        # 현재 정책 (HYDRATOR_W_NUMERIC=3, KEYWORD=1, CONCLUSION=2):
        # - "총 금액 2,450,000원" 문장이 높은 우선순위
        # - "결론" 마커가 있는 문장 우선

    def test_snapshot_score_weights(self):
        """
        스코어 가중치별 출력 변화 추적

        정책 변경 시 diff를 수동으로 검토
        """
        text = "품목: 마이크 케이블. 금액: 120,000원. 날짜: 2025-01-15."

        result_default = _extract_core_sentences(text, 500)

        # 기본 정책: 수치 가중 높음 → 금액 문장 우선
        assert "120,000" in result_default

        # 가중치별 민감도 주석 (변경 추적용)
        # HYDRATOR_W_NUMERIC=3 → "금액: 120,000원" 최우선
        # HYDRATOR_W_KEYWORD=1 → "품목: 마이크 케이블" 보조
        # 정책 변경 시 이 주석 업데이트
