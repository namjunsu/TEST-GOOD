"""
세션 상태 관리 유틸리티
Streamlit 세션 상태를 중앙에서 관리
"""

import streamlit as st
from typing import Any, Dict, Optional, List
import json
from pathlib import Path
import pickle


class SessionManager:
    """세션 상태 중앙 관리 클래스"""

    # 기본 세션 값
    DEFAULT_VALUES = {
        'messages': [],
        'selected_doc': None,
        'show_doc_preview': False,
        'pdf_preview_shown': False,
        'unified_rag': None,
        'documents_df': None,
        'auto_indexer': None,
        'ocr_processor': None,
        'performance_metrics': {},
        'debug_mode': False
    }

    @classmethod
    def init_session(cls):
        """세션 초기화 (한 번만 실행)"""
        for key, default_value in cls.DEFAULT_VALUES.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

        # 초기화 플래그
        if 'session_initialized' not in st.session_state:
            st.session_state.session_initialized = True
            cls._log_session_init()

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        안전한 세션 값 가져오기

        Args:
            key: 세션 키
            default: 기본값

        Returns:
            세션 값 또는 기본값
        """
        return st.session_state.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        세션 값 설정

        Args:
            key: 세션 키
            value: 설정할 값
        """
        st.session_state[key] = value

    @classmethod
    def update(cls, updates: Dict[str, Any]) -> None:
        """
        여러 세션 값 한번에 업데이트

        Args:
            updates: 업데이트할 키-값 딕셔너리
        """
        for key, value in updates.items():
            st.session_state[key] = value

    @classmethod
    def delete(cls, key: str) -> bool:
        """
        세션 값 삭제

        Args:
            key: 삭제할 키

        Returns:
            삭제 성공 여부
        """
        if key in st.session_state:
            del st.session_state[key]
            return True
        return False

    @classmethod
    def exists(cls, key: str) -> bool:
        """
        세션 키 존재 여부 확인

        Args:
            key: 확인할 키

        Returns:
            존재 여부
        """
        return key in st.session_state

    @classmethod
    def clear(cls, preserve_keys: Optional[List[str]] = None) -> None:
        """
        세션 클리어

        Args:
            preserve_keys: 유지할 키 리스트
        """
        if preserve_keys is None:
            preserve_keys = []

        # 보존할 값 백업
        preserved = {}
        for key in preserve_keys:
            if key in st.session_state:
                preserved[key] = st.session_state[key]

        # 세션 클리어
        for key in list(st.session_state.keys()):
            if key not in preserve_keys:
                del st.session_state[key]

        # 기본값 재설정
        cls.init_session()

        # 보존된 값 복원
        for key, value in preserved.items():
            st.session_state[key] = value

    @classmethod
    def clear_doc_preview(cls) -> None:
        """문서 미리보기 관련 세션 클리어"""
        cls.update({
            'show_doc_preview': False,
            'selected_doc': None,
            'pdf_preview_shown': False
        })

    @classmethod
    def clear_chat_history(cls) -> None:
        """채팅 기록 클리어"""
        st.session_state.messages = []

    @classmethod
    def get_state_size(cls) -> Dict[str, int]:
        """
        세션 상태 크기 정보

        Returns:
            각 키별 대략적인 크기 (바이트)
        """
        sizes = {}
        for key, value in st.session_state.items():
            try:
                # pickle을 사용해 크기 추정
                sizes[key] = len(pickle.dumps(value))
            except Exception:
                sizes[key] = -1  # 크기를 측정할 수 없음

        return sizes

    @classmethod
    def export_session(cls, file_path: str = "session_backup.json") -> bool:
        """
        세션 상태 내보내기

        Args:
            file_path: 저장할 파일 경로

        Returns:
            성공 여부
        """
        try:
            # JSON 직렬화 가능한 데이터만 추출
            exportable = {}
            for key, value in st.session_state.items():
                if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    exportable[key] = value

            # 파일로 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(exportable, f, indent=2, ensure_ascii=False)

            st.success(f"세션이 {file_path}에 저장되었습니다")
            return True

        except Exception as e:
            st.error(f"세션 내보내기 실패: {e}")
            return False

    @classmethod
    def import_session(cls, file_path: str = "session_backup.json") -> bool:
        """
        세션 상태 가져오기

        Args:
            file_path: 불러올 파일 경로

        Returns:
            성공 여부
        """
        try:
            if not Path(file_path).exists():
                st.error(f"파일을 찾을 수 없습니다: {file_path}")
                return False

            # 파일에서 로드
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 세션 상태 업데이트
            for key, value in data.items():
                st.session_state[key] = value

            st.success(f"세션이 {file_path}에서 복원되었습니다")
            return True

        except Exception as e:
            st.error(f"세션 가져오기 실패: {e}")
            return False

    @classmethod
    def display_debug_info(cls):
        """디버그 정보 표시"""
        with st.expander("🔍 세션 상태 디버그 정보"):
            # 세션 크기 정보
            sizes = cls.get_state_size()
            total_size = sum(s for s in sizes.values() if s > 0)
            st.text(f"총 세션 크기: {total_size / 1024:.2f} KB")

            # 각 키별 정보
            st.text("세션 키별 정보:")
            for key in sorted(st.session_state.keys()):
                value = st.session_state[key]
                value_type = type(value).__name__
                size = sizes.get(key, -1)
                size_str = f"{size / 1024:.2f} KB" if size > 0 else "측정 불가"

                # 값 미리보기 (길면 자르기)
                value_preview = str(value)[:50]
                if len(str(value)) > 50:
                    value_preview += "..."

                st.text(f"  {key}: {value_type} ({size_str})")
                st.text(f"    → {value_preview}")

    @classmethod
    def _log_session_init(cls):
        """세션 초기화 로깅"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Session initialized with default values")


# 세션 관리 헬퍼 함수들
def get_session(key: str, default: Any = None) -> Any:
    """세션 값 가져오기 (간단한 래퍼)"""
    return SessionManager.get(key, default)


def set_session(key: str, value: Any) -> None:
    """세션 값 설정 (간단한 래퍼)"""
    SessionManager.set(key, value)


def clear_session(preserve_keys: Optional[List[str]] = None) -> None:
    """세션 클리어 (간단한 래퍼)"""
    SessionManager.clear(preserve_keys)