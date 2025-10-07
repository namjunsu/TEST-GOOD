#!/usr/bin/env python3
"""
Channel A RAG 시스템 - ChatGPT 스타일 웹 인터페이스
메인: AI 채팅 인터페이스
사이드바: 문서 검색, 필터링, 관리
"""

import streamlit as st
import pandas as pd
import time
from pathlib import Path
from datetime import datetime
import hashlib
import sys
import warnings
import re
from collections import defaultdict
import base64

# 경고 메시지 억제
warnings.filterwarnings("ignore")

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

import config
from perfect_rag import PerfectRAG
from hybrid_chat_rag import HybridChatRAG

# 페이지 설정
st.set_page_config(
    page_title="Channel A AI Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (ChatGPT 스타일)
st.markdown("""
<style>
    /* 메인 배경 */
    .stApp {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 50%, #0f1419 100%);
        background-attachment: fixed;
    }

    /* 메인 콘텐츠 영역 */
    .main .block-container {
        background: rgba(15, 20, 25, 0.95);
        border-radius: 15px;
        padding: 20px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }

    /* 사이드바 스타일 */
    .sidebar .sidebar-content {
        background: rgba(26, 31, 46, 0.95);
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(255,255,255,0.1);
    }

    /* 채팅 메시지 스타일 */
    .chat-message {
        padding: 15px;
        border-radius: 15px;
        margin: 15px 0;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
    }

    .user-message {
        background: rgba(74, 144, 226, 0.2);
        margin-left: 20%;
        border-color: rgba(74, 144, 226, 0.3);
    }

    .assistant-message {
        background: rgba(26, 31, 46, 0.3);
        margin-right: 20%;
        border-color: rgba(255,255,255,0.1);
    }

    /* 입력창 스타일 */
    .stTextInput > div > div > input {
        background: rgba(26, 31, 46, 0.5);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 25px;
        color: white;
        padding: 12px 20px;
    }

    /* 버튼 스타일 */
    .stButton > button {
        border-radius: 25px;
        border: 1px solid rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
    }

    /* 제목 스타일 */
    h1 {
        text-align: center;
        background: linear-gradient(45deg, #4A90E2, #9C27B0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3em;
        margin-bottom: 0.5em;
    }
</style>
""", unsafe_allow_html=True)

# 문서 로드 함수 (간단 버전)
@st.cache_data(ttl=300)
def load_documents_simple():
    """SQLite에서 직접 문서 메타데이터 로드"""
    import sqlite3

    try:
        conn = sqlite3.connect('everything_index.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT filename, path, date, year, category, department, keywords
            FROM files
            ORDER BY year DESC, filename ASC
        """)

        rows = cursor.fetchall()
        documents = []

        for filename, path, date, year, category, department, keywords in rows:
            # 카테고리 분류
            if '구매' in filename:
                doc_category = "구매"
            elif '수리' in filename:
                doc_category = "수리"
            elif '교체' in filename:
                doc_category = "교체"
            elif '검토' in filename:
                doc_category = "검토"
            else:
                doc_category = category or "기타"

            # 기안자 정보
            drafter = department if department and department not in ['영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출'] else "미확인"

            documents.append({
                'filename': filename,
                'title': filename.replace('.pdf', '').replace('_', ' '),
                'date': date or '날짜없음',
                'year': year or '연도없음',
                'category': doc_category,
                'drafter': drafter,
                'path': path,
                'keywords': keywords or ''
            })

        conn.close()
        return pd.DataFrame(documents)

    except Exception as e:
        print(f"문서 로드 실패: {e}")
        return pd.DataFrame()

# 문서 필터링 함수
def filter_documents(df, query):
    """문서 검색 필터링"""
    if df.empty or not query:
        return df

    query = query.lower()
    mask = (
        df['filename'].str.lower().str.contains(query, na=False) |
        df['title'].str.lower().str.contains(query, na=False) |
        df['drafter'].str.lower().str.contains(query, na=False) |
        df['category'].str.lower().str.contains(query, na=False) |
        df['keywords'].str.lower().str.contains(query, na=False)
    )
    return df[mask]

def main():
    # HybridChatRAG 초기화 (세션 상태로 관리)
    if 'hybrid_chat_rag' not in st.session_state:
        with st.spinner("🤖 AI 채팅 시스템 초기화 중..."):
            st.session_state.hybrid_chat_rag = HybridChatRAG()

    # 대화 기록 초기화
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    # 사이드바 - 문서 검색 및 관리
    with st.sidebar:
        # 로고 표시
        st.markdown("""
        <div style='text-align: center; padding: 20px 0;'>
            <h2 style='color: #4A90E2; margin: 0;'>📚 Channel A</h2>
            <p style='color: #a0a0a0; margin: 5px 0 0 0; font-size: 0.9em;'>Document AI</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # 문서 로드
        df = load_documents_simple()

        # 문서 현황
        st.markdown("### 📊 문서 현황")
        if not df.empty:
            total_docs = len(df)
            recent_docs = len(df[df['year'] >= 2024]) if 'year' in df.columns else 0
            st.info(f"""
            **전체 문서**: {total_docs:,}개
            **최근 문서**: {recent_docs}개 (2024년~)
            """)

        # 빠른 검색
        st.markdown("### 🔍 문서 검색")
        search_query = st.text_input(
            "문서 제목, 기안자, 키워드 검색",
            placeholder="예: 구매, 수리, 남준수",
            key="sidebar_search"
        )

        if search_query:
            filtered_df = filter_documents(df, search_query)
            if not filtered_df.empty:
                st.success(f"🔍 {len(filtered_df)}개 문서 발견")

                # 검색 결과 표시 (간단히)
                for idx, row in filtered_df.head(5).iterrows():
                    if st.button(f"📄 {row['title'][:30]}...", key=f"search_doc_{idx}"):
                        # 문서 정보를 채팅에 자동 입력
                        auto_question = f"{row['filename']} 문서에 대해 분석해줘"
                        st.session_state.auto_question = auto_question
                        st.rerun()
            else:
                st.warning("검색 결과 없음")

        # 연도별 필터
        st.markdown("### 📅 연도별 문서")
        if not df.empty and 'year' in df.columns:
            years = sorted(df['year'].unique(), reverse=True)
            year_counts = df['year'].value_counts().to_dict()

            selected_year = st.selectbox(
                "연도 선택",
                years,
                format_func=lambda x: f"{x}년 ({year_counts.get(x, 0)}개)",
                key="sidebar_year"
            )

            year_df = df[df['year'] == selected_year]
            st.caption(f"{selected_year}년 문서 {len(year_df)}개")

            # 연도별 문서 리스트 (간단히)
            for idx, row in year_df.head(3).iterrows():
                if st.button(f"📄 {row['title'][:25]}...", key=f"year_doc_{idx}"):
                    auto_question = f"{selected_year}년 {row['category']} 관련 문서들을 분석해줘"
                    st.session_state.auto_question = auto_question
                    st.rerun()

        # 주요 기안자
        st.markdown("### 👥 주요 기안자")
        if not df.empty and 'drafter' in df.columns:
            drafter_counts = df['drafter'].value_counts()
            top_drafters = drafter_counts[drafter_counts.index != '미확인'].head(5)

            for drafter, count in top_drafters.items():
                if st.button(f"{drafter} ({count}개)", key=f"drafter_{drafter}"):
                    # 기안자별 검색 수행
                    auto_question = f"기안자 {drafter}가 작성한 문서들의 특징을 분석해줘"
                    st.session_state.auto_question = auto_question
                    st.rerun()

        # 카테고리별 통계
        st.markdown("### 📈 카테고리별")
        if not df.empty and 'category' in df.columns:
            category_counts = df['category'].value_counts().head(5)
            for category, count in category_counts.items():
                if st.button(f"{category} ({count}개)", key=f"cat_{category}"):
                    auto_question = f"{category} 관련 문서들을 요약해줘"
                    st.session_state.auto_question = auto_question
                    st.rerun()

        # 설정
        st.markdown("---")
        st.markdown("### ⚙️ 설정")

        # 응답 모드 기본값
        default_mode = st.selectbox(
            "기본 응답 모드",
            ["🔍 빠른 검색", "🤖 AI 채팅"],
            key="default_mode"
        )

        # 대화 기록 관리
        if st.button("🗑️ 전체 대화 기록 삭제"):
            st.session_state.chat_history = []
            if hasattr(st.session_state.get('hybrid_chat_rag'), 'conversation_history'):
                st.session_state.hybrid_chat_rag.clear_conversation()
            st.success("대화 기록이 삭제되었습니다!")
            st.rerun()

        # 시스템 정보
        st.markdown("---")
        st.markdown("### 🖥️ 시스템 정보")
        st.info(f"""
        **AI 모델**: Qwen2.5-7B
        **문서 수**: {len(df) if not df.empty else 0:,}개
        **대화 수**: {len(st.session_state.chat_history)}개
        """)

    # 메인 영역 - ChatGPT 스타일 채팅 인터페이스

    # 헤더
    st.markdown("""
    <div style='text-align: center; padding: 20px 0 40px 0;'>
        <h1>🤖 Channel A AI</h1>
        <p style='color: #e0e0e0; font-size: 1.2em; margin: 0;'>방송장비 문서 AI 어시스턴트</p>
        <p style='color: #a0a0a0; font-size: 0.9em; margin-top: 5px;'>
            {len(df) if not df.empty else 0:,}개 문서 • 빠른 검색 (0.02초) • AI 분석 (15초)
        </p>
    </div>
    """.format(len(df) if not df.empty else 0), unsafe_allow_html=True)

    # 자동 질문이 있는 경우 처리
    if 'auto_question' in st.session_state:
        auto_q = st.session_state.auto_question
        del st.session_state.auto_question

        # 자동 질문 처리
        with st.spinner("답변을 생성하는 중..."):
            start_time = time.time()

            if st.session_state.get('default_mode', '🔍 빠른 검색') == "🔍 빠른 검색":
                answer = st.session_state.hybrid_chat_rag.search_only(auto_q)
            else:
                answer = st.session_state.hybrid_chat_rag.chat_with_documents(auto_q)

            response_time = time.time() - start_time

            # 대화 기록에 추가
            st.session_state.chat_history.append({
                'question': auto_q,
                'answer': answer,
                'mode': st.session_state.get('default_mode', '🔍 빠른 검색'),
                'time': response_time,
                'timestamp': time.time()
            })

    # 대화 기록 표시 (ChatGPT 스타일)
    chat_container = st.container()

    with chat_container:
        if st.session_state.chat_history:
            for chat in st.session_state.chat_history:
                # 사용자 메시지
                st.markdown(f"""
                <div style='display: flex; justify-content: flex-end; margin: 20px 0;'>
                    <div style='background: rgba(74, 144, 226, 0.15); padding: 15px 20px; border-radius: 20px 20px 5px 20px; max-width: 70%; border: 1px solid rgba(74, 144, 226, 0.3); backdrop-filter: blur(10px);'>
                        <div style='color: #4A90E2; font-weight: bold; margin-bottom: 8px; font-size: 0.9em;'>👤 You</div>
                        <div style='color: #ffffff; line-height: 1.5;'>{chat['question']}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # AI 응답
                mode_emoji = "🔍" if "빠른 검색" in chat['mode'] else "🤖"
                mode_color = "rgba(76, 175, 80, 0.15)" if "빠른 검색" in chat['mode'] else "rgba(156, 39, 176, 0.15)"
                border_color = "rgba(76, 175, 80, 0.3)" if "빠른 검색" in chat['mode'] else "rgba(156, 39, 176, 0.3)"
                mode_title_color = "#4CAF50" if "빠른 검색" in chat['mode'] else "#9C27B0"

                st.markdown(f"""
                <div style='display: flex; justify-content: flex-start; margin: 20px 0;'>
                    <div style='background: {mode_color}; padding: 15px 20px; border-radius: 20px 20px 20px 5px; max-width: 70%; border: 1px solid {border_color}; backdrop-filter: blur(10px);'>
                        <div style='color: {mode_title_color}; font-weight: bold; margin-bottom: 8px; font-size: 0.9em;'>{mode_emoji} Channel A AI</div>
                        <div style='color: #ffffff; line-height: 1.6; white-space: pre-wrap;'>{chat['answer']}</div>
                        <div style='color: #a0a0a0; font-size: 0.8em; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);'>
                            {chat['mode']} • {chat['time']:.2f}초 • {time.strftime('%H:%M', time.localtime(chat['timestamp']))}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            # 환영 메시지
            st.markdown(f"""
            <div style='text-align: center; padding: 60px 20px; margin: 40px 0;'>
                <div style='background: rgba(255,255,255,0.03); padding: 50px; border-radius: 25px; border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(10px);'>
                    <h2 style='color: #ffffff; margin-bottom: 25px; font-size: 2em;'>👋 안녕하세요!</h2>
                    <p style='color: #e0e0e0; font-size: 1.2em; margin-bottom: 35px; line-height: 1.6;'>
                        Channel A 방송장비 문서에 대해 무엇이든 물어보세요.<br>
                        AI가 <strong>{len(df) if not df.empty else 0:,}개</strong>의 문서를 분석하여 정확한 답변을 드립니다.
                    </p>

                    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 40px 0;'>
                        <div style='background: rgba(74, 144, 226, 0.1); padding: 20px; border-radius: 15px; border: 1px solid rgba(74, 144, 226, 0.2); backdrop-filter: blur(5px);'>
                            <div style='color: #4A90E2; font-weight: bold; margin-bottom: 8px; font-size: 1.1em;'>🔍 빠른 검색</div>
                            <div style='color: #a0a0a0; font-size: 0.95em; line-height: 1.4;'>0.02초 만에 즉시 답변<br>패턴 매칭으로 빠른 결과</div>
                        </div>
                        <div style='background: rgba(156, 39, 176, 0.1); padding: 20px; border-radius: 15px; border: 1px solid rgba(156, 39, 176, 0.2); backdrop-filter: blur(5px);'>
                            <div style='color: #9C27B0; font-weight: bold; margin-bottom: 8px; font-size: 1.1em;'>🤖 AI 분석</div>
                            <div style='color: #a0a0a0; font-size: 0.95em; line-height: 1.4;'>15초간 심도있는 분석<br>Qwen2.5-7B로 정확한 해석</div>
                        </div>
                    </div>

                    <div style='margin-top: 30px;'>
                        <p style='color: #a0a0a0; font-size: 0.9em; margin: 0;'>
                            💡 사이드바에서 문서를 클릭하거나 아래에서 직접 질문해보세요!
                        </p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # 하단 고정 입력창 (ChatGPT 스타일)
    st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)  # 간격

    # 입력 영역을 컨테이너로 감싸기
    input_container = st.container()

    with input_container:
        # 질문 입력
        user_input = st.text_input(
            "메시지를 입력하세요...",
            placeholder="예: 2024년 구매한 카메라 장비들을 정리해줘",
            key="chat_input_main",
            label_visibility="collapsed"
        )

        # 입력 옵션과 버튼
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            response_mode = st.radio(
                "응답 모드:",
                ["🔍 빠른 검색", "🤖 AI 채팅"],
                horizontal=True,
                key="chat_response_mode",
                index=0 if st.session_state.get('default_mode', '🔍 빠른 검색') == "🔍 빠른 검색" else 1
            )

        with col2:
            send_button = st.button("📤 전송", type="primary", use_container_width=True)

        with col3:
            clear_button = st.button("🧹 새 대화", use_container_width=True)
            if clear_button:
                st.session_state.chat_history = []
                if hasattr(st.session_state.get('hybrid_chat_rag'), 'conversation_history'):
                    st.session_state.hybrid_chat_rag.clear_conversation()
                st.rerun()

    # 질문 처리
    if (send_button or user_input) and user_input.strip():
        with st.spinner("답변을 생성하는 중..."):
            start_time = time.time()

            if response_mode == "🔍 빠른 검색":
                answer = st.session_state.hybrid_chat_rag.search_only(user_input)
            else:
                answer = st.session_state.hybrid_chat_rag.chat_with_documents(user_input)

            response_time = time.time() - start_time

            # 대화 기록에 추가
            st.session_state.chat_history.append({
                'question': user_input,
                'answer': answer,
                'mode': response_mode,
                'time': response_time,
                'timestamp': time.time()
            })

            # 입력창 비우기
            st.session_state.chat_input_main = ""
            st.rerun()

    # 추천 질문 (대화가 없을 때만 표시)
    if not st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### 💡 추천 질문")

        suggestions = [
            "2024년에 구매한 장비들을 정리해줘",
            "남준수 기안자가 작성한 문서들의 특징은?",
            "카메라 관련 수리 내역을 요약해줘",
            "최근 방송장비 교체 패턴은?",
            "영상장비 구매 예산을 분석해줘",
            "장비 유지보수 주기를 분석해줘"
        ]

        suggestion_cols = st.columns(2)
        for i, suggestion in enumerate(suggestions):
            with suggestion_cols[i % 2]:
                if st.button(suggestion, key=f"suggest_{i}", use_container_width=True):
                    # 추천 질문을 입력창에 설정
                    st.session_state.chat_input_main = suggestion
                    st.rerun()

    # 페이지 하단 여백
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()