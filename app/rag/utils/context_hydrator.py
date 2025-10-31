#!/usr/bin/env python3
"""
Context Hydrator - 청크에서 텍스트 추출 및 PDF 보강
"""

from typing import List, Dict, Any, Tuple
from pathlib import Path
import logging
import os
import re
import time

logger = logging.getLogger(__name__)


def hydrate_context(chunks: List[Dict[str, Any]], max_len: int = 10000, mode: str = "rag") -> Tuple[str, Dict[str, Any]]:
    """
    청크에서 텍스트를 추출하고 부족하면 PDF 보강

    Args:
        chunks: 검색 결과 청크 리스트
        max_len: 최대 컨텍스트 길이 (문자 수)
        mode: 생성 모드 (chat/rag/summarize)

    Returns:
        (context_text, metrics)
    """
    start_time = time.perf_counter()

    # 🎯 환경 변수에서 컨텍스트 토큰 상한 읽기 (1 token ≈ 3 chars in Korean)
    context_max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", "1200"))
    context_max_chars = context_max_tokens * 3  # 1200 tokens = 3600 chars
    effective_max_len = min(max_len, context_max_chars)

    # 🎯 RAG 스타일 압축 모드 확인
    rag_style_compact = os.getenv("RAG_STYLE_COMPACT", "true").lower() == "true"

    metrics = {
        "chunks_received": len(chunks),
        "chunks_used": 0,
        "pdf_tail_pages": 0,
        "total_length": 0,
        "fallback_chain": [],
        "context_max_tokens": context_max_tokens,
        "context_max_chars": context_max_chars,
        "extraction_time": 0.0,
        "compression_applied": False
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
        pdf_text = _extract_pdf_tail(chunks[0], metrics, needed=effective_max_len - current_len)
        if pdf_text:
            parts.insert(0, pdf_text)
            current_text = "\n\n".join(parts)
            current_len = len(current_text)

    # 3. 🎯 RAG 스타일 압축: 핵심 문장 추출 (모드가 rag이고 compact가 활성화된 경우)
    if mode == "rag" and rag_style_compact and current_len > effective_max_len:
        current_text = _extract_core_sentences(current_text, effective_max_len)
        current_len = len(current_text)
        metrics["compression_applied"] = True

    # 4. 최대 길이 제한 (하드 컷)
    if current_len > effective_max_len:
        current_text = current_text[:effective_max_len]
        current_len = effective_max_len

    metrics["total_length"] = current_len
    metrics["extraction_time"] = time.perf_counter() - start_time

    # 5. 로깅
    parts_info = []
    if metrics["pdf_tail_pages"] > 0:
        parts_info.append(f"pdf_tail:{metrics['pdf_tail_pages']}")
    if metrics["chunks_used"] > 0:
        parts_info.append(f"chunks:{metrics['chunks_used']}")

    logger.info(
        f"LLM_CTX len={current_len}/{effective_max_len}; "
        f"parts=[{', '.join(parts_info)}]; "
        f"compact={metrics['compression_applied']}; "
        f"time={metrics['extraction_time']:.3f}s"
    )

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


def _extract_core_sentences(text: str, max_len: int) -> str:
    """
    핵심 문장 추출 (정보 밀도 기반 필터링)

    우선순위:
    1. 수치 정보 (금액, 날짜, 수량)
    2. 구체적 품목명/모델명
    3. 결론/요약 문장

    Args:
        text: 원본 텍스트
        max_len: 최대 길이

    Returns:
        압축된 텍스트
    """
    # 문장 분리 (한국어 종결어미 기반)
    sentences = re.split(r'([.!?]\s+|\n{2,})', text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]

    # 각 문장에 점수 부여
    scored_sentences = []
    for sent in sentences:
        score = 0

        # 1. 수치 정보 (금액, 날짜, 수량)
        if re.search(r'\d+[,원년월일개대식통만억]', sent):
            score += 3

        # 2. 구체적 키워드 (품목, 모델, 기안, 구매)
        keywords = ['기안', '구매', '수리', '교체', '렌즈', '마이크', '카메라', '케이블',
                    '품목', '모델', '금액', '날짜', '작성', '신청', '건전지', '배터리']
        for kw in keywords:
            if kw in sent:
                score += 1

        # 3. 결론/요약 문장
        if any(marker in sent for marker in ['따라서', '요약', '결론', '목적', '내용']):
            score += 2

        # 4. 첫 문장/마지막 문장 가중치
        if sent == sentences[0] or sent == sentences[-1]:
            score += 1

        scored_sentences.append((score, sent))

    # 점수 순 정렬
    scored_sentences.sort(key=lambda x: x[0], reverse=True)

    # 상위 문장 선택 (길이 제한)
    selected = []
    current_len = 0
    for score, sent in scored_sentences:
        if current_len + len(sent) > max_len:
            break
        selected.append(sent)
        current_len += len(sent)

    # 원본 순서 복원 (가독성 유지)
    selected_set = set(selected)
    ordered = [s for s in sentences if s in selected_set]

    return "\n\n".join(ordered)
