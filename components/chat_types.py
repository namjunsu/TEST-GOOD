"""
Chat Type Definitions
채팅 인터페이스 타입 정의

책임:
- TypedDict 정의
- Protocol 정의
- 설정 상수 클래스
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from typing_extensions import TypedDict

# ============================================================================
# 타입 정의
# ============================================================================


class Evidence(TypedDict, total=False):
    """출처 문서 증거 구조"""

    doc_id: str
    filename: str
    page: int
    snippet: str
    file_path: str
    meta: dict[str, Any]


class ChatMessage(TypedDict, total=False):
    """채팅 메시지 구조"""

    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    evidence: list[Evidence]
    similar_documents: list[dict[str, Any]]


class RAGProtocol(Protocol):
    """RAG Pipeline 인터페이스 정의

    가변 인자를 지원하여 top_k, selected_filename 등 다양한 옵션 전달 가능
    """

    def answer(self, query: str, /, **kwargs: Any) -> dict:
        """질문에 대한 답변 생성

        Args:
            query: 사용자 질문
            **kwargs: 옵션 (top_k, selected_filename 등)

        Returns:
            dict: {
                "text": 답변 텍스트,
                "evidence": [Evidence, ...],
                "status": {"from_cache": bool, ...},
                "diagnostics": {...}
            }
        """
        ...


# ============================================================================
# 설정 상수
# ============================================================================


class ChatConfig:
    """채팅 인터페이스 설정 상수"""

    # 역할 정의
    ROLE_USER: Literal["user"] = "user"
    ROLE_ASSISTANT: Literal["assistant"] = "assistant"

    # 한글 역할명
    ROLE_DISPLAY_USER = "사용자"
    ROLE_DISPLAY_ASSISTANT = "AI"

    # 아바타
    AVATAR_USER = "👤"
    AVATAR_ASSISTANT = "🤖"

    # 메모리 관리
    MAX_MESSAGES = 100
    MAX_CONTEXT_TURNS = 3
    MAX_MESSAGE_LENGTH = 10000

    # UI 문자열
    INPUT_PLACEHOLDER = "💬 무엇을 도와드릴까요?"
    SPINNER_SEARCH = "검색 중..."
    SPINNER_GENERATE = "답변 생성 중..."
    DIVIDER = "---"

    # 진행 상태 단계
    PROGRESS_STEPS = [
        ("🔍 쿼리 분석", "질문 의도 파악 중..."),
        ("📚 문서 검색", "관련 문서 검색 중..."),
        ("🤖 답변 생성", "AI 답변 생성 중..."),
    ]

    # 옵션 기본값
    DEFAULT_TOP_K = 5
    DEFAULT_STREAMING_SPEED = "medium"
    DEFAULT_SHOW_EVIDENCE = True
