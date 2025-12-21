"""텍스트 청킹 모듈 v1.0

Sliding window + 오버랩 방식으로 문서를 청크 단위로 분할합니다.

특징:
- 고정 크기 청킹 (chunk_size)
- 오버랩으로 경계 정보 손실 방지 (overlap)
- 문장 경계 존중 (sentence-aware)
- 청크별 메타데이터 보존
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Chunk:
    """청크 데이터 클래스

    Attributes:
        doc_id: 원본 문서 ID (파일명)
        chunk_id: 청크 고유 ID (doc_id#chunk_index)
        text: 청크 텍스트
        start_char: 원본 문서에서 시작 위치
        end_char: 원본 문서에서 끝 위치
        chunk_index: 청크 순서 번호
        metadata: 추가 메타데이터
    """
    doc_id: str
    chunk_id: str
    text: str
    start_char: int
    end_char: int
    chunk_index: int
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


class TextChunker:
    """텍스트 청킹 클래스

    Sliding window 방식으로 텍스트를 청크로 분할합니다.
    문장 경계를 존중하여 자연스러운 분할을 수행합니다.

    Args:
        chunk_size: 청크 최대 크기 (문자 수, 기본 512)
        overlap: 오버랩 크기 (문자 수, 기본 128)
        min_chunk_size: 최소 청크 크기 (이하면 이전 청크에 병합)
        respect_sentences: 문장 경계 존중 여부
    """

    # 한국어/영어 문장 종료 패턴
    SENTENCE_END_PATTERN = re.compile(r"[.!?。]\s+|[.!?。]$|\n\n+")

    def __init__(
        self,
        chunk_size: int = 768,  # 512 → 768 (2025-12-21: 한국어 컨텍스트 확대)
        overlap: int = 192,  # 128 → 192 (25% 유지)
        min_chunk_size: int = 50,
        respect_sentences: bool = True,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size
        self.respect_sentences = respect_sentences

        # stride = chunk_size - overlap
        self.stride = chunk_size - overlap

        logger.info(
            f"✅ TextChunker 초기화: "
            f"size={chunk_size}, overlap={overlap}, stride={self.stride}"
        )

    def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """텍스트를 청크로 분할

        Args:
            text: 원본 텍스트
            doc_id: 문서 ID
            metadata: 청크에 포함할 메타데이터

        Returns:
            청크 리스트
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        metadata = metadata or {}
        chunks = []

        # 텍스트가 chunk_size 이하면 단일 청크
        if len(text) <= self.chunk_size:
            chunks.append(Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}#0",
                text=text,
                start_char=0,
                end_char=len(text),
                chunk_index=0,
                metadata=metadata.copy(),
            ))
            return chunks

        # Sliding window 청킹
        start = 0
        chunk_index = 0

        while start < len(text):
            # 끝 위치 계산
            end = min(start + self.chunk_size, len(text))

            # 문장 경계 존중 (마지막 청크 제외)
            if self.respect_sentences and end < len(text):
                end = self._find_sentence_boundary(text, start, end)

            chunk_text = text[start:end].strip()

            # 최소 크기 체크 (마지막 청크가 너무 작으면 이전에 병합)
            if len(chunk_text) < self.min_chunk_size and chunks:
                # 이전 청크에 병합
                prev_chunk = chunks[-1]
                prev_chunk.text = prev_chunk.text + " " + chunk_text
                prev_chunk.end_char = end
                break

            if chunk_text:
                chunks.append(Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}#{chunk_index}",
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                    chunk_index=chunk_index,
                    metadata=metadata.copy(),
                ))
                chunk_index += 1

            # 다음 시작 위치 (stride만큼 이동)
            start = start + self.stride

            # 무한 루프 방지
            if start >= end and end >= len(text):
                break

        logger.debug(f"📄 {doc_id}: {len(chunks)}개 청크 생성 (원본 {len(text)}자)")
        return chunks

    def _find_sentence_boundary(self, text: str, start: int, end: int) -> int:
        """문장 경계 찾기

        end 위치에서 가장 가까운 문장 경계를 찾습니다.
        찾지 못하면 원래 end 반환.

        Args:
            text: 전체 텍스트
            start: 청크 시작 위치
            end: 청크 예상 끝 위치

        Returns:
            조정된 끝 위치
        """
        # end 근처에서 문장 종료 패턴 검색
        search_start = max(start, end - 100)  # 최대 100자 범위에서 검색
        search_text = text[search_start:end + 50]  # 약간 더 넓게 검색

        matches = list(self.SENTENCE_END_PATTERN.finditer(search_text))

        if not matches:
            return end

        # end에 가장 가까운 문장 경계 선택
        best_match = None
        best_distance = float("inf")

        target = end - search_start

        for match in matches:
            match_end = match.end()
            distance = abs(match_end - target)

            # end를 크게 넘지 않는 선에서 가장 가까운 것
            if match_end <= target + 20 and distance < best_distance:
                best_distance = distance
                best_match = match

        if best_match:
            return search_start + best_match.end()

        return end

    def chunk_documents(
        self,
        documents: list[dict],
        text_field: str = "text_preview",
        id_field: str = "filename",
    ) -> list[Chunk]:
        """여러 문서를 한번에 청킹

        Args:
            documents: 문서 리스트 (dict)
            text_field: 텍스트가 있는 필드명
            id_field: 문서 ID 필드명

        Returns:
            전체 청크 리스트
        """
        all_chunks = []

        for doc in documents:
            text = doc.get(text_field, "")
            doc_id = doc.get(id_field, "unknown")

            # 문서 메타데이터 추출
            metadata = {
                k: v for k, v in doc.items()
                if k not in [text_field, id_field]
            }

            chunks = self.chunk(text, doc_id, metadata)
            all_chunks.extend(chunks)

        logger.info(
            f"✅ {len(documents)}개 문서 → {len(all_chunks)}개 청크 생성"
        )
        return all_chunks


# 싱글톤 인스턴스
_chunker_instance: Optional[TextChunker] = None


def get_text_chunker(
    chunk_size: int = 768,  # 512 → 768 (2025-12-21)
    overlap: int = 192,  # 128 → 192 (2025-12-21)
) -> TextChunker:
    """TextChunker 싱글톤 인스턴스 반환

    Args:
        chunk_size: 청크 크기
        overlap: 오버랩 크기

    Returns:
        TextChunker 인스턴스
    """
    global _chunker_instance

    if _chunker_instance is None:
        _chunker_instance = TextChunker(
            chunk_size=chunk_size,
            overlap=overlap,
        )

    return _chunker_instance
