#!/usr/bin/env python3
"""
최적화된 웹 인터페이스
=====================

Lazy Loading과 메모리 최적화를 적용한 버전입니다.
시작 시간: 7-10초 → 2초 목표
"""

import os
import sys
import time
import logging
import gc
import streamlit as st
from pathlib import Path
from typing import Optional, Dict, Any

# 시작 시간 측정
startup_start = time.time()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 메모리 최적화 환경 설정
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:512'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['CUDA_MODULE_LOADING'] = 'LAZY'

# Lazy imports (필요시에만 로드)
class LazyImports:
    def __init__(self):
        self._perfect_rag = None
        self._auto_indexer = None
        self._memory_optimizer = None

    @property
    def perfect_rag(self):
        if self._perfect_rag is None:
            logger.info("Loading PerfectRAG module...")
            from perfect_rag import PerfectRAG
            self._perfect_rag = PerfectRAG
        return self._perfect_rag

    @property
    def auto_indexer(self):
        if self._auto_indexer is None:
            logger.info("Loading AutoIndexer module...")
            from auto_indexer import AutoIndexer
            self._auto_indexer = AutoIndexer
        return self._auto_indexer

    @property
    def memory_optimizer(self):
        if self._memory_optimizer is None:
            logger.info("Loading MemoryOptimizer...")
            from memory_optimizer import MemoryOptimizer
            self._memory_optimizer = MemoryOptimizer()
        return self._memory_optimizer

# Lazy imports 인스턴스
lazy = LazyImports()

# Streamlit 페이지 설정 (빠른 UI 표시)
st.set_page_config(
    page_title="AI-CHAT RAG (최적화)",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'About': "AI-CHAT RAG System - 최적화 버전"
    }
)

# CSS 스타일 (최소화)
st.markdown("""
<style>
    .main { padding: 0; }
    .block-container { padding: 1rem 2rem; }
    div[data-testid="stSidebar"] { background: #f0f2f6; }
    .stButton>button { background: #ff4b4b; color: white; }
    .stTextInput>div>div>input { font-size: 16px; }
</style>
""", unsafe_allow_html=True)


def initialize_session():
    """세션 상태 초기화 (최소한만)"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = False
        st.session_state.rag_instance = None
        st.session_state.auto_indexer = None
        st.session_state.query_count = 0
        st.session_state.cache_hits = 0
        st.session_state.loading_progress = 0

def load_rag_async():
    """백그라운드에서 RAG 시스템 로드"""
    if st.session_state.rag_instance is None:
        with st.spinner("🚀 시스템 초기화 중... (최적화 모드)"):
            progress = st.progress(0)
            status = st.empty()

            try:
                # 1. 메모리 최적화 적용
                status.text("메모리 최적화 중...")
                lazy.memory_optimizer.cleanup_memory()
                progress.progress(20)

                # 2. RAG 인스턴스 생성
                status.text("RAG 엔진 로딩...")
                PerfectRAG = lazy.perfect_rag
                st.session_state.rag_instance = PerfectRAG()
                progress.progress(60)

                # 3. Auto Indexer (백그라운드)
                status.text("자동 인덱서 시작...")
                AutoIndexer = lazy.auto_indexer
                st.session_state.auto_indexer = AutoIndexer(
                    st.session_state.rag_instance,
                    watch_dir="docs",
                    check_interval=60
                )
                st.session_state.auto_indexer.start_watching()
                progress.progress(100)

                # 완료
                status.text("✅ 시스템 준비 완료!")
                time.sleep(0.5)
                progress.empty()
                status.empty()

                st.session_state.initialized = True
                logger.info("RAG system initialized successfully")

            except Exception as e:
                st.error(f"시스템 초기화 실패: {e}")
                logger.error(f"Initialization failed: {e}")
                return False

    return True

def main():
    """메인 인터페이스"""

    # 헤더 (즉시 표시)
    st.title("🚀 AI-CHAT RAG System")
    st.caption("최적화 버전 - 빠른 시작, 낮은 메모리")

    # 세션 초기화
    initialize_session()

    # 탭 생성 (간소화)
    tab1, tab2, tab3 = st.tabs(["💬 검색", "📊 상태", "⚙️ 설정"])

    with tab1:
        # 검색 UI
        col1, col2 = st.columns([5, 1])

        with col1:
            query = st.text_input(
                "검색어를 입력하세요",
                placeholder="예: 2024년 장비 구매 계획",
                key="search_query"
            )

        with col2:
            search_mode = st.selectbox(
                "모드",
                ["문서", "자산"],
                key="search_mode"
            )

        # 검색 버튼
        if st.button("🔍 검색", type="primary", use_container_width=True):
            if query:
                # RAG 시스템 로드 (처음 검색시)
                if not st.session_state.initialized:
                    if not load_rag_async():
                        return

                # 검색 실행
                with st.spinner("검색 중..."):
                    try:
                        start_time = time.time()

                        # 모드 변환
                        mode = "document" if search_mode == "문서" else "asset"

                        # 검색 수행 (캐시 활용)
                        response = st.session_state.rag_instance.search_and_generate(
                            query,
                            mode=mode,
                            top_k=5,
                            use_cache=True
                        )

                        search_time = time.time() - start_time

                        # 결과 표시
                        st.success(f"✅ 검색 완료 ({search_time:.2f}초)")

                        # 응답 표시
                        with st.container():
                            st.markdown(response)

                        # 통계 업데이트
                        st.session_state.query_count += 1
                        if search_time < 0.5:  # 캐시 히트로 추정
                            st.session_state.cache_hits += 1

                    except Exception as e:
                        st.error(f"검색 오류: {e}")
                        logger.error(f"Search error: {e}")
            else:
                st.warning("검색어를 입력해주세요.")

    with tab2:
        # 시스템 상태
        st.subheader("📊 시스템 상태")

        if st.session_state.initialized:
            # 메모리 상태
            stats = lazy.memory_optimizer.get_optimization_stats()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("메모리 사용", f"{stats['current_memory_gb']:.1f}GB")
                st.metric("GPU 사용", f"{stats['gpu_usage_gb']:.1f}GB")

            with col2:
                st.metric("검색 횟수", st.session_state.query_count)
                hit_rate = (st.session_state.cache_hits / max(1, st.session_state.query_count)) * 100
                st.metric("캐시 적중률", f"{hit_rate:.1f}%")

            with col3:
                startup_time = time.time() - startup_start
                st.metric("시작 시간", f"{startup_time:.1f}초")
                st.metric("메모리 절약", f"{stats['saved_gb']:.1f}GB")

            # 리프레시 버튼
            if st.button("🔄 새로고침"):
                st.rerun()
        else:
            st.info("시스템이 대기 중입니다. 첫 검색 시 자동으로 초기화됩니다.")

    with tab3:
        # 설정
        st.subheader("⚙️ 최적화 설정")

        # 메모리 설정
        with st.expander("메모리 최적화"):
            low_vram = st.checkbox("Low VRAM 모드", value=True)
            max_context = st.slider("최대 컨텍스트", 1024, 8192, 4096, 512)
            batch_size = st.slider("배치 크기", 64, 512, 256, 64)

            if st.button("적용"):
                os.environ['LOW_VRAM'] = str(low_vram)
                os.environ['N_CTX'] = str(max_context)
                os.environ['N_BATCH'] = str(batch_size)
                st.success("설정이 적용되었습니다.")

        # 캐시 관리
        with st.expander("캐시 관리"):
            if st.button("캐시 초기화"):
                if st.session_state.rag_instance:
                    st.session_state.rag_instance.clear_cache()
                    st.session_state.cache_hits = 0
                    st.success("캐시가 초기화되었습니다.")

            if st.button("메모리 정리"):
                gc.collect()
                if lazy._memory_optimizer:
                    lazy.memory_optimizer.cleanup_memory()
                st.success("메모리가 정리되었습니다.")

    # 푸터
    st.markdown("---")
    st.caption(f"🚀 최적화 버전 | 시작 시간: {time.time() - startup_start:.2f}초")


if __name__ == "__main__":
    # 시작 로그
    logger.info(f"Starting optimized web interface...")

    # 메인 실행
    main()

    # 완료 로그
    total_startup = time.time() - startup_start
    logger.info(f"✅ UI ready in {total_startup:.2f}s")

    if total_startup < 3:
        logger.info("🎯 Target achieved! Startup under 3 seconds!")
    else:
        logger.info(f"⚠️  Target missed by {total_startup - 3:.1f}s")