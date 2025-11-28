#!/usr/bin/env python3
"""
Streaming utilities for progressive text display
Simulates ChatGPT-style incremental text rendering

방송 기술관리팀 RAG 시스템 스트리밍:
- 동기/비동기 버전 지원
- 설정 중앙 관리
- WebSocket 대응
- 빈 문자열 안전 처리
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Generator
from typing import Literal

logger = logging.getLogger(__name__)

# 스트리밍 설정 (중앙 관리)
StreamingConfig = {
    "slow": {
        "mode": "char",
        "delay": 0.015,
        "description": "글자 단위 느린 스트리밍",
    },
    "medium_short": {
        "mode": "chunk",
        "chunk_size": 5,
        "delay": 0.015,
        "description": "짧은 텍스트용 청크 스트리밍",
    },
    "medium_long": {
        "mode": "chunk",
        "chunk_size": 15,
        "delay": 0.02,
        "description": "긴 텍스트용 청크 스트리밍",
    },
    "fast": {
        "mode": "word",
        "delay": 0.03,
        "description": "단어 단위 빠른 스트리밍",
    },
}

# 텍스트 길이 임계값
TEXT_LENGTH_THRESHOLD = 300


# ============================================================================
# 동기 스트리밍 함수들
# ============================================================================

def stream_text_incremental(
    text: str,
    delay_per_char: float = 0.01,
) -> Generator[str, None, None]:
    """
    Stream text character by character for ChatGPT-style display

    Args:
        text: Complete text to stream
        delay_per_char: Delay between characters in seconds (default 0.01 = 10ms)

    Yields:
        Progressive accumulated text (always full string up to current position)

    Note:
        - Returns immediately if text is empty
        - First yield contains the first character (no empty string)
        - Each yield contains the full accumulated text so far
    """
    if not text:
        logger.debug("Empty text provided to stream_text_incremental")
        return

    for i in range(1, len(text) + 1):
        yield text[:i]
        if delay_per_char > 0:
            time.sleep(delay_per_char)


def stream_text_by_words(
    text: str,
    delay_per_word: float = 0.05,
) -> Generator[str, None, None]:
    """
    Stream text word by word for faster progressive display

    Args:
        text: Complete text to stream
        delay_per_word: Delay between words in seconds (default 0.05 = 50ms)

    Yields:
        Progressive accumulated text (always full string up to current word)

    Note:
        - Returns immediately if text is empty or contains only whitespace
        - First yield contains the first word
        - Each yield contains all words accumulated so far
    """
    if not text or not text.strip():
        logger.debug("Empty or whitespace-only text provided to stream_text_by_words")
        return

    words = text.split()
    for i in range(1, len(words) + 1):
        yield " ".join(words[:i])
        if delay_per_word > 0:
            time.sleep(delay_per_word)


def stream_text_by_chunks(
    text: str,
    chunk_size: int = 10,
    delay_per_chunk: float = 0.02,
) -> Generator[str, None, None]:
    """
    Stream text in fixed-size character chunks for balanced speed and smoothness

    Args:
        text: Complete text to stream
        chunk_size: Number of characters per chunk (default 10)
        delay_per_chunk: Delay between chunks in seconds (default 0.02 = 20ms)

    Yields:
        Progressive accumulated text (always full string up to current chunk)

    Note:
        - Returns immediately if text is empty
        - First yield contains the first chunk
        - Each yield contains all text accumulated so far
    """
    if not text:
        logger.debug("Empty text provided to stream_text_by_chunks")
        return

    for i in range(chunk_size, len(text) + chunk_size, chunk_size):
        yield text[:i]
        if delay_per_chunk > 0:
            time.sleep(delay_per_chunk)


def stream_text_smart(
    text: str,
    speed: Literal["slow", "medium", "fast"] = "medium",
) -> Generator[str, None, None]:
    """
    Smart streaming that adapts based on text length and desired speed

    Args:
        text: Complete text to stream
        speed: "slow" (char by char), "medium" (adaptive chunks), "fast" (words)

    Yields:
        Progressive accumulated text

    Note:
        - Medium mode automatically selects chunk size based on text length
        - Configuration can be adjusted via StreamingConfig
    """
    if not text:
        logger.debug("Empty text provided to stream_text_smart")
        return

    length = len(text)

    if speed == "slow":
        config = StreamingConfig["slow"]
        yield from stream_text_incremental(text, delay_per_char=config["delay"])

    elif speed == "fast":
        config = StreamingConfig["fast"]
        yield from stream_text_by_words(text, delay_per_word=config["delay"])

    else:  # medium (adaptive)
        if length < TEXT_LENGTH_THRESHOLD:
            config = StreamingConfig["medium_short"]
        else:
            config = StreamingConfig["medium_long"]

        yield from stream_text_by_chunks(
            text,
            chunk_size=config["chunk_size"],
            delay_per_chunk=config["delay"],
        )


# ============================================================================
# 비동기 스트리밍 함수들 (WebSocket/FastAPI 대응)
# ============================================================================

async def astream_text_incremental(
    text: str,
    delay_per_char: float = 0.01,
) -> AsyncGenerator[str, None]:
    """
    Async version of stream_text_incremental

    Args:
        text: Complete text to stream
        delay_per_char: Delay between characters in seconds

    Yields:
        Progressive accumulated text

    Usage:
        async for chunk in astream_text_incremental("Hello"):
            await websocket.send_text(chunk)
    """
    if not text:
        return

    for i in range(1, len(text) + 1):
        yield text[:i]
        if delay_per_char > 0:
            await asyncio.sleep(delay_per_char)


async def astream_text_by_words(
    text: str,
    delay_per_word: float = 0.05,
) -> AsyncGenerator[str, None]:
    """
    Async version of stream_text_by_words

    Args:
        text: Complete text to stream
        delay_per_word: Delay between words in seconds

    Yields:
        Progressive accumulated text
    """
    if not text or not text.strip():
        return

    words = text.split()
    for i in range(1, len(words) + 1):
        yield " ".join(words[:i])
        if delay_per_word > 0:
            await asyncio.sleep(delay_per_word)


async def astream_text_by_chunks(
    text: str,
    chunk_size: int = 10,
    delay_per_chunk: float = 0.02,
) -> AsyncGenerator[str, None]:
    """
    Async version of stream_text_by_chunks

    Args:
        text: Complete text to stream
        chunk_size: Number of characters per chunk
        delay_per_chunk: Delay between chunks in seconds

    Yields:
        Progressive accumulated text
    """
    if not text:
        return

    for i in range(chunk_size, len(text) + chunk_size, chunk_size):
        yield text[:i]
        if delay_per_chunk > 0:
            await asyncio.sleep(delay_per_chunk)


async def astream_text_smart(
    text: str,
    speed: Literal["slow", "medium", "fast"] = "medium",
) -> AsyncGenerator[str, None]:
    """
    Async version of stream_text_smart

    Args:
        text: Complete text to stream
        speed: Streaming speed mode

    Yields:
        Progressive accumulated text

    Usage:
        async for chunk in astream_text_smart(response, speed="fast"):
            await websocket.send_text(chunk)
    """
    if not text:
        return

    length = len(text)

    if speed == "slow":
        config = StreamingConfig["slow"]
        async for chunk in astream_text_incremental(text, delay_per_char=config["delay"]):
            yield chunk

    elif speed == "fast":
        config = StreamingConfig["fast"]
        async for chunk in astream_text_by_words(text, delay_per_word=config["delay"]):
            yield chunk

    else:  # medium
        if length < TEXT_LENGTH_THRESHOLD:
            config = StreamingConfig["medium_short"]
        else:
            config = StreamingConfig["medium_long"]

        async for chunk in astream_text_by_chunks(
            text,
            chunk_size=config["chunk_size"],
            delay_per_chunk=config["delay"],
        ):
            yield chunk


# ============================================================================
# 유틸리티 함수
# ============================================================================

def get_streaming_config() -> dict:
    """
    Get current streaming configuration

    Returns:
        Dictionary of streaming configuration
    """
    return StreamingConfig.copy()


def update_streaming_config(
    speed_mode: str,
    **kwargs,
) -> None:
    """
    Update streaming configuration

    Args:
        speed_mode: Configuration key to update (e.g., "slow", "fast")
        **kwargs: Configuration values to update (e.g., delay=0.02)

    Example:
        update_streaming_config("slow", delay=0.02)
    """
    if speed_mode not in StreamingConfig:
        raise ValueError(f"Invalid speed mode: {speed_mode}")

    StreamingConfig[speed_mode].update(kwargs)
    logger.info(f"Updated streaming config for {speed_mode}: {kwargs}")


def estimate_streaming_duration(
    text: str,
    speed: Literal["slow", "medium", "fast"] = "medium",
) -> float:
    """
    Estimate total streaming duration

    Args:
        text: Text to stream
        speed: Streaming speed mode

    Returns:
        Estimated duration in seconds
    """
    if not text:
        return 0.0

    length = len(text)

    if speed == "slow":
        return length * StreamingConfig["slow"]["delay"]

    if speed == "fast":
        words = len(text.split())
        return words * StreamingConfig["fast"]["delay"]

    # medium
    if length < TEXT_LENGTH_THRESHOLD:
        config = StreamingConfig["medium_short"]
    else:
        config = StreamingConfig["medium_long"]

    chunks = (length + config["chunk_size"] - 1) // config["chunk_size"]
    return chunks * config["delay"]
