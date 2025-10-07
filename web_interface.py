#!/usr/bin/env python3
"""
브로드캐스트 기술관리팀 RAG 시스템 - 웹 인터페이스 (개선 버전)
- 문서 앞에 연도 표시
- 자주 묻는 질문 대신 통계 분석 버튼
- 연도별/월별 구매/수리 통계
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
    page_title="Channel A MEDIATECH RAG",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (Channel A 브랜드 컬러 배경)
st.markdown("""
<style>
    /* 메인 배경 - Channel A 파란색 그라데이션 */
    .stApp {
        background: linear-gradient(135deg, #87CEEB 0%, #4A90E2 25%, #1E5FA8 75%, #0A3D7A 100%);
        background-attachment: fixed;
    }
    
    /* 콘텐츠 영역을 위한 반투명 배경 */
    .main .block-container {
        background: rgba(10, 15, 25, 0.85);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 2rem;
        margin-top: 1rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    
    /* 사이드바 - 반투명 검정 */
    section[data-testid="stSidebar"] {
        background: rgba(15, 20, 30, 0.95);
        backdrop-filter: blur(10px);
        border-right: 2px solid rgba(74, 144, 226, 0.5);
    }
    
    section[data-testid="stSidebar"] .block-container {
        background: transparent;
    }
    
    /* 모든 텍스트 */
    .stMarkdown, .stText {
        color: #fafafa !important;
    }
    
    /* 입력 필드 - 라이트/다크 모드 호환 */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: rgba(255, 255, 255, 0.95) !important;
        backdrop-filter: blur(5px);
        color: #000000 !important;
        border: 2px solid rgba(74, 144, 226, 0.5) !important;
        font-weight: 500;
        border-radius: 8px;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        background: rgba(255, 255, 255, 1) !important;
        border-color: #1E5FA8 !important;
        box-shadow: 0 0 15px rgba(30, 95, 168, 0.3) !important;
        color: #000000 !important;
    }
    
    /* placeholder 텍스트도 보이도록 */
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: #666666 !important;
        opacity: 0.8;
    }
    
    /* 버튼 기본 - 반투명 스타일 */
    .stButton > button {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(5px);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.3);
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        background: rgba(255, 255, 255, 0.2);
        border-color: #87CEEB;
        box-shadow: 0 4px 8px rgba(135, 206, 235, 0.3);
    }
    
    /* Primary 버튼 - 흰색 강조 */
    .stButton > button[kind="primary"] {
        background: rgba(255, 255, 255, 0.95);
        color: #1E5FA8;
        border: none;
        font-weight: 700;
        box-shadow: 0 4px 12px rgba(255, 255, 255, 0.3);
    }
    
    .stButton > button[kind="primary"]:hover {
        background: rgba(255, 255, 255, 1);
        color: #0A3D7A;
        box-shadow: 0 6px 16px rgba(255, 255, 255, 0.4);
        transform: translateY(-2px);
    }
    
    /* 메트릭 카드 - 반투명 흰색 */
    [data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 0.8rem 1rem;
        border-radius: 12px;
        color: #ffffff;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    [data-testid="metric-container"]:hover {
        background: rgba(255, 255, 255, 0.2);
        border-color: rgba(255, 255, 255, 0.5);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
        transform: translateY(-2px);
    }
    
    /* 정보 박스 - 반투명 */
    .stAlert {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(5px);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* 스크롤바 스타일링 */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.3);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.5);
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #1a1d23;
        gap: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #262730;
        color: #fafafa;
        border-radius: 8px 8px 0 0;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #393946;
        color: #ffffff;
    }
    
    /* 표 스타일 */
    pre {
        background-color: #1a1d23 !important;
        color: #00ff00 !important;
        padding: 1rem !important;
        border-radius: 8px !important;
        border: 1px solid #393946 !important;
        font-family: 'Courier New', monospace !important;
        overflow-x: auto !important;
    }
    
    /* 코드 블록 */
    code {
        background-color: #262730 !important;
        color: #00ff00 !important;
        padding: 2px 4px !important;
        border-radius: 4px !important;
    }

    /* 통계 카드 스타일 */
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        color: white;
    }

    /* 질문 입력창과 버튼 정렬 - 핵심 수정 */
    .stForm {
        background: transparent !important;
    }

    /* 폼 내부 컴럼들을 수평 중앙 정렬 */
    .stForm [data-testid="stHorizontalBlock"] {
        display: flex !important;
        align-items: stretch !important;  /* stretch로 변경하여 높이 맞춤 */
        gap: 8px !important;  /* 요소 간 8px 간격 */
    }

    /* 폼 내부 컴럼들의 내부 요소 정렬 */
    .stForm [data-testid="stHorizontalBlock"] > div {
        display: flex !important;
        align-items: center !important;
        height: 100% !important;
    }

    /* 입력창 컨테이너 */
    .stForm .stTextInput {
        display: flex !important;
        align-items: center !important;
    }

    /* 입력창과 버튼 동일 높이(50px) 설정 */
    .stForm input[type="text"] {
        height: 50px !important;
        min-height: 50px !important;
        max-height: 50px !important;
        line-height: 50px !important;
        padding: 0 12px !important;
    }

    .stForm button[type="submit"] {
        height: 50px !important;
        min-height: 50px !important;
        max-height: 50px !important;
        padding: 0 20px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* 버튼 컨테이너 정렬 */
    .stForm [data-testid="stFormSubmitButton"] {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        display: flex !important;
        align-items: center !important;
        height: 100% !important;
    }

    /* 버튼 wrapper 정렬 */
    .stForm [data-testid="stFormSubmitButton"] > div {
        height: 100% !important;
        display: flex !important;
        align-items: center !important;
    }
</style>
""", unsafe_allow_html=True)


def show_pdf_preview(file_path, height=700):
    """PDF 미리보기 표시 - 성능 최적화 및 오류 처리 개선

    Args:
        file_path: PDF 파일 경로
        height: 미리보기 높이 (픽셀)
    """
    import base64
    from pathlib import Path

    try:
        file_path = Path(file_path)
        if not file_path.exists():
            st.error(f"⚠️ 파일을 찾을 수 없습니다: {file_path.name}")
            return False

        # 파일 크기 확인
        file_size = file_path.stat().st_size
        file_size_mb = file_size / (1024*1024)

        # PyMuPDF 설치 여부 체크
        PYMUPDF_AVAILABLE = False
        try:
            import fitz
            PYMUPDF_AVAILABLE = True
        except ImportError:
            pass
        
        # 상단 정보 바 (모든 PDF 동일)
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"**📄 {Path(file_path).name}**")
        with col2:
            st.markdown(f"**💾 {file_size_mb:.1f}MB**")
        with col3:
            with open(file_path, "rb") as f:
                st.download_button(
                    label="📥 다운로드",
                    data=f,
                    file_name=Path(file_path).name,
                    mime="application/pdf",
                    key=f"download_{file_path}"
                )
        
        st.markdown("---")
        
        # 보기 옵션 선택 (PyMuPDF 설치 여부에 따라 다르게)
        if PYMUPDF_AVAILABLE:
            if file_size_mb > 10:
                # 대용량 파일은 페이지별 이미지 모드 권장
                default_mode = "🖼️ 페이지별 이미지"
                st.info(f"💡 대용량 파일({file_size_mb:.1f}MB)은 페이지별 이미지 모드를 권장합니다")
            else:
                default_mode = "📖 원본 PDF"
            view_modes = ["📖 원본 PDF", "🖼️ 페이지별 이미지", "📄 텍스트 추출"]
        else:
            default_mode = "📄 텍스트 추출"
            view_modes = ["📄 텍스트 추출"]
            st.warning("⚠️ PyMuPDF 미설치로 텍스트 추출만 가능합니다. 전체 기능을 위해 'pip install pymupdf' 실행을 권장합니다")

        view_mode = st.radio(
            "보기 모드 선택",
            view_modes,
            index=view_modes.index(default_mode),
            key=f"view_mode_{file_path}",
            horizontal=True
        )
        
        if view_mode == "📖 원본 PDF":
            # 1.5MB 이하: base64 인코딩으로 바로 표시
            if file_size_mb <= 1.5:
                with open(file_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                # iframe 표시
                pdf_display = f'''
                <div style="width: 100%; border: 1px solid #ddd; border-radius: 5px; background: white;">
                    <iframe 
                        src="data:application/pdf;base64,{base64_pdf}#view=FitH&toolbar=1&navpanes=1&scrollbar=1" 
                        width="100%" 
                        height="{height}px" 
                        type="application/pdf"
                        style="border: none;">
                    </iframe>
                </div>
                '''
                st.markdown(pdf_display, unsafe_allow_html=True)
            
            # 1.5MB 초과: 페이지별 이미지로 표시하되 원본 품질 유지
            else:
                st.warning(f"⚠️ 큰 파일({file_size_mb:.1f}MB)은 페이지별 이미지 모드를 사용해주세요")
                st.info("🖼️ 위에서 '페이지별 이미지' 모드를 선택하시면 PDF를 볼 수 있습니다")
        
        elif view_mode == "🖼️ 페이지별 이미지":
            if not PYMUPDF_AVAILABLE:
                st.error("PyMuPDF가 필요합니다. 'pip install pymupdf'로 설치해주세요")
                return False

            try:
                import fitz  # PyMuPDF
                from PIL import Image
                import io

                # 캐싱 키 생성 (파일 경로와 수정 시간 기반)
                cache_key = f"pdf_render_{file_path}_{file_size}"

                # 총 페이지 수 확인
                pdf_document = fitz.open(str(file_path))
                total_pages = pdf_document.page_count
                
                # 세션 상태로 페이지 번호 관리
                if f'page_{file_path}' not in st.session_state:
                    st.session_state[f'page_{file_path}'] = 1
                
                current_page = st.session_state[f'page_{file_path}']
                
                # 페이지 선택 UI
                col1, col2, col3 = st.columns([1, 3, 1])
                with col2:
                    new_page = st.slider(
                        "📄 페이지 이동",
                        min_value=1,
                        max_value=total_pages,
                        value=current_page,
                        key=f"slider_{file_path}",
                        help="슬라이더를 움직여 페이지를 이동하세요"
                    )
                    if new_page != current_page:
                        st.session_state[f'page_{file_path}'] = new_page
                        st.rerun()
                
                # 현재 페이지를 고품질 이미지로 렌더링
                page = pdf_document[current_page - 1]
                
                # 성능 최적화: 파일 크기에 따라 렌더링 품질 동적 조정
                if file_size_mb > 50:
                    zoom = 1.0  # 대용량: 낮은 해상도
                    st.caption("📊 대용량 파일 - 최적화된 품질로 렌더링")
                elif file_size_mb > 20:
                    zoom = 1.5  # 중간: 중간 해상도
                else:
                    zoom = 2.0  # 소형: 고해상도

                mat = fitz.Matrix(zoom, zoom)

                # 프로그레스 표시 (대용량 파일)
                if file_size_mb > 10:
                    with st.spinner(f"페이지 {current_page}/{total_pages} 렌더링 중..."):
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                else:
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # PIL 이미지로 변환
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # 화면에 맞게 크기 조정
                display_width = 850  # 표시 너비
                if img.width > display_width:
                    ratio = display_width / img.width
                    display_height = int(img.height * ratio)
                    img_display = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                else:
                    img_display = img
                
                # 이미지 표시
                st.image(img_display, width="stretch")
                
                # 페이지 네비게이션 버튼
                col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 2])
                with col2:
                    if st.button("◀ 이전", key=f"prev_{file_path}", disabled=(current_page == 1)):
                        st.session_state[f'page_{file_path}'] = max(1, current_page - 1)
                        st.rerun()
                with col3:
                    st.markdown(f"<center><b>{current_page} / {total_pages}</b></center>", unsafe_allow_html=True)
                with col4:
                    if st.button("다음 ▶", key=f"next_{file_path}", disabled=(current_page == total_pages)):
                        st.session_state[f'page_{file_path}'] = min(total_pages, current_page + 1)
                        st.rerun()
                
                # 메모리 해제
                pdf_document.close()

            except Exception as e:
                st.error(f"🔴 PDF 이미지 렌더링 실패: {str(e)}")
                st.info("💡 대체 방법: 텍스트 추출 모드를 시도해보세요")
                return False
        
        elif view_mode == "📄 텍스트 추출":
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                
                # 페이지 선택
                page_num = st.slider(
                    "📄 페이지 선택",
                    min_value=1,
                    max_value=total_pages,
                    value=1,
                    key=f"text_page_{file_path}"
                )
                
                st.markdown(f"**페이지 {page_num} / {total_pages}**")
                
                page = pdf.pages[page_num - 1]
                text = page.extract_text()
                if text and text.strip():
                    st.text_area("페이지 내용", text, height=500, key=f"text_content_{file_path}")
                else:
                    # OCR 시도
                    st.info("🔍 스캔된 문서로 보입니다. OCR 처리를 시도합니다...")
                    try:
                        from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor

                        # OCR 프로세서 초기화 (캐싱)
                        if 'ocr_processor' not in st.session_state:
                            st.session_state.ocr_processor = EnhancedOCRProcessor()
                        ocr = st.session_state.ocr_processor

                        with st.spinner("OCR 처리 중... 시간이 걸릴 수 있습니다"):
                            ocr_text = ocr.process_pdf_with_ocr(str(file_path), page_num)

                        if ocr_text and ocr_text.strip():
                            st.success("✅ OCR 처리 성공!")
                            st.text_area("OCR 추출 내용", ocr_text, height=500, key=f"ocr_content_{file_path}")
                        else:
                            st.warning("⚠️ OCR 처리 후에도 텍스트를 추출할 수 없습니다")
                    except ImportError:
                        st.warning("⚠️ OCR 기능을 사용하려면 'pip install pytesseract pdf2image' 설치가 필요합니다")
                    except Exception as ocr_error:
                        st.error(f"❌ OCR 처리 실패: {str(ocr_error)}")
                        st.info("💡 Tesseract OCR이 설치되어 있는지 확인해주세요")
            
        return True
            
    except Exception as e:
        st.error(f"❌ PDF 미리보기 오류: {str(e)}")

        # 상세 오류 정보 (디버깅용)
        with st.expander("🔍 상세 오류 정보"):
            import traceback
            st.text(traceback.format_exc())

        # 오류 시에도 다운로드는 제공
        try:
            with open(file_path, "rb") as f:
                st.download_button(
                    label="📥 PDF 다운로드 (미리보기 실패)",
                    data=f,
                    file_name=Path(file_path).name,
                    mime="application/pdf",
                    help="미리보기는 실패했지만 파일을 다운로드할 수 있습니다"
                )
                st.info("💡 미리보기가 실패해도 다운로드하여 로컬에서 확인 가능합니다")
        except Exception as dl_error:
            st.error(f"다운로드도 실패: {str(dl_error)}")
        return False

def apply_sidebar_styles():
    """사이드바 스타일 적용"""
    st.markdown("""
    <style>
    /* 강제 라이트 모드 스타일 */
    .stApp[data-theme="light"] [data-testid="stSidebar"] .stButton > button,
    [data-testid="stAppViewContainer"][data-theme="light"] [data-testid="stSidebar"] .stButton > button {
        color: #000000 !important;
        opacity: 1 !important;
    }

    .stApp[data-theme="light"] [data-testid="stSidebar"] .stButton > button:hover,
    [data-testid="stAppViewContainer"][data-theme="light"] [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(0, 0, 0, 0.05) !important;
        color: #000000 !important;
    }

    .stApp[data-theme="light"] .year-divider,
    [data-testid="stAppViewContainer"][data-theme="light"] .year-divider {
        color: #000000 !important;
        border-bottom: 1px solid rgba(0, 0, 0, 0.15) !important;
    }

    /* 강제 다크 모드 스타일 */
    .stApp[data-theme="dark"] [data-testid="stSidebar"] .stButton > button,
    [data-testid="stAppViewContainer"][data-theme="dark"] [data-testid="stSidebar"] .stButton > button {
        color: #FFFFFF !important;
        opacity: 1 !important;
    }

    .stApp[data-theme="dark"] [data-testid="stSidebar"] .stButton > button:hover,
    [data-testid="stAppViewContainer"][data-theme="dark"] [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255, 255, 255, 0.1) !important;
        color: #FFFFFF !important;
    }

    .stApp[data-theme="dark"] .year-divider,
    [data-testid="stAppViewContainer"][data-theme="dark"] .year-divider {
        color: #FFFFFF !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2) !important;
    }

    /* 공통 버튼 스타일 */
    [data-testid="stSidebar"] .stButton > button {
        padding: 3px 10px !important;
        font-size: 13px !important;
        line-height: 22px !important;
        min-height: 26px !important;
        margin: 2px 0 !important;
        border: none !important;
        background: transparent !important;
        text-align: left !important;
        justify-content: flex-start !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
        font-weight: 400 !important;
        transition: all 0.15s ease !important;
        width: 100% !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* 연도 구분선 공통 스타일 */
    .year-divider {
        font-size: 12px;
        font-weight: 700;
        padding: 6px 0 3px;
        margin: 12px 0 6px;
        letter-spacing: 0.5px;
    }

    /* 사이드바 전체 스타일 */
    [data-testid="stSidebar"] {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
    }

    /* 탭 스타일 개선 */
    [data-testid="stSidebar"] .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    [data-testid="stSidebar"] .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-size: 14px;
        font-weight: 500;
    }

    /* 검색창 스타일 */
    [data-testid="stSidebar"] input[type="text"] {
        font-size: 13px !important;
        padding: 8px 12px !important;
    }

    /* SelectBox 스타일 */
    [data-testid="stSidebar"] [data-baseweb="select"] {
        font-size: 13px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def display_document_list(filtered_df, df, prefix="doc"):
    """문서 리스트를 표시하는 헬퍼 함수"""
    if isinstance(filtered_df, pd.DataFrame) and not filtered_df.empty:
        doc_counter = 0  # 전역 고유 카운터
        for year in sorted(filtered_df['year'].unique(), reverse=True):
            year_docs = filtered_df[filtered_df['year'] == year]

            # 연도 구분선
            st.markdown(f"### {year}년 ({len(year_docs)}개)")

            # 문서 리스트 - 날짜와 문서명
            for idx, row in year_docs.iterrows():
                # 날짜 처리
                if row['date'] and len(row['date']) >= 10:
                    date_str = row['date'][5:10]  # MM-DD
                else:
                    date_str = "     "  # 날짜 없으면 공백

                # 제목 처리 (길면 자르기)
                title = row['title'][:30] + "..." if len(row['title']) > 30 else row['title']

                # 날짜와 제목을 함께 표시
                button_text = f"[{date_str}] {title}"

                # 고유한 키 생성 (prefix, 카운터, 파일명 조합)
                unique_key = f"{prefix}_{doc_counter}_{row['filename'][:10]}"
                doc_counter += 1

                # 심플한 버튼으로 문서 선택
                if st.button(button_text, key=unique_key, use_container_width=True):
                    st.session_state.selected_doc = row
                    st.session_state.show_doc_preview = True
                    st.rerun()
    else:
        # 문서가 없거나 데이터프레임이 비어있을 때
        if not isinstance(filtered_df, pd.DataFrame):
            st.error("문서 목록을 불러올 수 없습니다.")
        elif filtered_df.empty:
            if df.empty:
                st.warning("문서가 없습니다. docs 폴더에 PDF 파일을 추가해주세요.")
            else:
                st.caption("표시할 문서가 없습니다.")

@st.cache_data
def load_documents(_rag_instance, version="v3.0"):  # Fast DB loading
    """초고속 문서 메타데이터 로드 - DB에서 직접 조회"""
    print("🚀 초고속 문서 로드 시작 (DB 직접 조회)")

    try:
        import sqlite3
        import pandas as pd

        # SQLite DB 연결
        conn = sqlite3.connect('everything_index.db')
        cursor = conn.cursor()

        # 모든 문서 정보 조회
        cursor.execute("""
            SELECT filename, path, date, year, category, department, keywords
            FROM files
            ORDER BY year DESC, filename ASC
        """)

        rows = cursor.fetchall()
        documents = []

        print(f"📊 DB에서 {len(rows)}개 문서 로드됨")

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
            elif '폐기' in filename:
                doc_category = "폐기"
            else:
                doc_category = category or "기타"

            # 기안자 정보 (이미 DB에 동기화됨)
            drafter = department if department and department not in ['영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출'] else "미확인"

            # 문서 정보 구성
            documents.append({
                'filename': filename,
                'title': filename.replace('.pdf', '').replace('_', ' '),
                'date': date or '날짜없음',
                'year': year or '연도없음',
                'category': doc_category,
                'drafter': drafter,
                'size': '알 수 없음',
                'path': path,
                'keywords': keywords or ''
            })

        conn.close()
        print(f"✅ {len(documents)}개 문서 초고속 로드 완료!")

        # DataFrame으로 변환 후 반환
        df = pd.DataFrame(documents)
        if not df.empty:
            # 연도와 파일명으로 정렬
            df = df.sort_values(['year', 'filename'], ascending=[False, True])

        # 통계 출력
        drafter_count = len(df[df['drafter'] != '미확인']) if not df.empty else 0
        print(f"📈 기안자 통계:")
        print(f"  - 기안자 확인: {drafter_count}개 ({drafter_count*100//max(len(documents), 1)}%)")
        print(f"  - 기안자 미확인: {len(documents) - drafter_count}개")

        return df

    except Exception as e:
        print(f"❌ 초고속 로드 실패: {e}")
        return pd.DataFrame()

def _legacy_load_documents(_rag_instance):
    """Legacy document loading function (for reference only)"""
    print("Loading documents from metadata cache...")
    documents = []

    # 기안자 추출을 위한 패턴
    drafter_patterns = [
        r'기\s*안\s*자\s*[:：]?\s*([^담\s]{2,5})',  # 기안자: XXX
        r'작\s*성\s*자\s*[:：]?\s*([^담\s]{2,5})',  # 작성자: XXX
        r'작\s*성\s*[:：]?\s*([^담\s]{2,5})',  # 작성: XXX
        r'담\s*당\s*자\s*[:：]?\s*([^담\s]{2,5})',  # 담당자: XXX
        r'담\s*당\s*[:：]?\s*([^담\s]{2,5})',  # 담당: XXX
        r'신\s*청\s*자\s*[:：]?\s*([^담\s]{2,5})',  # 신청자: XXX
        r'상\s*신\s*[:：]?\s*([^담\s]{2,5})',  # 상신: XXX
    ]

    # RAG 인스턴스의 메타데이터 캐시 활용
    try:
        # 메타데이터 캐시에서 직접 가져오기
        if hasattr(_rag_instance, 'metadata_cache') and _rag_instance.metadata_cache:
            print(f"Using cached metadata for {len(_rag_instance.metadata_cache)} documents")

            for cache_key, metadata in _rag_instance.metadata_cache.items():
                if not metadata.get('is_pdf', True):
                    continue  # PDF 파일만 처리

                file_path = metadata.get('path')
                if isinstance(file_path, str):
                    file_path = Path(file_path)

                filename = metadata.get('filename', cache_key)

                # 날짜와 제목 추출
                date_str = metadata.get('date', '')
                year = metadata.get('year', '연도없음')
                title = metadata.get('title', filename)

                # 카테고리 분류
                category = "기타"
                if "구매" in filename or "구입" in filename:
                    category = "구매"
                elif "폐기" in filename:
                    category = "폐기"
                elif "수리" in filename or "보수" in filename:
                    category = "수리"
                elif "소모품" in filename:
                    category = "소모품"

                # 기안자 추출 시도 (메타데이터 DB 우선, 없으면 PDF에서 직접)
                drafter = "미상"

                # 1. 메타데이터 DB에서 확인
                if hasattr(_rag_instance, 'metadata_db') and _rag_instance.metadata_db:
                    db_info = _rag_instance.metadata_db.get_document(filename)
                    if db_info and db_info.get('drafter'):
                        drafter = db_info['drafter']

                # 2. 메타데이터 DB에 없으면 PDF에서 직접 추출
                if drafter == "미상" and file_path and file_path.exists():
                    try:
                        # 빠른 추출을 위해 철 페이지만 검사
                        with pdfplumber.open(file_path) as pdf:
                            if pdf.pages:
                                # 첨 두 페이지에서 기안자 찾기
                                for page_num in range(min(2, len(pdf.pages))):
                                    text = pdf.pages[page_num].extract_text() or ""
                                    if text:
                                        for pattern in drafter_patterns:
                                            match = re.search(pattern, text)
                                            if match:
                                                candidate = match.group(1).strip()
                                                # 유효한 이름인지 체크 (한글 2-4자)
                                                if re.match(r'^[가-힣]{2,4}$', candidate):
                                                    drafter = candidate
                                                    print(f"  ✅ 기안자 추출: {filename} -> {drafter}")
                                                    break
                                    if drafter != "미상":
                                        break
                    except Exception as e:
                        # 기안자 추출 실패 시 무시 (미상으로 유지)
                        pass

                # 문서 메타데이터 생성
                doc_metadata = {
                    'title': title,
                    'filename': filename,
                    'path': str(file_path),
                    'category': category,
                    'date': date_str if date_str else "날짜 미상",
                    'year': year,
                    'drafter': drafter,
                    'month': "",
                    'modified': datetime.now()  # 기본값
                }

                # 파일 수정 시간 가져오기
                if file_path and file_path.exists():
                    try:
                        doc_metadata['modified'] = datetime.fromtimestamp(file_path.stat().st_mtime)
                    except Exception as e:
                        pass

                documents.append(doc_metadata)

        else:
            # 메타데이터 캐시가 없으면 pdf_files에서 직접 로드
            print("Metadata cache not available, loading from pdf_files...")
            pdf_files = _rag_instance.pdf_files if hasattr(_rag_instance, 'pdf_files') else []

            # 중복 제거를 위한 딕셔너리
            unique_docs = {}

            for pdf_file in pdf_files:
                # archive 폴더의 파일은 낮은 우선순위
                is_archive = 'archive' in str(pdf_file).lower()

                # 이미 등록된 파일인지 확인
                if pdf_file.name in unique_docs:
                    # archive가 아닌 파일을 우선
                    if is_archive:
                        continue  # 이미 있고 현재가 archive면 스킵
                    # 현재 파일이 archive가 아니면 교체

                # 파일명에서 메타데이터 추출 (개선된 날짜 처리)
                name_parts = pdf_file.stem.split('_', 1)
                doc_date = name_parts[0] if len(name_parts) > 0 else ""
                doc_title = name_parts[1] if len(name_parts) > 1 else pdf_file.stem
                doc_title = html.unescape(doc_title)

                # 날짜 추출 개선 - 다양한 형식 지원
                extracted_date = None
                year = "연도없음"
                month = ""

                # 1. 파일명에서 날짜 패턴 찾기
                date_patterns = [
                    r'(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})',  # YYYY-MM-DD
                    r'(20\d{2})(\d{2})(\d{2})',               # YYYYMMDD
                    r'(20\d{2})[-_.](\d{1,2})',               # YYYY-MM
                    r'(20\d{2})'                              # YYYY
                ]

                filename = pdf_file.name
                for pattern in date_patterns:
                    match = re.search(pattern, filename)
                    if match:
                        groups = match.groups()
                        if len(groups) == 3:  # YYYY-MM-DD
                            try:
                                year_val, month_val, day_val = groups
                                extracted_date = f"{year_val}-{int(month_val):02d}-{int(day_val):02d}"
                                year = year_val
                                month = f"{int(month_val):02d}"
                                break
                            except ValueError:
                                continue
                        elif len(groups) == 2:  # YYYY-MM
                            try:
                                year_val, month_val = groups
                                extracted_date = f"{year_val}-{int(month_val):02d}-01"
                                year = year_val
                                month = f"{int(month_val):02d}"
                                break
                            except ValueError:
                                continue
                        elif len(groups) == 1:  # YYYY
                            year_val = groups[0]
                            extracted_date = f"{year_val}-01-01"
                            year = year_val
                            break

                # 2. 추출된 날짜가 없으면 기존 방식 사용
                if not extracted_date:
                    if len(doc_date) >= 4:
                        year = doc_date[:4]
                        if len(doc_date) >= 7:
                            month = doc_date[5:7]
                        extracted_date = doc_date

                # 최종 날짜 설정
                doc_date = extracted_date if extracted_date else "날짜 미상"

                # 카테고리 분류
                category = "기타"
                if "구매" in pdf_file.name or "구입" in pdf_file.name:
                    category = "구매"
                elif "폐기" in pdf_file.name:
                    category = "폐기"
                elif "수리" in pdf_file.name or "보수" in pdf_file.name:
                    category = "수리"
                elif "소모품" in pdf_file.name:
                    category = "소모품"

                # 기안자 정보 추출 (파일이 존재하는 경우)
                drafter = "미상"

                # 메타데이터 DB 활용 (있는 경우)
                if hasattr(_rag_instance, 'metadata_db') and _rag_instance.metadata_db:
                    db_info = _rag_instance.metadata_db.get_document(pdf_file.name)
                    if db_info and db_info.get('drafter'):
                        drafter = db_info['drafter']

                # DB에 없고 파일 크기가 작으면 직접 추출 시도
                if drafter == "미상" and pdf_file.stat().st_size < 10 * 1024 * 1024:  # 10MB 미만
                    try:
                        with pdfplumber.open(pdf_file) as pdf:
                            if pdf.pages:
                                # 첫 페이지만 확인 (성능)
                                text = pdf.pages[0].extract_text() or ""
                                if text:
                                    for pattern in drafter_patterns:
                                        match = re.search(pattern, text)
                                        if match:
                                            candidate = match.group(1).strip()
                                            if re.match(r'^[가-힣]{2,4}$', candidate):
                                                drafter = candidate
                                                break
                    except Exception as e:
                        pass

                # 메타데이터 생성
                metadata = {
                    'title': doc_title,
                    'filename': pdf_file.name,
                    'path': str(pdf_file),
                    'category': category,
                    'date': doc_date,
                    'year': year,
                    'drafter': drafter,
                    'month': month,
                    'modified': datetime.fromtimestamp(pdf_file.stat().st_mtime)
                }

                unique_docs[pdf_file.name] = metadata

            # 딕셔너리 값들을 리스트로 변환
            documents = list(unique_docs.values())

    except FileNotFoundError as e:
        print(f"📁 문서 디렉토리를 찾을 수 없습니다: {e}")
        st.error(f"문서 폴더를 찾을 수 없습니다. docs 폴더가 존재하는지 확인해주세요")
    except PermissionError as e:
        print(f"🔒 파일 접근 권한 오류: {e}")
        st.error("파일 접근 권한이 없습니다. 관리자 권한으로 실행해주세요")
    except Exception as e:
        print(f"🔴 문서 로드 중 오류: {e}")
        import traceback
        traceback.print_exc()
        st.warning(f"문서 로드 중 일부 오류가 발생했지만 계속 진행합니다")

    # DataFrame 생성 및 정렬
    df = pd.DataFrame(documents)
    if not df.empty:
        df = df.sort_values('date', ascending=False)

    # 기안자 통계
    drafter_count = sum(1 for doc in documents if doc.get('drafter') and doc['drafter'] != '미상')
    print(f"📊 총 {len(documents)}개 문서 로드 완료")
    print(f"  - 기안자 확인: {drafter_count}개 ({drafter_count*100//max(len(documents), 1)}%)")
    print(f"  - 기안자 미확인: {len(documents) - drafter_count}개")

    return df
@st.cache_resource(ttl=3600)  # 1시간 TTL로 캐시 관리
def initialize_rag_system():
    """RAG 시스템 초기화 (한 번만 실행) - QuickFixRAG 사용"""
    import importlib
    import sys

    # 모듈 재로드로 최신 버전 보장
    if 'quick_fix_rag' in sys.modules:
        importlib.reload(sys.modules['quick_fix_rag'])

    from quick_fix_rag import QuickFixRAG
    print("🚀 QuickFixRAG 초기화 중...")
    return QuickFixRAG()

def format_answer_with_table(answer):
    """답변에서 표 형식을 제대로 표시하도록 처리"""
    # 이미 코드 블록이 있는지 확인
    if "```" in answer:
        # 이미 코드 블록이 있으면 그대로 반환
        return answer
    
    # 표 패턴 찾기
    if "│" in answer or "┌" in answer or "├" in answer or "└" in answer:
        # 표를 코드 블록으로 감싸기
        lines = answer.split('\n')
        in_table = False
        formatted_lines = []
        table_lines = []
        
        for line in lines:
            if any(char in line for char in ['│', '┌', '├', '└', '─', '┬', '┼', '┴']):
                if not in_table:
                    in_table = True
                table_lines.append(line)
            else:
                if in_table and table_lines:
                    # 표를 코드 블록으로 추가
                    formatted_lines.append("```")
                    formatted_lines.extend(table_lines)
                    formatted_lines.append("```")
                    table_lines = []
                    in_table = False
                formatted_lines.append(line)
        
        # 마지막에 표가 남아있으면 추가
        if table_lines:
            formatted_lines.append("```")
            formatted_lines.extend(table_lines)
            formatted_lines.append("```")
        
        return '\n'.join(formatted_lines)
    
    return answer

def render_document_card(title, info):
    """각 문서를 카드 형태로 렌더링"""
    with st.container():
        # 카드 스타일 적용
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                # 제목 (이모지와 볼드 제거)
                clean_title = title.replace('#### ', '').strip()
                st.markdown(f"### {clean_title}")

                # 카테고리와 날짜
                if 'category' in info:
                    st.caption(info['category'])

                # 상세 정보 (- ** 형식 제거)
                if 'drafter' in info:
                    drafter_text = info['drafter'].replace('- **기안자**: ', '').replace('- **기안자**:', '')
                    st.write(f"👤 기안자: {drafter_text}")
                if 'amount' in info:
                    amount_text = info['amount'].replace('- **금액**: ', '').replace('- **금액**:', '')
                    st.write(f"💰 금액: {amount_text}")
                if 'summary' in info:
                    summary_text = info['summary'].replace('- **개요**: ', '').replace('- **개요**:', '')
                    st.info(f"📝 {summary_text}")
        
        with col2:
            # 미리보기 버튼
            if 'filename' in info:
                # Use the full path from metadata
                if 'path' in info:
                    file_path = Path(info['path'])
                else:
                    file_path = Path(config.DOCS_DIR) / info['filename']

                if file_path.exists():
                    # 미리보기 버튼 (토글 방식) - 경로 포함하여 유니크 키 생성
                    unique_id = str(file_path) if 'path' in info else info['filename']
                    preview_key = f"preview_{hashlib.md5(unique_id.encode()).hexdigest()}"
                    current_state = st.session_state.get(f'show_preview_{preview_key}', False)
                    
                    if st.button(
                        "🔍 미리보기" if not current_state else "📖 미리보는중",
                        key=preview_key,
                        use_container_width=True,
                        type="secondary" if not current_state else "primary"
                    ):
                        st.session_state[f'show_preview_{preview_key}'] = not current_state
                        st.rerun()
        
        with col3:
            # 다운로드 버튼
            if 'filename' in info:
                # Use the full path from metadata
                if 'path' in info:
                    file_path = Path(info['path'])
                else:
                    file_path = Path(config.DOCS_DIR) / info['filename']

                if file_path.exists():
                    try:
                        with open(file_path, 'rb') as f:
                            pdf_bytes = f.read()

                        # 파일 크기 확인
                        file_size_mb = len(pdf_bytes) / (1024 * 1024)
                        if file_size_mb > 100:
                            st.warning(f"⚠️ 대용량 파일 ({file_size_mb:.1f}MB)")

                        # 유니크 ID 생성 (경로 포함)
                        unique_id = str(file_path) if 'path' in info else info['filename']

                        st.download_button(
                            label=f"📥 다운로드 ({file_size_mb:.1f}MB)",
                            data=pdf_bytes,
                            file_name=info['filename'],
                            mime="application/pdf",
                            key=f"dl_{hashlib.md5(unique_id.encode()).hexdigest()}",
                            use_container_width=True,
                            help=f"클릭하여 {info['filename']} 파일을 다운로드합니다"
                        )
                    except MemoryError:
                        st.error("💾 파일이 너무 커서 메모리가 부족합니다")
                        st.info("💡 파일을 직접 폴더에서 열어주세요")
                    except Exception as e:
                        st.error(f"📥 다운로드 버튼 생성 실패")
                        with st.expander("오류 상세"):
                            st.text(str(e))
                else:
                    st.warning("📁 파일 없음")
        
        # 미리보기 표시 (버튼 클릭시)
        if 'filename' in info:
            # 유니크 ID 생성 (경로 포함)
            if 'path' in info:
                file_path = Path(info['path'])
            else:
                file_path = Path(config.DOCS_DIR) / info['filename']

            unique_id = str(file_path) if 'path' in info else info['filename']
            preview_key = f"preview_{hashlib.md5(unique_id.encode()).hexdigest()}"

            if st.session_state.get(f'show_preview_{preview_key}', False):
                with st.expander(f"📖 PDF 미리보기: {info['filename']}", expanded=True):
                    col1, col2 = st.columns([10, 1])
                    with col2:
                        if st.button("❌ 닫기", key=f"close_{preview_key}", help="미리보기 닫기"):
                            st.session_state[f'show_preview_{preview_key}'] = False
                            st.rerun()
                    
                    # Use the full path from metadata
                    if 'path' in info:
                        file_path = Path(info['path'])
                    else:
                        file_path = Path(config.DOCS_DIR) / info['filename']

                    if file_path.exists():
                        try:
                            # PDF 미리보기 표시 (높이 500px로 고정)
                            show_pdf_preview(file_path, height=500)
                        except Exception as e:
                            st.error(f"📄 PDF 미리보기 실패")
                            st.info(f"💡 다운로드 버튼을 사용하여 파일을 열어보세요")
                            with st.expander("오류 상세"):
                                st.text(str(e))
                    else:
                        st.error(f"📁 PDF 파일을 찾을 수 없습니다: {info['filename']}")
                        st.info("💡 파일이 이동되었거나 삭제되었을 수 있습니다")
        
        st.markdown("---")

def generate_statistics_report(df, year=None, month=None):
    """통계 보고서 생성"""
    # 필터링
    filtered_df = df.copy()
    if year:
        filtered_df = filtered_df[filtered_df['year'] == str(year)]
    if month:
        filtered_df = filtered_df[filtered_df['month'] == month]
    
    # 통계 계산
    total_docs = len(filtered_df)
    category_counts = filtered_df['category'].value_counts().to_dict()
    
    # 기안자 통계 (미상 제외)
    drafter_df = filtered_df[filtered_df['drafter'] != '미상']
    drafter_counts = drafter_df['drafter'].value_counts().to_dict() if len(drafter_df) > 0 else {}
    
    # 월별 통계 (연도 선택시)
    monthly_stats = {}
    if year and not month:
        for m in range(1, 13):
            month_str = f"{m:02d}"
            month_df = filtered_df[filtered_df['month'] == month_str]
            if len(month_df) > 0:
                monthly_stats[month_str] = {
                    'total': len(month_df),
                    'categories': month_df['category'].value_counts().to_dict()
                }
    
    return {
        'total_docs': total_docs,
        'category_counts': category_counts,
        'drafter_counts': drafter_counts,
        'monthly_stats': monthly_stats
    }

def main():
    # 로고 및 타이틀 표시
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col2:
        # 로고 이미지 표시 (흰색 버전)
        if Path('channel_a_logo_inverted.png').exists():
            st.image('channel_a_logo_inverted.png', width="stretch")
        elif Path('channel_a_logo.png').exists():
            st.image('channel_a_logo.png', use_container_width=True)
        
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
    docs_path = Path(config.DOCS_DIR)
    pdf_count = len(list(docs_path.glob("*.pdf")))
    txt_count = len(list(docs_path.glob("*.txt")))
    
    # 현황 표시
    # 자동 인덱싱 시스템 초기화
    if 'auto_indexer' not in st.session_state:
        from auto_indexer import AutoIndexer
        st.session_state.auto_indexer = AutoIndexer(check_interval=60)  # 60초마다 체크
        st.session_state.auto_indexer.start_monitoring()
        print("🚀 자동 인덱싱 시스템 시작")
    
    # RAG 시스템 초기화 (개선된 로딩 화면)
    if 'rag' not in st.session_state:
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
                        <p style='color: white; margin: 0;'>📦 Qwen2.5-7B 모델 로드 중...</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 프로그레스 바
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 단계별 로딩 표시
            import time
            status_text.text("📋 문서 메타데이터 로드 중...")
            progress_bar.progress(25)
            time.sleep(0.5)
            
            status_text.text("🤖 AI 모델 초기화 중...")
            progress_bar.progress(50)
            
            # 실제 RAG 시스템 초기화
            st.session_state.rag = initialize_rag_system()
            
            status_text.text("🔍 검색 엔진 준비 중...")
            progress_bar.progress(75)
            time.sleep(0.3)
            
            status_text.text("✅ 시스템 준비 완료!")
            progress_bar.progress(100)
            time.sleep(0.5)
            
            # 로딩 컨테이너 비우기
            loading_container.empty()
    
    # 사이드바 - 문서 목록 (단순화)
    with st.sidebar:
        # 사이드바에도 로고 표시 (흰색 버전, 작게)
        if Path('logo_inverted.png').exists():
            st.image('logo_inverted.png', width=200)
        elif Path('logo.png').exists():
            st.image('logo.png', width=200)
        st.markdown("---")
        
        # 자동 인덱싱 상태 표시
        st.markdown("### 자동 인덱싱")
        if 'auto_indexer' in st.session_state:
            stats = st.session_state.auto_indexer.get_statistics()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("PDF", f"{stats['pdf_count']}개")
            with col2:
                st.metric("TXT", f"{stats['txt_count']}개")
            
            # 마지막 업데이트
            if stats['last_update'] != 'Never':
                st.caption(f"마지막 체크: {stats['last_update'][:16]}")
            
            # 수동 재인덱싱 버튼
            col1, col2 = st.columns(2)
            with col1:
                if st.button("새로고침", key="refresh_index", use_container_width=True):
                    with st.spinner("인덱싱 중..."):
                        result = st.session_state.auto_indexer.check_new_files()
                        if result['new']:
                            st.success(f"✅ {len(result['new'])}개 새 파일 인덱싱 완료!")
                            # RAG 시스템 리로드
                            if 'rag' in st.session_state:
                                del st.session_state.rag
                            st.rerun()
                        else:
                            st.info("변경사항 없음")
            
            with col2:
                if st.button("♻️ 전체재인덱싱", key="force_reindex", use_container_width=True):
                    with st.spinner("전체 재인덱싱 중..."):
                        result = st.session_state.auto_indexer.force_reindex()
                        st.success(f"✅ {result['total']}개 파일 재인덱싱 완료!")
                        # RAG 시스템 리로드
                        if 'rag' in st.session_state:
                            del st.session_state.rag
                        st.rerun()
        
        st.markdown("---")
        st.markdown("### 📂 문서 라이브러리")

        # 빠른 문서 개수만 먼저 표시
        if hasattr(st.session_state.rag, 'metadata_cache'):
            doc_count = len(st.session_state.rag.metadata_cache)
            st.caption(f"📚 {doc_count}개 문서")

        # 문서 로드 (캐시됨 - @st.cache_data 덕분에 빠름)
        with st.spinner("문서 목록 로드 중..."):
            df = load_documents(st.session_state.rag)
            st.session_state.documents_df = df

        # 문서 목록이 로드된 경우 탭 표시
        if not df.empty:
            # 전체 문서 개수를 작게 표시
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"전체 {len(df)}개 문서")

            # 탭 구성
            tab1, tab2 = st.tabs(["📁 문서 검색", "📅 연도별"])

            with tab1:
                # 검색창
                search_query = st.text_input(
                    "문서 검색",
                    placeholder="제목, 파일명, 기안자 입력...",
                    label_visibility="collapsed",
                    key="doc_search_input"
                )

                # 검색 처리
                if search_query:
                    # 검색 결과
                    mask = (df['title'].str.contains(search_query, case=False, na=False) |
                           df['filename'].str.contains(search_query, case=False, na=False) |
                           df['drafter'].str.contains(search_query, case=False, na=False))
                    filtered_df = df[mask]

                    if len(filtered_df) > 0:
                        st.success(f"검색 결과: {len(filtered_df)}개")
                    else:
                        st.warning("검색 결과가 없습니다")
                        filtered_df = pd.DataFrame()
                else:
                    # 검색어가 없으면 전체 문서 표시
                    filtered_df = df if not df.empty else pd.DataFrame()

                # 검색 탭에서 문서 리스트 표시
                display_document_list(filtered_df, df, "search")

            with tab2:
                # 연도 선택
                if not df.empty and 'year' in df.columns:
                    years = sorted(df['year'].unique(), reverse=True)

                    # 연도별 문서 개수 포함하여 표시
                    year_counts = df['year'].value_counts().to_dict()
                    year_options = [f"{year}년 ({year_counts.get(year, 0)}개)" for year in years]

                    selected_year_str = st.selectbox(
                        "연도 선택",
                        year_options,
                        label_visibility="collapsed",
                        key="year_select"
                    )

                    # 선택된 연도 추출 (연도없음 처리)
                    if selected_year_str == "연도없음":
                        selected_year = 0
                        filtered_df = df[df['year'] == 0]
                    else:
                        selected_year = int(selected_year_str.split("년")[0])
                        filtered_df = df[df['year'] == selected_year]

                    # 선택된 연도 정보
                    if selected_year == 0:
                        st.info(f"연도 정보 없는 문서 {len(filtered_df)}개")
                    else:
                        st.info(f"{selected_year}년 문서 {len(filtered_df)}개")

                    # 연도별 탭에서 문서 리스트 표시
                    display_document_list(filtered_df, df, "year")
                else:
                    st.info("문서가 없습니다")

        # CSS 스타일 적용
        apply_sidebar_styles()
        
        # 시스템 정보
        st.markdown("---")
        st.markdown("### 시스템 정보")
        if not df.empty and 'year' in df.columns:
            year_range = f"{df['year'].min()}년 ~ {df['year'].max()}년"
        else:
            year_range = "데이터 없음"

        st.info(f"""
        **모델**: Qwen2.5-7B
        **문서**: {len(df)}개
        **기간**: {year_range}
        """)
    
    # ===== 메인 화면: AI 채팅 =====
    st.markdown("# 🤖 AI 문서 상담")
    st.info("💡 문서를 바탕으로 AI와 대화할 수 있습니다. 질문을 입력하세요!")

    # HybridChatRAG 초기화 (세션 상태로 관리)
    if 'hybrid_chat_rag' not in st.session_state:
        with st.spinner("AI 채팅 시스템 초기화 중..."):
            st.session_state.hybrid_chat_rag = HybridChatRAG()

    # 채팅 입력
    chat_input = st.text_input(
        "AI에게 문서에 대해 질문하세요:",
        placeholder="예: 남준수가 작성한 문서들의 특징을 분석해줘",
        key="chat_input"
    )

    # 검색 모드 선택 및 버튼
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        search_mode = st.radio(
            "응답 모드:",
            ["🔍 빠른 검색", "🤖 AI 채팅"],
            key="search_mode",
            horizontal=True
        )

    with col3:
        submit_btn = st.button("✨ 질문하기", type="primary", use_container_width=True)

    # 질문 처리
    if submit_btn and chat_input:
        with st.spinner("AI가 답변을 생성하는 중..."):
            if search_mode == "🔍 빠른 검색":
                response = st.session_state.hybrid_chat_rag.search_only(chat_input)
            else:
                response = st.session_state.hybrid_chat_rag.chat_with_documents(chat_input)

            # 응답 표시
            st.markdown("---")
            st.markdown("### 💬 AI 응답")
            st.markdown(response)
    elif submit_btn:
        st.warning("질문을 입력해주세요!")

    # 대화 기록 표시
    if hasattr(st.session_state.get('hybrid_chat_rag'), 'conversation_history'):
        history = st.session_state.hybrid_chat_rag.get_conversation_history()
        if history:
            st.markdown("---")
            st.markdown("### 📝 대화 기록")

            # 기록 초기화 버튼
            if st.button("🗑️ 대화 기록 초기화", key="clear_history"):
                st.session_state.hybrid_chat_rag.clear_conversation()
                st.success("대화 기록이 초기화되었습니다!")
                st.rerun()

            # 최근 대화부터 표시
            for i, conv in enumerate(reversed(history[-5:])):  # 최근 5개만
                with st.expander(f"💬 대화 {len(history)-i}", expanded=(i==0)):
                    st.markdown(f"**Q:** {conv['query']}")
                    st.markdown(f"**A:** {conv['response'][:500]}{'...' if len(conv['response']) > 500 else ''}")
                    st.caption(f"시간: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conv['timestamp']))}")

    # 사용 팁
    with st.expander("💡 사용 팁"):
        st.markdown("""
        - **빠른 검색**: 0.02초 만에 패턴 매칭으로 빠른 검색
        - **AI 채팅**: 15초 정도 소요되지만 더 자연스러운 대화 및 분석
        - **예시 질문**:
          - "남준수 기안자의 문서 특징은?"
          - "2024년 구매 문서들을 요약해줘"
          - "영상장비 수리 관련 문서들을 분석해줘"
        """)

    st.markdown("---")

    # 선택된 문서 미리보기 (사이드바에서 선택시)
    if 'selected_doc' in st.session_state and st.session_state.get('show_doc_preview', False):
        doc = st.session_state.selected_doc
        
        # 문서 정보 헤더
        st.markdown(f"### 📄 {doc['title']}")
        
        # 메타데이터와 컨트롤 버튼
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        
        with col1:
            st.caption(f"**기안자**: {doc['drafter'] if doc['drafter'] != '미상' else '미상'} | **날짜**: {doc['date']}")
        
        with col2:
            st.caption(f"**카테고리**: {doc['category']} | **파일**: {doc['filename']}")
        
        with col3:
            # Use the full path from metadata, not just filename
            file_path = Path(doc.get('path', Path(config.DOCS_DIR) / doc['filename']))
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    pdf_bytes = f.read()
                
                st.download_button(
                    label="📥 다운로드",
                    data=pdf_bytes,
                    file_name=doc['filename'],
                    mime="application/pdf",
                    key=f"dl_{hashlib.md5(doc['filename'].encode()).hexdigest()}",
                    use_container_width=True
                )
        
        with col4:
            if st.button("❌ 닫기", use_container_width=True):
                st.session_state.show_doc_preview = False
                if 'selected_doc' in st.session_state:
                    del st.session_state.selected_doc
                st.rerun()
        
        # 탭 구성: 질문/답변과 PDF 미리보기
        doc_tab1, doc_tab2 = st.tabs(["💬 문서 질문하기", "📖 PDF 미리보기"])
        
        with doc_tab1:
            st.success("🎯 **문서 전용 모드** - 이 문서에 대해서만 집중 분석합니다")
            
            # 전용 질문 입력
            col1, col2 = st.columns([5, 1])
            with col1:
                doc_query = st.text_input(
                    "이 문서에 대해 질문하세요",
                    placeholder=f"{doc['title']}에 대해 궁금한 점을 물어보세요",
                    key="doc_specific_query"
                )
            with col2:
                doc_submit = st.button("🔍 문서 검색", type="primary", key="doc_search_btn")
            
            # 답변 처리
            if doc_submit and doc_query:
                with st.spinner("🔍 문서를 분석하고 있습니다..."):
                    try:
                        answer = st.session_state.rag.answer_from_specific_document(doc_query, doc['filename'])
                        st.markdown("---")
                        st.markdown(answer)
                    except FileNotFoundError as e:
                        st.error(f"📁 파일을 찾을 수 없습니다: {doc['filename']}")
                        st.info("💡 파일이 이동되었거나 삭제되었을 수 있습니다. 재인덱싱을 시도해주세요")
                    except PermissionError as e:
                        st.error(f"🔒 파일 접근 권한이 없습니다: {doc['filename']}")
                        st.info("💡 파일이 다른 프로그램에서 사용 중이거나 권한이 제한되어 있습니다")
                    except MemoryError as e:
                        st.error(f"💾 메모리 부족: 너무 큰 문서를 처리하려고 합니다")
                        st.info("💡 문서를 개별로 검색하거나 시스템을 재시작해주세요")
                    except Exception as e:
                        st.error(f"❌ 예상치 못한 오류가 발생했습니다")
                        with st.expander("🔍 상세 오류 정보"):
                            st.text(f"오류 타입: {type(e).__name__}")
                            st.text(f"오류 메시지: {str(e)}")
                            import traceback
                            st.text("\n스택 트레이스:")
                            st.text(traceback.format_exc())
        
        with doc_tab2:
            st.info("📖 PDF 문서를 브라우저에서 직접 확인할 수 있습니다")
            
            # PDF 미리보기 제어 (성능 고려)
            if 'pdf_preview_shown' not in st.session_state:
                st.session_state.pdf_preview_shown = False
            
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                if st.button("👁️ PDF 미리보기 표시", type="primary", disabled=st.session_state.pdf_preview_shown):
                    st.session_state.pdf_preview_shown = True
                    st.rerun()
            
            with col2:
                if st.session_state.pdf_preview_shown:
                    if st.button("🔄 미리보기 숨기기"):
                        st.session_state.pdf_preview_shown = False
                        st.rerun()
            
            with col3:
                # 미리보기 높이 조절
                if st.session_state.pdf_preview_shown:
                    height = st.selectbox("높이", [500, 700, 900], index=1, label_visibility="collapsed")
                else:
                    height = 700
            
            # PDF 미리보기 표시
            if st.session_state.pdf_preview_shown:
                # Use the full path from metadata, not just filename
                file_path = Path(doc.get('path', Path(config.DOCS_DIR) / doc['filename']))
                if file_path.exists():
                    with st.spinner("📄 PDF 로딩 중..."):
                        show_pdf_preview(file_path, height)
                else:
                    st.error("PDF 파일을 찾을 수 없습니다")
        
        st.markdown("---")
    
    # 메인 영역 - 2개 탭만 (깔끔하게)
    # 기안서 중심 RAG 시스템 - 장비 자산 검색 탭 제거
    st.markdown("### 💬 기안서 문서 검색")

    # 문서 전용 모드가 활성화되어 있으면 안내만 표시
    if 'selected_doc' in st.session_state and st.session_state.get('show_doc_preview', False):
        st.info(f"📌 **문서 전용 모드 활성화 중**  \n위에서 [{st.session_state.selected_doc['filename']}] 문서를 분석 중입니다.  \n문서 전용 질문은 위의 탭을 이용해주세요.")
        submit = False
        query = None
    else:
        # 일반 모드일 때
        st.caption("💡 **문서 검색**: 질문 내용에 따라 자동으로 단일 문서 또는 다중 문서를 검색합니다.")

        # 질문 입력 폼 정렬을 위한 CSS
        st.markdown("""
        <style>
        /* 폼 전체 컨테이너 - 보더 제거 */
        .stForm {
            border: none !important;
            padding: 0 !important;
            background: transparent !important;
        }

        /* 핵심: 폼 내부 컬럼들을 수평 중앙 정렬 */
        .stForm [data-testid="stHorizontalBlock"] {
            display: flex !important;
            align-items: center !important;  /* 수직 중앙 정렬 */
            gap: 8px !important;  /* 요소 간 8px 간격 */
            margin: 0 !important;
            padding: 0 !important;
        }

        /* 각 컬럼 - 라벨과 입력 요소를 분리 */
        .stForm [data-testid="column"] {
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;  /* 수직 중앙 정렬 */
            padding: 0 !important;
            margin: 0 !important;
        }

        /* 첫 번째 컬럼(입력창) - 라벨 제거 또는 숨김 처리 */
        .stForm [data-testid="column"]:first-child label {
            display: none !important;  /* 라벨 숨김 */
        }

        /* 두 번째 컬럼(버튼) - 상단 여백 제거 */
        .stForm [data-testid="column"]:last-child {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }

        /* 입력창과 버튼 동일 높이(45px) 설정 */
        .stForm input[type="text"],
        .stForm input[type="text"]:focus {
            height: 45px !important;
            min-height: 45px !important;
            max-height: 45px !important;
            padding: 0 14px !important;
            font-size: 14px !important;
            line-height: 45px !important;
            border: 1px solid rgba(49, 51, 63, 0.2) !important;
            border-radius: 4px !important;
            margin: 0 !important;
            box-sizing: border-box !important;
        }

        /* 검색 버튼 - 입력창과 동일 높이 */
        .stForm button[type="submit"],
        .stForm button[kind="primary"] {
            height: 45px !important;
            min-height: 45px !important;
            max-height: 45px !important;
            padding: 0 24px !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            line-height: 45px !important;
            border-radius: 4px !important;
            margin: 0 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            white-space: nowrap !important;
            box-sizing: border-box !important;
        }

        /* 입력창 wrapper div 정렬 */
        .stForm .stTextInput > div {
            display: flex !important;
            align-items: center !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* 버튼 wrapper div 정렬 */
        .stForm .stFormSubmitButton > div {
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 45px !important;
        }

        /* 입력창 포커스 효과 */
        .stForm input[type="text"]:focus {
            border-color: #0068C9 !important;
            outline: none !important;
            box-shadow: 0 0 0 1px #0068C9 !important;
        }

        /* 반응형 - 모바일 */
        @media (max-width: 768px) {
            .stForm [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
                align-items: stretch !important;
                gap: 8px !important;
            }

            .stForm button[type="submit"],
            .stForm button[kind="primary"] {
                width: 100% !important;
            }
        }
        </style>
        """, unsafe_allow_html=True)

        # 질문 입력 - Enter 키로도 제출 가능하도록 form 사용
        with st.form(key="query_form", clear_on_submit=False):
            col1, col2 = st.columns([5, 1])
            with col1:
                query = st.text_input(
                    "질문을 입력하세요",
                    placeholder="예: 2024년 중계차 보수건 기안자 누구? / CCU 장비 몇 대? / 광화문 무선마이크 구매 내용",
                    key="query_input_form",
                    label_visibility="collapsed"  # 라벨 숨기기
                )
            with col2:
                submit = st.form_submit_button("🔍 검색", type="primary", use_container_width=True)
        
        # 답변 영역
        # Form 제출 시 처리
        final_query = query if submit else None
        
        if final_query:
            with st.spinner("🔍 답변을 생성하고 있습니다..."):
                try:
                    # 질문 자동 분석 - 다중 문서가 필요한지 판단
                    query_lower = final_query.lower()
                    # MultiDocumentSearch는 에러가 있으므로 사용하지 않음
                    needs_multi = False

                    if needs_multi:
                        # 다중 문서 모드 (자동 선택)
                        # MultiDocumentSearch 초기화
                        if 'multi_search' not in st.session_state:
                            from multi_doc_search import MultiDocumentSearch
                            st.session_state.multi_search = MultiDocumentSearch()

                        # 다중 문서 검색
                        search_results = st.session_state.multi_search.search_multiple_docs(final_query, top_k=5)

                        # 결과가 딕셔너리인 경우 documents 키에서 실제 문서 추출
                        if isinstance(search_results, dict) and 'documents' in search_results:
                            documents = search_results['documents']
                        elif isinstance(search_results, list):
                            documents = search_results
                        else:
                            documents = None

                        if documents:
                            # 종합 답변 생성
                            answer = st.session_state.multi_search.aggregate_answer(final_query, documents)
                        else:
                            # 다중 문서 검색 실패시 단일 문서로 폴백
                            answer = st.session_state.rag.answer(final_query)
                    else:
                        # 단일 문서 모드 (자동 선택)
                        answer = st.session_state.rag.answer(final_query)
                    
                    # 검색 결과를 session_state에 저장
                    st.session_state['last_query'] = final_query
                    st.session_state['last_answer'] = answer
                    
                    # 답변 표시
                    st.markdown("---")
                    
                    # 표 형식 처리
                    formatted_answer = format_answer_with_table(answer)
                    
                    # 검색 결과가 있는지 확인 (파일 목록이 있으면 카드 UI 사용)
                    has_search_results = ('검색 결과' in answer and '개 문서 발견' in answer) or \
                                       '@@PDF_PREVIEW@@' in answer or \
                                       re.search(r'\[([^\]]+\.pdf)\]', answer)

                    # 답변을 파싱하여 각 문서별로 카드 생성
                    if has_search_results and '@@PDF_PREVIEW@@' in answer:
                        # 검색 헤더 표시
                        if '검색 결과' in answer:
                            header_match = re.search(r"'(.+?)'.*검색 결과.*총 (\d+)개 문서", answer)
                            if header_match:
                                query_text = header_match.group(1)
                                doc_count = header_match.group(2)
                                st.markdown(f"## 🔍 '{query_text}' 검색 결과")
                                st.markdown(f"**총 {doc_count}개 문서 발견**")
                                st.markdown("---")

                        # 문서별로 파싱하여 카드 렌더링
                        lines = formatted_answer.split('\n')
                        current_doc = {}
                        in_doc = False

                        for line in lines:
                            # 연도 헤더
                            if '📅' in line and '년' in line:
                                st.markdown(line)

                            # 문서 시작 (이모지로 시작)
                            elif any(emoji in line for emoji in ['📋', '🔧', '🛒', '🗑️', '📄']):
                                # 이전 문서 렌더링
                                if current_doc and 'filename' in current_doc:
                                    render_document_card(current_doc.get('title', ''), current_doc)

                                # 새 문서 시작
                                current_doc = {'title': line}
                                in_doc = True

                            # 문서 정보 수집
                            elif in_doc:
                                if '[' in line and ']' in line and '|' in line:
                                    current_doc['category'] = line
                                elif '기안자:' in line:
                                    current_doc['drafter'] = line
                                elif '개요:' in line:
                                    current_doc['summary'] = line
                                elif '@@PDF_PREVIEW@@' in line:
                                    # 파일 경로 추출
                                    preview_match = re.search(r'@@PDF_PREVIEW@@(.+?)@@', line)
                                    if preview_match:
                                        file_path = preview_match.group(1)
                                        current_doc['filename'] = Path(file_path).name
                                        current_doc['path'] = str(Path(config.DOCS_DIR) / file_path)
                                        in_doc = False  # 문서 정보 수집 완료

                        # 마지막 문서 렌더링
                        if current_doc and 'filename' in current_doc:
                            render_document_card(current_doc.get('title', ''), current_doc)

                    elif has_search_results:
                        # PDF_PREVIEW 마커가 없는 경우 텍스트만 출력
                        st.markdown(formatted_answer)
                    else:
                        # 일반 답변 (문서 리스트가 아닌 경우)
                        # PDF_PREVIEW 마커 제거
                        cleaned_answer = re.sub(r'@@PDF_PREVIEW@@.+?@@', '📥', formatted_answer)
                        st.markdown(cleaned_answer)
                    
                    # 통합 UI로 인해 하단 다운로드 영역 제거
                    
                except ConnectionError as e:
                    st.error("🌐 네트워크 연결 오류")
                    st.info("💡 인터넷 연결을 확인하고 다시 시도해주세요")
                except TimeoutError as e:
                    st.error("⏱️ 시간 초과")
                    st.info("💡 요청이 너무 오래 걸립니다. 검색 범위를 좀덤거하거나 간단한 질문을 시도해주세요")
                except ImportError as e:
                    missing_module = str(e).split("'")[1] if "'" in str(e) else "unknown"
                    st.error(f"📦 필수 모듈 누락: {missing_module}")
                    st.info(f"💡 다음 명령을 실행해주세요: pip install {missing_module}")
                except ValueError as e:
                    st.error(f"🔢 입력값 오류: {str(e)}")
                    st.info("💡 올바른 형식으로 질문해주세요")
                except KeyError as e:
                    st.error(f"🔑 필수 필드 누락: {str(e)}")
                    st.info("💡 데이터 형식이 올바른지 확인해주세요")
                except Exception as e:
                    # 기타 모든 예외 처리
                    error_type = type(e).__name__
                    st.error(f"❌ 오류 발생 ({error_type})")

                    # 사용자 친화적인 오류 메시지
                    if 'cuda' in str(e).lower() or 'gpu' in str(e).lower():
                        st.info("🎮 GPU 관련 오류입니다. CPU 모드로 전환하거나 GPU 드라이버를 확인해주세요")
                    elif 'encoding' in str(e).lower() or 'decode' in str(e).lower():
                        st.info("📄 문자 인코딩 오류입니다. 파일이 UTF-8 형식인지 확인해주세요")
                    elif 'model' in str(e).lower():
                        st.info("🤖 AI 모델 로듩 오류입니다. 모델 파일이 올바른 위치에 있는지 확인해주세요")
                    else:
                        # 자세한 오류 정보 제공
                        with st.expander("🔍 오류 상세 정보 보기"):
                            st.text(f"오류 타입: {error_type}")
                            st.text(f"오류 메시지: {str(e)}")

                            # 스택 트레이스
                            import traceback
                            st.text("\n스택 트레이스:")
                            trace = traceback.format_exc()
                            # 긴 스택 트레이스는 생략하고 핵심만
                            lines = trace.split('\n')
                            if len(lines) > 20:
                                st.text('\n'.join(lines[:10]) + '\n...\n' + '\n'.join(lines[-10:]))
                            else:
                                st.text(trace)

                            # 해결 방법 제안
                            st.markdown("### 💡 해결 방법")
                            st.markdown("""
                            1. 페이지를 새로고침하거나 (F5) 세션을 초기화해보세요
                            2. 검색 범위를 좀더거하거나 다른 키워드로 시도해보세요
                            3. 문제가 계속되면 시스템 관리자에게 문의하세요
                            """)
        
        # 이전 검색 결과가 있으면 표시 (미리보기 등으로 인한 리렌더링 시)
        elif 'last_answer' in st.session_state and 'last_query' in st.session_state:
            # 이전 질문과 지우기 버튼 표시
            col1, col2 = st.columns([5, 1])
            with col1:
                st.info(f"📌 이전 검색: {st.session_state['last_query']}")
            with col2:
                if st.button("🗑️ 결과 지우기", key="clear_results"):
                    del st.session_state['last_query']
                    del st.session_state['last_answer']
                    # 모든 미리보기 상태도 초기화
                    keys_to_remove = [key for key in st.session_state.keys() if 'show_preview_' in key]
                    for key in keys_to_remove:
                        del st.session_state[key]
                    st.rerun()
            
            # 답변 표시
            st.markdown("---")
            
            # 표 형식 처리
            formatted_answer = format_answer_with_table(st.session_state['last_answer'])
            
            # PDF_PREVIEW 마커 확인
            has_preview_markers = '@@PDF_PREVIEW@@' in st.session_state['last_answer']

            # 답변을 파싱하여 각 문서별로 카드 생성
            if has_preview_markers:
                # 검색 헤더 표시
                if '검색 결과' in st.session_state['last_answer']:
                    header_match = re.search(r"'(.+?)'.*검색 결과.*총 (\d+)개 문서", st.session_state['last_answer'])
                    if header_match:
                        query_text = header_match.group(1)
                        doc_count = header_match.group(2)
                        st.markdown(f"## 🔍 '{query_text}' 검색 결과")
                        st.markdown(f"**총 {doc_count}개 문서 발견**")
                        st.markdown("---")
                # 문서별로 파싱하여 카드 렌더링
                lines = formatted_answer.split('\n')
                current_doc = {}
                in_doc = False

                for line in lines:
                    # 연도 헤더
                    if '📅' in line and '년' in line:
                        st.markdown(line)

                    # 문서 시작 (이모지로 시작)
                    elif any(emoji in line for emoji in ['📋', '🔧', '🛒', '🗑️', '📄']):
                        # 이전 문서 렌더링
                        if current_doc and 'filename' in current_doc:
                            render_document_card(current_doc.get('title', ''), current_doc)

                        # 새 문서 시작
                        current_doc = {'title': line}
                        in_doc = True

                    # 문서 정보 수집
                    elif in_doc:
                        if '[' in line and ']' in line and '|' in line:
                            current_doc['category'] = line
                        elif '기안자:' in line:
                            current_doc['drafter'] = line
                        elif '개요:' in line:
                            current_doc['summary'] = line
                        elif '@@PDF_PREVIEW@@' in line:
                            # 파일 경로 추출
                            preview_match = re.search(r'@@PDF_PREVIEW@@(.+?)@@', line)
                            if preview_match:
                                file_path = preview_match.group(1)
                                current_doc['filename'] = Path(file_path).name
                                current_doc['path'] = str(Path(config.DOCS_DIR) / file_path)
                                in_doc = False  # 문서 정보 수집 완료

                # 마짉 문서 렌더링
                if current_doc and 'filename' in current_doc:
                    render_document_card(current_doc.get('title', ''), current_doc)
            else:
                # 일반 답변 (문서 리스트가 아닌 경우)
                st.markdown(formatted_answer)

if __name__ == "__main__":
    main()
