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
from hybrid_chat_rag_v2 import UnifiedRAG
from utils.css_loader import load_all_css  # CSS 로더 임포트
from components.pdf_viewer import show_pdf_preview  # PDF 뷰어 컴포넌트
from utils.document_loader import load_documents  # 문서 로더
from components.sidebar_library import render_sidebar_library  # 사이드바 컴포넌트

# 페이지 설정
st.set_page_config(
    page_title="Channel A MEDIATECH RAG",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일 적용 (외부 파일에서 로드: main.css + sidebar.css)
load_all_css()


def initialize_rag_system():
    """RAG 시스템 초기화 (한 번만 실행) - UnifiedRAG 사용 (LLM 포함)"""
    import importlib
    import sys

    # 모듈 재로드로 최신 버전 보장
    if 'hybrid_chat_rag_v2' in sys.modules:
        importlib.reload(sys.modules['hybrid_chat_rag_v2'])

    from hybrid_chat_rag_v2 import UnifiedRAG
    print("🚀 UnifiedRAG 초기화 중... (LLM 포함)")
    return UnifiedRAG()

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
            st.image('channel_a_logo_inverted.png', use_container_width=True)
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
    
    # 사이드바 - 문서 라이브러리 (컴포넌트)
    with st.sidebar:
        render_sidebar_library(st.session_state.rag)
    
    # ===== 메인 화면: AI 채팅 =====
    # UnifiedRAG 초기화 (자동 모드)
    # 강제 재초기화 (모든 구버전 제거)
    if 'hybrid_chat_rag' in st.session_state:
        del st.session_state.hybrid_chat_rag

    # OCR 캐시 업데이트 체크 (파일 수정 시간)
    import os
    ocr_cache_path = "docs/.ocr_cache.json"
    if os.path.exists(ocr_cache_path):
        ocr_cache_mtime = os.path.getmtime(ocr_cache_path)
        if 'ocr_cache_mtime' not in st.session_state or st.session_state.ocr_cache_mtime != ocr_cache_mtime:
            # OCR 캐시가 업데이트됨 - 강제 재초기화
            if 'unified_rag' in st.session_state:
                del st.session_state.unified_rag
            st.session_state.ocr_cache_mtime = ocr_cache_mtime

    # 최초 1회만 초기화
    if 'unified_rag' not in st.session_state:
        with st.spinner("🔄 통합 시스템 초기화 중..."):
            st.session_state.unified_rag = UnifiedRAG()

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
                    response = st.session_state.unified_rag.answer(enhanced_query)

                    # 응답 표시
                    message_placeholder.markdown(response)

                    # 메시지 저장
                    st.session_state.messages.append({"role": "assistant", "content": response})

                except Exception as e:
                    error_msg = f"죄송합니다. 오류가 발생했습니다: {str(e)}"
                    message_placeholder.markdown(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

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


if __name__ == "__main__":
    main()
