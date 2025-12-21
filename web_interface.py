#!/usr/bin/env python3
"""
브로드캐스트 기술관리팀 RAG 시스템 - 웹 인터페이스 (개선 버전)
- 문서 앞에 연도 표시
- 자주 묻는 질문 대신 통계 분석 버튼
- 연도별/월별 구매/수리 통계
"""

import os
import sys
import time
import warnings
from pathlib import Path

import streamlit as st

# 경고 메시지 억제
warnings.filterwarnings("ignore")

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

import app.config.settings as config  # config 모듈 이름으로도 사용 (하위 호환성)
from app.config.settings import settings  # 중앙 설정 객체
from app.rag.pipeline import RAGPipeline  # 파사드 패턴: 단일 진입점
from components.admin_panel import render_admin_panel  # 관리자 패널 컴포넌트
from components.chat_interface import render_chat_interface  # 채팅 인터페이스 컴포넌트
from components.document_preview import render_document_preview  # 문서 미리보기 컴포넌트
from components.sidebar_library import render_sidebar_library  # 사이드바 컴포넌트
from utils.css_loader import load_all_css  # CSS 로더 임포트

# 페이지 설정
st.set_page_config(
    page_title="Channel A MEDIATECH RAG",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS 스타일 적용 (외부 파일에서 로드: main.css + sidebar.css)
load_all_css()


@st.cache_data(ttl=60)
def count_docs_recursive(base_dir: str) -> tuple[int, int]:
    """문서 수 재귀 스캔 (하위 폴더 포함, 60초 캐싱)"""
    base = Path(base_dir)
    pdf_cnt = sum(1 for _ in base.rglob("*.pdf"))
    txt_cnt = sum(1 for _ in base.rglob("*.txt"))
    return pdf_cnt, txt_cnt


@st.cache_resource
def initialize_rag_system():
    """RAG 시스템 초기화 (한 번만 실행) - RAGPipeline 사용 (파사드 패턴)

    @st.cache_resource 데코레이터를 사용하여 전역적으로 한 번만 초기화하고
    모든 세션에서 동일한 인스턴스를 공유합니다.
    """
    print("🚀 RAGPipeline 초기화 중...")
    pipeline = RAGPipeline()

    # 워밍업: 인덱스 및 모델 사전 로드
    print("⏳ 워밍업 중...")
    pipeline.warmup()
    print("✅ RAGPipeline 준비 완료")

    return pipeline


def main():
    # 로고 및 타이틀 표시
    col1, col2, col3 = st.columns([1, 3, 1])

    with col2:
        # 로고 이미지 표시 (흰색 버전)
        if Path("channel_a_logo_inverted.png").exists():
            st.image("channel_a_logo_inverted.png")
        elif Path("channel_a_logo.png").exists():
            st.image("channel_a_logo.png")

        # 제목
        st.markdown("""
        <h2 style='text-align: center; color: #ffffff; margin-top: 10px; margin-bottom: 5px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);'>
            RAG 도우미
        </h2>
        <p style='text-align: center; color: #e0e0e0; font-size: 14px; margin-top: 0; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);'>
            기술관리팀 방송장비 문서 검색 시스템
        </p>
        """, unsafe_allow_html=True)

    # 구분선
    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.3); margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.2);'>", unsafe_allow_html=True)

    # 문서 개수 동적 계산 (하드코딩 제거)
    pdf_count, txt_count = count_docs_recursive(settings.DOCS_DIR)

    # 현황 표시
    # 자동 인덱싱 시스템 초기화
    if "auto_indexer" not in st.session_state:
        from scripts.utils.auto_indexer import AutoIndexer
        if not getattr(st, "_auto_indexer_started", False):
            st.session_state.auto_indexer = AutoIndexer(check_interval=60)
            st.session_state.auto_indexer.start_monitoring()
            st._auto_indexer_started = True
            st.toast("AutoIndexer 시작됨 (60s 주기)", icon="🧩")

    # RAG 시스템 초기화 (개선된 로딩 화면)
    if "rag" not in st.session_state:
        # 로딩 컨테이너
        loading_container = st.empty()

        with loading_container.container():
            # 로딩 애니메이션
            st.markdown("""
            <div style='text-align: center; padding: 50px;'>
                <h2 style='color: white; margin-bottom: 20px;'>🔄 시스템 초기화 중...</h2>
                <p style='color: #e0e0e0; font-size: 16px;'>
                    AI 모델을 로드하고 있습니다.<br>
                    첫 실행 시 10-20초 정도 소요됩니다.
                </p>
                <div style='margin-top: 30px;'>
                    <div style='display: inline-block; padding: 10px 20px; background: rgba(255,255,255,0.1); border-radius: 10px;'>
                        <p style='color: white; margin: 0;'>📦 로컬 LLM 모델 로드 중...</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 프로그레스 바
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 단계별 로딩 표시 (2025-12-21: 불필요한 sleep 제거)
            status_text.text("📋 문서 메타데이터 로드 중...")
            progress_bar.progress(25)

            status_text.text("🤖 AI 모델 초기화 중...")
            progress_bar.progress(50)

            # 실제 RAG 시스템 초기화
            st.session_state.rag = initialize_rag_system()

            status_text.text("🔍 검색 엔진 준비 중...")
            progress_bar.progress(75)

            status_text.text("✅ 시스템 준비 완료!")
            progress_bar.progress(100)

            # 로딩 컨테이너 비우기
            loading_container.empty()

    # 사이드바 - 문서 라이브러리 + 관리자 모드 토글
    with st.sidebar:
        # 관리자 모드 토글 (사이드바 상단)
        st.divider()
        admin_mode = st.toggle("⚙️ 관리자 모드", value=st.session_state.get("admin_mode", False), key="admin_toggle")
        st.session_state.admin_mode = admin_mode
        st.divider()

        if not admin_mode:
            render_sidebar_library(st.session_state.rag)

    # ===== 관리자 모드 =====
    if st.session_state.get("admin_mode", False):
        render_admin_panel()
        return  # 관리자 모드에서는 채팅 UI 표시 안함

    # ===== 메인 화면: AI 채팅 =====
    # UnifiedRAG 초기화 (자동 모드)
    # 강제 재초기화 (모든 구버전 제거)
    if "hybrid_chat_rag" in st.session_state:
        del st.session_state.hybrid_chat_rag

    # OCR 캐시 업데이트 체크 (파일 수정 시간)
    ocr_cache_path = "docs/.ocr_cache.json"
    if Path(ocr_cache_path).exists():
        ocr_mtime = os.path.getmtime(ocr_cache_path)
        prev_mtime = st.session_state.get("ocr_cache_mtime")

        if prev_mtime is None:
            st.session_state["ocr_cache_mtime"] = ocr_mtime
        elif prev_mtime != ocr_mtime:
            st.session_state["ocr_cache_mtime"] = ocr_mtime
            if "unified_rag" in st.session_state:
                st.session_state.pop("unified_rag", None)
            st.toast("OCR 캐시 갱신 감지 → RAG 재초기화", icon="🔁")

    # 최초 1회만 초기화 (rag와 unified_rag는 동일한 인스턴스)
    if "unified_rag" not in st.session_state:
        st.session_state.unified_rag = st.session_state.rag

    # ===== ChatGPT 스타일 채팅 인터페이스 (컴포넌트) =====
    render_chat_interface(st.session_state.unified_rag)

    # 선택된 문서 미리보기 (컴포넌트)
    render_document_preview(st.session_state.rag, config)


if __name__ == "__main__":
    main()
