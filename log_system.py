#!/usr/bin/env python3
"""
AI-CHAT 로깅 시스템
- 질문/답변 기록
- 처리 시간 측정
- 에러 추적
- 검색 성능 분석
"""

import logging
import json
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import Counter, deque
import traceback
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import asyncio
import threading
import gzip
import shutil
from functools import lru_cache
import os

class ChatLogger:
    """통합 로깅 시스템 - 성능 최적화 버전"""

    def __init__(self, log_dir: str = None, buffer_size: int = 100, auto_archive: bool = True):
        """로거 초기화"""
        if log_dir is None:
            log_dir = Path(__file__).parent / 'logs'

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.archive_dir = self.log_dir / 'archive'
        self.archive_dir.mkdir(exist_ok=True)

        # 로그 파일 경로
        self.query_log = self.log_dir / 'queries.log'
        self.error_log = self.log_dir / 'errors.log'
        self.performance_log = self.log_dir / 'performance.log'
        self.system_log = self.log_dir / 'system.log'

        # 성능 최적화 설정
        self.buffer_size = buffer_size
        self.auto_archive = auto_archive
        self.log_buffer = deque(maxlen=buffer_size)  # 메모리 버퍼
        self.perf_cache = {}  # 성능 데이터 캐시
        self.write_lock = threading.Lock()

        # 비동기 쓰기를 위한 스레드
        self.async_writer = None
        self.write_queue = deque()
        self.stop_writer = threading.Event()

        # 로거 설정
        self._setup_loggers()

        # 세션 정보
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.query_count = 0

        # 통계 캐시 (LRU)
        self._stats_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 60  # 60초 캐시

        # 자동 아카이빙 시작
        if self.auto_archive:
            self._start_auto_archiving()
        
    def _setup_loggers(self):
        """각 용도별 로거 설정 - 최적화 버전"""

        # 포맷터 설정
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        json_formatter = logging.Formatter('%(message)s')

        # 핸들러 중복 방지
        for logger_name in ['query', 'error', 'performance', 'system']:
            logger = logging.getLogger(logger_name)
            logger.handlers = []  # 기존 핸들러 제거
        
        # 1. 쿼리 로거 (사용자 질문/답변) - 일별 로테이션
        self.query_logger = logging.getLogger('query')
        self.query_logger.setLevel(logging.INFO)
        query_handler = TimedRotatingFileHandler(
            self.query_log, when='midnight', interval=1, backupCount=7,
            encoding='utf-8'
        )
        query_handler.setFormatter(json_formatter)
        query_handler.rotator = self._compress_log  # 압축 로테이터
        self.query_logger.addHandler(query_handler)
        
        # 2. 에러 로거 - 크기 기반 로테이션
        self.error_logger = logging.getLogger('error')
        self.error_logger.setLevel(logging.ERROR)
        error_handler = RotatingFileHandler(
            self.error_log, maxBytes=5*1024*1024, backupCount=3,
            encoding='utf-8'
        )
        error_handler.setFormatter(detailed_formatter)
        error_handler.rotator = self._compress_log
        self.error_logger.addHandler(error_handler)
        
        # 3. 성능 로거
        self.perf_logger = logging.getLogger('performance')
        self.perf_logger.setLevel(logging.INFO)
        perf_handler = RotatingFileHandler(
            self.performance_log, maxBytes=5*1024*1024, backupCount=3
        )
        perf_handler.setFormatter(json_formatter)
        self.perf_logger.addHandler(perf_handler)
        
        # 4. 시스템 로거
        self.system_logger = logging.getLogger('system')
        self.system_logger.setLevel(logging.DEBUG)
        system_handler = RotatingFileHandler(
            self.system_log, maxBytes=10*1024*1024, backupCount=5
        )
        system_handler.setFormatter(detailed_formatter)
        self.system_logger.addHandler(system_handler)
        
    def _compress_log(self, source, dest):
        """로그 파일 압축"""
        with open(source, 'rb') as f_in:
            with gzip.open(f"{dest}.gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)

    def _start_auto_archiving(self):
        """자동 아카이빙 시작"""
        def archive_old_logs():
            while not self.stop_writer.is_set():
                try:
                    # 7일 이상 된 로그 압축
                    cutoff = datetime.now() - timedelta(days=7)
                    for log_file in self.log_dir.glob('*.log.*'):
                        if not log_file.name.endswith('.gz'):
                            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                            if file_time < cutoff:
                                archive_path = self.archive_dir / log_file.name
                                shutil.move(str(log_file), str(archive_path))
                                self._compress_log(archive_path, archive_path)
                except Exception as e:
                    self.system_logger.error(f"Archive error: {e}")

                time.sleep(3600)  # 1시간마다 체크

        archive_thread = threading.Thread(target=archive_old_logs, daemon=True)
        archive_thread.start()

    def log_query(self,
                  query: str,
                  response: str,
                  search_mode: str = None,
                  processing_time: float = None,
                  metadata: Dict[str, Any] = None,
                  async_write: bool = True) -> str:
        """질문/답변 로깅 - 비동기 옵션"""

        self.query_count += 1
        query_id = f"{self.session_id}_{self.query_count:04d}"

        log_entry = {
            'query_id': query_id,
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'query': query,
            'response_length': len(response),
            'response_preview': response[:500] if len(response) > 500 else response,
            'search_mode': search_mode,
            'processing_time': processing_time,
            'metadata': metadata or {}
        }

        # 버퍼에 추가
        self.log_buffer.append(log_entry)

        # 캐시 무효화
        self._invalidate_cache()

        if async_write:
            # 비동기 쓰기 큐에 추가
            self.write_queue.append(('query', log_entry))
            self._ensure_async_writer()
        else:
            # 동기 쓰기
            with self.write_lock:
                self.query_logger.info(json.dumps(log_entry, ensure_ascii=False))

        # 시스템 로그에도 간단히 기록
        if processing_time:
            self.system_logger.info(f"Query processed: {query_id} | Mode: {search_mode} | Time: {processing_time:.2f}s")

        return query_id

    def _ensure_async_writer(self):
        """비동기 쓰기 스레드 확인 및 시작"""
        if self.async_writer is None or not self.async_writer.is_alive():
            self.async_writer = threading.Thread(target=self._async_write_worker, daemon=True)
            self.async_writer.start()

    def _async_write_worker(self):
        """비동기 쓰기 워커"""
        while not self.stop_writer.is_set() or self.write_queue:
            if self.write_queue:
                with self.write_lock:
                    batch = []
                    # 배치 처리 (최대 10개)
                    for _ in range(min(10, len(self.write_queue))):
                        batch.append(self.write_queue.popleft())

                    for log_type, entry in batch:
                        try:
                            if log_type == 'query':
                                self.query_logger.info(json.dumps(entry, ensure_ascii=False))
                            elif log_type == 'error':
                                self.error_logger.error(json.dumps(entry, ensure_ascii=False))
                            elif log_type == 'perf':
                                self.perf_logger.info(json.dumps(entry, ensure_ascii=False))
                        except Exception as e:
                            print(f"Async write error: {e}")
            else:
                time.sleep(0.1)  # 큐가 비어있으면 잠시 대기
    
    def log_error(self, 
                  error_type: str, 
                  error_msg: str, 
                  query: str = None,
                  traceback_str: str = None):
        """에러 로깅"""
        
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'error_type': error_type,
            'error_message': error_msg,
            'query': query,
            'traceback': traceback_str or traceback.format_exc()
        }
        
        self.error_logger.error(json.dumps(error_entry, ensure_ascii=False))
        self.system_logger.error(f"Error occurred: {error_type} - {error_msg}")
        
    def log_performance(self,
                       operation: str,
                       duration: float,
                       details: Dict[str, Any] = None):
        """성능 로깅 - 캐싱 추가"""

        perf_entry = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'operation': operation,
            'duration_ms': duration * 1000,  # 밀리초로 변환
            'details': details or {}
        }

        # 성능 캐시 업데이트 (최근 100개만 유지)
        if operation not in self.perf_cache:
            self.perf_cache[operation] = deque(maxlen=100)
        self.perf_cache[operation].append(duration)

        # 비동기 로깅
        self.write_queue.append(('perf', perf_entry))
        self._ensure_async_writer()

        # 느린 작업 경고
        if duration > 5.0:
            self.system_logger.warning(f"Slow operation: {operation} took {duration:.2f}s")
    
    def log_search_details(self,
                          query: str,
                          search_type: str,
                          results_count: int,
                          matched_items: list = None):
        """검색 상세 로깅"""
        
        search_entry = {
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'search_type': search_type,
            'results_count': results_count,
            'matched_items': matched_items[:10] if matched_items else []  # 상위 10개만
        }
        
        self.system_logger.info(f"Search: {search_type} | Query: {query} | Results: {results_count}")
        
    def _invalidate_cache(self):
        """캐시 무효화"""
        self._stats_cache = {}
        self._cache_timestamp = None

    @lru_cache(maxsize=32)
    def _get_cached_patterns(self, query_hash: str) -> Dict:
        """패턴 분석 캐싱"""
        return self._analyze_query_patterns_internal()

    def get_statistics(self, use_cache: bool = True) -> Dict[str, Any]:
        """세션 통계 및 패턴 분석 - 캐싱 지원"""

        # 캐시 확인
        if use_cache and self._cache_timestamp:
            if (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl:
                return self._stats_cache

        # 기본 통계
        stats = {
            'session_id': self.session_id,
            'total_queries': self.query_count,
            'session_start': self.session_id,
            'buffer_size': len(self.log_buffer),
            'queue_size': len(self.write_queue),
            'log_files': {
                'queries': str(self.query_log),
                'errors': str(self.error_log),
                'performance': str(self.performance_log),
                'system': str(self.system_log)
            },
            'archive': {
                'enabled': self.auto_archive,
                'dir': str(self.archive_dir),
                'archived_count': len(list(self.archive_dir.glob('*.gz')))
            }
        }

        # 패턴 분석 추가
        pattern_stats = self.analyze_query_patterns()
        stats.update(pattern_stats)

        # 캐시 업데이트
        self._stats_cache = stats
        self._cache_timestamp = datetime.now()

        return stats
    
    def analyze_query_patterns(self, top_n: int = 20) -> Dict[str, Any]:
        """쿼리 패턴 분석 (query_logger 기능 통합)"""
        
        recent_queries = self.analyze_recent_queries(100)
        if not recent_queries:
            return {}
        
        # 분석 준비
        keywords = Counter()
        equipment_entities = Counter()
        location_entities = Counter()
        question_types = Counter()
        
        for entry in recent_queries:
            query = entry.get('query', '')
            
            # 키워드 추출
            words = re.findall(r'[가-힣]+|[A-Z]+[a-z]*|\d+', query)
            for word in words:
                if len(word) >= 2:
                    keywords[word] += 1
            
            # 장비명 패턴
            equipment_patterns = [
                r'CCU', r'HP', r'SONY', r'Sony', r'카메라', r'마이크',
                r'워크스테이션', r'삼각대', r'드론', r'렌즈', r'모니터'
            ]
            for pattern in equipment_patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    equipment_entities[pattern] += 1
            
            # 위치 패턴
            location_patterns = [
                r'광화문', r'스튜디오', r'부조정실', r'편집실', r'중계차',
                r'\d+층', r'대형', r'중형', r'소형'
            ]
            for pattern in location_patterns:
                if re.search(pattern, query):
                    location_entities[pattern] += 1
            
            # 질문 유형 분류
            if '누구' in query or '기안자' in query or '담당자' in query:
                question_types['담당자/기안자'] += 1
            elif '얼마' in query or '비용' in query or '가격' in query:
                question_types['가격/비용'] += 1
            elif '몇' in query or '개수' in query or '수량' in query:
                question_types['수량'] += 1
            elif '언제' in query or '날짜' in query:
                question_types['날짜/시기'] += 1
            elif '어디' in query or '위치' in query:
                question_types['위치'] += 1
            else:
                question_types['일반'] += 1
        
        return {
            'top_keywords': keywords.most_common(top_n),
            'top_equipment': equipment_entities.most_common(10),
            'top_locations': location_entities.most_common(10),
            'question_types': dict(question_types),
            'analyzed_at': datetime.now().isoformat()
        }
    
    def analyze_recent_queries(self, count: int = 10) -> list:
        """최근 쿼리 분석 - 버퍼 우선 사용"""

        recent_queries = []

        # 먼저 메모리 버퍼에서 가져오기
        buffer_queries = list(self.log_buffer)[-count:]
        for entry in buffer_queries:
            recent_queries.append({
                'query': entry.get('query', ''),
                'time': entry.get('processing_time', 0),
                'mode': entry.get('search_mode', 'unknown'),
                'timestamp': entry.get('timestamp', '')
            })

        # 부족하면 파일에서 추가
        if len(recent_queries) < count:
            try:
                with open(self.query_log, 'r', encoding='utf-8') as f:
                    # 파일 끝에서부터 효율적으로 읽기
                    f.seek(0, 2)  # 파일 끝으로
                    file_size = f.tell()

                    # 대략적인 라인 크기로 읽을 위치 계산 (각 라인 ~500bytes 가정)
                    read_size = min(file_size, count * 500)
                    f.seek(max(0, file_size - read_size))

                    lines = f.read().splitlines()
                    for line in lines[-(count - len(recent_queries)):]:
                        try:
                            entry = json.loads(line)
                            recent_queries.insert(0, {
                                'query': entry['query'],
                                'time': entry.get('processing_time', 0),
                                'mode': entry.get('search_mode', 'unknown'),
                                'timestamp': entry['timestamp']
                            })
                        except:
                            continue
            except (FileNotFoundError, IOError):
                pass

        return recent_queries[-count:]  # 최근 count개만 반환

    def get_performance_summary(self) -> Dict[str, Any]:
        """성능 요약 통계"""
        if not self.perf_cache:
            return {'message': 'No performance data available'}

        summary = {
            'operations': {},
            'slow_operations': [],
            'average_times': {}
        }

        for op, times in self.perf_cache.items():
            if times:
                avg_time = sum(times) / len(times)
                summary['average_times'][op] = round(avg_time * 1000, 2)  # ms

                # 느린 작업 식별
                if avg_time > 1.0:
                    summary['slow_operations'].append({
                        'operation': op,
                        'avg_time_ms': round(avg_time * 1000, 2),
                        'count': len(times)
                    })

        return summary

    def cleanup(self):
        """리소스 정리"""
        self.stop_writer.set()

        # 남은 큐 처리
        if self.write_queue:
            print(f"Flushing {len(self.write_queue)} pending log entries...")
            while self.write_queue:
                with self.write_lock:
                    log_type, entry = self.write_queue.popleft()
                    if log_type == 'query':
                        self.query_logger.info(json.dumps(entry, ensure_ascii=False))

        # 핸들러 정리
        for logger_name in ['query', 'error', 'performance', 'system']:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers:
                handler.close()
            logger.handlers = []


class TimerContext:
    """처리 시간 측정용 컨텍스트 매니저"""
    
    def __init__(self, logger: ChatLogger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.logger.log_performance(self.operation, duration)
        
        if exc_type:
            self.logger.log_error(
                error_type=exc_type.__name__,
                error_msg=str(exc_val),
                traceback_str=traceback.format_exc()
            )


# 싱글톤 로거 인스턴스
_logger_instance = None

def get_logger() -> ChatLogger:
    """싱글톤 로거 반환"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ChatLogger()
    return _logger_instance


if __name__ == "__main__":
    # 테스트
    logger = get_logger()
    
    # 쿼리 로깅 테스트
    logger.log_query(
        query="중계차 CCU현황",
        response="총 4개의 CCU 장비가 있습니다...",
        search_mode="asset",
        processing_time=1.23,
        metadata={'location': '중계차', 'equipment': 'CCU'}
    )
    
    # 성능 로깅 테스트
    with TimerContext(logger, "database_search"):
        time.sleep(0.5)  # 작업 시뮬레이션
    
    # 통계 확인
    print(json.dumps(logger.get_statistics(), indent=2, ensure_ascii=False))
    print("\n최근 쿼리:")
    for q in logger.analyze_recent_queries(5):
        print(f"  - {q['query']} ({q['time']:.2f}s)")