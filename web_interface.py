"""
Professional RAG System Web Interface
프로페셔널 RAG 시스템 웹 인터페이스
"""

import streamlit as st
import time
from datetime import datetime
from rag_core import create_rag_engine
from log_system import ChatLogger

# 페이지 설정
st.set_page_config(
    page_title="AI-CHAT RAG System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 로거 초기화
logger = ChatLogger()

# CSS 스타일
st.markdown("""
<style>
    /* 메인 컨테이너 */
    .main > div {
        padding-top: 1rem;
    }

    /* 사이드바 */
    .css-1d391kg {
        padding-top: 1rem;
    }

    /* 메트릭 카드 */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    [data-testid="metric-container"] > div {
        color: white !important;
    }

    /* 입력 필드 */
    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #e2e8f0;
        padding: 10px;
    }

    /* 버튼 */
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        padding: 0.5rem 2rem;
        border: none;
        font-weight: bold;
    }

    .stButton > button:hover {
        background: linear-gradient(90deg, #5a67d8 0%, #6b4199 100%);
    }

    /* 답변 박스 */
    .answer-box {
        background: #f7fafc;
        border-left: 4px solid #667eea;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
    }

    /* 소스 박스 */
    .source-box {
        background: white;
        border: 1px solid #e2e8f0;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def initialize_rag_system():
    """RAG 시스템 초기화 - 한 번만 실행"""
    with st.spinner("🤖 AI 모델 초기화 중..."):
        try:
            rag = create_rag_engine()

            # 문서 인덱싱
            with st.spinner("📚 문서 인덱싱 중..."):
                start_time = time.time()
                results = rag.index_documents('docs')
                elapsed = time.time() - start_time

                st.success(f"✅ 초기화 완료! ({results['processed']}개 문서, {elapsed:.1f}초)")

            return rag
        except Exception as e:
            st.error(f"❌ 시스템 초기화 실패: {e}")
            return None


def main():
    # 헤더
    st.title("🤖 AI-CHAT RAG System")
    st.markdown("### 프로페셔널 문서 검색 및 질의응답 시스템")

    # RAG 시스템 초기화
    if 'rag_instance' not in st.session_state:
        st.session_state.rag_instance = initialize_rag_system()

    if not st.session_state.rag_instance:
        st.error("시스템을 초기화할 수 없습니다.")
        return

    rag = st.session_state.rag_instance

    # 사이드바
    with st.sidebar:
        st.header("📊 시스템 상태")

        # 시스템 통계
        if hasattr(rag, 'documents'):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("문서", f"{len(rag.documents)}")
            with col2:
                st.metric("청크", f"{len(rag.chunks)}")

        st.divider()

        # 문서 목록
        st.header("📂 문서 라이브러리")

        if hasattr(rag, 'documents'):
            # 연도별 그룹화
            docs_by_year = {}
            for doc in rag.documents.values():
                year = doc.metadata.get('year', '기타')
                if year not in docs_by_year:
                    docs_by_year[year] = []
                docs_by_year[year].append(doc.metadata.get('filename', '알 수 없음'))

            # 연도별 표시
            for year in sorted(docs_by_year.keys(), reverse=True):
                with st.expander(f"📅 {year}년 ({len(docs_by_year[year])}개)"):
                    for filename in sorted(docs_by_year[year]):
                        st.text(f"📄 {filename[:40]}...")

        st.divider()

        # 설정
        st.header("⚙️ 설정")
        top_k = st.slider("검색 결과 수", 1, 10, 5)

    # 메인 영역
    # 검색 영역
    st.header("🔍 문서 검색")

    col1, col2 = st.columns([5, 1])
    with col1:
        query = st.text_input(
            "질문을 입력하세요",
            placeholder="예: 2020년 중계차 구매 내역을 알려주세요",
            key="query_input"
        )
    with col2:
        search_button = st.button("검색", type="primary", use_container_width=True)

    # 검색 처리
    if search_button and query:
        with st.spinner("🔍 검색 중..."):
            start_time = time.time()

            try:
                # RAG 시스템으로 질의
                result = rag.query(query)
                elapsed = time.time() - start_time

                # 답변 표시
                st.markdown("### 💡 답변")
                st.markdown(f'<div class="answer-box">{result["answer"]}</div>', unsafe_allow_html=True)

                # 출처 표시
                if result.get('sources'):
                    st.markdown("### 📚 참고 문서")
                    for i, source in enumerate(result['sources'], 1):
                        with st.expander(f"📄 출처 {i}: {source.get('filename', '알 수 없음')}"):
                            st.write(f"**파일**: {source.get('filename', '알 수 없음')}")
                            if source.get('year'):
                                st.write(f"**연도**: {source.get('year')}")
                            if source.get('category'):
                                st.write(f"**카테고리**: {source.get('category')}")

                # 성능 메트릭
                st.divider()
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("응답 시간", f"{elapsed:.2f}초")
                with col2:
                    st.metric("검색 문서", f"{len(result.get('sources', []))}개")
                with col3:
                    st.metric("신뢰도", "높음")

                # 로그 저장
                logger.log_query(query, result['answer'], elapsed)

            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")
                logger.log_error(f"Query failed: {query}", str(e))

    # 예시 질문
    st.divider()
    st.subheader("💭 예시 질문")

    example_queries = [
        "2020년 중계차 관련 문서를 찾아주세요",
        "카메라 구매 내역을 요약해주세요",
        "최근 3년간 장비 구매 현황은?",
        "방송 장비 수리 이력을 알려주세요"
    ]

    cols = st.columns(2)
    for i, example in enumerate(example_queries):
        with cols[i % 2]:
            if st.button(example, key=f"example_{i}"):
                st.session_state.query_input = example
                st.rerun()

    # 푸터
    st.divider()
    st.markdown(
        """
        <div style='text-align: center; color: #718096; padding: 20px;'>
            Professional RAG System v2.0 |
            <a href='#' style='color: #667eea;'>문서</a> |
            <a href='#' style='color: #667eea;'>도움말</a>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()