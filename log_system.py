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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import Counter
import traceback
from logging.handlers import RotatingFileHandler

class ChatLogger:
    """통합 로깅 시스템"""
    
    def __init__(self, log_dir: str = None):
        """로거 초기화"""
        if log_dir is None:
            log_dir = Path(__file__).parent / 'logs'
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 로그 파일 경로
        self.query_log = self.log_dir / 'queries.log'
        self.error_log = self.log_dir / 'errors.log'
        self.performance_log = self.log_dir / 'performance.log'
        self.system_log = self.log_dir / 'system.log'
        
        # 로거 설정
        self._setup_loggers()
        
        # 세션 정보
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.query_count = 0
        
    def _setup_loggers(self):
        """각 용도별 로거 설정"""
        
        # 포맷터 설정
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        json_formatter = logging.Formatter('%(message)s')
        
        # 1. 쿼리 로거 (사용자 질문/답변)
        self.query_logger = logging.getLogger('query')
        self.query_logger.setLevel(logging.INFO)
        query_handler = RotatingFileHandler(
            self.query_log, maxBytes=10*1024*1024, backupCount=5
        )
        query_handler.setFormatter(json_formatter)
        self.query_logger.addHandler(query_handler)
        
        # 2. 에러 로거
        self.error_logger = logging.getLogger('error')
        self.error_logger.setLevel(logging.ERROR)
        error_handler = RotatingFileHandler(
            self.error_log, maxBytes=5*1024*1024, backupCount=3
        )
        error_handler.setFormatter(detailed_formatter)
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
        
    def log_query(self, 
                  query: str, 
                  response: str, 
                  search_mode: str = None,
                  processing_time: float = None,
                  metadata: Dict[str, Any] = None) -> str:
        """질문/답변 로깅"""
        
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
        
        # JSON 형태로 저장 (나중에 분석하기 쉽게)
        self.query_logger.info(json.dumps(log_entry, ensure_ascii=False))
        
        # 시스템 로그에도 간단히 기록
        self.system_logger.info(f"Query processed: {query_id} | Mode: {search_mode} | Time: {processing_time:.2f}s")
        
        return query_id
    
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
        """성능 로깅"""
        
        perf_entry = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'operation': operation,
            'duration_ms': duration * 1000,  # 밀리초로 변환
            'details': details or {}
        }
        
        self.perf_logger.info(json.dumps(perf_entry, ensure_ascii=False))
        
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
        
    def get_statistics(self) -> Dict[str, Any]:
        """세션 통계 및 패턴 분석"""
        
        # 기본 통계
        stats = {
            'session_id': self.session_id,
            'total_queries': self.query_count,
            'session_start': self.session_id,
            'log_files': {
                'queries': str(self.query_log),
                'errors': str(self.error_log),
                'performance': str(self.performance_log),
                'system': str(self.system_log)
            }
        }
        
        # 패턴 분석 추가
        pattern_stats = self.analyze_query_patterns()
        stats.update(pattern_stats)
        
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
        """최근 쿼리 분석"""
        
        recent_queries = []
        
        try:
            with open(self.query_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-count:]:
                    try:
                        entry = json.loads(line)
                        recent_queries.append({
                            'query': entry['query'],
                            'time': entry.get('processing_time', 0),
                            'mode': entry.get('search_mode', 'unknown'),
                            'timestamp': entry['timestamp']
                        })
                    except:
                        continue
        except FileNotFoundError:
            pass
        
        return recent_queries


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