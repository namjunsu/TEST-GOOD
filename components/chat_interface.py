"""
Chat Interface Component
ChatGPT 스타일의 채팅 인터페이스 UI를 렌더링하는 컴포넌트
"""

import streamlit as st
from typing import Any


def render_chat_interface(unified_rag_instance: Any) -> None:
    """채팅 인터페이스 렌더링

    Args:
        unified_rag_instance: UnifiedRAG 시스템 인스턴스 (st.session_state.unified_rag)
    """
    # ===== ChatGPT 스타일 채팅 인터페이스 =====

    # 세션 상태 초기화
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # 기존 대화 표시 (Streamlit native chat)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 채팅 입력창 (하단 고정)
    if prompt := st.chat_input("💬 무엇을 도와드릴까요? (예: 중계차 보수건 내용 요약해줘)"):
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답 생성 및 표시
        with st.chat_message("assistant"):
            message_placeholder = st.empty()

            # 대화 맥락 구성 (최근 3개 대화)
            context = ""
            if len(st.session_state.messages) > 1:
                recent_messages = st.session_state.messages[-6:-1]  # 최근 3턴 (6개 메시지)
                for msg in recent_messages:
                    role = "사용자" if msg["role"] == "user" else "AI"
                    context += f"{role}: {msg['content']}\n"

            # 맥락을 포함한 쿼리
            enhanced_query = f"{context}\n현재 질문: {prompt}" if context else prompt

            # 검색 및 응답 생성
            with st.spinner("생각 중..."):
                try:
                    # UnifiedRAG 사용 (이미 맥락 관리 기능 있음)
                    response = unified_rag_instance.answer(enhanced_query)

                    # 응답 표시
                    message_placeholder.markdown(response)

                    # 메시지 저장
                    st.session_state.messages.append({"role": "assistant", "content": response})

                except Exception as e:
                    error_msg = f"죄송합니다. 오류가 발생했습니다: {str(e)}"
                    message_placeholder.markdown(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

    st.markdown("---")
