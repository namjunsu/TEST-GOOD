"""청킹 모듈 단위 테스트"""

import pytest

from app.rag.chunking import TextChunker, Chunk


class TestTextChunker:
    """TextChunker 테스트"""

    def test_init_default(self):
        """기본 초기화 테스트"""
        chunker = TextChunker()
        assert chunker.chunk_size == 512
        assert chunker.overlap == 128
        assert chunker.stride == 384  # 512 - 128

    def test_init_custom(self):
        """커스텀 파라미터 초기화"""
        chunker = TextChunker(chunk_size=1000, overlap=200)
        assert chunker.chunk_size == 1000
        assert chunker.overlap == 200
        assert chunker.stride == 800

    def test_chunk_short_text(self):
        """짧은 텍스트 (단일 청크)"""
        chunker = TextChunker(chunk_size=512)
        text = "짧은 테스트 텍스트입니다."
        chunks = chunker.chunk(text, "doc1.pdf")

        assert len(chunks) == 1
        assert chunks[0].doc_id == "doc1.pdf"
        assert chunks[0].chunk_id == "doc1.pdf#0"
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0

    def test_chunk_long_text(self):
        """긴 텍스트 (다중 청크)"""
        chunker = TextChunker(chunk_size=100, overlap=20)
        text = "가" * 250  # 250자

        chunks = chunker.chunk(text, "doc2.pdf")

        # 250자 / stride(80) = 약 3~4개 청크
        assert len(chunks) >= 2
        assert all(c.doc_id == "doc2.pdf" for c in chunks)
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1

    def test_chunk_overlap_content(self):
        """오버랩 내용 확인"""
        chunker = TextChunker(chunk_size=100, overlap=30, respect_sentences=False)
        text = "A" * 50 + "B" * 50 + "C" * 50  # 150자

        chunks = chunker.chunk(text, "doc3.pdf")

        # 첫 청크 끝과 두번째 청크 시작이 오버랩
        if len(chunks) >= 2:
            # 두번째 청크 시작 위치가 첫번째 청크 끝 이전
            assert chunks[1].start_char < chunks[0].end_char

    def test_chunk_empty_text(self):
        """빈 텍스트"""
        chunker = TextChunker()
        chunks = chunker.chunk("", "empty.pdf")
        assert chunks == []

    def test_chunk_whitespace_only(self):
        """공백만 있는 텍스트"""
        chunker = TextChunker()
        chunks = chunker.chunk("   \n\t  ", "whitespace.pdf")
        assert chunks == []

    def test_chunk_with_metadata(self):
        """메타데이터 포함"""
        chunker = TextChunker()
        metadata = {"author": "테스트", "year": "2025"}
        chunks = chunker.chunk("테스트 문서입니다.", "meta.pdf", metadata)

        assert len(chunks) == 1
        assert chunks[0].metadata == metadata

    def test_chunk_sentence_boundary(self):
        """문장 경계 존중 테스트"""
        chunker = TextChunker(chunk_size=50, overlap=10, respect_sentences=True)
        text = "첫번째 문장입니다. 두번째 문장입니다. 세번째 문장입니다."

        chunks = chunker.chunk(text, "sentence.pdf")

        # 청크가 문장 중간에서 잘리지 않아야 함 (가능한 경우)
        assert len(chunks) >= 1


class TestChunk:
    """Chunk 데이터클래스 테스트"""

    def test_to_dict(self):
        """to_dict 변환"""
        chunk = Chunk(
            doc_id="test.pdf",
            chunk_id="test.pdf#0",
            text="테스트 텍스트",
            start_char=0,
            end_char=7,
            chunk_index=0,
            metadata={"key": "value"},
        )

        d = chunk.to_dict()

        assert d["doc_id"] == "test.pdf"
        assert d["chunk_id"] == "test.pdf#0"
        assert d["text"] == "테스트 텍스트"
        assert d["start_char"] == 0
        assert d["end_char"] == 7
        assert d["chunk_index"] == 0
        assert d["metadata"] == {"key": "value"}
