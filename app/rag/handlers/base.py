"""핸들러 기본 클래스

모든 RAG 핸들러의 공통 인터페이스와 유틸리티 제공.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


class HandlerResponse:
    """핸들러 응답 표준 구조"""

    def __init__(
        self,
        mode: str,
        text: str,
        files: list[str],
        count: int,
        citations: Optional[list[dict[str, Any]]] = None,
        evidence: Optional[list[dict[str, Any]]] = None,
        status: Optional[dict[str, Any]] = None,
        latency_ms: float = 0.0,
    ):
        self.mode = mode
        self.text = text
        self.files = files
        self.count = count
        self.citations = citations or []
        self.evidence = evidence or citations or []
        self.status = status or {
            "retrieved_count": count,
            "selected_count": count,
            "found": count > 0,
        }
        self.latency_ms = latency_ms

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (기존 pipeline.py 응답 형식 호환)"""
        return {
            "mode": self.mode,
            "text": self.text,
            "files": self.files,
            "count": self.count,
            "citations": self.citations,
            "evidence": self.evidence,
            "status": self.status,
        }


class BaseHandler(ABC):
    """핸들러 기본 클래스

    모든 핸들러는 이 클래스를 상속받아 handle() 메서드를 구현합니다.

    Attributes:
        pipeline: RAGPipeline 인스턴스 (retriever, generator 등 접근용)
        mode: 핸들러 모드 이름 (예: "SEARCH", "DOCUMENT")
    """

    mode: str = "BASE"

    def __init__(self, pipeline: "RAGPipeline"):
        """핸들러 초기화

        Args:
            pipeline: 부모 RAGPipeline 인스턴스
        """
        self.pipeline = pipeline

    @property
    def retriever(self):
        """Retriever 접근 단축"""
        return self.pipeline.retriever

    @property
    def generator(self):
        """Generator 접근 단축"""
        return self.pipeline.generator

    @abstractmethod
    def handle(self, query: str, **kwargs) -> dict[str, Any]:
        """쿼리 처리

        Args:
            query: 사용자 쿼리
            **kwargs: 추가 파라미터

        Returns:
            표준 응답 딕셔너리
        """
        pass

    def _make_error_response(self, error: str) -> dict[str, Any]:
        """에러 응답 생성"""
        return {
            "mode": self.mode,
            "text": f"오류: {error}",
            "files": [],
            "count": 0,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": 0,
                "selected_count": 0,
                "found": False,
            },
        }

    def _make_empty_response(self, message: str) -> dict[str, Any]:
        """빈 결과 응답 생성"""
        return {
            "mode": self.mode,
            "text": message,
            "files": [],
            "count": 0,
            "citations": [],
            "evidence": [],
            "status": {
                "retrieved_count": 0,
                "selected_count": 0,
                "found": False,
            },
        }
