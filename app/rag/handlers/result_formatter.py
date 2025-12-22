"""검색 결과 포맷팅 모듈

검색 결과를 사용자에게 보여줄 형식으로 변환.
search.py에서 분리된 SRP 적용 모듈.

2025-12-22: search.py 리팩토링으로 분리
"""

from typing import Any

from app.core.logging import get_logger
from config.constants import HandlerConfig

from app.rag.handlers.query_processor import is_count_query
from app.rag.handlers.response import build_file_path, format_title_from_filename

logger = get_logger(__name__)


# 빈 값으로 간주할 값들 (UI 표시 시 필터링)
EMPTY_VALUES = frozenset({None, "", "None", "없음", "정보 없음", "기타", "작성자 미상", "날짜 없음"})


class ResultFormatter:
    """검색 결과 포맷터

    검색 결과를 카드 형식, 응답 텍스트, evidence 형식으로 변환.
    """

    def __init__(self, retriever: Any = None, similarity_service: Any = None):
        """초기화

        Args:
            retriever: 청크 검색을 위한 retriever (선택)
            similarity_service: 유사 문서 서비스 (선택)
        """
        self.retriever = retriever
        self.similarity_service = similarity_service

    def format_search_response(
        self,
        keywords: str,
        query: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str],
    ) -> dict[str, Any]:
        """검색 응답 생성

        Args:
            keywords: 검색 키워드
            query: 원본 쿼리
            doc_details: 문서 상세 정보 목록
            filenames: 파일명 목록

        Returns:
            검색 응답 딕셔너리
        """
        # 카드 생성
        cards = []
        for i, doc in enumerate(doc_details, 1):
            title = format_title_from_filename(doc["filename"])
            card_lines = [f"{i}. {title}"]

            # 메타데이터 한 줄로 표시 (날짜 | 기안자 | 금액)
            meta_parts = self._build_meta_parts(doc)
            if meta_parts:
                card_lines.append("   " + " | ".join(meta_parts))

            cards.append("\n".join(card_lines))

        # 응답 텍스트 생성
        if is_count_query(query):
            answer_text = f"**'{keywords}' 관련 문서는 총 {len(doc_details)}개**입니다.\n\n"
            answer_text += "\n\n".join(cards[:HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT])
            if len(cards) > HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT:
                answer_text += f"\n\n... 외 {len(cards) - HandlerConfig.COUNT_QUERY_DISPLAY_LIMIT}개 문서"
        else:
            answer_text = f"📄 **'{keywords}' 관련 문서 ({len(doc_details)}건)**\n\n"
            answer_text += "\n\n".join(cards)

        # Evidence 생성
        evidence = self.build_evidence(doc_details)

        # 유사 문서 추천 및 병합
        similar_documents, merged_count = self._find_similar_documents(
            query, filenames, evidence
        )

        return {
            "mode": "SEARCH",
            "text": answer_text,
            "files": filenames,
            "count": len(doc_details),
            "citations": evidence,
            "evidence": evidence,
            "similar_documents": similar_documents[:HandlerConfig.SIMILAR_DISPLAY_LIMIT],
            "status": {
                "retrieved_count": len(doc_details),
                "selected_count": len(doc_details),
                "found": True,
                "merged_similar": merged_count,
            },
        }

    def format_content_only_response(
        self,
        keywords: str,
        doc_details: list[dict[str, Any]],
        filenames: list[str],
    ) -> dict[str, Any]:
        """정밀 검색 응답 생성

        Args:
            keywords: 검색 키워드
            doc_details: 문서 상세 정보 목록
            filenames: 파일명 목록

        Returns:
            정밀 검색 응답 딕셔너리
        """
        response_text = f"📄 **'{keywords}' 내용 포함 문서 ({len(doc_details)}건)**\n\n"

        for i, doc in enumerate(doc_details, 1):
            title = format_title_from_filename(doc.get("filename", ""))

            # 메타데이터 한 줄로 표시
            meta_parts = self._build_meta_parts(doc)

            response_text += f"{i}. {title}\n"
            if meta_parts:
                response_text += "   " + " | ".join(meta_parts) + "\n"
            response_text += "\n"

        # Citations 생성
        citations = []
        for doc in doc_details:
            citations.append({
                "doc_id": doc["filename"],
                "filename": doc["filename"],
                "page": 1,
                "snippet": doc["text_preview"],
                "file_path": doc["path"],
                "meta": {
                    "filename": doc["filename"],
                    "date": doc["date"],
                    "drafter": doc["drafter"],
                    "category": doc["category"],
                },
            })

        logger.info(f"✅ 정밀 내용 검색 완료: {len(doc_details)}건")

        return {
            "mode": "SEARCH_CONTENT_ONLY",
            "text": response_text,
            "files": filenames[:HandlerConfig.CONTENT_ONLY_RESULT_LIMIT],
            "count": len(doc_details),
            "citations": citations,
            "evidence": citations,
            "status": {
                "retrieved_count": len(filenames),
                "selected_count": len(citations),
                "found": len(citations) > 0,
            },
        }

    def build_evidence(self, doc_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Evidence 목록 생성

        Args:
            doc_details: 문서 상세 정보 목록

        Returns:
            Evidence 목록
        """
        evidence = []

        for doc in doc_details:
            filename = doc["filename"]
            file_path = build_file_path(filename)
            title = format_title_from_filename(filename)

            # Snippet 생성
            snippet = doc.get("text_preview", "").strip()
            if not snippet and self.retriever:
                snippet = self._get_snippet_from_retriever(filename, title)

            if not snippet:
                snippet = title[:HandlerConfig.TITLE_FALLBACK_MAX]

            evidence.append({
                "doc_id": filename,
                "filename": filename,
                "file_path": file_path,
                "page": 1,
                "snippet": snippet[:HandlerConfig.EVIDENCE_SNIPPET_MAX],
                "ref": None,
                "meta": {
                    "filename": filename,
                    "drafter": doc.get("drafter"),
                    "date": doc.get("date"),
                    "doctype": doc.get("doctype"),
                },
            })

        return evidence

    def _build_meta_parts(self, doc: dict[str, Any]) -> list[str]:
        """문서 메타데이터를 표시용 문자열 리스트로 변환"""
        meta_parts = []
        if doc.get("date") and doc["date"] not in EMPTY_VALUES:
            meta_parts.append(f"📅 {doc['date']}")
        if doc.get("drafter") and doc["drafter"] not in EMPTY_VALUES:
            meta_parts.append(f"👤 {doc['drafter']}")
        if doc.get("claimed_total"):
            meta_parts.append(f"💰 {doc['claimed_total']:,}원")
        return meta_parts

    def _get_snippet_from_retriever(self, filename: str, title: str) -> str:
        """Retriever에서 스니펫 가져오기"""
        try:
            chunks = self.retriever.search(filename, top_k=HandlerConfig.EVIDENCE_CHUNK_TOP_K)
            if chunks:
                chunk_text = chunks[0].get("text", "")
                return chunk_text[:HandlerConfig.EVIDENCE_SNIPPET_MAX] if chunk_text else ""
        except (AttributeError, KeyError) as e:
            logger.debug(f"⚠️ BM25 청크 폴백 실패 (구조 오류, {filename}): {e}")
        except Exception as e:
            logger.debug(f"⚠️ BM25 청크 폴백 실패 ({type(e).__name__}, {filename}): {e}")
        return ""

    def _find_similar_documents(
        self,
        query: str,
        filenames: list[str],
        evidence: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """유사 문서 찾기 및 병합

        Args:
            query: 검색 쿼리
            filenames: 제외할 파일명 목록
            evidence: 병합할 evidence 목록

        Returns:
            (유사 문서 목록, 병합된 문서 수)
        """
        similar_documents: list[dict[str, Any]] = []
        merged_count = 0

        if not filenames or not self.similarity_service:
            return similar_documents, merged_count

        try:
            all_similar = self.similarity_service.find_similar_by_query(
                query, filenames, top_k=HandlerConfig.SIMILAR_SEARCH_TOP_K
            )

            for sim_doc in all_similar:
                similarity = sim_doc.get("similarity", 0)
                if similarity >= HandlerConfig.SIMILAR_MERGE_THRESHOLD:
                    # 고유사도 문서는 출처에 추가
                    merged_count += 1
                    merged_evidence = {
                        "doc_id": sim_doc["filename"],
                        "filename": sim_doc["filename"],
                        "page": 1,
                        "snippet": f"[유사도 {int(similarity * 100)}%] {sim_doc.get('title', '')}",
                        "file_path": "",
                        "meta": {
                            "filename": sim_doc["filename"],
                            "date": sim_doc.get("date", ""),
                            "drafter": sim_doc.get("drafter", ""),
                            "category": sim_doc.get("category", ""),
                            "is_similar": True,
                        },
                    }
                    evidence.append(merged_evidence)
                else:
                    similar_documents.append(sim_doc)

            if merged_count > 0:
                logger.info(f"📊 유사 문서 {merged_count}건 출처에 병합됨")

        except (AttributeError, KeyError) as e:
            logger.debug(f"⚠️ 유사 문서 추천 실패 (접근 오류, 무시): {e}")
        except Exception as e:
            logger.warning(f"⚠️ 유사 문서 추천 실패 ({type(e).__name__}, 무시): {e}")

        return similar_documents, merged_count


__all__ = [
    "EMPTY_VALUES",
    "ResultFormatter",
]
