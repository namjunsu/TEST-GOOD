#!/usr/bin/env python3
"""
통합 에러 핸들링 시스템
======================
모든 에러를 체계적으로 관리하고 자동 복구
"""

import sys
import traceback
import logging
from typing import Any, Callable, Optional, Dict, List
from datetime import datetime
from functools import wraps
import json
from pathlib import Path
import time
import psutil
import gc

class ErrorHandler:
    """통합 에러 핸들링 클래스"""

    def __init__(self, log_dir: str = "logs/errors"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.error_count = {}
        self.recovery_strategies = {}
        self.setup_logging()

    def setup_logging(self):
        """에러 전용 로깅 설정"""
        self.logger = logging.getLogger("ErrorHandler")
        self.logger.setLevel(logging.ERROR)

        # 파일 핸들러
        error_file = self.log_dir / f"errors_{datetime.now():%Y%m%d}.log"
        fh = logging.FileHandler(error_file)
        fh.setLevel(logging.ERROR)

        # JSON 포맷터
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","error":"%(message)s"}'
        )
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def safe_execute(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        """안전한 함수 실행"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.handle_error(e, func.__name__)
            return None

    def handle_error(self, error: Exception, context: str = "Unknown"):
        """에러 처리 및 로깅"""
        error_type = type(error).__name__
        error_msg = str(error)

        # 에러 카운트
        key = f"{context}:{error_type}"
        self.error_count[key] = self.error_count.get(key, 0) + 1

        # 에러 정보 수집
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "error_type": error_type,
            "error_message": error_msg,
            "traceback": traceback.format_exc(),
            "occurrence_count": self.error_count[key],
            "system_info": self._get_system_info()
        }

        # 로깅
        self.logger.error(json.dumps(error_info))

        # 자동 복구 시도
        if key in self.recovery_strategies:
            self._attempt_recovery(key, error_info)

    def _get_system_info(self) -> Dict:
        """시스템 정보 수집"""
        try:
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
                "process_count": len(psutil.pids())
            }
        except:
            return {}

    def _attempt_recovery(self, error_key: str, error_info: Dict):
        """자동 복구 시도"""
        strategy = self.recovery_strategies.get(error_key)
        if strategy:
            try:
                print(f"🔧 자동 복구 시도: {error_key}")
                strategy(error_info)
                print(f"✅ 복구 성공: {error_key}")
            except Exception as e:
                print(f"❌ 복구 실패: {e}")

    def register_recovery(self, context: str, error_type: str, strategy: Callable):
        """복구 전략 등록"""
        key = f"{context}:{error_type}"
        self.recovery_strategies[key] = strategy

    def get_error_stats(self) -> Dict:
        """에러 통계 반환"""
        return {
            "total_errors": sum(self.error_count.values()),
            "error_types": len(self.error_count),
            "details": self.error_count,
            "top_errors": sorted(
                self.error_count.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }

class SmartErrorDecorator:
    """스마트 에러 데코레이터"""

    def __init__(self, handler: ErrorHandler):
        self.handler = handler

    def catch_errors(self, retry_count: int = 3, delay: float = 1.0):
        """에러 캐치 데코레이터"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(retry_count):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        self.handler.handle_error(e, func.__name__)
                        if attempt < retry_count - 1:
                            time.sleep(delay * (attempt + 1))
                            print(f"🔄 재시도 {attempt + 2}/{retry_count}: {func.__name__}")

                # 모든 재시도 실패
                print(f"❌ 최종 실패: {func.__name__}")
                raise last_error

            return wrapper
        return decorator

    def fallback(self, default_value: Any = None):
        """폴백 값 반환 데코레이터"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.handler.handle_error(e, func.__name__)
                    return default_value
            return wrapper
        return decorator

class MemoryGuard:
    """메모리 보호 시스템"""

    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold

    def check_memory(self):
        """메모리 체크 및 정리"""
        memory = psutil.virtual_memory()
        if memory.percent > self.threshold:
            print(f"⚠️  메모리 사용률 높음: {memory.percent:.1f}%")
            self._cleanup_memory()

    def _cleanup_memory(self):
        """메모리 정리"""
        print("🧹 메모리 정리 중...")
        gc.collect()

        # 캐시 정리
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        # 프로세스 메모리 정보
        process = psutil.Process()
        memory_info = process.memory_info()
        print(f"📊 프로세스 메모리: {memory_info.rss / 1024 / 1024:.1f} MB")

# 전역 인스턴스
error_handler = ErrorHandler()
decorator = SmartErrorDecorator(error_handler)
memory_guard = MemoryGuard()

# 일반적인 복구 전략들
def restart_service_strategy(error_info: Dict):
    """서비스 재시작 전략"""
    import subprocess
    context = error_info.get('context', '')
    if 'streamlit' in context.lower():
        subprocess.run(['pkill', '-f', 'streamlit'])
        time.sleep(2)
        subprocess.Popen(['streamlit', 'run', 'web_interface.py'])

def clear_cache_strategy(error_info: Dict):
    """캐시 정리 전략"""
    cache_dirs = ['.cache', '__pycache__', 'rag_system/__pycache__']
    for cache_dir in cache_dirs:
        if Path(cache_dir).exists():
            import shutil
            shutil.rmtree(cache_dir)
    print("✅ 캐시 정리 완료")

def reduce_memory_strategy(error_info: Dict):
    """메모리 감소 전략"""
    memory_guard._cleanup_memory()

    # 설정 조정
    try:
        import config
        if hasattr(config, 'N_BATCH'):
            config.N_BATCH = max(32, config.N_BATCH // 2)
        if hasattr(config, 'MAX_DOCUMENTS'):
            config.MAX_DOCUMENTS = max(10, config.MAX_DOCUMENTS // 2)
    except:
        pass

# 복구 전략 등록
error_handler.register_recovery("perfect_rag", "MemoryError", reduce_memory_strategy)
error_handler.register_recovery("web_interface", "ConnectionError", restart_service_strategy)
error_handler.register_recovery("auto_indexer", "FileNotFoundError", clear_cache_strategy)

# 사용 예제
if __name__ == "__main__":
    print("🛡️ 에러 핸들러 테스트")

    @decorator.catch_errors(retry_count=2)
    def risky_function():
        import random
        if random.random() > 0.5:
            raise ValueError("테스트 에러")
        return "성공!"

    @decorator.fallback(default_value="기본값")
    def fallback_function():
        raise RuntimeError("항상 실패")

    # 테스트 실행
    try:
        result = risky_function()
        print(f"결과: {result}")
    except:
        print("risky_function 실패")

    result = fallback_function()
    print(f"폴백 결과: {result}")

    # 통계 출력
    stats = error_handler.get_error_stats()
    print(f"\n📊 에러 통계:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # 메모리 체크
    memory_guard.check_memory()