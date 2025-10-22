#!/usr/bin/env python3
"""
ChatGPT 스타일 채팅 UI - Channel A MEDIATECH RAG 시스템
"""

import streamlit as st
from datetime import datetime
from pathlib import Path
import time
import json

# RAG 시스템 import
from quick_fix_rag import QuickFixRAG

# 페이지 설정
st.set_page_config(
    page_title="Channel A RAG Chat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일 - ChatGPT 스타일 말풍선
st.markdown("""
<style>
    /* 전체 배경 */
    .main {
        background-color: #ffffff;
    }

    /* 채팅 컨테이너 */
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }

    /* 메시지 공통 */
    .message {
        margin-bottom: 20px;
        display: flex;
        align-items: flex-start;
        animation: fadeIn 0.3s ease-in;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* 사용자 메시지 (오른쪽) */
    .user-message {
        justify-content: flex-end;
    }

    .user-bubble {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 12px 18px;
        border-radius: 18px 18px 4px 18px;
        max-width: 70%;
        word-wrap: break-word;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
    }

    /* 어시스턴트 메시지 (왼쪽) */
    .assistant-message {
        justify-content: flex-start;
    }

    .assistant-bubble {
        background: #f7f7f8;
        color: #374151;
        padding: 12px 18px;
        border-radius: 18px 18px 18px 4px;
        max-width: 70%;
        word-wrap: break-word;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        border: 1px solid #e5e7eb;
    }

    /* 시스템 메시지 */
    .system-message {
        text-align: center;
        color: #9ca3af;
        font-size: 0.85em;
        margin: 30px 0;
    }

    /* 타임스탬프 */
    .timestamp {
        font-size: 0.75em;
        color: #9ca3af;
        margin-top: 4px;
        text-align: right;
    }

    /* 소스 문서 */
    .source-docs {
        margin-top: 12px;
        padding: 10px;
        background: #fefce8;
        border-left: 3px solid #eab308;
        border-radius: 6px;
        font-size: 0.85em;
    }

    .source-doc-item {
        padding: 6px 0;
        border-bottom: 1px solid #fef9c3;
    }

    .source-doc-item:last-child {
        border-bottom: none;
    }

    /* 입력창 */
    .stTextInput > div > div > input {
        border-radius: 24px;
        padding: 12px 20px;
        border: 2px solid #e5e7eb;
        font-size: 0.95em;
    }

    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }

    /* 버튼 */
    .stButton > button {
        border-radius: 20px;
        padding: 8px 24px;
        font-weight: 500;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }

    /* 로딩 애니메이션 */
    .loading-dots {
        display: inline-block;
    }

    .loading-dots::after {
        content: '.';
        animation: dots 1.5s steps(4, end) infinite;
    }

    @keyframes dots {
        0%, 20% { content: '.'; }
        40% { content: '..'; }
        60%, 100% { content: '...'; }
    }
</style>
""", unsafe_allow_html=True)


# 세션 상태 초기화
def init_session_state():
    """세션 상태 초기화"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
        # 환영 메시지
        st.session_state.messages.append({
            'role': 'system',
            'content': '안녕하세요! 📚 Channel A 기술관리팀 문서 검색 시스템입니다.\n궁금하신 내용을 질문해주세요.',
            'timestamp': datetime.now()
        })

    if 'rag' not in st.session_state:
        with st.spinner('🔧 RAG 시스템 초기화 중...'):
            st.session_state.rag = QuickFixRAG()

    if 'session_id' not in st.session_state:
        st.session_state.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')


def display_message(message):
    """메시지 표시 (말풍선 스타일)"""
    role = message['role']
    content = message['content']
    timestamp = message.get('timestamp', datetime.now())
    sources = message.get('sources', [])

    if role == 'system':
        st.markdown(f'<div class="system-message">💬 {content}</div>', unsafe_allow_html=True)

    elif role == 'user':
        st.markdown(f'''
        <div class="message user-message">
            <div class="user-bubble">
                {content}
                <div class="timestamp">{timestamp.strftime('%H:%M')}</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    elif role == 'assistant':
        # 소스 문서 HTML 생성
        sources_html = ""
        if sources:
            sources_html = '<div class="source-docs">📄 <strong>참고 문서:</strong><br>'
            for i, source in enumerate(sources[:3], 1):
                sources_html += f'''
                <div class="source-doc-item">
                    <strong>{i}. {source.get('filename', 'Unknown')}</strong><br>
                    <small>점수: {source.get('score', 0):.2f} | 날짜: {source.get('date', 'N/A')}</small>
                </div>
                '''
            sources_html += '</div>'

        st.markdown(f'''
        <div class="message assistant-message">
            <div class="assistant-bubble">
                {content}
                <div class="timestamp">{timestamp.strftime('%H:%M')}</div>
                {sources_html}
            </div>
        </div>
        ''', unsafe_allow_html=True)


def stream_response(response_text):
    """응답 스트리밍 효과 (토큰 단위)"""
    words = response_text.split()
    streamed_text = ""
    placeholder = st.empty()

    for i, word in enumerate(words):
        streamed_text += word + " "

        # 말풍선 형태로 표시
        placeholder.markdown(f'''
        <div class="message assistant-message">
            <div class="assistant-bubble">
                {streamed_text}<span class="loading-dots"></span>
            </div>
        </div>
        ''', unsafe_allow_html=True)

        # 단어마다 약간의 딜레이 (자연스러운 타이핑 효과)
        time.sleep(0.03)

    # 최종 메시지 (로딩 애니메이션 제거)
    placeholder.markdown(f'''
    <div class="message assistant-message">
        <div class="assistant-bubble">
            {streamed_text}
        </div>
    </div>
    ''', unsafe_allow_html=True)

    return streamed_text.strip()


def save_chat_session():
    """채팅 세션 저장"""
    session_dir = Path("chat_sessions")
    session_dir.mkdir(exist_ok=True)

    session_file = session_dir / f"{st.session_state.session_id}.json"

    # 메시지를 JSON 직렬화 가능한 형태로 변환
    messages_to_save = []
    for msg in st.session_state.messages:
        msg_copy = msg.copy()
        msg_copy['timestamp'] = msg_copy['timestamp'].isoformat()
        messages_to_save.append(msg_copy)

    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(messages_to_save, f, ensure_ascii=False, indent=2)

    return session_file


def load_chat_session(session_file):
    """채팅 세션 불러오기"""
    with open(session_file, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    # timestamp를 datetime으로 변환
    for msg in messages:
        msg['timestamp'] = datetime.fromisoformat(msg['timestamp'])

    st.session_state.messages = messages
    st.session_state.session_id = Path(session_file).stem


def main():
    """메인 함수"""
    init_session_state()

    # 사이드바
    with st.sidebar:
        st.title("💬 채팅 세션")

        # 새 대화 시작
        if st.button("🆕 새 대화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
            st.session_state.messages.append({
                'role': 'system',
                'content': '새로운 대화를 시작합니다. 무엇을 도와드릴까요?',
                'timestamp': datetime.now()
            })
            st.rerun()

        # 현재 세션 저장
        if st.button("💾 대화 저장", use_container_width=True):
            saved_file = save_chat_session()
            st.success(f"✅ 저장 완료: {saved_file.name}")

        st.divider()

        # 저장된 세션 목록
        st.subheader("📂 저장된 대화")
        session_dir = Path("chat_sessions")
        if session_dir.exists():
            session_files = sorted(session_dir.glob("*.json"), reverse=True)

            for session_file in session_files[:10]:  # 최근 10개만
                session_name = session_file.stem
                session_time = datetime.strptime(session_name, '%Y%m%d_%H%M%S')

                if st.button(
                    f"📅 {session_time.strftime('%Y-%m-%d %H:%M')}",
                    key=f"load_{session_name}",
                    use_container_width=True
                ):
                    load_chat_session(session_file)
                    st.rerun()

        st.divider()

        # 시스템 정보
        st.subheader("ℹ️ 시스템 정보")
        st.caption(f"**세션 ID:** {st.session_state.session_id}")
        st.caption(f"**메시지 수:** {len(st.session_state.messages)}")
        st.caption(f"**문서 수:** 812개")
        st.caption(f"**기안자 추출:** 327개")

    # 메인 채팅 영역
    st.title("🌐 Channel A MEDIATECH RAG Chat")
    st.caption("기술관리팀 문서 검색 및 AI 답변 시스템")

    st.divider()

    # 채팅 메시지 표시
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages:
            display_message(message)

    # 입력창 (하단 고정)
    st.divider()

    col1, col2 = st.columns([6, 1])

    with col1:
        user_input = st.text_input(
            "메시지를 입력하세요...",
            key="user_input",
            label_visibility="collapsed",
            placeholder="질문을 입력하세요 (예: 카메라 수리 관련 문서, 기안자 남준수)"
        )

    with col2:
        send_button = st.button("전송 ➤", use_container_width=True, type="primary")

    # 메시지 전송 처리
    if send_button and user_input:
        # 사용자 메시지 추가
        st.session_state.messages.append({
            'role': 'user',
            'content': user_input,
            'timestamp': datetime.now()
        })

        # RAG 응답 생성
        with st.spinner('🤔 답변 생성 중...'):
            try:
                # QuickFixRAG를 사용한 검색
                response = st.session_state.rag.answer(user_input)

                # 어시스턴트 메시지 추가
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': response,
                    'timestamp': datetime.now(),
                    'sources': []  # TODO: 실제 소스 문서 추가
                })

            except Exception as e:
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': f"❌ 오류가 발생했습니다: {str(e)}",
                    'timestamp': datetime.now()
                })

        # 페이지 새로고침
        st.rerun()


if __name__ == "__main__":
    main()
