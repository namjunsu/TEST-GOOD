#!/usr/bin/env python3
"""
Streaming utilities for progressive text display
Simulates ChatGPT-style incremental text rendering
"""
import time
from typing import Generator


def stream_text_incremental(text: str, delay_per_char: float = 0.01) -> Generator[str, None, None]:
    """
    Stream text character by character for ChatGPT-style display

    Args:
        text: Complete text to stream
        delay_per_char: Delay between characters in seconds (default 0.01 = 10ms)

    Yields:
        Progressive chunks of text
    """
    for i in range(len(text) + 1):
        yield text[:i]
        if delay_per_char > 0:
            time.sleep(delay_per_char)


def stream_text_by_words(text: str, delay_per_word: float = 0.05) -> Generator[str, None, None]:
    """
    Stream text word by word for faster progressive display

    Args:
        text: Complete text to stream
        delay_per_word: Delay between words in seconds (default 0.05 = 50ms)

    Yields:
        Progressive chunks of text
    """
    words = text.split()
    for i in range(len(words) + 1):
        yield ' '.join(words[:i])
        if delay_per_word > 0:
            time.sleep(delay_per_word)


def stream_text_by_chunks(text: str, chunk_size: int = 10, delay_per_chunk: float = 0.02) -> Generator[str, None, None]:
    """
    Stream text in fixed-size character chunks for balanced speed and smoothness

    Args:
        text: Complete text to stream
        chunk_size: Number of characters per chunk (default 10)
        delay_per_chunk: Delay between chunks in seconds (default 0.02 = 20ms)

    Yields:
        Progressive chunks of text
    """
    for i in range(0, len(text), chunk_size):
        yield text[:i + chunk_size]
        if delay_per_chunk > 0:
            time.sleep(delay_per_chunk)


def stream_text_smart(text: str, speed: str = "medium") -> Generator[str, None, None]:
    """
    Smart streaming that adapts based on text length and desired speed

    Args:
        text: Complete text to stream
        speed: "slow" (char by char), "medium" (chunks), "fast" (words)

    Yields:
        Progressive chunks of text
    """
    if speed == "slow":
        yield from stream_text_incremental(text, delay_per_char=0.015)
    elif speed == "fast":
        yield from stream_text_by_words(text, delay_per_word=0.03)
    else:  # medium (default)
        # Adaptive: use chunks for short text, words for long text
        if len(text) < 300:
            yield from stream_text_by_chunks(text, chunk_size=5, delay_per_chunk=0.015)
        else:
            yield from stream_text_by_chunks(text, chunk_size=15, delay_per_chunk=0.02)
