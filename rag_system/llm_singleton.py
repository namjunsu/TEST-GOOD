"""
LLM 싱글톤 패턴 - 성능 최적화 버전
"""

import threading
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from rag_system.qwen_llm import QwenLLM

class LLMSingleton:
    """LLM 인스턴스를 싱글톤으로 관리"""

    _instance: Optional[QwenLLM] = None
    _lock = threading.Lock()
    _initialized = False
    _load_time: float = 0.0
    _usage_count: int = 0
    _first_load_timestamp: Optional[datetime] = None
    _last_usage_timestamp: Optional[datetime] = None
    _total_processing_time: float = 0.0

    # 로거
    _logger = logging.getLogger(__name__)
    
    @classmethod
    def get_instance(cls, model_path: str = None, **kwargs) -> QwenLLM:
        """싱글톤 인스턴스 반환 (스레드 안전)"""
        
        # 빠른 체크 (락 없이)
        if cls._instance is not None:
            cls._usage_count += 1
            cls._last_usage_timestamp = datetime.now()
            return cls._instance

        # 더블 체크 락킹
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                cls._logger.info("🤖 LLM 모델 최초 로딩...")

                cls._instance = QwenLLM(model_path=model_path, **kwargs)
                cls._load_time = time.time() - start_time
                cls._initialized = True
                cls._first_load_timestamp = datetime.now()
                cls._last_usage_timestamp = datetime.now()

                cls._logger.info(f"✅ LLM 로드 완료 ({cls._load_time:.1f}초)")
            else:
                cls._usage_count += 1
                cls._last_usage_timestamp = datetime.now()
                cls._logger.debug(f"♻️ LLM 재사용 (#{cls._usage_count})")
        
        return cls._instance
    
    @classmethod
    def is_loaded(cls) -> bool:
        """모델 로드 여부 확인"""
        return cls._initialized
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """사용 통계 반환 (확장된 메트릭)"""
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
            "avg_processing_time": cls._total_processing_time / cls._usage_count if cls._usage_count > 0 else 0.0
        }
    
    @classmethod
    def clear(cls):
        """인스턴스 초기화 (메모리 정리용)"""
        with cls._lock:
            if cls._instance:
                try:
                    # LLM 리소스 정리
                    if hasattr(cls._instance, 'llm') and cls._instance.llm:
                        del cls._instance.llm
                except:
                    pass
                
                cls._instance = None
                cls._initialized = False
                cls._first_load_timestamp = None
                cls._last_usage_timestamp = None
                cls._usage_count = 0
                cls._total_processing_time = 0.0
                cls._logger.info("🧹 LLM 인스턴스 정리 완료")
