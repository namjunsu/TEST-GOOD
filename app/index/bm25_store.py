# app/index/bm25_store.py
from __future__ import annotations
from pathlib import Path
import pickle
import math
from typing import List, Tuple, Dict, Any

class BM25Store:
    def __init__(self, index_path: str = "var/index/bm25_index.pkl"):
        self.path = Path(index_path)
        if not self.path.exists():
            raise FileNotFoundError(f"BM25 index not found: {self.path}")
        self._load()

    def _load(self):
        with self.path.open("rb") as f:
            idx = pickle.load(f)

        # 인덱스 구조 자동 감지
        # 신규 구조: documents (list of texts), metadata (list of dicts)
        # 레거시 구조: doc_ids, doc_texts, texts

        # documents가 texts를 담고 있는 경우 (reindex_atomic.py 출력)
        if "documents" in idx and isinstance(idx["documents"], list):
            self.texts = idx["documents"]
            self.doc_ids = None  # documents가 texts 자체임
        else:
            # 레거시 fallback
            self.doc_ids   = idx.get("doc_ids")
            self.texts     = idx.get("doc_texts") or idx.get("texts") or idx.get("documents")

        self.metadata  = idx.get("metadata") or []
        self.df        = idx.get("doc_freqs") or {}
        self.tf        = idx.get("term_freqs") or []
        self.doc_lens  = idx.get("doc_lens") or []
        self.avgdl     = idx.get("avg_doc_len") or idx.get("avgdl") or 0.0

        if not self.texts:
            raise ValueError("Invalid index: missing texts/documents")

        self.N = len(self.texts)

        # avgdl 계산 (없는 경우)
        if not self.avgdl and self.doc_lens:
            self.avgdl = sum(self.doc_lens) / len(self.doc_lens)
        elif not self.avgdl:
            # doc_lens도 없으면 근사치 계산
            self.avgdl = sum(len(t.split()) for t in self.texts) / self.N if self.N > 0 else 1.0
            self.doc_lens = [len(t.split()) for t in self.texts]

        # 토큰화는 인덱스 생성 시점과 동일해야 함(간단 토크나이즈로 방어)
        self._token = lambda s: [t for t in s.lower().split() if t]

    def _bm25(self, query_tokens: List[str], k1: float = 1.6, b: float = 0.75) -> List[Tuple[int, float]]:
        # term_freqs/ doc_freqs 가 있을 때 사용, 없으면 라이트 가중치로 대체
        scores = [0.0]*self.N
        for q in query_tokens:
            if self.df and q in self.df:
                df = self.df[q]
                idf = math.log(1 + (self.N - df + 0.5)/(df + 0.5))
            else:
                # df 없으면 라이트 idf
                idf = 1.0

            for i in range(self.N):
                # 사전계산 tf가 있으면 활용
                f = self.tf[i].get(q, 0) if (self.tf and i < len(self.tf)) else self.texts[i].lower().count(q)
                if f == 0:
                    continue
                dl = self.doc_lens[i] if self.doc_lens else len(self.texts[i].split())
                denom = f + k1*(1 - b + b*(dl/self.avgdl))
                scores[i] += idf * (f*(k1+1))/max(denom, 1e-9)
        # 상위만 정렬
        return sorted([(i, s) for i, s in enumerate(scores) if s > 0], key=lambda x: x[1], reverse=True)

    def search(self, query: str, k: int | None = None, **kwargs) -> List[Dict[str, Any]]:
        # backward/forward compatible alias: top_k=와 k= 모두 지원
        if k is None:
            k = kwargs.get("top_k", None)
        if k is None:
            k = 10

        q_tokens = self._token(query)
        ranked = self._bm25(q_tokens)
        top = ranked[:k] if ranked else []
        out = []
        for idx, score in top:
            meta = self.metadata[idx]
            # 충분한 길이의 본문 제공(LLM 컨텍스트 품질 개선)
            text = self.texts[idx]
            out.append({
                "doc_id": meta.get("filename") or meta.get("doc_id") or (self.doc_ids[idx] if self.doc_ids else f"doc_{idx}"),
                "score": float(score),
                "snippet": text[:5000],  # UI/LLM 모두에 넉넉히 제공
                "meta": meta,
                "page": 1  # 호환성
            })
        return out

    def stats(self) -> Dict[str, Any]:
        return {
            "bm25_index_docs": self.N,
            "bm25_index_path": str(self.path),
        }
