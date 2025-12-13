"""테스트 전역 설정 (conftest.py)

모든 테스트에서 공유하는 fixture 및 설정.
streamlit 등 외부 의존성 mock.
"""

import sys
from unittest.mock import MagicMock, Mock

import pytest

# ==============================================================================
# Streamlit Mock (session_state 지원)
# ==============================================================================


class MockSessionState:
    """Streamlit session_state Mock - dict-like + attribute 접근 지원"""

    def __init__(self):
        self._data = {}

    def __setattr__(self, name, value):
        if name == "_data":
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __getattr__(self, name):
        return self._data.get(name)

    def __contains__(self, name):
        return name in self._data

    def __setitem__(self, name, value):
        self._data[name] = value

    def __getitem__(self, name):
        return self._data[name]

    def get(self, name, default=None):
        return self._data.get(name, default)

    def __delattr__(self, name):
        if name in self._data:
            del self._data[name]

    def clear(self):
        self._data.clear()


def _create_streamlit_mock():
    """Streamlit mock 객체 생성"""
    st_mock = MagicMock()
    st_mock.session_state = MockSessionState()
    st_mock.error = Mock()
    st_mock.warning = Mock()
    st_mock.info = Mock()
    st_mock.caption = Mock()
    st_mock.success = Mock()
    st_mock.metric = Mock()
    st_mock.markdown = Mock()
    st_mock.expander = Mock(return_value=MagicMock(__enter__=Mock(), __exit__=Mock()))
    st_mock.columns = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
    st_mock.dataframe = Mock()
    st_mock.spinner = Mock(return_value=MagicMock(__enter__=Mock(), __exit__=Mock()))
    st_mock.toast = Mock()
    st_mock.rerun = Mock()

    # 유연한 데코레이터 mock: @st.cache_data와 @st.cache_data(ttl=300) 모두 지원
    def flexible_decorator(*args, **kwargs):
        """@decorator 또는 @decorator(args) 모두 지원"""
        if args and callable(args[0]):
            # @st.cache_data 형태 (인자 없이 직접 함수에 적용)
            return args[0]
        # @st.cache_data(ttl=300) 형태 (팩토리 패턴)
        return lambda func: func

    st_mock.cache_data = flexible_decorator
    st_mock.cache_resource = flexible_decorator

    return st_mock


# 전역 streamlit mock 설정
_st_mock = _create_streamlit_mock()

# 테스트 모듈 로드 전에 sys.modules에 등록
if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = _st_mock


@pytest.fixture(autouse=True)
def reset_streamlit_session():
    """각 테스트 전후로 streamlit session_state 초기화"""
    # 테스트 전: 세션 상태 초기화
    if hasattr(_st_mock, "session_state") and hasattr(_st_mock.session_state, "clear"):
        _st_mock.session_state.clear()

    yield

    # 테스트 후: 세션 상태 초기화
    if hasattr(_st_mock, "session_state") and hasattr(_st_mock.session_state, "clear"):
        _st_mock.session_state.clear()


# ==============================================================================
# Pandas Mock
# ==============================================================================

if "pandas" not in sys.modules:
    pd_mock = MagicMock()
    pd_mock.DataFrame = MagicMock(return_value=MagicMock())
    sys.modules["pandas"] = pd_mock
