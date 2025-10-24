"""
CSS 로더 유틸리티
외부 CSS 파일을 로드하여 Streamlit 앱에 적용
"""

import streamlit as st
from pathlib import Path


def load_css(css_file: str = "static/css/main.css"):
    """
    외부 CSS 파일을 로드하여 페이지에 적용

    Args:
        css_file: CSS 파일 경로 (프로젝트 루트 기준)
    """
    css_path = Path(__file__).parent.parent / css_file

    if css_path.exists():
        with open(css_path, 'r', encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
            return True
    else:
        st.warning(f"⚠️ CSS 파일을 찾을 수 없습니다: {css_file}")
        # 폴백: 최소한의 스타일 적용
        st.markdown("""
        <style>
            .stApp {
                background: linear-gradient(135deg, #87CEEB 0%, #1E5FA8 100%);
            }
        </style>
        """, unsafe_allow_html=True)
        return False


def load_all_css():
    """
    모든 CSS 파일을 로드 (main.css + sidebar.css)

    Returns:
        성공 여부
    """
    results = []
    results.append(load_css("static/css/main.css"))
    results.append(load_css("static/css/sidebar.css"))
    return all(results)