"""
Chat Helper Functions
채팅 인터페이스를 위한 헬퍼 함수들

책임:
- RAG 응답 정규화
- 대화 컨텍스트 구성
- Evidence 매칭 알고리즘
- 에러 핸들링
- 입력 검증
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import Any, Literal

from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# 상수
# ============================================================================

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

# 제한값 (2025-12-21: 대화 컨텍스트 확장)
MAX_MESSAGES = 100
MAX_CONTEXT_TURNS = 5  # 3 → 5 (더 긴 대화 맥락 유지)
MAX_MESSAGE_LENGTH = 10000
MAX_CONTEXT_LENGTH = 1500  # 500 → 1500 (턴당 더 많은 컨텍스트)

# Evidence 매칭
MATCH_THRESHOLD = 0.3

# 역할
ROLE_USER: Literal["user"] = "user"
ROLE_ASSISTANT: Literal["assistant"] = "assistant"
ROLE_DISPLAY_USER = "사용자"
ROLE_DISPLAY_ASSISTANT = "AI"


# ============================================================================
# 로깅
# ============================================================================


def log_query_to_terminal(query: str, client_ip: str = "local") -> None:
    """터미널에 질문 로그 출력 (간단한 형식)"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    query_short = query[:50] + "..." if len(query) > 50 else query
    try:
        print(
            f'\033[0;90m[{timestamp}]\033[0m \033[0;36m{client_ip}\033[0m → "{query_short}"',
            file=sys.stderr,
            flush=True,
        )
    except BrokenPipeError:
        pass  # Streamlit 재시작 시 무시


# ============================================================================
# RAG 응답 정규화
# ============================================================================


def normalize_rag_response(resp: Any) -> dict:
    """RAG 응답을 안전하게 dict로 정규화

    RAG Pipeline이 반환할 수 있는 다양한 타입(객체, dict, str)을
    통일된 dict 형식으로 변환합니다.

    Args:
        resp: RAG Pipeline의 응답

    Returns:
        dict: {
            "text": str,
            "evidence": list,
            "status": dict,
            "diagnostics": dict,
            "similar_documents": list
        }
    """
    empty_response = {
        "text": "",
        "evidence": [],
        "status": {},
        "diagnostics": {},
        "similar_documents": [],
    }

    if resp is None:
        logger.warning("Received None response from RAG")
        return empty_response

    if isinstance(resp, str):
        return {**empty_response, "text": resp}

    # 객체인 경우 (RAGResponse 등)
    if hasattr(resp, "text") or hasattr(resp, "answer"):
        text = getattr(resp, "text", None) or getattr(resp, "answer", "")
        evidence = (
            getattr(resp, "evidence", None)
            or getattr(resp, "evidences", None)
            or getattr(resp, "sources", None)
            or getattr(resp, "sources_cited", None)
            or []
        )
        return {
            "text": str(text),
            "evidence": evidence,
            "status": getattr(resp, "status", {}),
            "diagnostics": getattr(resp, "diagnostics", {}),
            "similar_documents": getattr(resp, "similar_documents", []) or [],
        }

    # dict인 경우
    if isinstance(resp, dict):
        text = resp.get("text") or resp.get("answer", "")
        evidence = (
            resp.get("evidence")
            or resp.get("evidences")
            or resp.get("sources")
            or resp.get("sources_cited")
            or []
        )
        return {
            "text": str(text),
            "evidence": evidence,
            "status": resp.get("status", {}),
            "diagnostics": resp.get("diagnostics", {}),
            "similar_documents": resp.get("similar_documents") or [],
        }

    logger.warning(f"Unknown response type: {type(resp)}")
    return {**empty_response, "text": str(resp)}


# ============================================================================
# 메시지 검증
# ============================================================================


def validate_message_structure(message: Any) -> bool:
    """메시지 구조 검증

    Args:
        message: 검증할 메시지 객체

    Returns:
        bool: 유효한 메시지 구조면 True
    """
    if not isinstance(message, dict):
        return False

    required_keys = {"role", "content"}
    if not required_keys.issubset(message.keys()):
        return False

    if message["role"] not in (ROLE_USER, ROLE_ASSISTANT):
        return False

    if not isinstance(message["content"], str):
        return False

    return True


def validate_input(prompt: str) -> tuple[bool, str | None]:
    """사용자 입력 검증

    Args:
        prompt: 사용자 입력 문자열

    Returns:
        tuple[bool, str | None]: (유효성, 에러 메시지)
    """
    if not prompt or not prompt.strip():
        return False, "입력이 비어있습니다."

    if len(prompt) > MAX_MESSAGE_LENGTH:
        return False, ERROR_INVALID_INPUT

    return True, None


# ============================================================================
# 대화 컨텍스트
# ============================================================================


def build_conversation_context(
    messages: list[dict[str, str]],
    max_turns: int = MAX_CONTEXT_TURNS,
) -> str:
    """대화 맥락 구성

    최근 N개 턴의 대화를 문자열로 변환하여 컨텍스트를 구성합니다.

    Args:
        messages: 전체 메시지 리스트
        max_turns: 포함할 최대 대화 턴 수

    Returns:
        str: 구성된 컨텍스트 문자열
    """
    if len(messages) < 2:
        return ""

    max_messages = max_turns * 2
    recent_messages = messages[-(max_messages + 1) : -1]

    context_parts: list[str] = []

    for msg in recent_messages:
        if not validate_message_structure(msg):
            logger.warning(f"Invalid message structure in context: {msg}")
            continue

        role = msg["role"]
        display_role = ROLE_DISPLAY_USER if role == ROLE_USER else ROLE_DISPLAY_ASSISTANT
        content = msg["content"]

        # AI 응답이 너무 길면 요약
        if role == ROLE_ASSISTANT and len(content) > MAX_CONTEXT_LENGTH:
            if "관련 문서" in content and "건)" in content:
                match = re.search(r"\((\d+)건\)", content)
                if match:
                    doc_count = match.group(1)
                    content = f"(이전 응답: {doc_count}건의 문서 리스트 제공됨)"
                else:
                    content = "(이전 응답: 문서 리스트 제공됨 - 생략)"
            else:
                content = content[:MAX_CONTEXT_LENGTH] + "...(생략)"

        context_parts.append(f"{display_role}: {content}")

    if not context_parts:
        return ""

    return "\n".join(context_parts)


def create_enhanced_query(context: str, prompt: str) -> str:
    """컨텍스트를 포함한 향상된 쿼리 생성

    Args:
        context: 이전 대화 컨텍스트
        prompt: 현재 사용자 질문

    Returns:
        str: 향상된 쿼리 문자열
    """
    if context:
        return f"{CONTEXT_PREFIX}\n{context}\n\n{CURRENT_QUERY_PREFIX} {prompt}"
    return prompt


# ============================================================================
# Evidence 매칭
# ============================================================================


def match_query_to_evidence(
    query: str,
    evidence_history: list,
) -> tuple[str | None, float]:
    """쿼리에서 언급된 문서명과 evidence_history 매칭

    사용자가 이전 검색 결과에서 특정 문서를 언급했을 때,
    evidence_history에서 가장 유사한 문서를 찾습니다.

    Args:
        query: 사용자 쿼리
        evidence_history: 이전 검색 결과 목록

    Returns:
        tuple[str | None, float]: (매칭된 파일명, 신뢰도 점수 0.0~1.0)
    """
    if not evidence_history:
        return None, 0.0

    # 후속 질문 패턴 감지
    follow_up_patterns = [
        "뒤에", "나머지", "더 보여", "더 알려", "계속", "이어서",
        "다음", "그 문서", "그거", "그 내용", "방금", "아까",
        "짤린", "잘린", "끊긴", "안 보이", "안보이",
    ]
    query_lower = query.lower()

    if any(p in query_lower for p in follow_up_patterns):
        latest = evidence_history[-1]
        if isinstance(latest, dict) and latest.get("filename"):
            logger.info(f"후속 질문 감지, 최근 문서 사용: {latest['filename']}")
            return latest["filename"], 0.8

    # 쿼리 정규화
    query_clean = query.lower()
    query_clean = re.sub(r"[&_\-\.]", " ", query_clean)
    query_clean = re.sub(r"\s+", " ", query_clean).strip()
    query_tokens = set(query_clean.split())

    # 불용어 제거
    stopwords = {"이", "그", "저", "문서", "파일", "좀", "요약", "내용", "보여줘", "알려줘", "해줘"}
    query_tokens = query_tokens - stopwords

    if not query_tokens:
        return None, 0.0

    best_match: str | None = None
    best_score = 0.0

    for ev in evidence_history:
        if not isinstance(ev, dict):
            continue

        filename = ev.get("filename", "")
        if not filename:
            continue

        # 파일명 정규화
        filename_clean = filename.lower()
        filename_clean = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", filename_clean)
        filename_clean = re.sub(r"\.pdf$", "", filename_clean)
        filename_clean = re.sub(r"[_\-]", " ", filename_clean)
        filename_clean = re.sub(r"\s+", " ", filename_clean).strip()
        filename_tokens = set(filename_clean.split())

        common_tokens = query_tokens & filename_tokens
        if not common_tokens:
            continue

        # Jaccard 유사도
        union_tokens = query_tokens | filename_tokens
        jaccard_score = len(common_tokens) / len(union_tokens) if union_tokens else 0.0

        # 쿼리 토큰 커버리지
        coverage_score = len(common_tokens) / len(query_tokens) if query_tokens else 0.0

        # 연속 토큰 보너스
        phrase_bonus = 0.0
        query_words = query_clean.split()
        for n in [3, 2]:
            for i in range(len(query_words) - n + 1):
                phrase = " ".join(query_words[i : i + n])
                if phrase in filename_clean:
                    phrase_bonus += n * 0.1

        final_score = (jaccard_score * 0.3) + (coverage_score * 0.5) + min(phrase_bonus, 0.2)

        if final_score > best_score:
            best_score = final_score
            best_match = filename

    if best_score < MATCH_THRESHOLD:
        return None, best_score

    logger.info(f"Evidence 매칭: '{best_match}' (score={best_score:.2f})")
    return best_match, best_score


# ============================================================================
# 메시지 관리
# ============================================================================


def cleanup_old_messages(messages: list) -> list:
    """오래된 메시지 정리

    Args:
        messages: 전체 메시지 리스트

    Returns:
        list: 정리된 메시지 리스트
    """
    if len(messages) > MAX_MESSAGES:
        removed_count = len(messages) - MAX_MESSAGES
        logger.warning(f"Message limit exceeded. Removing {removed_count} old messages.")
        return messages[-MAX_MESSAGES:]
    return messages


def export_history_json(messages: list) -> str:
    """대화 기록을 JSON 형식으로 내보내기

    Args:
        messages: 메시지 리스트

    Returns:
        str: JSON 형식의 대화 기록
    """
    return json.dumps(messages, ensure_ascii=False, indent=2)


# ============================================================================
# 에러 핸들링
# ============================================================================


def handle_error(error: Exception) -> dict:
    """예외 타입별 에러 메시지 생성

    Args:
        error: 발생한 예외 객체

    Returns:
        dict: {"message": str, "details": str, "error_type": str}
    """
    error_type = type(error).__name__
    error_msg = str(error)

    logger.error(f"Chat error occurred: {error_type} - {error_msg}", exc_info=True)

    error_map = {
        TimeoutError: (ERROR_TIMEOUT, "요청 처리 시간이 초과됐다."),
        MemoryError: (ERROR_MEMORY, "사용 가능한 메모리가 부족하다."),
        ConnectionError: (ERROR_NETWORK, "네트워크 연결에 문제가 발생했다."),
        AttributeError: (ERROR_INITIALIZATION, "시스템 초기화에 문제가 있다."),
        KeyError: (ERROR_GENERIC, "메시지 구조에 문제가 발생했다."),
    }

    for error_class, (user_msg, details) in error_map.items():
        if isinstance(error, error_class):
            return {
                "message": user_msg,
                "details": details,
                "error_type": error_type,
            }

    return {
        "message": ERROR_GENERIC,
        "details": "예상치 못한 오류가 발생했다.",
        "error_type": error_type,
    }
