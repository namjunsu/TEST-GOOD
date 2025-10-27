"""
Chat Interface Component
ChatGPT 스타일의 채팅 인터페이스 UI를 렌더링하는 컴포넌트

개선 사항:
- 완벽한 타입 시스템 (TypedDict, Protocol)
- 상수 정의로 매직 넘버/문자열 제거
- 헬퍼 함수 분리 (Single Responsibility Principle)
- 강화된 예외 처리 (타입별 처리, 로깅)
- 메모리 관리 (자동 메시지 정리)
- 입력 검증 및 보안 강화
- 포괄적인 문서화
"""

import os
import streamlit as st
import requests
from typing import List, Dict, Optional, Protocol, Any
from typing_extensions import TypedDict, Literal
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.core.logging import get_logger


# ===== 로깅 설정 =====
logger = get_logger(__name__)

# 진단 모드 설정
DIAG_RAG = os.getenv('DIAG_RAG', 'false').lower() == 'true'


# ===== 타입 정의 =====
class ChatMessage(TypedDict):
    """채팅 메시지 구조"""
    role: Literal["user", "assistant"]
    content: str
    timestamp: str


class RAGProtocol(Protocol):
    """RAG Pipeline 인터페이스 정의 (Evidence 포함)"""
    def answer(self, query: str, top_k: Optional[int] = None) -> dict:
        """질문에 대한 답변 생성

        Returns:
            dict: {
                "text": 답변 텍스트,
                "evidence": [{"doc_id": str, "page": int, "snippet": str, "meta": dict}, ...]
            }
        """
        ...


# ===== 상수 정의 =====
class ChatConfig:
    """채팅 인터페이스 설정 상수"""
    # 역할 정의
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    # 한글 역할명
    ROLE_DISPLAY_USER = "사용자"
    ROLE_DISPLAY_ASSISTANT = "AI"

    # 메모리 관리
    MAX_MESSAGES = 100  # 최대 메시지 수
    MAX_CONTEXT_TURNS = 3  # 컨텍스트에 포함할 최대 대화 턴 수
    MAX_MESSAGE_LENGTH = 10000  # 최대 메시지 길이

    # UI 문자열
    INPUT_PLACEHOLDER = "💬 무엇을 도와드릴까요?"
    SPINNER_TEXT = "🤔 생각 중..."
    DIVIDER = "---"

    # 에러 메시지
    ERROR_GENERIC = "죄송합니다. 오류가 발생했습니다."
    ERROR_TIMEOUT = "⏱️ 응답 시간이 초과되었습니다. 다시 시도해주세요."
    ERROR_MEMORY = "💾 메모리가 부족합니다. 대화 내역을 정리해주세요."
    ERROR_NETWORK = "🌐 네트워크 오류가 발생했습니다."
    ERROR_INITIALIZATION = "⚙️ 시스템 초기화가 필요합니다."
    ERROR_INVALID_INPUT = "⚠️ 입력이 너무 깁니다. 더 짧게 작성해주세요."

    # 컨텍스트 구성
    CONTEXT_PREFIX = "이전 대화 맥락:"
    CURRENT_QUERY_PREFIX = "현재 질문:"


# ===== 헬퍼 함수 =====

@lru_cache(maxsize=1)
def _get_api_base_url() -> str:
    """FastAPI 기준 URL을 동적으로 가져옴 (캐시 적용)

    우선순위:
    1. 환경변수 PUBLIC_API_BASE
    2. FastAPI /api/config 엔드포인트
    3. 기본값 (localhost:7860)

    Returns:
        str: API 기준 URL
    """
    # 1. 환경변수 우선
    env_base = os.getenv("PUBLIC_API_BASE")
    if env_base:
        logger.info(f"Using PUBLIC_API_BASE from env: {env_base}")
        return env_base.rstrip("/")

    # 2. FastAPI에서 가져오기 시도
    try:
        # Streamlit이 실행 중인 경우, FastAPI는 같은 머신의 7860 포트
        api_url = "http://localhost:7860/api/config"
        response = requests.get(api_url, timeout=2)
        if response.status_code == 200:
            config = response.json()
            base_url = config.get("base_url", "http://localhost:7860")
            logger.info(f"Fetched API base URL from FastAPI: {base_url}")
            return base_url
    except Exception as e:
        logger.warning(f"Failed to fetch API config from FastAPI: {e}")

    # 3. 기본값
    default_url = "http://localhost:7860"
    logger.info(f"Using default API base URL: {default_url}")
    return default_url


def render_doc_card(
    index: int,
    filename: str,
    file_path: Optional[Path],
    doctype: Optional[str],
    display_date: Optional[str],
    drafter: Optional[str],
    summary: str,
    show_preview_inline: bool = False
) -> None:
    """문서 카드 렌더링 (고정 레이아웃) - 안전가드 + 캐시 적용

    1행: 📄 파일명
    2행: 메타칩 (doctype · date · drafter)
    3행: LLM 요약 (최대 2줄, 160자)
    4행: 버튼 (미리보기 / 다운로드)
    5행: PDF 뷰어 (선택적, 예외 처리 강화)

    Args:
        index: 카드 번호 (1부터 시작)
        filename: 파일명
        file_path: 실제 파일 경로 (Path 객체)
        doctype: 문서 타입
        display_date: 날짜
        drafter: 기안자
        summary: LLM 요약 (이미 160자로 제한된 상태)
        show_preview_inline: 인라인 미리보기 표시 여부
    """
    from utils.pdf_utils import download_pdf_button, render_pdf_preview

    # 1행: 파일명
    st.markdown(f"**{index}. 📄 {filename}**")

    # 2행: 메타칩 (존재하는 것만 표시)
    meta_chips = []
    if doctype:
        meta_chips.append(f"🏷 {doctype}")
    if display_date:
        meta_chips.append(f"📅 {display_date}")
    if drafter:
        meta_chips.append(f"✍ {drafter}")

    if meta_chips:
        st.caption(" · ".join(meta_chips))
    else:
        st.caption("—")  # 메타 정보 없음

    # 3행: 요약 (최대 2줄, 160자)
    summary_truncated = summary[:160].strip()
    if len(summary) > 160:
        summary_truncated += "..."
    st.markdown(f"{summary_truncated}")

    # 4행: 버튼 (안전가드 + 표준 함수 사용)
    if file_path:
        col1, col2 = st.columns([1, 1])

        # 미리보기 버튼 (expander 토글)
        with col1:
            preview_key = f"preview_btn_{index}_{filename[:10]}"
            if st.button("🔎 미리보기", key=preview_key, use_container_width=True):
                # 세션 상태에 미리보기 정보 저장
                session_key = f"show_preview_{index}_{filename}"
                st.session_state[session_key] = not st.session_state.get(session_key, False)
                st.rerun()

        # 다운로드 버튼 (표준 함수 사용)
        with col2:
            download_pdf_button(
                file_path=str(file_path),
                key=f"download_{index}_{filename[:10]}",
                use_container_width=True
            )

        # 5행: PDF 뷰어 (예외 처리 강화, 다운로드 fallback)
        # 기본은 접힘 상태, 버튼 클릭 시에만 펼침
        session_key = f"show_preview_{index}_{filename}"
        if st.session_state.get(session_key, False):
            with st.expander("📄 PDF 미리보기", expanded=False):
                render_pdf_preview(
                    file_path=str(file_path),
                    height=600,
                    show_download_fallback=True
                )
    else:
        st.warning("⚠️ 파일 경로가 제공되지 않았습니다")


def _normalize_rag_response(resp: Any) -> dict:
    """RAG 응답을 안전하게 dict로 정규화

    RAG Pipeline이 반환할 수 있는 다양한 타입(객체, dict, str)을
    통일된 dict 형식으로 변환합니다.

    Args:
        resp: RAG Pipeline의 응답 (RAGResponse 객체, dict, str 등)

    Returns:
        dict: {"text": str, "evidence": list} 형식의 정규화된 응답

    Examples:
        >>> _normalize_rag_response(RAGResponse(text="답변", evidence=[...]))
        {"text": "답변", "evidence": [...]}

        >>> _normalize_rag_response(RAGResponse(answer="답변", sources=[...]))
        {"text": "답변", "evidence": [...]}

        >>> _normalize_rag_response({"text": "답변", "evidence": [...]})
        {"text": "답변", "evidence": [...]}

        >>> _normalize_rag_response("직접 문자열 답변")
        {"text": "직접 문자열 답변", "evidence": []}
    """
    # None 체크
    if resp is None:
        logger.warning("Received None response from RAG")
        return {"text": "", "evidence": []}

    # 문자열인 경우
    if isinstance(resp, str):
        return {"text": resp, "evidence": []}

    # 객체인 경우 (RAGResponse 등)
    # text, answer 필드 모두 지원
    if hasattr(resp, "text") or hasattr(resp, "answer"):
        text = getattr(resp, "text", None) or getattr(resp, "answer", "")
        # evidence, evidences, sources, sources_cited 모두 시도
        evidence = (
            getattr(resp, "evidence", None) or
            getattr(resp, "evidences", None) or
            getattr(resp, "sources", None) or
            getattr(resp, "sources_cited", None) or
            []
        )
        return {"text": str(text), "evidence": evidence}

    # dict인 경우
    if isinstance(resp, dict):
        text = resp.get("text") or resp.get("answer", "")
        evidence = (
            resp.get("evidence") or
            resp.get("evidences") or
            resp.get("sources") or
            resp.get("sources_cited") or
            []
        )
        return {"text": str(text), "evidence": evidence}

    # 그 외 알 수 없는 타입
    logger.warning(f"Unknown response type: {type(resp)}")
    return {"text": str(resp), "evidence": []}


def _initialize_chat_state() -> None:
    """채팅 세션 상태 초기화

    세션 상태에 messages 리스트가 없으면 빈 리스트로 초기화합니다.
    """
    if 'messages' not in st.session_state:
        st.session_state.messages = []
        logger.info("Chat session initialized")


def _validate_message_structure(message: Any) -> bool:
    """메시지 구조 검증

    Args:
        message: 검증할 메시지 객체

    Returns:
        bool: 유효한 메시지 구조면 True, 아니면 False
    """
    if not isinstance(message, dict):
        return False

    required_keys = {'role', 'content'}
    if not required_keys.issubset(message.keys()):
        return False

    if message['role'] not in [ChatConfig.ROLE_USER, ChatConfig.ROLE_ASSISTANT]:
        return False

    if not isinstance(message['content'], str):
        return False

    return True


def _validate_input(prompt: str) -> tuple[bool, Optional[str]]:
    """사용자 입력 검증

    Args:
        prompt: 사용자 입력 문자열

    Returns:
        tuple[bool, Optional[str]]: (유효성, 에러 메시지)
    """
    # 빈 문자열 체크
    if not prompt or not prompt.strip():
        return False, "입력이 비어있습니다."

    # 길이 체크
    if len(prompt) > ChatConfig.MAX_MESSAGE_LENGTH:
        return False, ChatConfig.ERROR_INVALID_INPUT

    # 기본 위험 문자 체크 (선택적, 필요시 확장)
    # dangerous_patterns = ['<script>', 'javascript:', 'onerror=']
    # if any(pattern in prompt.lower() for pattern in dangerous_patterns):
    #     return False, "보안상 허용되지 않는 입력입니다."

    return True, None


def _cleanup_old_messages(messages: List[ChatMessage]) -> List[ChatMessage]:
    """오래된 메시지 정리

    메시지 수가 MAX_MESSAGES를 초과하면 오래된 메시지부터 삭제합니다.
    최근 메시지들만 유지하여 메모리를 효율적으로 관리합니다.

    Args:
        messages: 전체 메시지 리스트

    Returns:
        List[ChatMessage]: 정리된 메시지 리스트
    """
    if len(messages) > ChatConfig.MAX_MESSAGES:
        removed_count = len(messages) - ChatConfig.MAX_MESSAGES
        logger.warning(f"Message limit exceeded. Removing {removed_count} old messages.")
        return messages[-ChatConfig.MAX_MESSAGES:]
    return messages


def _build_conversation_context(messages: List[Dict[str, str]], max_turns: int = ChatConfig.MAX_CONTEXT_TURNS) -> str:
    """대화 맥락 구성

    최근 N개 턴의 대화를 문자열로 변환하여 컨텍스트를 구성합니다.
    효율적인 문자열 연결을 위해 리스트를 사용합니다.

    Args:
        messages: 전체 메시지 리스트
        max_turns: 포함할 최대 대화 턴 수 (기본값: 3)

    Returns:
        str: 구성된 컨텍스트 문자열
    """
    # 메시지가 2개 미만이면 컨텍스트 없음
    if len(messages) < 2:
        return ""

    # 최근 N턴 = N*2개 메시지 (user + assistant 쌍)
    # 현재 user 메시지는 이미 추가된 상태이므로, 그 이전 메시지들만 가져옴
    max_messages = max_turns * 2
    recent_messages = messages[-(max_messages + 1):-1]  # 마지막 메시지(현재 질문) 제외

    # 효율적인 문자열 구성 (리스트 사용)
    context_parts = []

    for msg in recent_messages:
        # 메시지 구조 검증
        if not _validate_message_structure(msg):
            logger.warning(f"Invalid message structure in context: {msg}")
            continue

        # 역할 변환
        role = msg['role']
        display_role = ChatConfig.ROLE_DISPLAY_USER if role == ChatConfig.ROLE_USER else ChatConfig.ROLE_DISPLAY_ASSISTANT

        # 메시지 추가
        context_parts.append(f"{display_role}: {msg['content']}")

    # 컨텍스트가 비어있으면 빈 문자열 반환
    if not context_parts:
        return ""

    # 조인하여 반환
    return "\n".join(context_parts)


def _create_enhanced_query(context: str, prompt: str) -> str:
    """컨텍스트를 포함한 향상된 쿼리 생성

    Args:
        context: 이전 대화 컨텍스트
        prompt: 현재 사용자 질문

    Returns:
        str: 향상된 쿼리 문자열
    """
    if context:
        return f"{ChatConfig.CONTEXT_PREFIX}\n{context}\n\n{ChatConfig.CURRENT_QUERY_PREFIX} {prompt}"
    return prompt


def _handle_error(error: Exception) -> str:
    """예외 타입별 에러 메시지 생성

    예외 타입에 따라 적절한 사용자 친화적 메시지를 반환합니다.
    모든 에러는 로그에 기록됩니다.

    Args:
        error: 발생한 예외 객체

    Returns:
        str: 사용자에게 표시할 에러 메시지
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # 로깅 (디버깅용)
    logger.error(f"Chat error occurred: {error_type} - {error_msg}", exc_info=True)

    # 타입별 처리
    if isinstance(error, TimeoutError):
        return ChatConfig.ERROR_TIMEOUT
    elif isinstance(error, MemoryError):
        return ChatConfig.ERROR_MEMORY
    elif isinstance(error, ConnectionError):
        return ChatConfig.ERROR_NETWORK
    elif isinstance(error, AttributeError):
        # UnifiedRAG 인스턴스 문제일 가능성
        return ChatConfig.ERROR_INITIALIZATION
    elif isinstance(error, KeyError):
        # 메시지 구조 문제
        logger.error(f"Message structure error: {error_msg}")
        return ChatConfig.ERROR_GENERIC
    else:
        # 일반 에러 - 민감한 정보는 노출하지 않음
        return ChatConfig.ERROR_GENERIC


def _display_chat_history(messages: List[Dict[str, str]]) -> None:
    """채팅 기록 표시

    저장된 모든 메시지를 Streamlit chat UI로 표시합니다.

    Args:
        messages: 표시할 메시지 리스트
    """
    for message in messages:
        # 메시지 구조 검증
        if not _validate_message_structure(message):
            logger.warning(f"Skipping invalid message: {message}")
            continue

        try:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        except Exception as e:
            logger.error(f"Error displaying message: {e}")
            # 표시 오류는 사용자에게 알리지 않고 로그만 남김
            continue


def _generate_ai_response(
    query: str,
    rag_instance: RAGProtocol,
    message_placeholder: Any
) -> Optional[dict]:
    """AI 응답 생성 (Evidence 포함)

    RAG Pipeline을 사용하여 질문에 대한 답변과 근거 문서를 생성합니다.
    응답 타입(객체/dict/str)을 안전하게 정규화하여 처리합니다.

    Args:
        query: 향상된 쿼리 문자열
        rag_instance: RAG 시스템 인스턴스
        message_placeholder: Streamlit placeholder 객체

    Returns:
        Optional[dict]: {"text": str, "evidence": []} 또는 None (에러 시)
    """
    try:
        # RAG 인스턴스 검증
        if rag_instance is None:
            raise AttributeError("RAG instance is None")

        if not hasattr(rag_instance, 'answer'):
            raise AttributeError("RAG instance has no 'answer' method")

        # 응답 생성 (다양한 타입 가능: RAGResponse 객체, dict, str 등)
        raw_response = rag_instance.answer(query)

        # 응답 정규화: 모든 타입을 dict로 통일
        response = _normalize_rag_response(raw_response)

        # 정규화된 응답의 text가 비어있는지 확인
        if not response["text"].strip():
            logger.warning("Empty response text received after normalization")
            return None

        return response

    except Exception as e:
        error_msg = _handle_error(e)
        message_placeholder.markdown(error_msg)
        return {"text": error_msg, "evidence": []}  # 에러 메시지 반환


def _add_message(role: str, content: str) -> None:
    """메시지 추가

    세션 상태에 새로운 메시지를 추가합니다.
    타임스탬프를 자동으로 추가합니다.

    Args:
        role: 메시지 역할 (user 또는 assistant)
        content: 메시지 내용
    """
    message: ChatMessage = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    }

    st.session_state.messages.append(message)

    # 메모리 관리
    st.session_state.messages = _cleanup_old_messages(st.session_state.messages)


# ===== 메인 렌더링 함수 =====

def render_chat_interface(unified_rag_instance: RAGProtocol) -> None:
    """채팅 인터페이스 렌더링

    ChatGPT 스타일의 대화형 인터페이스를 렌더링합니다.
    - 세션 상태 관리
    - 기존 대화 표시
    - 사용자 입력 처리
    - AI 응답 생성
    - 에러 처리
    - 메모리 관리

    Args:
        unified_rag_instance: UnifiedRAG 시스템 인스턴스
    """
    # 1. 세션 상태 초기화
    _initialize_chat_state()

    # 2. 기존 대화 표시
    _display_chat_history(st.session_state.messages)

    # 3. 채팅 입력 처리
    if prompt := st.chat_input(ChatConfig.INPUT_PLACEHOLDER):
        # 3-1. 입력 검증
        is_valid, error_msg = _validate_input(prompt)
        if not is_valid:
            st.error(error_msg)
            return

        # 3-2. 사용자 메시지 추가
        _add_message(ChatConfig.ROLE_USER, prompt)

        # 3-3. 사용자 메시지 표시
        with st.chat_message(ChatConfig.ROLE_USER):
            st.markdown(prompt)

        # 3-4. AI 응답 생성 및 표시
        with st.chat_message(ChatConfig.ROLE_ASSISTANT):
            message_placeholder = st.empty()

            # 대화 맥락 구성
            context = _build_conversation_context(st.session_state.messages)

            # 향상된 쿼리 생성
            enhanced_query = _create_enhanced_query(context, prompt)

            # AI 응답 생성
            with st.spinner(ChatConfig.SPINNER_TEXT):
                response = _generate_ai_response(
                    enhanced_query,
                    unified_rag_instance,
                    message_placeholder
                )

                # 응답이 있으면 표시 및 저장
                if response:
                    # 답변 텍스트 표시
                    message_placeholder.markdown(response["text"])

                    # Evidence 표시 (Top-K=5 제한, 고정 카드 레이아웃, 문서 라이브러리와 통일)
                    if response.get("evidence"):
                        evidence_list = response["evidence"]

                        # Top-K=5 제한
                        MAX_DISPLAY = 5
                        display_evidence = evidence_list[:MAX_DISPLAY]
                        has_more = len(evidence_list) > MAX_DISPLAY

                        # 기본은 접힘 상태 (버튼 클릭 필요)
                        auto_expand = False

                        with st.expander(f"📚 출처 문서 ({len(display_evidence)}건)", expanded=auto_expand):
                            for i, ev in enumerate(display_evidence, 1):
                                # Evidence가 dict 또는 객체일 수 있으므로 안전하게 접근
                                if isinstance(ev, dict):
                                    doc_id = ev.get("doc_id") or ev.get("chunk_id", "unknown")
                                    filename = ev.get("filename", doc_id)
                                    snippet = ev.get("snippet") or ev.get("content", "") or ev.get("text", "")
                                    file_path_str = ev.get("file_path")  # ← 실제 파일 경로
                                    meta = ev.get("meta", {})
                                else:
                                    # 객체인 경우
                                    doc_id = getattr(ev, "doc_id", None) or getattr(ev, "chunk_id", "unknown")
                                    filename = getattr(ev, "filename", doc_id)
                                    snippet = getattr(ev, "snippet", None) or getattr(ev, "content", "") or getattr(ev, "text", "")
                                    file_path_str = getattr(ev, "file_path", None)
                                    meta = getattr(ev, "meta", {})

                                # 파일 경로 생성 (year 폴더 지원)
                                if file_path_str:
                                    file_path = Path(file_path_str)
                                else:
                                    # Fallback: _encode_file_ref 로직과 동일
                                    import re
                                    year_match = re.search(r'(\d{4})-', filename)
                                    if year_match:
                                        year = year_match.group(1)
                                        file_path = Path(f"docs/year_{year}") / filename
                                    else:
                                        file_path = Path("docs") / filename

                                # 메타 데이터 추출
                                doctype = meta.get("doctype") if isinstance(meta, dict) else None
                                display_date = meta.get("date") or meta.get("display_date") if isinstance(meta, dict) else None
                                drafter = meta.get("drafter") if isinstance(meta, dict) else None

                                # 카드 렌더링 (1건일 때만 인라인 미리보기 자동 표시)
                                render_doc_card(
                                    index=i,
                                    filename=filename,
                                    file_path=file_path,
                                    doctype=doctype,
                                    display_date=display_date,
                                    drafter=drafter,
                                    summary=snippet,
                                    show_preview_inline=(auto_expand and i == 1)
                                )

                                # 구분선 (마지막 아이템 제외)
                                if i < len(display_evidence):
                                    st.markdown("---")

                            # 더 보기 버튼 (5건 초과 시)
                            if has_more:
                                st.markdown("---")
                                remaining = len(evidence_list) - MAX_DISPLAY
                                st.info(f"📄 {remaining}건의 문서가 더 있습니다. (현재 상위 {MAX_DISPLAY}건만 표시)")
                                # 추후 "더 보기" 버튼 구현 가능

                    # 진단 패널 (DIAG_RAG=true일 때만 표시)
                    if DIAG_RAG and response.get("diagnostics"):
                        diag = response["diagnostics"]
                        with st.expander("🔍 진단 정보 (Diagnostics)", expanded=False):
                            # 컬럼 레이아웃
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.metric("모드", diag.get("mode", "unknown"))
                                st.metric("생성 경로", diag.get("generate_path", "unknown"))

                            with col2:
                                st.metric("검색 문서 수", diag.get("retrieved_k", 0))
                                st.metric("압축 후 문서 수", diag.get("after_compress_k", 0))

                            with col3:
                                st.metric("Evidence 개수", diag.get("evidence_count", 0))
                                injected = "Yes" if diag.get("evidence_injected") else "No"
                                st.metric("Evidence 강제 주입", injected)

                            # 상세 정보 (작은 텍스트로)
                            st.caption(f"압축 비율: {diag.get('compression_ratio', 'N/A')}")
                            st.caption(f"최종 사용 문서 수: {diag.get('used_k', 0)}")

                    # 메시지 저장 (텍스트만)
                    _add_message(ChatConfig.ROLE_ASSISTANT, response["text"])
                else:
                    # 응답이 없으면 기본 에러 메시지
                    error_msg = ChatConfig.ERROR_GENERIC
                    message_placeholder.markdown(error_msg)
                    _add_message(ChatConfig.ROLE_ASSISTANT, error_msg)

    # 4. UI 구분선
    st.markdown(ChatConfig.DIVIDER)
