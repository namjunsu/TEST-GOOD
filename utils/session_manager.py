"""
세션 상태 관리 유틸리티
Streamlit 세션 상태를 중앙에서 관리

방송 기술관리팀 시스템 세션 관리:
- 가변 객체 안전한 초기화
- 디버그 모드 통합 관리 (ENV + Session)
- DataFrame 기반 디버그 정보
- 세션 백업/복원 기능
"""

import streamlit as st
from typing import Any, Dict, Optional, List
import json
from pathlib import Path
import pickle
import logging
import os
from copy import deepcopy
import pandas as pd

logger = logging.getLogger(__name__)


class SessionManager:
    """세션 상태 중앙 관리 클래스"""

    # 기본 세션 값 (가변 객체는 init_session에서 복사됨)
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
        'debug_mode': False  # 환경 변수로 초기화됨
    }

    @classmethod
    def init_session(cls):
        """세션 초기화 (한 번만 실행)

        가변 객체(list, dict, set)는 deepcopy하여 세션 간 공유 방지
        """
        for key, default_value in cls.DEFAULT_VALUES.items():
            if key not in st.session_state:
                # 가변 객체는 복사해서 사용 (세션 간 공유 방지)
                if isinstance(default_value, (list, dict, set)):
                    st.session_state[key] = deepcopy(default_value)
                else:
                    st.session_state[key] = default_value

        # debug_mode는 환경 변수에서 초기값 결정
        if 'debug_mode' not in st.session_state:
            env_debug = os.getenv('DEBUG_MODE', '').lower() in ('true', '1', 'yes', 'on')
            st.session_state['debug_mode'] = env_debug

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
        세션 클리어 (완전 초기화)

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

        # 기본값 재설정 (가변 객체는 새 인스턴스로 생성됨)
        cls.init_session()

        # 보존된 값 복원
        for key, value in preserved.items():
            st.session_state[key] = value

        logger.info("Session cleared and re-initialized")

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
        """채팅 기록 클리어 (새 리스트 인스턴스 생성)"""
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
    def export_session(
        cls,
        file_path: str = "session_backup.json",
        show_message: bool = True
    ) -> bool:
        """
        세션 상태 내보내기 (JSON 직렬화 가능한 값만)

        Args:
            file_path: 저장할 파일 경로
            show_message: UI 메시지 표시 여부

        Returns:
            성공 여부
        """
        try:
            # JSON 직렬화 가능한 데이터만 추출
            exportable = {}
            skipped_keys = []

            for key, value in st.session_state.items():
                if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    exportable[key] = value
                else:
                    skipped_keys.append(key)

            # 경로 안전성 검증 (상대 경로는 현재 디렉터리 기준)
            safe_path = Path(file_path)
            if not safe_path.is_absolute():
                safe_path = Path.cwd() / safe_path

            # 부모 디렉터리 생성
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # 파일로 저장
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump(exportable, f, indent=2, ensure_ascii=False)

            if show_message:
                st.success(f"✅ 세션이 {safe_path}에 저장되었습니다")
                if skipped_keys:
                    st.info(
                        f"ℹ️ JSON으로 내보낼 수 없는 키는 제외되었습니다: "
                        f"{', '.join(skipped_keys[:5])}"
                        f"{'...' if len(skipped_keys) > 5 else ''}"
                    )

            logger.info(f"Session exported to {safe_path} ({len(exportable)} keys)")
            return True

        except Exception as e:
            logger.error(f"Session export failed: {e}")
            if show_message:
                st.error(f"❌ 세션 내보내기 실패: {e}")
            return False

    @classmethod
    def import_session(
        cls,
        file_path: str = "session_backup.json",
        show_message: bool = True
    ) -> bool:
        """
        세션 상태 가져오기

        Args:
            file_path: 불러올 파일 경로
            show_message: UI 메시지 표시 여부

        Returns:
            성공 여부
        """
        try:
            safe_path = Path(file_path)
            if not safe_path.is_absolute():
                safe_path = Path.cwd() / safe_path

            if not safe_path.exists():
                if show_message:
                    st.error(f"❌ 파일을 찾을 수 없습니다: {safe_path}")
                return False

            # 파일에서 로드
            with open(safe_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 세션 상태 업데이트
            for key, value in data.items():
                st.session_state[key] = value

            if show_message:
                st.success(f"✅ 세션이 {safe_path}에서 복원되었습니다 ({len(data)}개 키)")

            logger.info(f"Session imported from {safe_path} ({len(data)} keys)")
            return True

        except Exception as e:
            logger.error(f"Session import failed: {e}")
            if show_message:
                st.error(f"❌ 세션 가져오기 실패: {e}")
            return False

    @classmethod
    def display_debug_info(cls):
        """디버그 정보 표시 (DataFrame 기반)"""
        with st.expander("🔍 세션 상태 디버그 정보"):
            sizes = cls.get_state_size()
            rows = []

            for key in sorted(st.session_state.keys()):
                value = st.session_state[key]
                value_type = type(value).__name__
                size = sizes.get(key, -1)
                size_kb = size / 1024 if size > 0 else None

                # 값 미리보기
                value_str = str(value)
                preview = value_str[:80] + ("..." if len(value_str) > 80 else "")

                rows.append({
                    "키": key,
                    "타입": value_type,
                    "크기(KB)": round(size_kb, 3) if size_kb is not None else None,
                    "미리보기": preview,
                })

            # 총 크기 표시
            total_size = sum(s for s in sizes.values() if s > 0)
            st.caption(f"📊 총 세션 크기: {total_size / 1024:.2f} KB | 총 키 개수: {len(rows)}개")

            # DataFrame 표시
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "크기(KB)": st.column_config.NumberColumn(format="%.3f"),
                    }
                )

                # 디버그 모드 토글
                current_debug = cls.get('debug_mode', False)
                new_debug = st.toggle(
                    "🐛 디버그 모드 활성화",
                    value=current_debug,
                    help="성능 타이머 및 상세 로그 표시"
                )
                if new_debug != current_debug:
                    cls.set('debug_mode', new_debug)
                    st.rerun()

            else:
                st.caption("세션 상태가 비어 있습니다.")

    @classmethod
    def is_debug_mode(cls) -> bool:
        """
        디버그 모드 확인 (세션 우선, 환경 변수 대체)

        Returns:
            디버그 모드 활성화 여부
        """
        # 세션 state 우선
        if cls.exists('debug_mode'):
            return bool(cls.get('debug_mode'))

        # 환경 변수 대체
        return os.getenv('DEBUG_MODE', '').lower() in ('true', '1', 'yes', 'on')

    @classmethod
    def _log_session_init(cls):
        """세션 초기화 로깅"""
        debug_status = "enabled" if cls.is_debug_mode() else "disabled"
        logger.info(f"Session initialized (debug mode: {debug_status})")


# 세션 관리 헬퍼 함수들 (UI 레벨 사용 권장)
def get_session(key: str, default: Any = None) -> Any:
    """세션 값 가져오기 (간단한 래퍼)"""
    return SessionManager.get(key, default)


def set_session(key: str, value: Any) -> None:
    """세션 값 설정 (간단한 래퍼)"""
    SessionManager.set(key, value)


def update_session(updates: Dict[str, Any]) -> None:
    """여러 세션 값 한번에 업데이트 (간단한 래퍼)"""
    SessionManager.update(updates)


def clear_session(preserve_keys: Optional[List[str]] = None) -> None:
    """세션 클리어 (간단한 래퍼)"""
    SessionManager.clear(preserve_keys)


def is_debug_mode() -> bool:
    """디버그 모드 확인 (간단한 래퍼)"""
    return SessionManager.is_debug_mode()