#!/usr/bin/env python3
"""
RAG 인덱스 재구축 스크립트 (DB-Driven)
- BM25 인덱스 재구축
- Vector 인덱스 재구축
- metadata.db의 ID와 text_preview를 사용하여 인덱스와 DB를 1:1 매핑
"""

import sys
import time
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict

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
    """RAG 인덱스 빌더 (DB-Driven)"""

    def __init__(self, db_path: str = "metadata.db"):
        self.db_path = Path(db_path)
        self.bm25_store = None
        self.vector_store = None

    def collect_documents(self) -> List[Dict]:
        """metadata.db에서 문서 수집 (ID와 text_preview 사용)"""
        logger.info(f"📂 metadata.db에서 문서 로드 중: {self.db_path}")

        if not self.db_path.exists():
            logger.error(f"❌ {self.db_path} 파일이 없습니다!")
            return []

        documents = []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # text_preview가 있는 문서만 조회 (최소 50자 이상)
            MIN_TEXT_LEN = 50
            cursor.execute("""
                SELECT id, filename, path, text_preview
                FROM documents
                WHERE text_preview IS NOT NULL
                  AND LENGTH(text_preview) >= ?
                ORDER BY id ASC
            """, (MIN_TEXT_LEN,))

            rows = cursor.fetchall()
            logger.info(f"📊 발견된 문서: {len(rows)}개")

            for db_id, filename, path, text_preview in rows:
                if len(documents) % 100 == 0 and len(documents) > 0:
                    logger.info(f"진행: {len(documents)}/{len(rows)}")

                # CRITICAL: Use DB's ID directly (doc_4094, doc_4095, ...)
                documents.append({
                    'id': f"doc_{db_id}",  # DB ID와 동일하게 매핑
                    'filename': filename or "unknown.pdf",
                    'path': path or "",
                    'content': text_preview  # DB의 text_preview 사용
                })

            conn.close()
            logger.info(f"✅ 문서 로드 완료: {len(documents)}개")

        except Exception as e:
            logger.error(f"❌ DB 조회 실패: {e}")
            raise

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
            # CRITICAL: 파일명 키워드 추출하여 검색 가능하게 만들기
            import re
            texts = []
            for doc in documents:
                # 파일명에서 키워드 추출 (날짜, 확장자 제외)
                filename = doc['filename']
                # 날짜 패턴 제거 (2017-12-21, 2025-03-04 등)
                filename_clean = re.sub(r'\d{4}-\d{2}-\d{2}_?', '', filename)
                # 확장자 제거
                filename_clean = re.sub(r'\.(pdf|PDF)$', '', filename_clean)
                # 언더스코어를 공백으로
                filename_keywords = filename_clean.replace('_', ' ').strip()

                # 파일명 키워드 + 본문 내용
                enhanced_text = f"[파일명: {filename_keywords}]\n\n{doc['content']}"
                texts.append(enhanced_text)

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
            # CRITICAL: 파일명 키워드 추출하여 검색 가능하게 만들기
            import re
            texts = []
            metadatas = []

            for doc in documents:
                # 파일명에서 키워드 추출 (날짜, 확장자 제외)
                filename = doc['filename']
                filename_clean = re.sub(r'\d{4}-\d{2}-\d{2}_?', '', filename)
                filename_clean = re.sub(r'\.(pdf|PDF)$', '', filename_clean)
                filename_keywords = filename_clean.replace('_', ' ').strip()

                # 파일명 키워드 + 본문 내용
                content = doc['content']
                enhanced_content = f"[파일명: {filename_keywords}]\n\n{content}"

                # 긴 문서는 첫 5000자만 사용 (메모리 절약)
                if len(enhanced_content) > 5000:
                    enhanced_content = enhanced_content[:5000]

                texts.append(enhanced_content)
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
    print("🔨 RAG 인덱스 재구축 도구 (DB-Driven)")
    print("=" * 60)
    print()

    builder = RAGIndexBuilder(db_path="metadata.db")

    success = builder.build_all()

    if success:
        print("\n✅ 인덱스 재구축 성공!")
        print("이제 하이브리드 검색을 사용할 수 있습니다.")
        print("\n💡 중요:")
        print("  - 인덱스 ID가 metadata.db의 ID와 1:1 매칭됩니다")
        print("  - Streamlit 앱을 재시작하세요")
        return 0
    else:
        print("\n❌ 인덱스 재구축 실패")
        print("로그를 확인하세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
