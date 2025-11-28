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
- 툴바 (초기화/내보내기/옵션)
- JSON 내보내기
- 옵션 UI (top_k, 스트리밍 속도)
"""

import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

import requests
import streamlit as st
from typing_extensions import TypedDict

from app.core.logging import get_logger
from utils.streaming import stream_text_smart

# ===== 로깅 설정 =====
logger = get_logger(__name__)

# 진단 모드 설정
DIAG_RAG = os.getenv("DIAG_RAG", "false").lower() == "true"


# ===== 타입 정의 =====
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
    evidence: list[Evidence]  # NotRequired: total=False로 모든 필드가 선택적


class RAGProtocol(Protocol):
    """RAG Pipeline 인터페이스 정의 (Evidence 포함)

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


# ===== 상수 정의 =====
class ChatConfig:
    """채팅 인터페이스 설정 상수"""
    # 역할 정의 (Literal 타입으로 명시하여 Mypy 오류 방지)
    ROLE_USER: Literal["user"] = "user"
    ROLE_ASSISTANT: Literal["assistant"] = "assistant"

    # 한글 역할명
    ROLE_DISPLAY_USER = "사용자"
    ROLE_DISPLAY_ASSISTANT = "AI"

    # 아바타
    AVATAR_USER = "👤"
    AVATAR_ASSISTANT = "🤖"

    # 메모리 관리
    MAX_MESSAGES = 100  # 최대 메시지 수
    MAX_CONTEXT_TURNS = 3  # 컨텍스트에 포함할 최대 대화 턴 수
    MAX_MESSAGE_LENGTH = 10000  # 최대 메시지 길이

    # UI 문자열
    INPUT_PLACEHOLDER = "💬 무엇을 도와드릴까요?"
    SPINNER_TEXT = "문서 검색 및 응답 생성 중… (캐시 확인 → 인덱스 검색 → 생성)"
    DIVIDER = "---"

    # 에러 메시지 (사과 표현 제거, 운영 톤 통일)
    ERROR_GENERIC = "오류가 발생했다. 잠시 후 다시 시도하라."
    ERROR_TIMEOUT = "응답 시간이 초과됐다. 요청을 단순화해 재시도하라."
    ERROR_MEMORY = "메모리가 부족하다. 대화 내역을 정리하거나 입력을 줄여라."
    ERROR_NETWORK = "네트워크 오류가 발생했다. 연결 상태를 점검하라."
    ERROR_INITIALIZATION = "시스템 초기화가 필요하다. 페이지 새로고침 후 재시도하라."
    ERROR_INVALID_INPUT = "입력이 너무 길다. 더 짧게 작성하라."

    # 컨텍스트 구성
    CONTEXT_PREFIX = "이전 대화 맥락:"
    CURRENT_QUERY_PREFIX = "현재 질문:"

    # 옵션 기본값
    DEFAULT_TOP_K = 5
    DEFAULT_STREAMING_SPEED = "medium"
    DEFAULT_SHOW_EVIDENCE = True


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
    show_preview_inline: bool = False,
    msg_idx: int = 0
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
    # 리스트 형식으로 간결하게 표시
    import hashlib

    from utils.pdf_utils import download_pdf_button, render_pdf_preview
    # 고유 키 생성: msg_idx와 index를 포함하여 중복 방지
    file_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
    unique_key = f"{msg_idx}_{index}_{file_hash}"
    session_key = f"show_preview_{unique_key}"

    # 메타정보 구성
    meta_parts = []
    if display_date:
        meta_parts.append(display_date)
    if drafter:
        meta_parts.append(drafter)
    meta_str = " · ".join(meta_parts) if meta_parts else ""

    # 요약 (40자로 단축)
    summary_short = summary[:40].strip()
    if len(summary) > 40:
        summary_short += "..."

    # 한 줄 리스트 형식: • 파일명.pdf (날짜 · 기안자) - 요약...
    list_line = f"**{index}.** 📄 **{filename}**"
    if meta_str:
        list_line += f" `{meta_str}`"
    if summary_short:
        list_line += f" — {summary_short}"

    st.markdown(list_line)

    # 액션 버튼 (작게, 같은 줄에)
    if file_path:
        col1, col2, col3 = st.columns([1, 1, 8])

        with col1:
            preview_key = f"preview_btn_{unique_key}"
            current_state = st.session_state.get(session_key, False)
            icon = "📖" if current_state else "🔎"

            if st.button(icon, key=preview_key, help="미리보기", use_container_width=True):
                st.session_state[session_key] = not current_state
                # Streamlit 자동 재렌더링 (st.rerun() 제거, 2025-11-07)

        with col2:
            download_pdf_button(
                file_path=str(file_path),
                key=f"download_{unique_key}",
                width="stretch",
                icon_only=True
            )

        # PDF 미리보기 (선택 시)
        if st.session_state.get(session_key, False):
            st.markdown(f"**📄 {filename}**")
            render_pdf_preview(
                file_path=str(file_path),
                height=500,
                show_download_fallback=True
            )
    else:
        st.caption("⚠️ 파일 경로 없음")


def _normalize_rag_response(resp: Any) -> dict:
    """RAG 응답을 안전하게 dict로 정규화

    RAG Pipeline이 반환할 수 있는 다양한 타입(객체, dict, str)을
    통일된 dict 형식으로 변환하며, status/diagnostics를 보존합니다.

    Args:
        resp: RAG Pipeline의 응답 (RAGResponse 객체, dict, str 등)

    Returns:
        dict: {
            "text": str,
            "evidence": list,
            "status": dict (from_cache 등),
            "diagnostics": dict (메트릭 정보)
        } 형식의 정규화된 응답

    Examples:
        >>> _normalize_rag_response(RAGResponse(text="답변", evidence=[...]))
        {"text": "답변", "evidence": [...], "status": {}, "diagnostics": {}}

        >>> _normalize_rag_response({"text": "답변", "evidence": [...], "status": {"from_cache": True}})
        {"text": "답변", "evidence": [...], "status": {"from_cache": True}, "diagnostics": {}}

        >>> _normalize_rag_response("직접 문자열 답변")
        {"text": "직접 문자열 답변", "evidence": [], "status": {}, "diagnostics": {}}
    """
    # None 체크
    if resp is None:
        logger.warning("Received None response from RAG")
        return {"text": "", "evidence": [], "status": {}, "diagnostics": {}}

    # 문자열인 경우
    if isinstance(resp, str):
        return {"text": resp, "evidence": [], "status": {}, "diagnostics": {}}

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
        status = getattr(resp, "status", {})
        diagnostics = getattr(resp, "diagnostics", {})
        return {
            "text": str(text),
            "evidence": evidence,
            "status": status,
            "diagnostics": diagnostics
        }

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
        status = resp.get("status", {})
        diagnostics = resp.get("diagnostics", {})
        return {
            "text": str(text),
            "evidence": evidence,
            "status": status,
            "diagnostics": diagnostics
        }

    # 그 외 알 수 없는 타입
    logger.warning(f"Unknown response type: {type(resp)}")
    return {"text": str(resp), "evidence": [], "status": {}, "diagnostics": {}}


def _initialize_chat_state() -> None:
    """채팅 세션 상태 초기화

    세션 상태에 messages 리스트와 chat_options가 없으면 초기화합니다.
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []
        logger.info("Chat session initialized")

    if "chat_options" not in st.session_state:
        st.session_state.chat_options = {
            "top_k": ChatConfig.DEFAULT_TOP_K,
            "streaming_speed": ChatConfig.DEFAULT_STREAMING_SPEED,
            "show_evidence": ChatConfig.DEFAULT_SHOW_EVIDENCE,
        }
        logger.info("Chat options initialized")


def _export_history() -> str:
    """대화 기록을 JSON 형식으로 내보내기

    Returns:
        str: JSON 형식의 대화 기록
    """
    return json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)


def _render_toolbar() -> None:
    """채팅 인터페이스 상단 툴바 렌더링

    기능:
    - 대화 초기화
    - JSON 내보내기
    - 옵션 설정 (top_k, 스트리밍 속도, 출처 표시)

    Note:
        현재 비활성화됨. 필요 시 render_chat_interface()에서
        _render_toolbar() 호출을 추가하여 재활성화 가능
    """
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("🗑 대화 초기화", use_container_width=True, help="모든 대화 기록을 삭제합니다"):
            st.session_state.messages = []
            logger.info("Chat history cleared by user")
            st.rerun()

    with col2:
        # JSON 내보내기는 다운로드 버튼으로 구현
        if len(st.session_state.messages) > 0:
            st.download_button(
                label="📥 JSON 내보내기",
                data=_export_history(),
                file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
                help="대화 기록을 JSON 파일로 저장합니다"
            )
        else:
            st.button("📥 JSON 내보내기", use_container_width=True, disabled=True, help="대화 기록이 없습니다")

    with col3:
        with st.popover("⚙️ 옵션", use_container_width=True):
            st.markdown("**검색 및 표시 옵션**")

            # top_k 설정
            new_top_k = st.slider(
                "검색 문서 수 (top_k)",
                min_value=1,
                max_value=20,
                value=st.session_state.chat_options["top_k"],
                help="RAG 검색 시 가져올 최대 문서 수"
            )
            if new_top_k != st.session_state.chat_options["top_k"]:
                st.session_state.chat_options["top_k"] = new_top_k
                logger.info(f"top_k changed to {new_top_k}")

            # 스트리밍 속도 설정
            speed_options = {
                "slow": "느리게 (가독성)",
                "medium": "보통 (권장)",
                "fast": "빠르게 (효율성)"
            }
            current_speed = st.session_state.chat_options["streaming_speed"]
            new_speed = st.selectbox(
                "스트리밍 속도",
                options=list(speed_options.keys()),
                index=list(speed_options.keys()).index(current_speed),
                format_func=lambda x: speed_options[x],
                help="응답을 표시하는 속도 조절"
            )
            if new_speed != current_speed:
                st.session_state.chat_options["streaming_speed"] = new_speed
                logger.info(f"Streaming speed changed to {new_speed}")

            # 출처 표시 옵션
            new_show_evidence = st.checkbox(
                "출처 문서 표시",
                value=st.session_state.chat_options["show_evidence"],
                help="AI 응답의 근거가 된 문서를 표시합니다"
            )
            if new_show_evidence != st.session_state.chat_options["show_evidence"]:
                st.session_state.chat_options["show_evidence"] = new_show_evidence
                logger.info(f"Show evidence changed to {new_show_evidence}")

            # 현재 설정 요약
            st.markdown("---")
            st.caption(f"현재 설정: top_k={st.session_state.chat_options['top_k']}, "
                      f"속도={speed_options[st.session_state.chat_options['streaming_speed']]}, "
                      f"출처={'표시' if st.session_state.chat_options['show_evidence'] else '숨김'}")


def _display_evidence_section(evidence_list: list, msg_idx: int) -> None:
    """출처 문서 섹션 표시

    Evidence 리스트를 간결한 리스트 형식으로 표시하며,
    각 메시지별로 expander 상태를 session_state로 관리합니다.

    Args:
        evidence_list: 출처 문서 리스트
        msg_idx: 메시지 인덱스 (expander 상태 관리용)
    """
    from pathlib import Path

    # Top-K=20 제한
    MAX_DISPLAY = 20
    display_evidence = evidence_list[:MAX_DISPLAY]
    has_more = len(evidence_list) > MAX_DISPLAY

    # Expander는 기본 접힌 상태 (Streamlit 내부 상태 관리 사용)
    # expanded 파라미터를 동적으로 변경하면 재렌더링 시 충돌이 발생할 수 있음
    with st.expander(
        f"📚 출처 문서 ({len(display_evidence)}건)",
        expanded=False
    ):
        for i, ev in enumerate(display_evidence, 1):
            # Evidence가 dict 또는 객체일 수 있으므로 안전하게 접근
            if isinstance(ev, dict):
                doc_id = ev.get("doc_id") or ev.get("chunk_id", "unknown")
                filename = ev.get("filename", doc_id)
                snippet = ev.get("snippet") or ev.get("content", "") or ev.get("text", "")
                file_path_str = ev.get("file_path")
                meta = ev.get("meta", {})
            else:
                # 객체인 경우
                doc_id = getattr(ev, "doc_id", None) or getattr(ev, "chunk_id", "unknown")
                filename = getattr(ev, "filename", doc_id)
                snippet = getattr(ev, "snippet", None) or getattr(ev, "content", "") or getattr(ev, "text", "")
                file_path_str = getattr(ev, "file_path", None)
                meta = getattr(ev, "meta", {})

            # 파일 경로 생성 (year 폴더 지원) - 절대 경로 사용
            if file_path_str:
                file_path = Path(file_path_str)
                # 상대 경로인 경우 DOCS_DIR 기준으로 변환
                if not file_path.is_absolute():
                    from app.config.settings import settings
                    # DB path가 'docs/'로 시작하면 제거 (중복 방지)
                    path_str = str(file_path)
                    if path_str.startswith("docs/"):
                        path_str = path_str[5:]  # 'docs/' 제거
                    file_path = settings.DOCS_DIR / path_str
            else:
                # Fallback: year 폴더 추출 (절대 경로 생성)
                import re

                from app.config.settings import settings
                year_match = re.search(r"(\d{4})-", filename)
                if year_match:
                    year = year_match.group(1)
                    file_path = settings.DOCS_DIR / f"year_{year}" / filename
                else:
                    file_path = settings.DOCS_DIR / filename

            # 디버깅: 생성된 경로 확인
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[출처 문서] filename={filename}, file_path_str={file_path_str}, generated_path={file_path}, exists={file_path.exists() if isinstance(file_path, Path) else 'N/A'}")

            # 메타 데이터 추출
            doctype = meta.get("doctype") if isinstance(meta, dict) else None
            display_date = meta.get("date") or meta.get("display_date") if isinstance(meta, dict) else None
            drafter = meta.get("drafter") if isinstance(meta, dict) else None

            # 카드 렌더링 (리스트 형식)
            render_doc_card(
                index=i,
                filename=filename,
                file_path=file_path,
                doctype=doctype,
                display_date=display_date,
                drafter=drafter,
                summary=snippet,
                show_preview_inline=False,
                msg_idx=msg_idx
            )

            # 간결한 구분 (마지막 아이템 제외)
            if i < len(display_evidence):
                st.markdown("")  # 작은 여백만

        # 더 보기 정보 (5건 초과 시)
        if has_more:
            st.markdown("---")
            remaining = len(evidence_list) - MAX_DISPLAY
            st.info(f"📄 {remaining}건의 문서가 더 있습니다. (현재 상위 {MAX_DISPLAY}건만 표시)")


def _validate_message_structure(message: Any) -> bool:
    """메시지 구조 검증

    Args:
        message: 검증할 메시지 객체

    Returns:
        bool: 유효한 메시지 구조면 True, 아니면 False

    Note:
        role과 content는 필수, timestamp와 evidence는 선택적 (total=False)
    """
    if not isinstance(message, dict):
        return False

    # 필수 필드만 검사 (timestamp, evidence는 선택적)
    required_keys = {"role", "content"}
    if not required_keys.issubset(message.keys()):
        return False

    if message["role"] not in [ChatConfig.ROLE_USER, ChatConfig.ROLE_ASSISTANT]:
        return False

    if not isinstance(message["content"], str):
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


def _cleanup_old_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
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


def _build_conversation_context(messages: list[dict[str, str]], max_turns: int = ChatConfig.MAX_CONTEXT_TURNS) -> str:
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
        role = msg["role"]
        display_role = ChatConfig.ROLE_DISPLAY_USER if role == ChatConfig.ROLE_USER else ChatConfig.ROLE_DISPLAY_ASSISTANT

        # 메시지 내용 처리 (긴 응답은 요약)
        content = msg["content"]

        # AI 응답이 너무 길면 요약 (500자 제한)
        MAX_CONTEXT_LENGTH = 500
        if role == ChatConfig.ROLE_ASSISTANT and len(content) > MAX_CONTEXT_LENGTH:
            # 리스트 응답 패턴 감지
            if "관련 문서" in content and "건)" in content:
                # 문서 리스트 응답인 경우: 건수만 추출
                import re
                match = re.search(r"\((\d+)건\)", content)
                if match:
                    doc_count = match.group(1)
                    content = f"(이전 응답: {doc_count}건의 문서 리스트 제공됨)"
                else:
                    content = "(이전 응답: 문서 리스트 제공됨 - 생략)"
            else:
                # 일반 긴 응답: 앞부분만 유지
                content = content[:MAX_CONTEXT_LENGTH] + "...(생략)"

        # 메시지 추가
        context_parts.append(f"{display_role}: {content}")

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
    # 컨텍스트와 프롬프트를 결합하여 enhanced query 생성
    if context:
        return f"{ChatConfig.CONTEXT_PREFIX}\n{context}\n\n{ChatConfig.CURRENT_QUERY_PREFIX} {prompt}"
    else:
        return prompt


def _handle_error(error: Exception) -> dict:
    """예외 타입별 에러 메시지 및 상세 정보 생성

    예외 타입에 따라 적절한 사용자 친화적 메시지를 반환합니다.
    모든 에러는 로그에 기록됩니다.

    Args:
        error: 발생한 예외 객체

    Returns:
        dict: {"message": str, "details": str, "error_type": str}
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # 로깅 (디버깅용)
    logger.error(f"Chat error occurred: {error_type} - {error_msg}", exc_info=True)

    # 타입별 처리 (사과 표현 제거)
    if isinstance(error, TimeoutError):
        user_message = ChatConfig.ERROR_TIMEOUT
        details = "요청 처리 시간이 초과됐다. 서버가 무응답 상태이거나 요청이 너무 복잡하다."
    elif isinstance(error, MemoryError):
        user_message = ChatConfig.ERROR_MEMORY
        details = "사용 가능한 메모리가 부족하다. 대화 기록을 정리하거나 입력을 줄여라."
    elif isinstance(error, ConnectionError):
        user_message = ChatConfig.ERROR_NETWORK
        details = "네트워크 연결에 문제가 발생했다. 인터넷 연결을 점검하라."
    elif isinstance(error, AttributeError):
        # UnifiedRAG 인스턴스 문제일 가능성
        user_message = ChatConfig.ERROR_INITIALIZATION
        details = "시스템 초기화에 문제가 있다. 페이지를 새로고침하라."
    elif isinstance(error, KeyError):
        # 메시지 구조 문제
        logger.error(f"Message structure error: {error_msg}")
        user_message = ChatConfig.ERROR_GENERIC
        details = "메시지 구조에 문제가 발생했다. 다시 시도하라."
    else:
        # 일반 에러 - 민감한 정보는 노출하지 않음
        user_message = ChatConfig.ERROR_GENERIC
        details = "예상치 못한 오류가 발생했다. 잠시 후 다시 시도하라."

    return {
        "message": user_message,
        "details": details,
        "error_type": error_type
    }


def _display_chat_history(messages: list[dict[str, str]]) -> None:
    """채팅 기록 표시

    저장된 모든 메시지를 Streamlit chat UI로 표시합니다.
    Evidence가 포함된 메시지는 출처 문서도 함께 표시합니다.

    Args:
        messages: 표시할 메시지 리스트
    """
    for msg_idx, message in enumerate(messages):
        # 메시지 구조 검증
        if not _validate_message_structure(message):
            logger.warning(f"Skipping invalid message: {message}")
            continue

        try:
            # 아바타 설정
            avatar = ChatConfig.AVATAR_USER if message["role"] == ChatConfig.ROLE_USER else ChatConfig.AVATAR_ASSISTANT

            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

                # Evidence 표시 (assistant 메시지에만, 옵션 확인)
                if (message["role"] == "assistant" and
                    message.get("evidence") and
                    st.session_state.chat_options.get("show_evidence", True)):
                    _display_evidence_section(message["evidence"], msg_idx)

        except Exception as e:
            logger.error(f"Error displaying message: {e}")
            # 표시 오류는 사용자에게 알리지 않고 로그만 남김
            continue


def _generate_ai_response(
    query: str,
    rag_instance: RAGProtocol,
    message_placeholder: Any,
    selected_filename: Optional[str] = None
) -> Optional[dict]:
    """AI 응답 생성 (Evidence 포함)

    RAG Pipeline을 사용하여 질문에 대한 답변과 근거 문서를 생성합니다.
    응답 타입(객체/dict/str)을 안전하게 정규화하여 처리합니다.

    Args:
        query: 향상된 쿼리 문자열
        rag_instance: RAG 시스템 인스턴스
        message_placeholder: Streamlit placeholder 객체
        selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

    Returns:
        Optional[dict]: {"text": str, "evidence": [], "status": {}, "diagnostics": {}} 또는 None (에러 시)
    """
    try:
        # RAG 인스턴스 검증
        if rag_instance is None:
            raise AttributeError("RAG instance is None")

        if not hasattr(rag_instance, "answer"):
            raise AttributeError("RAG instance has no 'answer' method")

        # 옵션에서 top_k 가져오기
        opts = st.session_state.chat_options
        top_k = opts.get("top_k", ChatConfig.DEFAULT_TOP_K)

        # 응답 생성 (다양한 타입 가능: RAGResponse 객체, dict, str 등)
        # 선택된 문서와 top_k 모두 전달
        raw_response = rag_instance.answer(
            query,
            top_k=top_k,
            selected_filename=selected_filename
        )
        logger.info(f"RAG query executed with top_k={top_k}, selected_filename={selected_filename}")

        # 응답 정규화: 모든 타입을 dict로 통일
        response = _normalize_rag_response(raw_response)

        # 정규화된 응답의 text가 비어있는지 확인
        if not response["text"].strip():
            logger.warning("Empty response text received after normalization")
            return None

        return response

    except Exception as e:
        error_info = _handle_error(e)

        # 사용자 친화적 에러 메시지 표시
        message_placeholder.error(error_info["message"])

        # 상세 정보는 expander로 제공
        with message_placeholder.container():
            with st.expander("🔍 오류 상세 정보", expanded=False):
                st.caption(f"**오류 유형**: {error_info['error_type']}")
                st.caption(f"**상세 설명**: {error_info['details']}")
                st.info("💡 **해결 방법**: 위 설명을 참고하여 문제를 해결해주세요. 문제가 지속되면 관리자에게 문의하세요.")

        return {"text": error_info["message"], "evidence": []}  # 에러 메시지 반환


def _add_message(role: Literal["user", "assistant"], content: str, evidence: Optional[list] = None) -> None:
    """메시지 추가

    세션 상태에 새로운 메시지를 추가합니다.
    타임스탬프와 evidence를 자동으로 추가합니다.

    Args:
        role: 메시지 역할 (user 또는 assistant)
        content: 메시지 내용
        evidence: 출처 문서 리스트 (선택사항)
    """
    message: ChatMessage = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    }

    # Evidence 추가 (있는 경우만)
    if evidence:
        message["evidence"] = evidence

    st.session_state.messages.append(message)

    # 메모리 관리
    st.session_state.messages = _cleanup_old_messages(st.session_state.messages)


# ===== 메인 렌더링 함수 =====

def render_chat_interface(unified_rag_instance: RAGProtocol) -> None:
    """채팅 인터페이스 렌더링

    ChatGPT 스타일의 대화형 인터페이스를 렌더링합니다.
    - 세션 상태 관리
    - 툴바 (초기화/내보내기/옵션)
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

    # 1-1. 선택된 문서 알림 (사이드바에서 문서 선택시)
    if "selected_doc" in st.session_state and st.session_state.selected_doc is not None and st.session_state.get("show_doc_preview", False):
        selected_doc = st.session_state.selected_doc
        # pandas Series가 아닌 dict인 경우만 처리
        if isinstance(selected_doc, dict):
            title = selected_doc.get("title", "알 수 없음")
            col1, col2 = st.columns([10, 1])
            with col1:
                # 얇은 배너 스타일로 표시
                st.markdown(
                    f"""
                    <div class="doc-context-banner">
                        <span class="icon">🎯</span>
                        <span class="doc-context-label">문서 컨텍스트 모드:</span>
                        <span>{title} 문서를 우선적으로 검색합니다</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col2:
                if st.button("❌", key="clear_doc_context", help="문서 컨텍스트 해제"):
                    st.session_state.show_doc_preview = False
                    if "selected_doc" in st.session_state:
                        del st.session_state.selected_doc
                    # Streamlit 자동 재렌더링으로 충분 (st.rerun() 제거, 2025-11-07)

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

        # 3-3. 사용자 메시지 표시 (아바타 포함)
        with st.chat_message(ChatConfig.ROLE_USER, avatar=ChatConfig.AVATAR_USER):
            st.markdown(prompt)

        # 3-4. AI 응답 생성 및 표시 (아바타 포함)
        with st.chat_message(ChatConfig.ROLE_ASSISTANT, avatar=ChatConfig.AVATAR_ASSISTANT):
            message_placeholder = st.empty()

            # 대화 맥락 구성
            context = _build_conversation_context(st.session_state.messages)

            # 향상된 쿼리 생성
            enhanced_query = _create_enhanced_query(context, prompt)

            # 선택된 문서 확인 (사이드바에서 선택한 문서 우선 검색용)
            selected_filename = None
            doc = st.session_state.get("selected_doc")
            if doc is not None:
                try:
                    # 딕셔너리 또는 pandas Series에서 filename 추출
                    selected_filename = doc.get("filename") if hasattr(doc, "get") else doc["filename"]
                    if selected_filename:
                        logger.info(f"📌 선택된 문서 우선 검색: {selected_filename}")
                except (KeyError, TypeError, AttributeError):
                    pass

            # AI 응답 생성
            with st.spinner(ChatConfig.SPINNER_TEXT):
                response = _generate_ai_response(
                    enhanced_query,
                    unified_rag_instance,
                    message_placeholder,
                    selected_filename=selected_filename
                )

                # 응답이 있으면 표시 및 저장
                if response:
                    # 답변 텍스트를 점진적으로 표시 (ChatGPT 스타일)
                    # 캐시에서 가져온 경우 빠르게, 새로 생성한 경우 천천히
                    from_cache = response.get("status", {}).get("from_cache")

                    # 캐시 피드백 배지 표시
                    if from_cache:
                        st.caption("⚡ **Cached** - 이전 응답을 빠르게 불러왔습니다")

                    if from_cache:
                        # 캐시된 응답은 즉시 표시 (스트리밍 효과 없음)
                        message_placeholder.markdown(response["text"])
                    else:
                        # 새로 생성된 응답은 점진적으로 표시 (옵션에서 속도 가져오기)
                        streaming_speed = st.session_state.chat_options.get("streaming_speed", "medium")
                        for partial_text in stream_text_smart(response["text"], speed=streaming_speed):
                            message_placeholder.markdown(partial_text + "▌")  # 커서 효과
                        # 최종 텍스트 (커서 제거)
                        message_placeholder.markdown(response["text"])

                    # Evidence 표시 (옵션 확인, session_state 관리로 미리보기 클릭 시에도 유지됨)
                    if response.get("evidence") and st.session_state.chat_options.get("show_evidence", True):
                        # 새 응답의 인덱스는 메시지 리스트의 마지막 인덱스가 될 것임
                        # 하지만 아직 메시지가 저장되지 않았으므로 현재 길이를 사용
                        current_msg_idx = len(st.session_state.messages)
                        _display_evidence_section(response["evidence"], current_msg_idx)

                    # 진단 패널 (DIAG_RAG=true일 때만 표시)
                    if DIAG_RAG and response.get("diagnostics"):
                        diag = response["diagnostics"]
                        with st.expander("🔍 진단 정보 (Diagnostics)", expanded=False):
                            # 컬럼 레이아웃
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.metric("모드", diag.get("mode", "unknown"))
                                st.metric("생성 경로", diag.get("generate_path", "unknown"))
                                # 캐시 히트 여부
                                cache_hit = "⚡ Hit" if diag.get("cache_hit") else "❌ Miss"
                                st.metric("캐시", cache_hit)

                            with col2:
                                st.metric("검색 문서 수", diag.get("retrieved_k", 0))
                                st.metric("압축 후 문서 수", diag.get("after_compress_k", 0))
                                # 스니펫 총 글자수
                                snippet_chars = diag.get("snippet_total_chars", 0)
                                st.metric("스니펫 총 글자수", f"{snippet_chars:,}")

                            with col3:
                                st.metric("Evidence 개수", diag.get("evidence_count", 0))
                                # 토큰 사용량
                                input_tokens = diag.get("input_tokens", 0)
                                output_tokens = diag.get("output_tokens", 0)
                                st.metric("입력 토큰", f"{input_tokens:,}")
                                st.metric("출력 토큰", f"{output_tokens:,}")

                            # 상세 정보 (작은 텍스트로)
                            st.caption(f"압축 비율: {diag.get('compression_ratio', 'N/A')}")
                            st.caption(f"최종 사용 문서 수: {diag.get('used_k', 0)}")
                            # 응답 시간
                            latency_ms = diag.get("latency_ms", 0)
                            st.caption(f"응답 시간: {latency_ms:,}ms ({latency_ms / 1000:.2f}s)")
                            # Evidence 강제 주입 여부
                            injected = "Yes" if diag.get("evidence_injected") else "No"
                            st.caption(f"Evidence 강제 주입: {injected}")

                    # 메시지 저장 (텍스트 + evidence)
                    _add_message(ChatConfig.ROLE_ASSISTANT, response["text"], evidence=response.get("evidence"))
                else:
                    # 응답이 없으면 기본 에러 메시지
                    error_msg = ChatConfig.ERROR_GENERIC
                    message_placeholder.markdown(error_msg)
                    _add_message(ChatConfig.ROLE_ASSISTANT, error_msg)

    # 4. UI 구분선
    st.markdown(ChatConfig.DIVIDER)
