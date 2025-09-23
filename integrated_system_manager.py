#!/usr/bin/env python3
"""
통합 시스템 관리자
==================
모든 개선사항을 실용적으로 통합 관리
복잡도를 낮추고 안정성을 높인 시스템
"""

import json
import time
import psutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

class SystemMode(Enum):
    """시스템 모드 - 단순하게 3개만"""
    BASIC = "basic"      # 기본 모드 (안정적, 빠름)
    ADVANCED = "advanced" # 고급 모드 (FAISS, 캐싱)
    FULL = "full"        # 전체 모드 (모든 기능)

@dataclass
class SystemConfig:
    """시스템 설정 - 한 곳에서 관리"""
    mode: SystemMode = SystemMode.BASIC
    use_cache: bool = True
    use_faiss: bool = False
    use_redis: bool = False
    use_websocket: bool = False
    use_monitoring: bool = True
    use_backup: bool = True
    max_complexity: int = 3  # 동시 실행 기능 제한

class IntegratedSystemManager:
    """통합 시스템 관리자"""

    def __init__(self):
        self.config = SystemConfig()
        self.active_features = []
        self.errors = []
        self.performance_impact = {}

        # 로깅 설정 (심플하게)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # 기능별 의존성 정의
        self.dependencies = {
            'redis': ['redis-server'],
            'faiss': ['numpy', 'faiss'],
            'websocket': ['websockets'],
            'monitoring': ['psutil', 'plotly']
        }

        # 초기화
        self._initialize_system()

    def _initialize_system(self):
        """시스템 초기화 - 필요한 것만"""
        self.logger.info(f"🚀 시스템 초기화: {self.config.mode.value} 모드")

        # 모드별 자동 설정
        if self.config.mode == SystemMode.BASIC:
            # 기본 모드: 가장 안정적인 기능만
            self.config.use_cache = True
            self.config.use_faiss = False
            self.config.use_redis = False
            self.config.use_websocket = False
            self.config.use_monitoring = False
            self.config.use_backup = True

        elif self.config.mode == SystemMode.ADVANCED:
            # 고급 모드: 성능 향상 기능 추가
            self.config.use_cache = True
            self.config.use_faiss = True
            self.config.use_redis = False  # Redis는 별도 서버 필요
            self.config.use_websocket = False
            self.config.use_monitoring = True
            self.config.use_backup = True

        elif self.config.mode == SystemMode.FULL:
            # 전체 모드: 모든 기능 (주의 필요)
            self.config.use_cache = True
            self.config.use_faiss = True
            self.config.use_redis = self._check_redis()
            self.config.use_websocket = True
            self.config.use_monitoring = True
            self.config.use_backup = True

        self._load_features()

    def _check_redis(self) -> bool:
        """Redis 사용 가능 확인"""
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379)
            r.ping()
            self.logger.info("✅ Redis 서버 연결 가능")
            return True
        except:
            self.logger.warning("⚠️ Redis 사용 불가 - 로컬 캐시 사용")
            return False

    def _load_features(self):
        """필요한 기능만 로드"""
        self.active_features = []

        # 기본 캐시 (항상 사용)
        if self.config.use_cache:
            self.active_features.append('basic_cache')
            self.logger.info("✅ 기본 캐시 활성화")

        # FAISS 검색
        if self.config.use_faiss:
            try:
                from advanced_search_optimizer import search_optimizer
                self.active_features.append('faiss_search')
                self.logger.info("✅ FAISS 검색 활성화")
            except:
                self.logger.warning("⚠️ FAISS 로드 실패 - 기본 검색 사용")

        # Redis 캐시
        if self.config.use_redis:
            try:
                from redis_cache_system import redis_cache
                if redis_cache:
                    self.active_features.append('redis_cache')
                    self.logger.info("✅ Redis 캐시 활성화")
            except:
                self.logger.warning("⚠️ Redis 로드 실패")

        # 백업 시스템
        if self.config.use_backup:
            try:
                from auto_backup_system import backup_system
                self.active_features.append('auto_backup')
                self.logger.info("✅ 자동 백업 활성화")
            except:
                self.logger.warning("⚠️ 백업 시스템 로드 실패")

    def get_optimal_config(self) -> Dict[str, Any]:
        """현재 시스템에 최적화된 설정 반환"""
        # CPU 사용률 확인
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        recommendations = {
            'mode': self.config.mode.value,
            'active_features': self.active_features,
            'system_load': {
                'cpu': cpu_percent,
                'memory': memory.percent
            },
            'recommendations': []
        }

        # 시스템 부하에 따른 권장사항
        if cpu_percent > 80:
            recommendations['recommendations'].append("CPU 사용률 높음 - BASIC 모드 권장")
            if self.config.mode != SystemMode.BASIC:
                self.switch_mode(SystemMode.BASIC)

        if memory.percent > 85:
            recommendations['recommendations'].append("메모리 부족 - 캐시 크기 축소 권장")

        if len(self.errors) > 10:
            recommendations['recommendations'].append("오류 다수 발생 - 시스템 점검 필요")

        return recommendations

    def switch_mode(self, new_mode: SystemMode):
        """모드 전환 - 안전하게"""
        self.logger.info(f"🔄 모드 전환: {self.config.mode.value} → {new_mode.value}")

        # 기존 기능 정리
        self._cleanup_features()

        # 새 모드 설정
        self.config.mode = new_mode
        self._initialize_system()

        self.logger.info(f"✅ 모드 전환 완료: {new_mode.value}")

    def _cleanup_features(self):
        """기능 정리 - 메모리 해제"""
        import gc

        self.active_features = []
        gc.collect()

        if hasattr(self, '_cache'):
            del self._cache

        self.logger.info("🧹 기능 정리 완료")

    def handle_error(self, error: Exception, context: str = ""):
        """통합 에러 처리"""
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'error': str(error),
            'context': context,
            'mode': self.config.mode.value
        }

        self.errors.append(error_info)

        # 오류 누적 시 자동 다운그레이드
        if len(self.errors) > 5 and self.config.mode != SystemMode.BASIC:
            self.logger.warning("⚠️ 오류 다수 발생 - BASIC 모드로 전환")
            self.switch_mode(SystemMode.BASIC)

        # 최근 100개만 유지
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]

    def get_status(self) -> Dict[str, Any]:
        """시스템 상태 - 간단명료하게"""
        return {
            'mode': self.config.mode.value,
            'active_features': self.active_features,
            'feature_count': len(self.active_features),
            'error_count': len(self.errors),
            'cpu_usage': psutil.cpu_percent(),
            'memory_usage': psutil.virtual_memory().percent,
            'recommendations': self.get_optimal_config()['recommendations'],
            'health': self._calculate_health()
        }

    def _calculate_health(self) -> str:
        """시스템 건강도"""
        score = 100

        # 오류 수에 따른 감점
        score -= min(len(self.errors) * 2, 30)

        # CPU 사용률에 따른 감점
        cpu = psutil.cpu_percent()
        if cpu > 80:
            score -= 20
        elif cpu > 60:
            score -= 10

        # 메모리 사용률에 따른 감점
        mem = psutil.virtual_memory().percent
        if mem > 85:
            score -= 20
        elif mem > 70:
            score -= 10

        if score >= 90:
            return "🟢 Excellent"
        elif score >= 70:
            return "🟡 Good"
        elif score >= 50:
            return "🟠 Fair"
        else:
            return "🔴 Poor"

    def optimize_for_query(self, query_type: str) -> Dict[str, bool]:
        """쿼리 타입에 따른 최적화"""
        optimizations = {}

        if query_type == "simple":
            # 단순 쿼리: 기본 기능만
            optimizations['use_cache'] = True
            optimizations['use_faiss'] = False
            optimizations['use_redis'] = False

        elif query_type == "complex":
            # 복잡한 쿼리: 고급 기능 사용
            optimizations['use_cache'] = True
            optimizations['use_faiss'] = True
            optimizations['use_redis'] = self.config.use_redis

        elif query_type == "realtime":
            # 실시간 쿼리: WebSocket 필요
            optimizations['use_cache'] = False
            optimizations['use_websocket'] = True

        return optimizations

    def safe_execute(self, func, *args, **kwargs):
        """안전한 실행 - 오류 시 폴백"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.handle_error(e, f"Function: {func.__name__}")

            # 폴백 처리
            if self.config.mode != SystemMode.BASIC:
                self.logger.info("폴백: BASIC 모드 함수 실행")
                self.switch_mode(SystemMode.BASIC)
                try:
                    return func(*args, **kwargs)
                except:
                    return None
            return None


# 전역 인스턴스
system_manager = IntegratedSystemManager()

# 간단한 사용 예제
class SmartRAGSystem:
    """스마트 RAG 시스템 - 자동 최적화"""

    def __init__(self):
        self.manager = system_manager

    def search(self, query: str) -> List[Dict]:
        """지능형 검색"""
        # 쿼리 복잡도 판단
        query_length = len(query.split())

        if query_length < 5:
            query_type = "simple"
        elif query_length < 15:
            query_type = "complex"
        else:
            query_type = "complex"

        # 최적화 적용
        optimizations = self.manager.optimize_for_query(query_type)

        # 검색 실행
        if optimizations.get('use_faiss') and 'faiss_search' in self.manager.active_features:
            # FAISS 검색
            from advanced_search_optimizer import search_optimizer
            return self.manager.safe_execute(search_optimizer.search, query)
        else:
            # 기본 검색
            return self._basic_search(query)

    def _basic_search(self, query: str) -> List[Dict]:
        """기본 검색 - 항상 작동"""
        return [
            {'content': f"기본 검색 결과: {query}", 'score': 0.8}
        ]


if __name__ == "__main__":
    print("🎯 통합 시스템 관리자 테스트")

    # 시스템 상태 확인
    status = system_manager.get_status()
    print(f"\n📊 시스템 상태:")
    print(f"  모드: {status['mode']}")
    print(f"  활성 기능: {status['active_features']}")
    print(f"  건강도: {status['health']}")

    # 모드 전환 테스트
    print(f"\n🔄 모드 전환 테스트:")
    system_manager.switch_mode(SystemMode.ADVANCED)
    print(f"  새 모드: {system_manager.config.mode.value}")

    # 스마트 검색 테스트
    rag = SmartRAGSystem()
    results = rag.search("테스트 쿼리")
    print(f"\n🔍 검색 결과: {len(results)}개")

    # 권장사항
    recommendations = system_manager.get_optimal_config()
    if recommendations['recommendations']:
        print(f"\n💡 권장사항:")
        for rec in recommendations['recommendations']:
            print(f"  • {rec}")