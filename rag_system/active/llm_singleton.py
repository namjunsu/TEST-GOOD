"""
LLM 싱글톤 패턴 - 성능 최적화 버전
"""

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from rag_system.active.llm_wrapper import QwenLLM


class LLMSingleton:
    """LLM 인스턴스를 싱글톤으로 관리"""

    _instance: Optional[QwenLLM] = None
    _lock = threading.Lock()
    _stats_lock = threading.Lock()  # 통계 전용 락
    _initialized = False
    _load_time: float = 0.0
    _usage_count: int = 0
    _first_load_timestamp: Optional[datetime] = None
    _last_usage_timestamp: Optional[datetime] = None
    _total_processing_time: float = 0.0
    _model_config: dict[str, Any] = {}  # 초기 설정 저장

    # 로거
    _logger = logging.getLogger(__name__)

    @classmethod
    def get_instance(cls, model_path: Optional[str] = None, **kwargs) -> QwenLLM:
        """싱글톤 인스턴스 반환 (스레드 안전)"""

        # 빠른 체크 (락 없이)
        if cls._instance is not None:
            # 설정 변경 체크
            if model_path and cls._model_config.get("model_path") != model_path:
                cls._logger.warning(f"⚠️ 모델 경로 변경 시도 감지: {cls._model_config.get('model_path')} → {model_path}")
            if kwargs and cls._model_config.get("kwargs") != kwargs:
                cls._logger.warning(f"⚠️ 모델 설정 변경 시도 감지: {kwargs}")

            # 통계 업데이트 (통계 전용 락 사용)
            with cls._stats_lock:
                cls._usage_count += 1
                cls._last_usage_timestamp = datetime.now()
            return cls._instance

        # 더블 체크 락킹
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                cls._logger.info("🤖 LLM 모델 최초 로딩...")

                # 설정 저장
                cls._model_config = {
                    "model_path": model_path,
                    "kwargs": kwargs.copy() if kwargs else {}
                }

                cls._instance = QwenLLM(model_path=model_path, **kwargs)
                cls._load_time = time.time() - start_time
                cls._initialized = True
                cls._first_load_timestamp = datetime.now()
                cls._last_usage_timestamp = datetime.now()

                cls._logger.info(f"✅ LLM 로드 완료 ({cls._load_time:.1f}초)")
            else:
                # 이미 로드된 경우 - 통계만 업데이트
                with cls._stats_lock:
                    cls._usage_count += 1
                    cls._last_usage_timestamp = datetime.now()
                cls._logger.debug(f"♻️ LLM 재사용 (#{cls._usage_count})")

        return cls._instance

    @classmethod
    def is_loaded(cls) -> bool:
        """모델 로드 여부 확인"""
        return cls._initialized

    @classmethod
    @contextmanager
    def track_processing(cls):
        """처리 시간 추적용 컨텍스트 매니저"""
        start_time = time.time()
        try:
            yield
        finally:
            processing_time = time.time() - start_time
            with cls._stats_lock:
                cls._total_processing_time += processing_time
                cls._logger.debug(f"📊 처리 시간: {processing_time:.3f}초")

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        """사용 통계 반환 (확장된 메트릭, 스레드 안전)"""
        with cls._stats_lock:
            uptime = None
            if cls._first_load_timestamp:
                uptime = (datetime.now() - cls._first_load_timestamp).total_seconds()

            idle_time = None
            if cls._last_usage_timestamp:
                idle_time = (datetime.now() - cls._last_usage_timestamp).total_seconds()

            return {
                "loaded": cls._initialized,
                "load_time": cls._load_time,
                "usage_count": cls._usage_count,
                "first_load_timestamp": cls._first_load_timestamp.isoformat() if cls._first_load_timestamp else None,
                "last_usage_timestamp": cls._last_usage_timestamp.isoformat() if cls._last_usage_timestamp else None,
                "uptime_seconds": uptime,
                "idle_seconds": idle_time,
                "avg_processing_time": cls._total_processing_time / cls._usage_count if cls._usage_count > 0 else 0.0,
                "total_processing_time": cls._total_processing_time,
                "model_config": cls._model_config.copy()
            }

    @classmethod
    def clear(cls):
        """인스턴스 초기화 (메모리 정리용, 향상된 에러 처리)"""
        with cls._lock:
            if cls._instance:
                try:
                    # LLM 리소스 정리 시도
                    if hasattr(cls._instance, "llm") and cls._instance.llm:
                        cls._logger.debug("LLM 객체 메모리 해제 중...")
                        del cls._instance.llm

                    # 기타 리소스 정리 (있는 경우)
                    cls._instance = None

                except Exception as e:
                    cls._logger.warning(f"리소스 정리 중 오류 (무시됨): {e}")

                # 인스턴스 제거
                cls._instance = None
                cls._initialized = False

                # 통계 초기화 (통계 락 사용)
                with cls._stats_lock:
                    cls._first_load_timestamp = None
                    cls._last_usage_timestamp = None
                    cls._usage_count = 0
                    cls._total_processing_time = 0.0
                    cls._load_time = 0.0

                # 설정 초기화
                cls._model_config = {}

                cls._logger.info("🧹 LLM 인스턴스 정리 완료 (메모리 해제 및 통계 초기화)")
