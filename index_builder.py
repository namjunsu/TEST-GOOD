#!/usr/bin/env python3
"""
문서 인덱스 빌더
모든 PDF를 청킹하고 BM25/Vector 인덱스 생성
"""

import pickle
import json
from pathlib import Path
from typing import List, Dict, Any
import pdfplumber
import logging
from tqdm import tqdm

from rag_system.bm25_store import BM25Store
from rag_system.korean_vector_store import KoreanVectorStore

logger = logging.getLogger(__name__)

class IndexBuilder:
    """문서 인덱스 구축"""

    def __init__(self):
        self.docs_dir = Path("docs")
        self.index_dir = Path("indexes")
        self.index_dir.mkdir(exist_ok=True)

        # 청크 설정
        self.chunk_size = 1000  # 글자 수
        self.chunk_overlap = 200  # 중첩

        logger.info("IndexBuilder 초기화")

    def build_all_indexes(self):
        """모든 인덱스 구축"""
        print("📚 문서 인덱싱 시작...")

        # 1. 모든 문서 청킹
        chunks = self.chunk_all_documents()
        print(f"✅ {len(chunks)}개 청크 생성 완료")

        # 2. BM25 인덱스 구축
        self.build_bm25_index(chunks)
        print("✅ BM25 인덱스 구축 완료")

        # 3. Vector 인덱스 구축
        self.build_vector_index(chunks)
        print("✅ Vector 인덱스 구축 완료")

        # 4. 메타데이터 저장
        self.save_metadata(chunks)
        print("✅ 메타데이터 저장 완료")

        print(f"🎉 인덱싱 완료! 총 {len(chunks)}개 청크")

    def chunk_all_documents(self) -> List[Dict]:
        """모든 문서를 청크로 분할"""
        chunks = []
        chunk_id = 0

        # PDF 파일 찾기
        pdf_files = list(self.docs_dir.glob("**/*.pdf"))
        print(f"📄 {len(pdf_files)}개 PDF 발견")

        for pdf_path in tqdm(pdf_files, desc="문서 청킹"):
            try:
                # PDF 텍스트 추출
                text = self._extract_pdf_text(pdf_path)
                if not text:
                    continue

                # 청킹
                doc_chunks = self._create_chunks(text, pdf_path)

                for chunk_text in doc_chunks:
                    chunk = {
                        'id': f"chunk_{chunk_id}",
                        'content': chunk_text,
                        'metadata': {
                            'source': pdf_path.name,
                            'path': str(pdf_path),
                            'chunk_id': chunk_id
                        }
                    }
                    chunks.append(chunk)
                    chunk_id += 1

            except Exception as e:
                logger.error(f"청킹 실패: {pdf_path.name} - {e}")
                continue

        return chunks

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """PDF 텍스트 추출"""
        text = ""

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:50]:  # 최대 50페이지
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.error(f"PDF 읽기 실패: {pdf_path.name} - {e}")

        return text

    def _create_chunks(self, text: str, source_path: Path) -> List[str]:
        """텍스트를 청크로 분할"""
        chunks = []

        # 문장 단위로 분할
        sentences = text.replace('\n', ' ').split('.')

        current_chunk = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 청크 크기 체크
            if len(current_chunk) + len(sentence) < self.chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + ". "

        # 마지막 청크
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def build_bm25_index(self, chunks: List[Dict]):
        """BM25 인덱스 구축"""
        bm25 = BM25Store()

        # 텍스트와 메타데이터 추출
        texts = [chunk['content'] for chunk in chunks]
        metadatas = [chunk['metadata'] for chunk in chunks]

        # 인덱스 구축 (add_documents 사용)
        bm25.add_documents(texts, metadatas)

        # 저장
        index_path = self.index_dir / "bm25_index.pkl"
        with open(index_path, 'wb') as f:
            pickle.dump(bm25, f)

        logger.info(f"BM25 인덱스 저장: {index_path}")

    def build_vector_index(self, chunks: List[Dict]):
        """Vector 인덱스 구축"""
        vector_store = KoreanVectorStore()

        # 임베딩 생성 및 인덱싱
        vector_store.add_documents(chunks)

        # 저장
        vector_store.save_index(str(self.index_dir / "vector_index"))

        logger.info("Vector 인덱스 저장 완료")

    def save_metadata(self, chunks: List[Dict]):
        """청크 메타데이터 저장"""
        metadata_path = self.index_dir / "chunks_metadata.json"

        # 메타데이터만 추출 (content는 너무 크므로 제외)
        metadata = []
        for chunk in chunks:
            metadata.append({
                'id': chunk['id'],
                'source': chunk['metadata']['source'],
                'path': chunk['metadata']['path'],
                'content_preview': chunk['content'][:100]  # 미리보기만
            })

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"메타데이터 저장: {metadata_path}")

    def load_indexes(self) -> Dict:
        """저장된 인덱스 로드"""
        indexes = {}

        # BM25 로드
        bm25_path = self.index_dir / "bm25_index.pkl"
        if bm25_path.exists():
            with open(bm25_path, 'rb') as f:
                indexes['bm25'] = pickle.load(f)

        # Vector 로드
        vector_store = KoreanVectorStore()
        vector_index_path = self.index_dir / "vector_index"
        if vector_index_path.exists():
            vector_store.load_index(str(vector_index_path))
            indexes['vector'] = vector_store

        # 메타데이터 로드
        metadata_path = self.index_dir / "chunks_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                indexes['metadata'] = json.load(f)

        return indexes

if __name__ == "__main__":
    # 인덱스 구축 실행
    builder = IndexBuilder()
    builder.build_all_indexes()