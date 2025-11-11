# app/index/bm25_store.py
# DEPRECATED: 2025-11-11 이후 사용 금지 예정
# ⚠️  실제 운영은 rag_system/bm25_store.py를 사용합니다.
# ⚠️  이 파일은 레거시 라이트 버전으로, 현재 어디서도 import되지 않음
# ⚠️  2주 후 삭제 예정 (사용 흔적 없음 확인 완료: 2025-11-11)

from __future__ import annotations
from pathlib import Path
import pickle
import math
import re
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Any, Optional

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣_]+")  # 간단한 워드바운더리

class BM25Store:
    def __init__(self, index_path: str = "var/index/bm25_index.pkl"):
        self.path = Path(index_path)
        if not self.path.exists():
            raise FileNotFoundError(f"BM25 index not found: {self.path}")
        self._load()

    def _tokenize(self, s: str) -> List[str]:
        # 인덱스 생성 시점과 동일한 규칙을 유지할 것.
        # 최소 안전장치: 영숫자/한글 토큰 단위, 소문자화
        return [m.group(0).lower() for m in _TOKEN_RE.finditer(s or "")]

    def _load(self):
        with self.path.open("rb") as f:
            idx = pickle.load(f)

        if "documents" in idx and isinstance(idx["documents"], list):
            self.texts = idx["documents"]
            self.doc_ids = None
        else:
            self.doc_ids = idx.get("doc_ids")
            self.texts = idx.get("doc_texts") or idx.get("texts") or idx.get("documents")

        if not self.texts:
            raise ValueError("Invalid index: missing texts/documents")

        self.metadata  = idx.get("metadata") or []
        self.df        = idx.get("doc_freqs") or {}
        self.tf        = idx.get("term_freqs") or []
        self.doc_lens  = idx.get("doc_lens") or []
        self.avgdl     = idx.get("avg_doc_len") or idx.get("avgdl") or 0.0

        self.N = len(self.texts)

        # 메타데이터 길이 보정
        if len(self.metadata) < self.N:
            # 부족분은 빈 dict로 패딩
            self.metadata += [{} for _ in range(self.N - len(self.metadata))]
        elif len(self.metadata) > self.N:
            self.metadata = self.metadata[:self.N]

        if (not self.doc_lens) or (len(self.doc_lens) != self.N):
            self.doc_lens = [len(self._tokenize(t)) for t in self.texts]

        if not self.avgdl:
            self.avgdl = (sum(self.doc_lens) / self.N) if self.N else 1.0

        # 토큰 캐시(성능 최적화: tf/df 미보유 인덱스 대비)
        self._token_cache: Optional[List[List[str]]] = None
        if not self.tf:
            self._token_cache = [self._tokenize(t) for t in self.texts]

        # BM25 하이퍼파라미터 기본값
        self.k1_default = 1.6
        self.b_default  = 0.75

    def _ensure_tf_df(self):
        # tf/df가 없을 때 최소 역색인 생성(메모리 절충형)
        if self.tf and self.df:
            return
        if self._token_cache is None:
            self._token_cache = [self._tokenize(t) for t in self.texts]
        self.tf = []
        df_counter = defaultdict(int)
        for toks in self._token_cache:
            c = Counter(toks)
            self.tf.append(c)
            for term in c.keys():
                df_counter[term] += 1
        self.df = dict(df_counter)

    def _bm25(self, query_tokens: List[str], k1: float, b: float) -> List[Tuple[int, float]]:
        self._ensure_tf_df()

        scores = [0.0] * self.N
        for q in query_tokens:
            df = self.df.get(q, 0)
            # Robertson-Sparck Jones IDF with 0.5 smoothing
            idf = math.log(1.0 + (self.N - df + 0.5) / (df + 0.5)) if df > 0 else 0.0

            if idf == 0.0:
                continue

            for i in range(self.N):
                f = self.tf[i].get(q, 0)
                if f == 0:
                    continue
                dl = self.doc_lens[i]
                denom = f + k1 * (1 - b + b * (dl / self.avgdl))
                scores[i] += idf * (f * (k1 + 1.0)) / (denom if denom > 0 else 1e-9)

        ranked = [(i, s) for i, s in enumerate(scores)]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def search(self, query: str, k: int | None = None, **kwargs) -> List[Dict[str, Any]]:
        if k is None:
            k = kwargs.get("top_k", 10)
        # 빈/저품질 쿼리 방어
        q_tokens = [t for t in self._tokenize(query) if t]
        if not q_tokens:
            return []

        k1 = kwargs.get("k1", self.k1_default)
        b  = kwargs.get("b",  self.b_default)
        ranked = self._bm25(q_tokens, k1=k1, b=b)

        # 전부 0점인 경우에도 상위 k개 반환(UX 옵션)
        top = ranked[:k] if ranked else []

        # 스니펫 길이 파라미터화
        snippet_max = int(kwargs.get("snippet_max", 5000))

        out = []
        for idx, score in top:
            meta = self.metadata[idx] if idx < len(self.metadata) else {}
            text = self.texts[idx] or ""
            doc_id = (
                meta.get("filename")
                or meta.get("doc_id")
                or (self.doc_ids[idx] if self.doc_ids and idx < len(self.doc_ids) else f"doc_{idx}")
            )
            out.append({
                "doc_id": doc_id,
                "score": float(score),
                "snippet": text[:snippet_max],
                "meta": meta,
                "page": 1,
            })
        return out

    def stats(self) -> Dict[str, Any]:
        return {
            "bm25_index_docs": self.N,
            "bm25_index_path": str(self.path),
            "avgdl": self.avgdl,
            "has_tf": bool(self.tf),
            "has_df": bool(self.df),
        }
