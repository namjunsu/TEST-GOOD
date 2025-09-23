#!/usr/bin/env python3
"""
UI 개선 시스템
==============
사용자 경험을 향상시키는 UI 컴포넌트
"""

import streamlit as st
from typing import Optional, Dict, Any, List
import time
from datetime import datetime
import random
import json

class UIEnhancer:
    """UI 개선 클래스"""

    def __init__(self):
        self.animations = True
        self.sound_effects = False
        self.themes = {
            'default': {
                'primary': '#1E88E5',
                'background': '#FFFFFF',
                'text': '#262730'
            },
            'dark': {
                'primary': '#FFA726',
                'background': '#0E1117',
                'text': '#FAFAFA'
            },
            'cyberpunk': {
                'primary': '#00FF41',
                'background': '#0D0208',
                'text': '#00FF41'
            }
        }

    def loading_animation(self, text: str = "처리 중", duration: float = 2.0):
        """로딩 애니메이션"""
        placeholder = st.empty()
        animations = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        start_time = time.time()
        i = 0
        while time.time() - start_time < duration:
            placeholder.markdown(f"### {animations[i % len(animations)]} {text}...")
            time.sleep(0.1)
            i += 1

        placeholder.empty()

    def progress_bar(self, current: int, total: int, text: str = ""):
        """진행률 바"""
        progress = current / total if total > 0 else 0
        bar = st.progress(progress)

        if text:
            st.write(f"{text}: {current}/{total} ({progress*100:.1f}%)")

        return bar

    def success_message(self, message: str):
        """성공 메시지"""
        st.success(f"✅ {message}")
        if self.sound_effects:
            self._play_sound('success')

    def error_message(self, message: str, details: Optional[str] = None):
        """에러 메시지"""
        st.error(f"❌ {message}")
        if details:
            with st.expander("상세 정보 보기"):
                st.code(details)
        if self.sound_effects:
            self._play_sound('error')

    def info_card(self, title: str, content: Dict[str, Any]):
        """정보 카드"""
        with st.container():
            st.markdown(f"""
            <div style="
                background-color: #f0f2f6;
                border-radius: 10px;
                padding: 20px;
                margin: 10px 0;
                border-left: 5px solid #1E88E5;
            ">
                <h3 style="margin: 0 0 10px 0;">{title}</h3>
            """, unsafe_allow_html=True)

            for key, value in content.items():
                st.markdown(f"**{key}:** {value}")

            st.markdown("</div>", unsafe_allow_html=True)

    def metric_display(self, metrics: List[Dict]):
        """메트릭 표시"""
        cols = st.columns(len(metrics))
        for i, metric in enumerate(metrics):
            with cols[i]:
                st.metric(
                    label=metric['label'],
                    value=metric['value'],
                    delta=metric.get('delta'),
                    delta_color=metric.get('delta_color', 'normal')
                )

    def _play_sound(self, sound_type: str):
        """소리 효과 재생 (placeholder)"""
        pass  # 실제 구현은 웹 오디오 API 필요

class SmartTooltips:
    """스마트 툴팁 시스템"""

    def __init__(self):
        self.tips = {
            'search': "💡 Tip: '2020년 구매' 같은 자연어로 검색해보세요",
            'filter': "💡 Tip: 여러 필터를 조합하면 더 정확한 결과를 얻을 수 있습니다",
            'cache': "💡 Tip: 같은 검색은 캐시에서 즉시 응답됩니다",
            'performance': "💡 Tip: 문서가 많을수록 첫 검색이 느릴 수 있습니다"
        }

    def show_context_tip(self, context: str):
        """맥락별 툴팁 표시"""
        if context in self.tips:
            st.info(self.tips[context])

    def add_help_button(self, key: str, help_text: str):
        """도움말 버튼 추가"""
        if st.button("ℹ️", key=f"help_{key}"):
            st.info(help_text)

class ResponseFormatter:
    """응답 포맷터"""

    def __init__(self):
        self.format_styles = {
            'simple': self._format_simple,
            'detailed': self._format_detailed,
            'markdown': self._format_markdown,
            'json': self._format_json
        }

    def format_response(self, response: str, style: str = 'markdown') -> str:
        """응답 포맷팅"""
        formatter = self.format_styles.get(style, self._format_markdown)
        return formatter(response)

    def _format_simple(self, response: str) -> str:
        """단순 포맷"""
        return response.replace('\n\n', '\n')

    def _format_detailed(self, response: str) -> str:
        """상세 포맷"""
        sections = response.split('\n\n')
        formatted = []
        for i, section in enumerate(sections):
            if section.strip():
                formatted.append(f"### 섹션 {i+1}\n{section}")
        return '\n\n'.join(formatted)

    def _format_markdown(self, response: str) -> str:
        """마크다운 포맷"""
        # 자동 하이라이팅
        response = response.replace('**중요**', '🔴 **중요**')
        response = response.replace('**참고**', '📌 **참고**')
        response = response.replace('**팁**', '💡 **팁**')
        return response

    def _format_json(self, response: str) -> str:
        """JSON 포맷"""
        try:
            data = json.loads(response)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except:
            return response

class UserFeedback:
    """사용자 피드백 시스템"""

    def __init__(self):
        self.feedback_file = "logs/user_feedback.json"
        self.load_feedback()

    def load_feedback(self):
        """피드백 로드"""
        try:
            with open(self.feedback_file, 'r') as f:
                self.feedbacks = json.load(f)
        except:
            self.feedbacks = []

    def save_feedback(self):
        """피드백 저장"""
        with open(self.feedback_file, 'w') as f:
            json.dump(self.feedbacks, f, indent=2, ensure_ascii=False)

    def collect_feedback(self, query: str, response: str):
        """피드백 수집"""
        col1, col2, col3 = st.columns([1, 1, 3])

        with col1:
            if st.button("👍 도움됨"):
                self._save_rating(query, response, 'positive')
                st.success("감사합니다!")

        with col2:
            if st.button("👎 개선필요"):
                self._save_rating(query, response, 'negative')
                st.info("피드백 감사합니다. 개선하겠습니다.")

        with col3:
            comment = st.text_input("추가 의견 (선택사항)", key=f"feedback_{hash(query)}")
            if comment:
                self._save_comment(query, comment)

    def _save_rating(self, query: str, response: str, rating: str):
        """평가 저장"""
        feedback = {
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'response': response[:200],  # 처음 200자만
            'rating': rating
        }
        self.feedbacks.append(feedback)
        self.save_feedback()

    def _save_comment(self, query: str, comment: str):
        """코멘트 저장"""
        feedback = {
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'comment': comment
        }
        self.feedbacks.append(feedback)
        self.save_feedback()

    def get_stats(self) -> Dict:
        """피드백 통계"""
        positive = sum(1 for f in self.feedbacks if f.get('rating') == 'positive')
        negative = sum(1 for f in self.feedbacks if f.get('rating') == 'negative')
        total = positive + negative

        return {
            'total': total,
            'positive': positive,
            'negative': negative,
            'satisfaction_rate': (positive / total * 100) if total > 0 else 0
        }

class QuickActions:
    """빠른 작업 버튼"""

    def __init__(self):
        self.actions = [
            {'label': '🔄 새로고침', 'action': 'refresh'},
            {'label': '🗑️ 캐시 정리', 'action': 'clear_cache'},
            {'label': '📊 통계 보기', 'action': 'show_stats'},
            {'label': '⚙️ 설정', 'action': 'settings'},
            {'label': '❓ 도움말', 'action': 'help'}
        ]

    def render(self):
        """빠른 작업 렌더링"""
        cols = st.columns(len(self.actions))
        results = {}

        for i, action in enumerate(self.actions):
            with cols[i]:
                if st.button(action['label'], key=f"quick_{action['action']}"):
                    results[action['action']] = True

        return results

    def handle_action(self, action: str):
        """작업 처리"""
        if action == 'refresh':
            st.experimental_rerun()
        elif action == 'clear_cache':
            st.cache_data.clear()
            st.success("캐시가 정리되었습니다")
        elif action == 'show_stats':
            self._show_stats()
        elif action == 'settings':
            self._show_settings()
        elif action == 'help':
            self._show_help()

    def _show_stats(self):
        """통계 표시"""
        with st.expander("📊 시스템 통계"):
            st.write("TODO: 통계 구현")

    def _show_settings(self):
        """설정 표시"""
        with st.expander("⚙️ 설정"):
            st.write("TODO: 설정 구현")

    def _show_help(self):
        """도움말 표시"""
        with st.expander("❓ 도움말"):
            st.markdown("""
            ### 사용 방법
            1. 질문을 입력하세요
            2. 검색 버튼을 클릭하세요
            3. 결과를 확인하세요

            ### 팁
            - 자연어로 검색 가능
            - 연도, 금액, 담당자로 필터링 가능
            - 캐시 사용으로 빠른 응답
            """)

# 전역 인스턴스
ui_enhancer = UIEnhancer()
tooltips = SmartTooltips()
formatter = ResponseFormatter()
feedback = UserFeedback()
quick_actions = QuickActions()

# Streamlit 통합 함수
def enhance_streamlit_ui():
    """Streamlit UI 개선 적용"""

    # 커스텀 CSS
    st.markdown("""
    <style>
    .stButton > button {
        background-color: #1E88E5;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background-color: #1565C0;
        transform: translateY(-2px);
        box-shadow: 0 5px 10px rgba(0,0,0,0.2);
    }
    .stTextInput > div > div > input {
        border-radius: 5px;
        border: 2px solid #E0E0E0;
        padding: 0.5rem;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1E88E5;
        box-shadow: 0 0 0 2px rgba(30,136,229,0.2);
    }
    </style>
    """, unsafe_allow_html=True)

# 사용 예제
if __name__ == "__main__":
    st.set_page_config(page_title="UI 개선 테스트", layout="wide")

    st.title("🎨 UI 개선 시스템 테스트")

    # 빠른 작업
    actions = quick_actions.render()
    for action, triggered in actions.items():
        if triggered:
            quick_actions.handle_action(action)

    # 메트릭 표시
    ui_enhancer.metric_display([
        {'label': '문서 수', 'value': '812개', 'delta': '+12'},
        {'label': '응답 시간', 'value': '0.5초', 'delta': '-2.5초', 'delta_color': 'inverse'},
        {'label': '캐시 히트율', 'value': '85%', 'delta': '+15%'}
    ])

    # 로딩 애니메이션
    if st.button("로딩 테스트"):
        ui_enhancer.loading_animation("검색 중", 2.0)
        ui_enhancer.success_message("검색 완료!")

    # 피드백
    feedback.collect_feedback("테스트 질문", "테스트 응답")

    # 툴팁
    tooltips.show_context_tip('search')