#!/usr/bin/env python3
"""
Context Hydrator - 청크에서 텍스트 추출 및 PDF 보강
"""

from typing import List, Dict, Any, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def hydrate_context(chunks: List[Dict[str, Any]], max_len: int = 10000) -> Tuple[str, Dict[str, Any]]:
    """
    청크에서 텍스트를 추출하고 부족하면 PDF 보강

    Args:
        chunks: 검색 결과 청크 리스트
        max_len: 최대 컨텍스트 길이

    Returns:
        (context_text, metrics)
    """
    metrics = {
        "chunks_received": len(chunks),
        "chunks_used": 0,
        "pdf_tail_pages": 0,
        "total_length": 0,
        "fallback_chain": []
    }

    parts = []

    # 1. 청크에서 텍스트 추출 (키 폴백 체인)
    for i, chunk in enumerate(chunks):
        text = _extract_text_from_chunk(chunk, metrics)
        if text:
            parts.append(text)
            metrics["chunks_used"] += 1

    # 2. 길이 체크
    current_text = "\n\n".join(parts)
    current_len = len(current_text)

    if current_len < 500 and chunks:
        # PDF 보강 시도
        pdf_text = _extract_pdf_tail(chunks[0], metrics, needed=max_len - current_len)
        if pdf_text:
            parts.insert(0, pdf_text)
            current_text = "\n\n".join(parts)
            current_len = len(current_text)

    # 3. 최대 길이 제한
    if current_len > max_len:
        current_text = current_text[:max_len]
        current_len = max_len

    metrics["total_length"] = current_len

    # 4. 로깅
    parts_info = []
    if metrics["pdf_tail_pages"] > 0:
        parts_info.append(f"pdf_tail:{metrics['pdf_tail_pages']}")
    if metrics["chunks_used"] > 0:
        parts_info.append(f"chunks:{metrics['chunks_used']}")

    logger.info(f"LLM_CTX len={current_len}; parts=[{', '.join(parts_info)}]")

    if current_len == 0:
        logger.warning(f"⚠️ Context is empty! chunks={len(chunks)}, fallback_chain={metrics['fallback_chain']}")

    return current_text, metrics


def _extract_text_from_chunk(chunk: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    """
    청크에서 텍스트 추출 (폴백 체인)

    폴백 순서: text → content → snippet → text_preview → ""
    """
    # 폴백 체인
    keys = ["text", "content", "snippet", "text_preview"]

    for key in keys:
        if key in chunk and chunk[key]:
            text = str(chunk[key]).strip()
            if text:
                if key not in metrics["fallback_chain"]:
                    metrics["fallback_chain"].append(key)
                return text

    return ""


def _extract_pdf_tail(chunk: Dict[str, Any], metrics: Dict[str, Any], needed: int = 5000) -> str:
    """
    PDF 마지막 2페이지 추출 (결론/요약 가능성 높음)

    Args:
        chunk: 첫 번째 청크 (파일 경로 포함)
        metrics: 메트릭 딕셔너리
        needed: 필요한 텍스트 길이

    Returns:
        추출된 텍스트
    """
    try:
        # 파일 경로 찾기
        file_path = chunk.get("file_path") or chunk.get("path") or chunk.get("filename")

        if not file_path:
            return ""

        file_path = Path(file_path)

        # 보안: docs 폴더 외부 차단
        if "docs" not in file_path.parts:
            logger.warning(f"⚠️ PDF path outside docs: {file_path}")
            return ""

        if not file_path.exists():
            logger.warning(f"⚠️ PDF not found: {file_path}")
            return ""

        # PDF 읽기
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)

            if total_pages == 0:
                return ""

            # 마지막 2페이지 (또는 전체)
            start_page = max(0, total_pages - 2)
            pages_to_read = min(2, total_pages)

            text_parts = []
            for page_num in range(start_page, total_pages):
                page_text = pdf.pages[page_num].extract_text()
                if page_text:
                    text_parts.append(page_text)

            if text_parts:
                metrics["pdf_tail_pages"] = len(text_parts)
                combined = "\n\n".join(text_parts)

                # 필요한 만큼만 자르기
                if len(combined) > needed:
                    combined = combined[:needed]

                return combined

    except Exception as e:
        logger.warning(f"⚠️ PDF extraction failed: {e}")

    return ""
