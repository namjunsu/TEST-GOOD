"""
LLM 싱글톤 패턴 - 성능 최적화 버전
"""

import threading
from typing import Optional, Dict, Any
from rag_system.qwen_llm import QwenLLM
import time

class LLMSingleton:
    """LLM 인스턴스를 싱글톤으로 관리"""
    
    _instance: Optional[QwenLLM] = None
    _lock = threading.Lock()
    _initialized = False
    _load_time = 0
    _usage_count = 0
    
    @classmethod
    def get_instance(cls, model_path: str = None, **kwargs) -> QwenLLM:
        """싱글톤 인스턴스 반환 (스레드 안전)"""
        
        # 빠른 체크 (락 없이)
        if cls._instance is not None:
            cls._usage_count += 1
            return cls._instance
        
        # 더블 체크 락킹
        with cls._lock:
            if cls._instance is None:
                start_time = time.time()
                print("🤖 LLM 모델 최초 로딩...")
                
                cls._instance = QwenLLM(model_path=model_path)
                cls._load_time = time.time() - start_time
                cls._initialized = True
                
                print(f"✅ LLM 로드 완료 ({cls._load_time:.1f}초)")
            else:
                cls._usage_count += 1
                print(f"♻️ LLM 재사용 (#{cls._usage_count})")
        
        return cls._instance
    
    @classmethod
    def is_loaded(cls) -> bool:
        """모델 로드 여부 확인"""
        return cls._initialized
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """사용 통계 반환"""
        return {
            "loaded": cls._initialized,
            "load_time": cls._load_time,
            "usage_count": cls._usage_count
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
                print("🧹 LLM 인스턴스 정리 완료")
