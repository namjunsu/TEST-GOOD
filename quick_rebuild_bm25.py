#!/usr/bin/env python3
"""
BM25 인덱스만 빠르게 재구축
"""

import sys
import time
import logging
from pathlib import Path
import pdfplumber

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 프로젝트 루트 추가
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

def rebuild_bm25():
    """BM25 인덱스만 재구축"""
    from rag_system.bm25_store import BM25Store

    logger.info("BM25 인덱스 재구축 시작...")

    # 문서 수집
    docs_dir = Path("docs")
    pdf_files = list(docs_dir.rglob("*.pdf"))
    logger.info(f"PDF 파일: {len(pdf_files)}개")

    texts = []
    metadatas = []

    for i, pdf_path in enumerate(pdf_files, 1):
        if i % 100 == 0:
            logger.info(f"진행: {i}/{len(pdf_files)}")

        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:10]:
                    page_text = page.extract_text() or ""
                    text += page_text + "\n"

            if text.strip():
                texts.append(text)
                metadatas.append({
                    'filename': pdf_path.name,
                    'path': str(pdf_path),
                    'id': f'doc_{i}'
                })
        except Exception as e:
            pass  # 스킵

    logger.info(f"텍스트 추출 완료: {len(texts)}개")

    # BM25Store 초기화 및 인덱싱
    bm25 = BM25Store(index_path="rag_system/db/bm25_index.pkl")

    # 인덱스 초기화
    bm25.documents = []
    bm25.metadata = []
    bm25.term_freqs = []
    bm25.doc_freqs = {}
    bm25.doc_lens = []
    bm25.vocab = set()

    # 문서 직접 추가 (add_documents 메서드 우회)
    for text, metadata in zip(texts, metadatas):
        tokens = bm25.tokenizer.tokenize(text)

        bm25.documents.append(text)
        bm25.metadata.append(metadata)

        term_freq = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
            bm25.vocab.add(token)

        bm25.term_freqs.append(term_freq)
        bm25.doc_lens.append(len(tokens))

        for token in set(tokens):
            bm25.doc_freqs[token] = bm25.doc_freqs.get(token, 0) + 1

    # 평균 문서 길이 계산
    if bm25.doc_lens:
        bm25.avg_doc_len = sum(bm25.doc_lens) / len(bm25.doc_lens)

    # 저장
    bm25.save_index()

    logger.info(f"✅ BM25 인덱스 완료: {len(bm25.documents)}개 문서")

if __name__ == "__main__":
    rebuild_bm25()