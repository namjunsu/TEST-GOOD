"""
Chat Interface Component
ChatGPT 스타일의 채팅 인터페이스 UI 렌더링

책임:
- 세션 상태 관리
- 채팅 기록 표시
- 사용자 입력 처리
- AI 응답 표시 (스트리밍)
- 진단 패널 표시

분리된 모듈:
- chat_types.py: 타입 정의 (TypedDict, Protocol, ChatConfig)
- chat_helpers.py: 헬퍼 함수 (검증, 컨텍스트, 에러 핸들링)
- chat_evidence.py: Evidence UI (문서 카드, 출처 섹션)
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import streamlit as st

from app.core.logging import get_logger
from components.chat_evidence import (
    display_evidence_section,
    display_similar_documents_section,
)
from components.chat_helpers import (
    build_conversation_context,
    cleanup_old_messages,
    create_enhanced_query,
    handle_error,
    log_query_to_terminal,
    match_query_to_evidence,
    normalize_rag_response,
    validate_input,
    validate_message_structure,
)
from components.chat_types import ChatConfig, ChatMessage, RAGProtocol
from utils.streaming import stream_text_smart

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# 진단 모드 설정
DIAG_RAG = os.getenv("DIAG_RAG", "false").lower() == "true"


# ============================================================================
# 세션 상태 관리
# ============================================================================


def _initialize_chat_state() -> None:
    """채팅 세션 상태 초기화"""
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

    if "evidence_history" not in st.session_state:
        st.session_state.evidence_history = []
        logger.info("Evidence history initialized")


def _add_message(
    role: str,
    content: str,
    evidence: list | None = None,
    similar_documents: list | None = None,
) -> None:
    """메시지 추가

    Args:
        role: 메시지 역할
        content: 메시지 내용
        evidence: 출처 문서 리스트
        similar_documents: 유사 문서 리스트
    """
    message: ChatMessage = {
        "role": role,  # type: ignore
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }

    if evidence:
        message["evidence"] = evidence

    if similar_documents:
        message["similar_documents"] = similar_documents

    st.session_state.messages.append(message)
    st.session_state.messages = cleanup_old_messages(st.session_state.messages)


# ============================================================================
# UI 렌더링
# ============================================================================


def _display_chat_history(messages: list[dict[str, Any]]) -> None:
    """채팅 기록 표시

    Args:
        messages: 표시할 메시지 리스트
    """
    for msg_idx, message in enumerate(messages):
        if not validate_message_structure(message):
            logger.warning(f"Skipping invalid message: {message}")
            continue

        try:
            avatar = (
                ChatConfig.AVATAR_USER
                if message["role"] == ChatConfig.ROLE_USER
                else ChatConfig.AVATAR_ASSISTANT
            )

            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

                # Evidence 표시
                if (
                    message["role"] == "assistant"
                    and message.get("evidence")
                    and st.session_state.chat_options.get("show_evidence", True)
                ):
                    display_evidence_section(message["evidence"], msg_idx)

                # 유사 문서 추천 표시
                if message["role"] == "assistant" and message.get("similar_documents"):
                    display_similar_documents_section(message["similar_documents"], msg_idx)

        except Exception as e:
            logger.error(f"Error displaying message: {e}")
            continue


def _display_doc_context_banner() -> None:
    """선택된 문서 컨텍스트 배너 표시"""
    if "selected_doc" not in st.session_state:
        return

    if st.session_state.selected_doc is None:
        return

    if not st.session_state.get("show_doc_preview", False):
        return

    selected_doc = st.session_state.selected_doc
    if not isinstance(selected_doc, dict):
        return

    title = selected_doc.get("title", "알 수 없음")
    col1, col2 = st.columns([10, 1])

    with col1:
        st.markdown(
            f"""
            <div class="doc-context-banner">
                <span class="icon">🎯</span>
                <span class="doc-context-label">문서 컨텍스트 모드:</span>
                <span>{title} 문서를 우선적으로 검색합니다</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        if st.button("❌", key="clear_doc_context", help="문서 컨텍스트 해제"):
            st.session_state.show_doc_preview = False
            if "selected_doc" in st.session_state:
                del st.session_state.selected_doc


def _get_selected_filename() -> tuple[str | None, float]:
    """선택된 문서 파일명 가져오기

    Returns:
        tuple[str | None, float]: (파일명, 신뢰도)
    """
    # 1. 사이드바에서 명시적으로 선택한 문서
    doc = st.session_state.get("selected_doc")
    if doc is not None:
        try:
            filename = doc.get("filename") if hasattr(doc, "get") else doc["filename"]
            if filename:
                logger.info(f"사이드바 선택 문서: {filename}")
                return filename, 1.0
        except (KeyError, TypeError, AttributeError):
            pass

    return None, 0.0


def _display_diagnostics_panel(diagnostics: dict) -> None:
    """진단 패널 표시

    Args:
        diagnostics: 진단 정보 딕셔너리
    """
    with st.expander("🔍 진단 정보 (Diagnostics)", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("모드", diagnostics.get("mode", "unknown"))
            st.metric("생성 경로", diagnostics.get("generate_path", "unknown"))
            cache_hit = "⚡ Hit" if diagnostics.get("cache_hit") else "❌ Miss"
            st.metric("캐시", cache_hit)

        with col2:
            st.metric("검색 문서 수", diagnostics.get("retrieved_k", 0))
            st.metric("압축 후 문서 수", diagnostics.get("after_compress_k", 0))
            snippet_chars = diagnostics.get("snippet_total_chars", 0)
            st.metric("스니펫 총 글자수", f"{snippet_chars:,}")

        with col3:
            st.metric("Evidence 개수", diagnostics.get("evidence_count", 0))
            input_tokens = diagnostics.get("input_tokens", 0)
            output_tokens = diagnostics.get("output_tokens", 0)
            st.metric("입력 토큰", f"{input_tokens:,}")
            st.metric("출력 토큰", f"{output_tokens:,}")

        st.caption(f"압축 비율: {diagnostics.get('compression_ratio', 'N/A')}")
        st.caption(f"최종 사용 문서 수: {diagnostics.get('used_k', 0)}")
        latency_ms = diagnostics.get("latency_ms", 0)
        st.caption(f"응답 시간: {latency_ms:,}ms ({latency_ms / 1000:.2f}s)")
        injected = "Yes" if diagnostics.get("evidence_injected") else "No"
        st.caption(f"Evidence 강제 주입: {injected}")


# ============================================================================
# AI 응답 생성
# ============================================================================


def _generate_ai_response(
    query: str,
    rag_instance: RAGProtocol,
    message_placeholder: Any,
    selected_filename: str | None = None,
    cancel_flag: dict | None = None,
) -> dict | None:
    """AI 응답 생성

    Args:
        query: 향상된 쿼리 문자열
        rag_instance: RAG 시스템 인스턴스
        message_placeholder: Streamlit placeholder 객체
        selected_filename: 선택된 문서 파일명
        cancel_flag: 취소 플래그 딕셔너리 (cancelled 키 확인)

    Returns:
        dict | None: 정규화된 응답 또는 None
    """
    try:
        if rag_instance is None:
            raise AttributeError("RAG instance is None")

        if not hasattr(rag_instance, "answer"):
            raise AttributeError("RAG instance has no 'answer' method")

        opts = st.session_state.get("chat_options", {})
        top_k = opts.get("top_k", ChatConfig.DEFAULT_TOP_K)

        # 세션 정보 수집 (NEW)
        try:
            import streamlit.runtime.scriptrunner as sr
            ctx = sr.get_script_run_ctx()
            session_id = ctx.session_id if ctx else "unknown"
        except Exception:
            session_id = "unknown"

        # IP 주소는 현재 Streamlit에서 직접 추출 불가 → "localhost" 사용
        # 실제 배포 시 nginx/proxy에서 X-Forwarded-For 헤더 사용 필요
        client_ip = "localhost"

        raw_response = rag_instance.answer(
            query,
            top_k=top_k,
            selected_filename=selected_filename,
            # NEW 파라미터 전달
            client_ip=client_ip,
            session_id=session_id,
            cancel_flag=cancel_flag,  # 취소 플래그 전달
        )
        logger.info(f"RAG query executed with top_k={top_k}, selected_filename={selected_filename}")

        response = normalize_rag_response(raw_response)

        if not response["text"].strip():
            logger.warning("Empty response text received after normalization")
            return None

        return response

    except Exception as e:
        error_info = handle_error(e)
        message_placeholder.error(error_info["message"])

        with message_placeholder.container():
            with st.expander("🔍 오류 상세 정보", expanded=False):
                st.caption(f"**오류 유형**: {error_info['error_type']}")
                st.caption(f"**상세 설명**: {error_info['details']}")
                st.info("💡 **해결 방법**: 위 설명을 참고하여 문제를 해결해주세요.")

        return {"text": error_info["message"], "evidence": []}


def _display_response_with_streaming(
    response: dict,
    message_placeholder: Any,
) -> None:
    """응답을 스트리밍으로 표시

    Args:
        response: RAG 응답 딕셔너리
        message_placeholder: Streamlit placeholder
    """
    from_cache = response.get("status", {}).get("from_cache")

    if from_cache:
        st.caption("⚡ **Cached** - 이전 응답을 빠르게 불러왔습니다")
        message_placeholder.markdown(response["text"])
    else:
        # 2026-01-07: 스트리밍 안정성 개선 (에러 시 폴백)
        try:
            streaming_speed = st.session_state.chat_options.get("streaming_speed", "medium")
            for partial_text in stream_text_smart(response["text"], speed=streaming_speed):
                message_placeholder.markdown(partial_text + "▌")
        except Exception as e:
            logger.error(f"스트리밍 오류 (폴백 전체 표시): {e}", exc_info=True)
            # 폴백: 스트리밍 실패 시 전체 텍스트 즉시 표시
        finally:
            message_placeholder.markdown(response["text"])


def _update_evidence_history(evidence: list) -> None:
    """Evidence 히스토리 업데이트

    Args:
        evidence: 새로운 evidence 리스트
    """
    for ev in evidence:
        if isinstance(ev, dict) and ev.get("filename"):
            existing_filenames = {
                e.get("filename")
                for e in st.session_state.evidence_history
                if isinstance(e, dict)
            }
            if ev.get("filename") not in existing_filenames:
                st.session_state.evidence_history.append(ev)

    logger.info(f"Evidence 히스토리 업데이트: 총 {len(st.session_state.evidence_history)}건")


# ============================================================================
# 메인 렌더링 함수
# ============================================================================


def render_chat_interface(unified_rag_instance: RAGProtocol) -> None:
    """채팅 인터페이스 렌더링

    Args:
        unified_rag_instance: RAG 시스템 인스턴스
    """
    # 1. 세션 상태 초기화
    _initialize_chat_state()

    # 2. 문서 컨텍스트 배너
    _display_doc_context_banner()

    # 3. 기존 대화 표시
    _display_chat_history(st.session_state.messages)

    # 4. 채팅 입력 처리
    prompt = st.chat_input(ChatConfig.INPUT_PLACEHOLDER)
    if not prompt:
        return

    # 4-1. 입력 검증
    is_valid, error_msg = validate_input(prompt)
    if not is_valid:
        st.error(error_msg)
        return

    log_query_to_terminal(prompt)

    # 4-2. 사용자 메시지 추가 및 표시
    _add_message(ChatConfig.ROLE_USER, prompt)

    with st.chat_message(ChatConfig.ROLE_USER, avatar=ChatConfig.AVATAR_USER):
        st.markdown(prompt)

    # 4-3. AI 응답 생성 및 표시
    with st.chat_message(ChatConfig.ROLE_ASSISTANT, avatar=ChatConfig.AVATAR_ASSISTANT):
        message_placeholder = st.empty()

        # 대화 맥락 구성
        context = build_conversation_context(st.session_state.messages)
        enhanced_query = create_enhanced_query(context, prompt)

        # 선택된 문서 확인
        selected_filename, match_confidence = _get_selected_filename()

        # Evidence 히스토리에서 매칭 시도
        if not selected_filename:
            evidence_history = st.session_state.get("evidence_history", [])
            if evidence_history:
                matched_filename, match_confidence = match_query_to_evidence(
                    prompt, evidence_history
                )
                if matched_filename:
                    selected_filename = matched_filename
                    logger.info(
                        f"Evidence 히스토리에서 매칭: {selected_filename} "
                        f"(신뢰도={match_confidence:.2f})"
                    )

        # AI 응답 생성 (실시간 진행 상태 표시)
        start_time = time.time()

        # 공유 상태 (스레드 간 통신)
        progress_state = {
            "step": "시작",
            "done": False,
            "response": None,
            "error": None,
            "cancelled": False,
        }

        def run_rag():
            """백그라운드에서 RAG 실행"""
            try:
                progress_state["step"] = "🔍 쿼리 분석 중..."
                result = _generate_ai_response(
                    enhanced_query,
                    unified_rag_instance,
                    message_placeholder,
                    selected_filename=selected_filename,
                    cancel_flag=progress_state,  # 취소 플래그 전달
                )
                # 취소 확인
                if progress_state["cancelled"]:
                    progress_state["error"] = "사용자가 취소했습니다"
                    return
                progress_state["response"] = result
            except Exception as e:
                logger.error(f"RAG 실행 실패: {e}", exc_info=True)
                progress_state["error"] = str(e)
            finally:
                progress_state["done"] = True

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=run_rag, daemon=True)
        thread.start()

        # 진행 상태 표시 (폴링) - 사용자 친화적 메시지
        # 2열 레이아웃: 진행 상태 메시지 + 중단 버튼
        col1, col2 = st.columns([4, 1])
        status_placeholder = col1.empty()
        stop_button_placeholder = col2.empty()

        while not progress_state["done"]:
            elapsed = time.time() - start_time

            # 2026-01-07: 시간대별 진행 상태 메시지 개선
            if elapsed < 10:
                msg = f"🔍 **문서 검색 중...** ({elapsed:.1f}초)"
            elif elapsed < 30:
                msg = f"📊 **답변 생성 중...** ({elapsed:.1f}초) - 문서 분석 완료"
            elif elapsed < 60:
                msg = f"✍️ **답변 작성 중...** ({elapsed:.1f}초) - 품질 높은 답변을 준비하고 있습니다"
            elif elapsed < 120:
                msg = f"⏳ **답변 생성 중...** ({int(elapsed)}초) - 조금만 더 기다려주세요..."
            else:
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                msg = f"⌛ **긴 답변 생성 중...** ({minutes}분 {seconds}초) - 곧 완료됩니다 🕐"

            status_placeholder.markdown(msg)

            # 중단 버튼 (5초 이상 경과 시에만 표시)
            if elapsed > 5 and stop_button_placeholder.button(
                "⏹️ 중단", key=f"stop_{start_time}", type="secondary"
            ):
                progress_state["cancelled"] = True
                progress_state["done"] = True
                logger.info("사용자가 답변 생성 중단")
                break

            time.sleep(0.1)  # CPU 절약

        # 완료 후 상태 표시 제거
        status_placeholder.empty()
        stop_button_placeholder.empty()

        # 스레드 종료 대기 (취소 시에도 최대 2초 대기)
        if not progress_state["done"]:
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.warning("백그라운드 스레드가 2초 내에 종료되지 않음")

        # 총 소요 시간 계산
        total_elapsed = time.time() - start_time

        # 취소 여부 확인
        if progress_state["cancelled"]:
            cancelled_msg = "⏹️ **답변 생성이 중단되었습니다.**"
            message_placeholder.markdown(cancelled_msg)
            _add_message(ChatConfig.ROLE_ASSISTANT, cancelled_msg)
            st.info(f"⏱️ {total_elapsed:.1f}초 후 중단됨")
            return

        # 결과 가져오기
        if progress_state["error"]:
            error_msg = f"오류: {progress_state['error']}"
            st.error(error_msg)
            _add_message(ChatConfig.ROLE_ASSISTANT, f"❌ {error_msg}")
            return

        response = progress_state["response"]

        if not response:
            error_msg = "오류가 발생했다. 잠시 후 다시 시도하라."
            message_placeholder.markdown(error_msg)
            _add_message(ChatConfig.ROLE_ASSISTANT, error_msg)
            return

        # 응답 표시
        _display_response_with_streaming(response, message_placeholder)

        # 응답 시간 표시
        st.caption(f"⏱️ 응답 시간: {total_elapsed:.2f}초")

        # Evidence 표시
        if response.get("evidence") and st.session_state.chat_options.get("show_evidence", True):
            current_msg_idx = len(st.session_state.messages)
            display_evidence_section(response["evidence"], current_msg_idx)

        # 유사 문서 추천 표시
        if response.get("similar_documents"):
            current_msg_idx = len(st.session_state.messages)
            display_similar_documents_section(response["similar_documents"], current_msg_idx)

        # 진단 패널
        if DIAG_RAG and response.get("diagnostics"):
            _display_diagnostics_panel(response["diagnostics"])

        # Evidence 히스토리 업데이트
        if response.get("evidence"):
            _update_evidence_history(response["evidence"])

        # 메시지 저장
        _add_message(
            ChatConfig.ROLE_ASSISTANT,
            response["text"],
            evidence=response.get("evidence"),
            similar_documents=response.get("similar_documents"),
        )

    # 5. UI 구분선
    st.markdown(ChatConfig.DIVIDER)
