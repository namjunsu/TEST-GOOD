"""청킹 모듈

문서를 의미 있는 청크 단위로 분할하여 검색 정확도를 향상시킵니다.

구현체:
- TextChunker: Sliding window + 오버랩 청킹
"""

from app.rag.chunking.text_chunker import Chunk, TextChunker

__all__ = [
    "TextChunker",
    "Chunk",
]
