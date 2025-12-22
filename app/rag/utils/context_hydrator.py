#!/usr/bin/env python3
"""
Context Hydrator - 청크에서 텍스트 추출 및 PDF 보강

2025-12-21 v1.1 변경사항:
- 환경변수 캐싱 (os.getenv 반복 호출 제거)
- 프로젝트 표준 로거 사용 (app.core.logging)
"""

import os
import re
import time
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from config.constants import ContextHydratorConfig

logger = get_logger(__name__)


# ============================================================================
# 환경변수 캐싱 (모듈 로드 시 1회만 읽음)
# ============================================================================

# 문장 스코어링 휴리스틱 가중치
SCORE_WEIGHTS = {
    "numeric": int(os.getenv("HYDRATOR_W_NUMERIC", "3")),        # 금액/날짜/수량
    "keyword": int(os.getenv("HYDRATOR_W_KEYWORD", "1")),        # 도메인 키워드
    "conclusion": int(os.getenv("HYDRATOR_W_CONCLUSION", "2")),  # 결론/요약 마커
    "edge_bonus": int(os.getenv("HYDRATOR_W_EDGE", "1")),        # 첫/마지막 문장 가중
}

# 세미버(v1.2.3) 패턴을 숫자 가중에서 제외 (과다 반영 방지)
IGNORE_SEMVER_IN_NUMERIC = os.getenv("IGNORE_SEMVER_IN_NUMERIC", "false").lower() == "true"

# 말미 가중치 (마지막 문장/문단 보정)
END_BONUS = int(os.getenv("END_BONUS", "1"))

# Context 관련 환경변수 캐싱
_ENV_CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "1200"))
_ENV_TOKENS_PER_CHAR = float(os.getenv("TOKENS_PER_CHAR", "0.33"))
_ENV_RAG_STYLE_COMPACT = os.getenv("RAG_STYLE_COMPACT", "true").lower() == "true"
_ENV_DOCS_DIR = os.getenv("DOCS_DIR", "docs")


def hydrate_context(chunks: list[dict[str, Any]], max_len: int = 10000, mode: str = "rag") -> tuple[str, dict[str, Any]]:
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

    # 환경변수 동적 조회 (테스트 시 patch 가능)
    context_max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", str(_ENV_CONTEXT_MAX_TOKENS)))
    tokens_per_char = float(os.getenv("TOKENS_PER_CHAR", str(_ENV_TOKENS_PER_CHAR)))
    context_max_chars = int(context_max_tokens / max(tokens_per_char, 1e-6))
    effective_max_len = min(max_len, context_max_chars)
    rag_style_compact = os.getenv("RAG_STYLE_COMPACT", str(_ENV_RAG_STYLE_COMPACT).lower()).lower() == "true"

    metrics = {
        "chunks_received": len(chunks),
        "chunks_used": 0,
        "pdf_tail_pages": 0,
        "pdf_tail_status": "skipped",  # skipped | success | fail
        "total_length": 0,
        "fallback_chain": [],
        "context_max_tokens": context_max_tokens,
        "context_max_chars": context_max_chars,
        "extraction_time": 0.0,
        "compression_applied": False,
        "token_estimate": 0,
        "truncate_reason": "none",
    }

    parts = []
    seen_texts = set()  # 중복 제거용

    # 1. 청크에서 텍스트 추출 (키 폴백 체인 + 중복 제거)
    for chunk in chunks:
        text = _extract_text_from_chunk(chunk, metrics)
        if text:
            # 중복 체크: 텍스트의 처음 N자를 해시로 사용
            text_hash = text[:ContextHydratorConfig.DEDUP_HASH_LENGTH]
            if text_hash in seen_texts:
                continue
            seen_texts.add(text_hash)
            parts.append(text)
            metrics["chunks_used"] += 1

    # 2. 길이 체크
    current_text = "\n\n".join(parts)
    current_len = len(current_text)

    if current_len < ContextHydratorConfig.MIN_TEXT_FOR_PDF and chunks:
        # PDF 보강 시도
        pdf_text = _extract_pdf_tail(chunks[0], metrics, needed=effective_max_len - current_len)
        if pdf_text:
            parts.insert(0, pdf_text)
            current_text = "\n\n".join(parts)
            current_len = len(current_text)

    # 3. 🎯 모드별 컨텍스트 압축 정책
    if mode == "rag" and rag_style_compact and current_len > effective_max_len:
        # RAG 모드: 핵심 문장 추출 (정보 밀도 기반 압축)
        current_text = _extract_core_sentences(current_text, effective_max_len)
        current_len = len(current_text)
        metrics["compression_applied"] = True
    elif mode == "summarize":
        # Summarize 모드: 압축 비적용, 하드 컷만 수행
        pass

    # 4. 최대 길이 제한 (하드 컷 - 문단 단위)
    if current_len > effective_max_len:
        current_text = _hard_cut_paragraphwise(current_text, effective_max_len)
        current_len = len(current_text)

    metrics["total_length"] = current_len
    metrics["token_estimate"] = int(current_len * tokens_per_char)

    # 트렁케이션 사유 결정
    if metrics["compression_applied"]:
        metrics["truncate_reason"] = "compact"
    elif current_len >= effective_max_len:
        metrics["truncate_reason"] = "hardcut"
    else:
        metrics["truncate_reason"] = "none"

    metrics["extraction_time"] = time.perf_counter() - start_time

    # 5. 로깅 (단일 라인 요약 - 운영 모니터링)
    parts_info = []
    if metrics["chunks_used"] > 0:
        parts_info.append(f"chunks:{metrics['chunks_used']}")
    if metrics["pdf_tail_pages"] > 0:
        parts_info.append(f"pdf_tail:{metrics['pdf_tail_pages']}")

    logger.info(
        f"CTX len={current_len}/{effective_max_len} "
        f"tokens~={metrics['token_estimate']} "
        f"src=[{','.join(parts_info)}] "
        f"truncate={metrics['truncate_reason']} "
        f"mode={mode} "
        f"coef={tokens_per_char:.2f} "
        f"time={metrics['extraction_time']:.3f}s",
    )

    if current_len == 0:
        logger.error(
            f"❌ CONTEXT_EMPTY chunks={len(chunks)} "
            f"fallback_chain={metrics['fallback_chain']} "
            f"pdf_tail_status={metrics['pdf_tail_status']} "
            f"metrics={metrics}",
        )

    return current_text, metrics


def _hard_cut_paragraphwise(text: str, max_len: int) -> str:
    """
    문단 단위로 하드 컷 (의미 단위 보존)

    Args:
        text: 원본 텍스트
        max_len: 최대 길이

    Returns:
        문단 단위로 잘린 텍스트
    """
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    out, total = [], 0
    for p in paras:
        if total + len(p) + 2 > max_len:
            break
        out.append(p)
        total += len(p) + 2
    return "\n\n".join(out) if out else text[:max_len]


def _extract_text_from_chunk(chunk: dict[str, Any], metrics: dict[str, Any]) -> str:
    """
    청크에서 텍스트 추출 (폴백 체인 + 경량 정규화)

    폴백 순서: text → content → page_content → raw_text → snippet → text_preview → abstract → ""
    """
    # HTML/마크다운 잔여물 패턴
    html_tags = re.compile(r"<[^>]+>")
    md_artifacts = re.compile(r"^\s*[#>\-*|`]{1,}", re.MULTILINE)

    # 폴백 체인 (확장)
    keys = ["text", "content", "page_content", "raw_text", "snippet", "text_preview", "abstract"]

    for key in keys:
        val = chunk.get(key)
        if not val:
            continue
        text = str(val).strip()
        if not text:
            continue

        # 경량 정규화: HTML 태그, 마크다운 아티팩트 제거
        text = html_tags.sub(" ", text)
        text = md_artifacts.sub(" ", text)
        text = re.sub(r"[ \t]+", " ", text).strip()

        if text:
            if key not in metrics["fallback_chain"]:
                metrics["fallback_chain"].append(key)
            return text

    return ""


def _is_under_docs(path: Path) -> bool:
    """
    경로가 docs 디렉토리 하위인지 보안 검증

    Args:
        path: 검증할 경로

    Returns:
        docs 하위 여부
    """
    try:
        # 환경변수 동적 조회 (테스트 시 patch 가능)
        docs_dir = os.getenv("DOCS_DIR", _ENV_DOCS_DIR)
        base_docs = Path(docs_dir).resolve()
        resolved_path = path.resolve()
        return base_docs in resolved_path.parents or resolved_path == base_docs
    except Exception:
        return False


def _extract_pdf_tail(chunk: dict[str, Any], metrics: dict[str, Any], needed: int = ContextHydratorConfig.PDF_NEEDED_LENGTH) -> str:
    """
    PDF 마지막 2페이지 추출 (결론/요약 가능성 높음)

    보안 강화:
    - 경로 검증: resolve() 후 docs 하위 확인
    - 확장자 검증: .pdf만 허용
    - 파일 크기 제한: 64MB 상한

    실패 모드:
    - metrics["pdf_tail_status"] = "fail" 기록

    Args:
        chunk: 첫 번째 청크 (파일 경로 포함)
        metrics: 메트릭 딕셔너리
        needed: 필요한 텍스트 길이

    Returns:
        추출된 텍스트
    """
    try:
        # 파일 경로 찾기 (다중 키 폴백)
        file_path = chunk.get("file_path") or chunk.get("path") or chunk.get("filename")

        if not file_path:
            return ""

        p = Path(file_path)

        # 보안 검증 1: PDF 확장자 확인
        if p.suffix.lower() != ".pdf":
            return ""

        # 보안 검증 2: docs 디렉토리 하위인지 확인 (심볼릭 링크 우회 방지)
        if not _is_under_docs(p):
            logger.warning(f"⚠️ PDF outside docs root: {p}")
            metrics["pdf_tail_status"] = "fail"
            return ""

        # 보안 검증 3: 파일 존재 및 크기 제한 (64MB)
        if not p.exists():
            logger.warning(f"⚠️ PDF not found: {p}")
            metrics["pdf_tail_status"] = "fail"
            return ""

        max_pdf_bytes = ContextHydratorConfig.MAX_PDF_SIZE_MB * 1024 * 1024
        if p.stat().st_size > max_pdf_bytes:
            logger.warning(f"⚠️ PDF too large: {p} ({p.stat().st_size / 1024 / 1024:.1f}MB)")
            metrics["pdf_tail_status"] = "fail"
            return ""

        # PDF 읽기
        import pdfplumber

        with pdfplumber.open(p) as pdf:
            total_pages = len(pdf.pages)

            if total_pages == 0:
                metrics["pdf_tail_status"] = "fail"
                return ""

            # 마지막 2페이지 (또는 전체)
            start_page = max(0, total_pages - 2)

            text_parts = []
            for page_num in range(start_page, total_pages):
                page_text = pdf.pages[page_num].extract_text()
                if page_text:
                    text_parts.append(page_text)

            if text_parts:
                metrics["pdf_tail_pages"] = len(text_parts)
                metrics["pdf_tail_status"] = "success"
                combined = "\n\n".join(text_parts)

                # 필요한 만큼만 자르기
                if len(combined) > needed:
                    combined = combined[:needed]

                return combined
            # 텍스트 레이어 없음 (OCR 필요)
            metrics["pdf_tail_status"] = "fail"
            return ""

    except Exception as e:
        logger.warning(f"⚠️ PDF extraction failed: {e}")
        metrics["pdf_tail_status"] = "fail"

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
    # 문장 분리 (lookbehind로 구분자 미포함)
    sent_boundary = re.compile(r"(?<=[.!?])\s+|\n{2,}")
    sentences = [s.strip() for s in sent_boundary.split(text) if len(s.strip()) > ContextHydratorConfig.MIN_SENTENCE_LENGTH]

    # 수치/단위 패턴 (쉼표 구분 숫자 + 단위)
    numeric = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b")
    semver = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")  # 세미버 패턴 (v1.2.3)
    units = ("원", "년", "월", "일", "개", "대", "만", "억", "식", "통", "건", "명", "권", "대")

    # 도메인 키워드 확장
    keywords = ("기안", "구매", "수리", "교체", "렌즈", "마이크", "카메라", "케이블",
                "품목", "모델", "금액", "날짜", "작성", "신청", "배터리", "건전지",
                "소모품", "장비", "방송", "촬영", "사옥", "검토")

    # 각 문장에 점수 부여 (인덱스 보존)
    scored = []
    for idx, sent in enumerate(sentences):
        score = 0

        # 1) 수치 정보 (쉼표 구분 숫자 + 단위)
        has_numeric = numeric.search(sent) or any(u in sent for u in units)
        if has_numeric:
            # 세미버 무시 옵션: v1.2.3 같은 버전 번호 제외
            if IGNORE_SEMVER_IN_NUMERIC and semver.search(sent):
                pass  # 숫자 가중치 미적용
            else:
                score += SCORE_WEIGHTS["numeric"]

        # 2) 도메인 키워드
        score += sum(SCORE_WEIGHTS["keyword"] for kw in keywords if kw in sent)

        # 3) 결론·요약 마커
        if any(m in sent for m in ("따라서", "요약", "결론", "목적", "종합", "권고", "확정", "내용")):
            score += SCORE_WEIGHTS["conclusion"]

        # 4) 서두/말미 가중치
        if END_BONUS and idx in (0, len(sentences) - 1):
            score += SCORE_WEIGHTS["edge_bonus"]

        scored.append((score, idx, sent))

    # 점수 순 정렬 (점수 동일 시 원문 순서 유지)
    scored.sort(key=lambda x: (-x[0], x[1]))

    # 상위 문장 선택 (길이 제한)
    selected, total = [], 0
    for _, idx, s in scored:
        if total + len(s) > max_len:
            continue
        selected.append((idx, s))
        total += len(s)
        if total >= max_len:
            break

    # 원본 순서 복원 (인덱스 기반)
    selected.sort(key=lambda x: x[0])
    ordered = [s for _, s in selected]

    return "\n\n".join(ordered)
