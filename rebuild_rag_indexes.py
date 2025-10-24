#!/usr/bin/env python3
"""
RAG 인덱스 재구축 스크립트
- BM25 인덱스 재구축
- Vector 인덱스 재구축
- 현재 812개 PDF 문서 기준
"""

import sys
import time
import logging
from pathlib import Path
from typing import List, Dict
import pdfplumber

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 프로젝트 루트 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rag_system.bm25_store import BM25Store
from rag_system.korean_vector_store import KoreanVectorStore


class RAGIndexBuilder:
    """RAG 인덱스 빌더"""

    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = Path(docs_dir)
        self.bm25_store = None
        self.vector_store = None

    def collect_documents(self) -> List[Dict]:
        """모든 PDF 문서 수집"""
        logger.info(f"📂 문서 수집 중: {self.docs_dir}")

        pdf_files = list(self.docs_dir.rglob("*.pdf"))
        logger.info(f"📊 발견된 PDF: {len(pdf_files)}개")

        documents = []

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 100 == 0:
                logger.info(f"진행: {i}/{len(pdf_files)}")

            try:
                # PDF 텍스트 추출
                text = ""
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages[:10]:  # 최대 10페이지
                        page_text = page.extract_text() or ""
                        text += page_text + "\n"

                if text.strip():
                    documents.append({
                        'filename': pdf_path.name,
                        'path': str(pdf_path),
                        'content': text,
                        'id': f"doc_{i}"
                    })
            except Exception as e:
                logger.warning(f"⚠️  {pdf_path.name} 처리 실패: {e}")

        logger.info(f"✅ 텍스트 추출 완료: {len(documents)}개 문서")
        return documents

    def rebuild_bm25_index(self, documents: List[Dict]):
        """BM25 인덱스 재구축"""
        logger.info("🔨 BM25 인덱스 재구축 시작...")
        start_time = time.time()

        try:
            # BM25Store 초기화 (새 인덱스 생성)
            self.bm25_store = BM25Store(
                index_path="rag_system/db/bm25_index.pkl"
            )
            # 기존 인덱스 초기화
            self.bm25_store._create_new_index()

            # 문서 텍스트와 메타데이터 분리
            texts = [doc['content'] for doc in documents]
            metadatas = [
                {
                    'id': doc['id'],
                    'filename': doc['filename'],
                    'path': doc['path']
                }
                for doc in documents
            ]

            # 배치로 문서 추가
            self.bm25_store.add_documents(texts, metadatas, batch_size=100)

            # 인덱스 저장
            self.bm25_store.save_index()

            elapsed = time.time() - start_time
            logger.info(f"✅ BM25 인덱스 완료: {len(documents)}개 문서, {elapsed:.1f}초")

        except Exception as e:
            logger.error(f"❌ BM25 인덱스 실패: {e}")
            raise

    def rebuild_vector_index(self, documents: List[Dict]):
        """Vector 인덱스 재구축"""
        logger.info("🔨 Vector 인덱스 재구축 시작...")
        start_time = time.time()

        try:
            # KoreanVectorStore 초기화
            self.vector_store = KoreanVectorStore(
                index_path="rag_system/db/korean_vector_index.faiss"
            )
            # 새 인덱스 생성
            self.vector_store.create_new_index()

            # 문서 텍스트와 메타데이터 분리
            texts = []
            metadatas = []

            for doc in documents:
                # 긴 문서는 첫 5000자만 사용 (메모리 절약)
                content = doc['content']
                if len(content) > 5000:
                    content = content[:5000]

                texts.append(content)
                metadatas.append({
                    'id': doc['id'],
                    'filename': doc['filename'],
                    'path': doc['path']
                })

            # 배치로 문서 추가
            batch_size = 50
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                batch_metadatas = metadatas[i:i+batch_size]

                self.vector_store.add_documents(batch_texts, batch_metadatas)

                logger.info(f"진행: {min(i+batch_size, len(documents))}/{len(documents)}")

            # 인덱스 저장
            self.vector_store.save_index()

            elapsed = time.time() - start_time
            logger.info(f"✅ Vector 인덱스 완료: {len(documents)}개 문서, {elapsed:.1f}초")

        except Exception as e:
            logger.error(f"❌ Vector 인덱스 실패: {e}")
            raise

    def build_all(self):
        """전체 인덱스 재구축"""
        logger.info("🚀 RAG 인덱스 재구축 시작")
        logger.info("=" * 60)

        total_start = time.time()

        # 1. 문서 수집
        documents = self.collect_documents()

        if not documents:
            logger.error("❌ 문서가 없습니다!")
            return False

        # 2. BM25 인덱스
        try:
            self.rebuild_bm25_index(documents)
        except Exception as e:
            logger.error(f"BM25 인덱스 실패: {e}")
            return False

        # 3. Vector 인덱스
        try:
            self.rebuild_vector_index(documents)
        except Exception as e:
            logger.error(f"Vector 인덱스 실패: {e}")
            return False

        # 완료
        total_elapsed = time.time() - total_start
        logger.info("=" * 60)
        logger.info(f"🎉 전체 인덱스 재구축 완료!")
        logger.info(f"📊 총 문서: {len(documents)}개")
        logger.info(f"⏱️  총 시간: {total_elapsed:.1f}초 ({total_elapsed/60:.1f}분)")
        logger.info("=" * 60)

        return True


def main():
    """메인 실행"""
    print("🔨 RAG 인덱스 재구축 도구")
    print("=" * 60)
    print()

    builder = RAGIndexBuilder(docs_dir="docs")

    success = builder.build_all()

    if success:
        print("\n✅ 인덱스 재구축 성공!")
        print("이제 하이브리드 검색을 사용할 수 있습니다.")
        return 0
    else:
        print("\n❌ 인덱스 재구축 실패")
        print("로그를 확인하세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
