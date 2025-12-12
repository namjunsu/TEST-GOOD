"""RAG 응답 구성 로직 (ResponseBuilder)

pipeline.py에서 분리된 응답 구성 로직.
검색 결과와 생성된 답변을 RAGResponse로 변환합니다.
"""

import time
from typing import Any, Optional

from app.core.logging import get_logger
from app.rag.contracts import RAGResponse
from app.rag.query_routing import _encode_file_ref
from config.constants import PipelineConfig

logger = get_logger(__name__)


class ResponseBuilder:
    """RAG 응답 구성기

    검색 결과, 압축된 청크, 생성된 답변을
    RAGResponse 또는 dict 형태로 구성합니다.
    """

    # 대량 쿼리 감지 키워드
    BULK_KEYWORDS = frozenset(["전부", "모두", "모든", "전체", "all", "몇", "개수", "총"])

    def __init__(self, config: type = PipelineConfig):
        """초기화

        Args:
            config: 파이프라인 설정 클래스
        """
        self.config = config

    def build_rag_response(
        self,
        query: str,
        answer: str,
        results: list[dict[str, Any]],
        compressed: list[dict[str, Any]],
        determined_mode: str,
        start_time: float,
        metrics: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> RAGResponse:
        """RAGResponse 객체 구성

        Args:
            query: 사용자 질문
            answer: 생성된 답변
            results: 원본 검색 결과
            compressed: 압축된 결과
            determined_mode: 결정된 모드
            start_time: 시작 시간
            metrics: 메트릭
            diagnostics: 진단 정보

        Returns:
            RAGResponse 객체
        """
        total_latency = time.perf_counter() - start_time
        metrics["total_time"] = total_latency

        # 성능 가드
        self._log_slow_query(query, total_latency, metrics)

        # 메트릭 로깅
        logger.info(
            f"RAG query completed in {total_latency:.2f}s "
            f"(search={metrics.get('search_time', 0):.2f}s, "
            f"compress={metrics.get('compress_time', 0):.2f}s, "
            f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
            f"generate={metrics.get('generate_time', 0):.2f}s)",
        )

        # 출처 결정
        max_sources = self._get_max_sources(query)
        final_source_docs = (
            [] if determined_mode == "chat"
            else [c.get("doc_id") for c in results[:max_sources]]
        )
        final_evidence_chunks = [] if determined_mode == "chat" else compressed

        return RAGResponse(
            answer=answer,
            source_docs=final_source_docs,
            evidence_chunks=final_evidence_chunks,
            raw_results=results,
            latency=total_latency,
            success=True,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    def build_dict_response(
        self,
        text: str,
        selected: list[dict[str, Any]],
        retrieved: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """표준 dict 응답 구성 (citations 포함)

        Args:
            text: 생성된 답변 텍스트
            selected: 실제 사용된 청크 리스트 (압축 후)
            retrieved: 검색된 원본 결과 리스트

        Returns:
            표준화된 응답 dict (citations 필수)
        """
        citations = self._build_citations(selected)

        return {
            "text": text,
            "citations": citations,
            "evidence": citations,  # 하위 호환성
            "status": {
                "retrieved_count": len(retrieved),
                "selected_count": len(selected),
                "found": len(selected) > 0,
            },
        }

    def build_evidence_from_results(
        self,
        evidence_chunks: list[dict[str, Any]],
        raw_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Evidence 구성 (폴백 포함)

        Args:
            evidence_chunks: 압축된 청크
            raw_results: 원본 검색 결과

        Returns:
            (evidence 리스트, 폴백 사용 여부)
        """
        evidence = [
            {
                "doc_id": c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": c.get("snippet", ""),
                "meta": c.get(
                    "meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}
                ),
            }
            for c in (evidence_chunks or [])
        ]

        evidence_injected = False
        if not evidence and raw_results:
            logger.info("Evidence empty, using raw_results[:3] as fallback")
            evidence = [
                {
                    "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                    "page": 0,
                    "snippet": (
                        r.get("snippet") or r.get("text_preview", "")
                    )[:self.config.SNIPPET_PREVIEW_LENGTH],
                    "meta": {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "filename": r.get("filename", ""),
                        "page": 0,
                    },
                }
                for r in raw_results[:self.config.EVIDENCE_FALLBACK_COUNT]
            ]
            evidence_injected = True

        return evidence, evidence_injected

    def build_status(
        self,
        retrieved_count: int,
        selected_count: int,
    ) -> dict[str, Any]:
        """Status dict 구성

        Args:
            retrieved_count: 검색된 원본 결과 수
            selected_count: 실제 사용된 증거 수

        Returns:
            status dict
        """
        return {
            "retrieved_count": retrieved_count,
            "selected_count": selected_count,
            "found": selected_count > 0,
        }

    def build_error_response(
        self,
        error_msg: str,
        error_detail: Optional[str] = None,
    ) -> dict[str, Any]:
        """에러 응답 구성

        Args:
            error_msg: 에러 메시지
            error_detail: 상세 에러 정보

        Returns:
            에러 응답 dict
        """
        full_msg = error_msg
        if error_detail:
            full_msg = f"{error_msg}\n\n상세: {error_detail}"

        return {
            "text": full_msg,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": 0,
                "selected_count": 0,
                "found": False,
            },
        }

    def _build_citations(
        self, selected: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Citations 리스트 구성"""
        citations = []
        for c in selected:
            filename = c.get("filename") or c.get("doc_id") or c.get("title", "")
            ref = _encode_file_ref(filename) if filename else None

            citations.append({
                "doc_id": c.get("doc_id"),
                "filename": filename,
                "title": c.get("title") or filename or c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": (
                    c.get("text") or c.get("snippet") or c.get("content") or ""
                )[:self.config.SNIPPET_PREVIEW_LENGTH],
                "ref": ref,
                "preview_url": c.get("preview_url"),
                "download_url": c.get("download_url"),
            })

        return citations

    def _get_max_sources(self, query: str) -> int:
        """쿼리 유형에 따른 최대 출처 수 결정"""
        query_lower = query.lower()
        if any(kw in query_lower for kw in self.BULK_KEYWORDS):
            return self.config.BULK_MAX_SOURCES
        return self.config.DEFAULT_MAX_SOURCES

    def _log_slow_query(
        self, query: str, total_latency: float, metrics: dict[str, Any]
    ) -> None:
        """슬로 쿼리 로깅"""
        if total_latency > self.config.SLOW_QUERY_CRITICAL:
            logger.warning(
                f"⚠️  SLOW_QUERY (>{self.config.SLOW_QUERY_CRITICAL}s): "
                f"{total_latency:.2f}s | query='{query[:50]}...' | "
                f"search={metrics.get('search_time', 0):.2f}s, "
                f"hydrate={metrics.get('hydrate_time', 0):.3f}s, "
                f"generate={metrics.get('generate_time', 0):.2f}s",
            )
        elif total_latency > self.config.SLOW_QUERY_WARNING:
            logger.warning(
                f"⚠️  SLOW_QUERY (>{self.config.SLOW_QUERY_WARNING}s): "
                f"{total_latency:.2f}s | query='{query[:50]}...'",
            )


# 싱글톤 인스턴스
_builder_instance: ResponseBuilder | None = None


def get_response_builder() -> ResponseBuilder:
    """ResponseBuilder 싱글톤 인스턴스 반환"""
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = ResponseBuilder()
    return _builder_instance
