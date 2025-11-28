"""RAG 파이프라인 계약 (Protocol + Dataclass)

이 모듈은 RAG 시스템의 핵심 인터페이스를 정의합니다:
- RAGRequest: 요청 파라미터
- RAGResponse: 응답 결과
- Retriever/Compressor/Generator: 컴포넌트 프로토콜

의존성: 없음 (typing, dataclass만 사용)
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# ============================================================================
# Request / Response 데이터 클래스
# ============================================================================


@dataclass
class RAGRequest:
    """RAG 요청 파라미터

    Attributes:
        query: 사용자 질문
        top_k: 검색 결과 개수
        compression_ratio: 컨텍스트 압축 비율 (0.0~1.0)
        use_hyde: HyDE 사용 여부
        temperature: LLM 생성 온도
    """

    query: str
    top_k: int = 5
    compression_ratio: float = 0.7
    use_hyde: bool = False
    temperature: float = 0.1


@dataclass
class RAGResponse:
    """RAG 응답 결과

    Attributes:
        answer: 생성된 답변
        source_docs: 참고 문서 목록 (하위 호환)
        evidence_chunks: Evidence용 정규화 청크 (권장)
        raw_results: 원본 검색 결과 (Evidence 최소 보장용)
        latency: 전체 실행 시간 (초)
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        metrics: 내부 지표 (검색/압축/생성 시간 등)
        diagnostics: 진단 정보 (DIAG_RAG=true일 때만 채워짐)
    """

    answer: str
    source_docs: list[str] = field(default_factory=list)
    evidence_chunks: list[dict[str, Any]] = field(default_factory=list)
    raw_results: list[dict[str, Any]] = field(default_factory=list)
    latency: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)  # 진단 정보


# ============================================================================
# 프로토콜 정의 (의존성 역전)
# ============================================================================


class Retriever(Protocol):
    """검색 엔진 인터페이스"""

    def search(
        self,
        query: str,
        top_k: int,
        *,
        mode: str = "chat",
        selected_filename: Optional[str] = None,
        strict_content: bool = False,
    ) -> list[dict[str, Any]]:
        """검색 수행 (정규화 스키마 반환)

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            mode: 검색 모드 ("chat", "doc_anchored" 등)
            selected_filename: 우선 검색할 문서명
            strict_content: 정밀 내용 검색 모드 (본문 일치만, 2025-11-19 추가)

        Returns:
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict
                }, ...
            ]
        """
        ...


class Compressor(Protocol):
    """컨텍스트 압축기 인터페이스"""

    def compress(
        self, chunks: list[dict[str, Any]], ratio: float,
    ) -> list[dict[str, Any]]:
        """문서 압축

        Args:
            chunks: 원본 청크 목록 (정규화된 dict)
            ratio: 압축 비율

        Returns:
            압축된 청크 목록 (동일 스키마)
        """
        ...


class Generator(Protocol):
    """LLM 생성기 인터페이스"""

    def generate(self, query: str, context: str, temperature: float, mode: str = "rag") -> str:
        """답변 생성

        Args:
            query: 사용자 질문
            context: 참고 문서
            temperature: 생성 온도
            mode: 생성 모드 ("chat", "rag", "summarize") - 토큰 예산 제어

        Returns:
            생성된 답변
        """
        ...


__all__ = [
    "Compressor",
    "Generator",
    "RAGRequest",
    "RAGResponse",
    "Retriever",
]
