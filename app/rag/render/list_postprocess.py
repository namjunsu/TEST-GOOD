"""
검색 결과 목록 후처리 모듈
- 텍스트 노이즈 제거 (타임스탬프, URL, 페이지 번호)
- 중복 문서 제거 (정규화된 파일명 기준)
- 빈 스니펫 폴백 (메타데이터 기반)
"""

import re
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Tuple

# TextCleaner 가져오기 (폴백 포함)
try:
    from app.rag.preprocess.clean_text import TextCleaner
    _cleaner = TextCleaner()
    def clean_text(text: str) -> str:
        cleaned, _ = _cleaner.clean(text or "")
        return cleaned
except Exception:
    def clean_text(t: str) -> str:  # 최소 폴백
        return t or ""

# 노이즈 패턴
TS_RE = re.compile(r"(오전|오후)\s?\d{1,2}:\d{2}")
URL_RE = re.compile(r"(approval_form_popup\.php\S*|gw\.channela-mt\.com\S*)", re.I)
PAGE_NUM_RE = re.compile(r"^\s*-\s*\d+\s*-\s*$", re.M)


def _normalize_fname(name: str) -> str:
    """파일명 정규화 (중복 검출용)"""
    import unicodedata
    n = (name or "").strip()
    n = unicodedata.normalize("NFKC", n)
    n = n.replace(" ", "_").replace("-", "_").lower()  # 공백, 하이픈 → 언더스코어
    n = re.sub(r"\((\d+)\)(?=\.pdf$)", "", n, flags=re.I)  # (1).pdf 제거
    n = re.sub(r"_(\d+)(?=\.pdf$)", "", n, flags=re.I)     # _1.pdf 제거
    n = re.sub(r"__+", "_", n)  # 연속 언더스코어 제거
    return n


def _parse_date(s: str) -> Tuple[int, str]:
    """날짜 문자열을 타임스탬프로 변환 (정렬용)"""
    try:
        return (int(datetime.strptime(s[:10], "%Y-%m-%d").timestamp()), s)
    except Exception:
        return (0, s or "")


def _clean_snippet(text: str) -> str:
    """스니펫 텍스트 클리닝"""
    t = clean_text(text or "")
    t = TS_RE.sub("", t)
    t = URL_RE.sub("", t)
    t = PAGE_NUM_RE.sub("", t)
    # 잔여 공백 정리
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _fallback_snippet(item: Dict[str, Any]) -> str:
    """빈 스니펫 시 메타데이터 기반 폴백"""
    parts = []
    drafter = item.get("drafter") or "기안자 미상"
    date = item.get("date") or ""
    cat = item.get("category") or "미분류"

    if item.get("title"):
        parts.append(item["title"])
    parts.append(f"[{drafter}] {date} · {cat}")

    if "claimed_total" in item and item["claimed_total"]:
        parts.append(f"합계(VAT 별도): {item['claimed_total']}")

    return " / ".join([p for p in parts if p]).strip()


def _primary_snippet(item: Dict[str, Any]) -> str:
    """주 스니펫 생성 (클린 + 폴백)"""
    raw = item.get("content") or item.get("raw_fragment") or item.get("text_preview") or ""
    snip = _clean_snippet(raw)
    return snip if snip else _fallback_snippet(item)


def dedup_and_clean(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    동일 문서 중복 제거 + 스니펫 클린/폴백 적용

    Args:
        items: 검색 결과 리스트 (각 항목은 filename, date, drafter, category, content/text_preview, score 포함)

    Returns:
        중복 제거 및 클린된 결과 리스트 (각 항목에 snippet 키 추가)
    """
    buckets = defaultdict(list)

    for it in items:
        key = _normalize_fname(it.get("filename") or it.get("doc_name") or "")
        buckets[key].append(it)

    result = []
    for key, group in buckets.items():
        # 최신 날짜 > 높은 스코어 우선
        def _score(it):
            ts, _ = _parse_date(it.get("date") or "")
            sc = float(it.get("score") or 0.0)
            return (ts, sc)

        best = sorted(group, key=_score, reverse=True)[0]

        # snippet 키 추가 (클린 + 폴백)
        best["snippet"] = _primary_snippet(best)
        result.append(best)

    # 정렬: 날짜 desc, 제목 asc
    def _sort_key(it):
        ts, _ = _parse_date(it.get("date") or "")
        title = (it.get("title") or it.get("filename") or "").lower()
        return (-ts, title)

    result.sort(key=_sort_key)
    return result
