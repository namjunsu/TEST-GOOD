"""문서 처리 유틸리티 모듈

pipeline.py에서 분리된 문서 관련 유틸리티 함수들.
OCR 추출, 청크 로드, 컨텍스트 수집 등을 담당.
"""

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.config.settings import settings
from app.core.logging import get_logger
from config.constants import DocumentUtilsConfig

if TYPE_CHECKING:
    from app.rag.contracts import Retriever

logger = get_logger(__name__)


class DocumentUtils:
    """문서 처리 유틸리티 클래스

    RAG 파이프라인에서 사용하는 문서 관련 유틸리티 메서드 모음.
    """

    def __init__(
        self,
        retriever: Optional["Retriever"] = None,
        extracted_dir: Optional[Path] = None,
    ):
        """DocumentUtils 초기화

        Args:
            retriever: 검색 엔진 (청크 로드 시 사용)
            extracted_dir: 추출된 텍스트 파일 디렉토리
        """
        self.retriever = retriever
        self.extracted_dir = extracted_dir or settings.EXTRACTED_DIR

    def load_full_text_if_short(self, filename: str, snippet: str) -> str:
        """스니펫이 짧으면 data/extracted에서 전체 텍스트 로드

        Args:
            filename: 문서 파일명
            snippet: 현재 스니펫

        Returns:
            전체 텍스트 또는 원본 스니펫
        """
        min_snippet_len = settings.DOC_ANCHOR_MIN_SNIPPET

        if len(snippet) >= min_snippet_len:
            return snippet

        # 파일명에서 확장자 제거 후 .txt 찾기
        stem = os.path.splitext(filename)[0]
        txt_path = self.extracted_dir / f"{stem}.txt"

        if txt_path.exists():
            try:
                full_text = txt_path.read_text(encoding="utf-8", errors="ignore")
                logger.info(f"📄 DOC_ANCHORED: {filename} 전체 텍스트 로드 ({len(full_text)}자)")
                return full_text[:DocumentUtilsConfig.FULL_TEXT_MAX_LENGTH]
            except Exception as e:
                logger.warning(f"⚠️ 전체 텍스트 로드 실패: {e}")

        return snippet

    def safe_fname(self, meta: Optional[dict] = None, doc_path: Optional[str] = None) -> str:
        """파일명 안전 추출 (다양한 소스에서 시도)

        Args:
            meta: 메타데이터 딕셔너리
            doc_path: 문서 경로

        Returns:
            안전하게 추출된 파일명 (기본값: '미상 문서')
        """
        meta = meta or {}

        # 다양한 필드에서 파일명 시도
        fname = (
            meta.get("fname")
            or meta.get("filename")
            or meta.get("doc_id")
            or (os.path.basename(doc_path) if doc_path else None)
            or "미상 문서"
        )

        return fname

    def make_chunks_for_doc(self, filename: str) -> list[dict[str, Any]]:
        """특정 문서의 청크만 로드 (문서 고정 모드용)

        Args:
            filename: 문서 파일명

        Returns:
            해당 문서의 청크 리스트
        """
        if not self.retriever:
            logger.warning("⚠️ retriever가 없어 청크를 로드할 수 없습니다")
            return []

        try:
            # BM25 인덱스에서 직접 해당 문서 찾기 (검색 대신 직접 접근)
            if hasattr(self.retriever, "bm25") and self.retriever.bm25:
                bm25_store = self.retriever.bm25

                # metadata에서 filename이 일치하는 문서의 인덱스 찾기
                target_indices = []
                for i, meta in enumerate(bm25_store.metadata):
                    if meta.get("filename") == filename:
                        target_indices.append(i)
                        logger.info(f"✅ BM25 인덱스에서 발견: {filename} (index={i})")

                # 찾은 문서들의 content를 청크로 변환
                chunks = []
                for idx in target_indices:
                    content = bm25_store.documents[idx]
                    if content and len(content.strip()) > 0:
                        # 전체 문서를 하나의 큰 청크로 사용
                        chunks.append({
                            "doc_id": filename,
                            "page": 1,
                            "text": content,  # 전체 텍스트
                            "score": 1.0,  # 직접 매칭이므로 최고 스코어
                            "filename": filename,
                        })
                        logger.info(f"✓ 문서 content 로드: {len(content)}자")

                if chunks:
                    logger.info(f"✓ 문서 청크 {len(chunks)}개 로드 완료")
                    return chunks

            # BM25 사용 불가 시 폴백: 키워드 검색
            logger.warning("⚠️ BM25 직접 접근 불가, 검색으로 폴백")
            search_query = filename.replace(".pdf", "").replace("_", " ")
            results = self.retriever.search(search_query, top_k=DocumentUtilsConfig.FALLBACK_SEARCH_TOP_K)

            # 검색 결과를 해당 문서로 필터링
            chunks = []
            for result in results:
                # doc_id 또는 meta.filename이 일치하는 경우만 포함
                doc_id = result.get("doc_id", "")
                meta_filename = result.get("meta", {}).get("filename", "")

                if filename in doc_id or filename in meta_filename:
                    chunks.append({
                        "doc_id": result.get("doc_id", filename),
                        "page": result.get("page", 1),
                        "text": result.get("snippet", result.get("text", "")),
                        "score": result.get("score", 0.0),
                        "filename": filename,
                    })

            if not chunks:
                logger.warning(f"⚠️ 문서 청크 없음: {filename}")

            return chunks

        except Exception as e:
            logger.error(f"❌ 문서 청크 로드 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def extract_with_ocr(self, pdf_path: str, start_page: int, total_pages: int) -> str:
        """OCR을 사용하여 PDF에서 텍스트 추출 (pytesseract 우선, paddleocr 폴백)

        Args:
            pdf_path: PDF 파일 경로
            start_page: 시작 페이지 (0-based)
            total_pages: 전체 페이지 수

        Returns:
            추출된 텍스트
        """
        try:
            import pytesseract
            from pdf2image import convert_from_path

            # PDF를 이미지로 변환 (끝 3페이지만)
            images = convert_from_path(
                pdf_path,
                first_page=start_page + 1,  # 1-based
                last_page=total_pages,
            )

            text = ""
            for i, img in enumerate(images):
                try:
                    # pytesseract 사용
                    page_text = pytesseract.image_to_string(img, lang="kor+eng")
                    text += page_text + "\n"
                    logger.info(f"✓ OCR (pytesseract) 페이지 {start_page + i + 1}: {len(page_text)}자")
                except Exception as e:
                    logger.warning(f"⚠️ pytesseract 실패 (페이지 {start_page + i + 1}): {e}")

            if len(text.strip()) > DocumentUtilsConfig.OCR_MIN_VALID_LENGTH:
                return text

            # pytesseract 실패 시 paddleocr 시도
            logger.info("🔄 paddleocr 폴백 시도...")
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang="korean")

                text = ""
                for i, img in enumerate(images):
                    # PaddleOCR는 파일 경로 또는 numpy array를 받음
                    import numpy as np
                    img_array = np.array(img)
                    result = ocr.ocr(img_array, cls=True)

                    if result and result[0]:
                        page_text = "\n".join([line[1][0] for line in result[0]])
                        text += page_text + "\n"
                        logger.info(f"✓ OCR (paddleocr) 페이지 {start_page + i + 1}: {len(page_text)}자")

                return text

            except Exception as e:
                logger.warning(f"⚠️ paddleocr 실패: {e}")
                return ""

        except Exception as e:
            logger.error(f"❌ OCR 추출 실패: {e}")
            return ""

    def gather_summary_context(
        self,
        filename: str,
        pdf_path: str,
        doc_locked: bool = False,
    ) -> str:
        """요약용 컨텍스트 수집 (인덱스 청크 기반, PDF tail 비활성)

        Args:
            filename: 파일명
            pdf_path: PDF 파일 경로
            doc_locked: True면 해당 문서 청크만 사용 (다른 문서 검색 금지)

        Returns:
            수집된 컨텍스트 텍스트 (최대 ~3600자, 약 1.8k 토큰)
        """
        if not self.retriever:
            logger.warning("⚠️ retriever가 없어 컨텍스트를 수집할 수 없습니다")
            return ""

        parts = []

        # 인덱스 청크 기반 컨텍스트 수집 (섹션 가중치 적용)
        # 우선순위 키워드: 개요, 배경, 검토사유, 대안, 견적, 결론, 비용, 도입사유
        priority_keywords = (
            r"(개요|배경|검토사유|검토\s*사유|대안|견적|결론|비용|"
            r"도입사유|도입\s*사유|구매목적|구매\s*목적|선정|권고|총액|합계)"
        )

        try:
            if doc_locked:
                # 문서 고정 모드: 해당 문서의 청크만 로드
                logger.info(f"🔒 문서 고정 모드: {filename}의 청크만 사용")
                chunks = self.make_chunks_for_doc(filename)

                # 섹션 가중치 적용: 우선순위 키워드 포함 청크를 앞으로
                priority_chunks = []
                normal_chunks = []
                for chunk in chunks:
                    chunk_text = chunk.get("text") or chunk.get("snippet") or chunk.get("content") or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_chunks.append(chunk)
                    else:
                        normal_chunks.append(chunk)

                # 우선순위 청크 + 일반 청크 순서로 재조합
                sorted_chunks = (priority_chunks + normal_chunks)[:DocumentUtilsConfig.MAX_CHUNKS_COUNT]

                for i, chunk in enumerate(sorted_chunks, 1):
                    chunk_text = chunk.get("text") or chunk.get("snippet") or chunk.get("content") or ""
                    if chunk_text:
                        max_len = DocumentUtilsConfig.CHUNK_TEXT_MAX_LENGTH
                        parts.append(f"=== [문서 청크 {i}] ===\n" + chunk_text[:max_len])

                if sorted_chunks:
                    logger.info(f"✓ 문서 고정 청크 {len(sorted_chunks)}개 추출 (우선순위: {len(priority_chunks)}개)")
            else:
                # 일반 모드: 키워드 검색 후 같은 파일 필터링
                search_keywords = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", filename)  # 날짜 제거
                search_keywords = re.sub(r"\.pdf$", "", search_keywords, flags=re.IGNORECASE)
                search_keywords = search_keywords.replace("_", " ")

                hits = self.retriever.search(search_keywords, top_k=DocumentUtilsConfig.SUMMARY_SEARCH_TOP_K)
                same_file_hits = [h for h in hits if h.get("filename") == filename]

                # 섹션 가중치 적용
                priority_hits = []
                normal_hits = []
                for h in same_file_hits:
                    chunk_text = h.get("text") or h.get("snippet") or h.get("content") or ""
                    if re.search(priority_keywords, chunk_text):
                        priority_hits.append(h)
                    else:
                        normal_hits.append(h)

                sorted_hits = (priority_hits + normal_hits)[:DocumentUtilsConfig.MAX_CHUNKS_COUNT]

                for i, h in enumerate(sorted_hits, 1):
                    chunk_text = h.get("text") or h.get("snippet") or h.get("content") or ""
                    if chunk_text:
                        max_len = DocumentUtilsConfig.CHUNK_TEXT_MAX_LENGTH
                        parts.append(f"=== [관련 청크 {i}] ===\n" + chunk_text[:max_len])

                if sorted_hits:
                    logger.info(f"✓ RAG 청크 {len(sorted_hits)}개 추출 (우선순위: {len(priority_hits)}개)")
        except Exception as e:
            logger.warning(f"⚠️ RAG 청크 추출 실패: {e}")

        # 결합 및 길이 제한 (약 3k 토큰)
        context = "\n\n".join(parts)[:DocumentUtilsConfig.CONTEXT_MAX_LENGTH]
        logger.info(f"📋 최종 컨텍스트 길이: {len(context)}자 (청크 수: {len(parts)})")
        return context
