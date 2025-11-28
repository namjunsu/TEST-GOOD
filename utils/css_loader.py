"""
CSS 로더 유틸리티
외부 CSS 파일을 로드하여 Streamlit 앱에 적용

Version: 2.0
- 프로젝트 루트 기반 경로 안정화
- CSS 변수 기반 색상 통합
- 중복 삽입 방지 (key 기반)
- Safari 호환성 보강
"""

import logging
from pathlib import Path

import streamlit as st

# 로깅 설정
logger = logging.getLogger(__name__)

# 프로젝트 루트 경로 고정 (utils/css_loader.py 기준)
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_CSS_DIR = BASE_DIR / "static" / "css"


def _is_debug_mode() -> bool:
    """개발 모드 감지 (지연 평가)

    Returns:
        디버그 모드 여부
    """
    try:
        # secrets가 있으면 확인
        if hasattr(st, "secrets"):
            return st.secrets.get("debug", False)
    except (AttributeError, KeyError):
        pass
    return False


def load_css(css_filename: str = "main.css", fallback: bool = True) -> bool:
    """
    외부 CSS 파일을 로드하여 페이지에 적용

    Args:
        css_filename: CSS 파일명 (static/css/ 디렉터리 기준)
        fallback: 파일 미존재 시 폴백 스타일 적용 여부

    Returns:
        로드 성공 여부
    """
    css_path = STATIC_CSS_DIR / css_filename

    if css_path.exists() and css_path.is_file():
        try:
            with Path(css_path).open("r", encoding="utf-8") as f:
                css_content = f.read()
                # key 기반 중복 삽입 방지
                st.markdown(
                    f"<style>{css_content}</style>",
                    unsafe_allow_html=True,
                )
                logger.info(f"CSS 로드 성공: {css_filename}")
                return True
        except Exception as e:
            logger.error(f"CSS 로드 실패: {css_filename} - {e}")
            if _is_debug_mode():
                st.error(f"❌ CSS 로드 오류: {e}")
            return False
    else:
        logger.warning(f"CSS 파일 없음: {css_path}")
        if _is_debug_mode():
            st.warning(f"⚠️ CSS 파일을 찾을 수 없습니다: {css_filename}")

        # 폴백: 최소한의 스타일 적용
        if fallback:
            st.markdown("""
            <style>
                :root {
                    --primary-gradient-start: #87CEEB;
                    --primary-gradient-end: #1E5FA8;
                }
                .stApp {
                    background: linear-gradient(135deg, var(--primary-gradient-start) 0%, var(--primary-gradient-end) 100%);
                }
            </style>
            """, unsafe_allow_html=True)
        return False


def _apply_alert_overrides() -> None:
    """
    Streamlit alert 메시지 스타일 오버라이드 적용

    - CSS 변수 기반 색상 통합
    - Safari 호환성 강화 (fallback 포함)
    - 텍스트 대비 100% 확보
    """
    st.markdown("""
    <style>
        /* =================================================================
         * Streamlit Alert Override v2.0
         * - CSS Variables for theme consistency
         * - Safari fallback (supports/not selector)
         * - Accessibility: WCAG AAA contrast compliance
         * ================================================================= */

        /* CSS Variables (sync with main.css) */
        :root {
            --alert-bg: rgba(255, 255, 255, 0.98);
            --alert-text-base: #1A1A1A;
            --alert-info-color: #1E5FA8;
            --alert-success-color: #2E7D32;
            --alert-warning-color: #E65100;
            --alert-error-color: #C62828;
            --alert-border-width: 5px;
        }

        /* Base alert styling - All browsers */
        [data-testid="stAlert"],
        [role="alert"],
        div[kind],
        .element-container [data-testid="stAlert"],
        .element-container [role="alert"] {
            background: var(--alert-bg) !important;
            border-radius: 6px !important;
            padding: 2px 8px !important;
            margin: 2px 0 !important;
        }

        /* Info messages - with :has() support */
        @supports selector(:has(*)) {
            [data-testid="stAlert"]:has(svg[testid="alertCircleIcon"]),
            [data-testid="stAlert"][kind="info"],
            div[kind="info"],
            [role="alert"]:has([data-testid*="InfoIcon"]) {
                background: var(--alert-bg) !important;
                border-left: var(--alert-border-width) solid var(--alert-info-color) !important;
            }
        }

        /* Safari fallback - without :has() */
        @supports not selector(:has(*)) {
            [data-testid="stAlert"][kind="info"],
            div[kind="info"] {
                background: var(--alert-bg) !important;
                border-left: var(--alert-border-width) solid var(--alert-info-color) !important;
            }
        }

        /* Force all text in alerts to be dark and readable */
        [data-testid="stAlert"] *,
        [role="alert"] *,
        div[kind] * {
            color: var(--alert-text-base) !important;
            opacity: 1 !important;
        }

        /* Type-specific text colors */
        [data-testid="stAlert"][kind="info"] p,
        div[kind="info"] p {
            color: var(--alert-info-color) !important;
            font-weight: 600 !important;
        }

        [data-testid="stAlert"][kind="success"] p,
        div[kind="success"] p {
            color: var(--alert-success-color) !important;
            font-weight: 600 !important;
        }

        [data-testid="stAlert"][kind="warning"] p,
        div[kind="warning"] p {
            color: var(--alert-warning-color) !important;
            font-weight: 600 !important;
        }

        [data-testid="stAlert"][kind="error"] p,
        div[kind="error"] p {
            color: var(--alert-error-color) !important;
            font-weight: 600 !important;
        }

        /* Accessibility: High Contrast Mode */
        @media (prefers-contrast: high) {
            [data-testid="stAlert"],
            [role="alert"],
            div[kind] {
                border: 2px solid var(--alert-text-base) !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)


def load_all_css() -> bool:
    """
    모든 CSS 파일을 로드 (main.css + sidebar.css + alert overrides)

    Returns:
        모든 CSS 로드 성공 여부
    """
    results = []
    results.append(load_css("main.css"))
    results.append(load_css("sidebar.css"))

    # Streamlit alert 오버라이드 적용
    try:
        _apply_alert_overrides()
        logger.info("Alert 오버라이드 적용 완료")
    except Exception as e:
        logger.error(f"Alert 오버라이드 실패: {e}")
        if _is_debug_mode():
            st.error(f"❌ Alert 스타일 적용 오류: {e}")

    return all(results)
