#!/usr/bin/env python3
"""
사용자 질문과 답변을 로깅하는 시스템
- 질문, 답변, 시간, 성공 여부 등 기록
- 자주 묻는 질문 패턴 분석
- 에러 패턴 분석
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter
import re

class QueryLogger:
    """질문/답변 로깅 및 분석 시스템"""
    
    def __init__(self, log_dir: str = "logs/query_logs"):
        """로거 초기화"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 일별 로그 파일
        today = datetime.now().strftime("%Y%m%d")
        self.log_file = self.log_dir / f"queries_{today}.jsonl"
        
        # 통계 파일
        self.stats_file = self.log_dir / "query_statistics.json"
        
        # 메모리 캐시 (실시간 분석용)
        self.recent_queries = []
        self.load_recent_queries()
    
    def log_query(self, 
                  query: str, 
                  answer: str,
                  mode: str = 'auto',
                  success: bool = True,
                  error: Optional[str] = None,
                  processing_time: float = 0.0,
                  metadata: Optional[Dict] = None) -> None:
        """질문과 답변 로깅"""
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'answer': answer[:500] if answer else None,  # 답변은 500자만 저장
            'mode': mode,
            'success': success,
            'error': error,
            'processing_time': processing_time,
            'metadata': metadata or {}
        }
        
        # 파일에 저장 (JSONL 형식)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write('\n')
        
        # 메모리 캐시 업데이트
        self.recent_queries.append(log_entry)
        if len(self.recent_queries) > 1000:  # 최근 1000개만 유지
            self.recent_queries.pop(0)
        
        # 통계 업데이트
        self.update_statistics()
    
    def load_recent_queries(self, days: int = 7) -> None:
        """최근 N일간의 질문 로드"""
        self.recent_queries = []
        
        # 최근 N일 파일들 읽기
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            log_file = self.log_dir / f"queries_{date_str}.jsonl"
            
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            self.recent_queries.append(entry)
                        except:
                            continue
    
    def analyze_frequent_patterns(self, top_n: int = 20) -> Dict[str, Any]:
        """자주 묻는 질문 패턴 분석"""
        
        if not self.recent_queries:
            return {}
        
        # 키워드 추출
        keywords = Counter()
        entities = Counter()  # 장비명, 위치명 등
        question_types = Counter()  # 질문 유형
        error_patterns = Counter()  # 에러 패턴
        
        for entry in self.recent_queries:
            query = entry.get('query', '')
            
            # 키워드 추출 (명사 위주)
            words = re.findall(r'[가-힣]+|[A-Z]+[a-z]*|\d+', query)
            for word in words:
                if len(word) >= 2:  # 2글자 이상만
                    keywords[word] += 1
            
            # 장비명 패턴
            equipment_patterns = [
                r'CCU', r'HP', r'SONY', r'Sony', r'카메라', r'마이크',
                r'워크스테이션', r'삼각대', r'드론', r'렌즈'
            ]
            for pattern in equipment_patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    entities[pattern] += 1
            
            # 위치 패턴
            location_patterns = [
                r'광화문', r'스튜디오', r'부조정실', r'편집실',
                r'\d+층', r'대형', r'중형', r'소형'
            ]
            for pattern in location_patterns:
                if re.search(pattern, query):
                    entities[pattern] += 1
            
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
            
            # 에러 패턴
            if not entry.get('success'):
                error = entry.get('error', '알 수 없는 오류')
                error_patterns[error] += 1
        
        # 통계 생성
        statistics = {
            'total_queries': len(self.recent_queries),
            'success_rate': sum(1 for e in self.recent_queries if e.get('success')) / len(self.recent_queries) * 100,
            'avg_processing_time': sum(e.get('processing_time', 0) for e in self.recent_queries) / len(self.recent_queries),
            'top_keywords': keywords.most_common(top_n),
            'top_entities': entities.most_common(top_n),
            'question_types': dict(question_types),
            'error_patterns': error_patterns.most_common(10),
            'analyzed_at': datetime.now().isoformat()
        }
        
        return statistics
    
    def update_statistics(self) -> None:
        """통계 파일 업데이트"""
        stats = self.analyze_frequent_patterns()
        
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    
    def get_frequent_queries(self, top_n: int = 10) -> List[str]:
        """실제 자주 묻는 질문 추출"""
        
        if not self.recent_queries:
            return []
        
        # 질문 정규화 및 카운팅
        query_counter = Counter()
        
        for entry in self.recent_queries:
            query = entry.get('query', '')
            # 간단한 정규화 (숫자, 날짜 등을 일반화)
            normalized = re.sub(r'\d{4}년|\d{1,2}월', 'YYYY년', query)
            normalized = re.sub(r'\d+', 'N', normalized)
            query_counter[normalized] += 1
        
        # 상위 N개 반환
        frequent = []
        for query, count in query_counter.most_common(top_n):
            # 정규화된 것을 다시 실제 예시로 변환
            for entry in self.recent_queries:
                if self._normalize_query(entry.get('query', '')) == query:
                    frequent.append({
                        'query': entry.get('query'),
                        'count': count,
                        'normalized': query
                    })
                    break
        
        return frequent
    
    def _normalize_query(self, query: str) -> str:
        """질문 정규화"""
        normalized = re.sub(r'\d{4}년|\d{1,2}월', 'YYYY년', query)
        normalized = re.sub(r'\d+', 'N', normalized)
        return normalized
    
    def get_error_logs(self, limit: int = 50) -> List[Dict]:
        """최근 에러 로그 조회"""
        errors = []
        
        for entry in reversed(self.recent_queries):
            if not entry.get('success'):
                errors.append({
                    'timestamp': entry.get('timestamp'),
                    'query': entry.get('query'),
                    'error': entry.get('error'),
                    'mode': entry.get('mode')
                })
                
                if len(errors) >= limit:
                    break
        
        return errors
    
    def generate_report(self) -> str:
        """분석 리포트 생성"""
        stats = self.analyze_frequent_patterns()
        
        report = []
        report.append("=" * 60)
        report.append("📊 사용자 질문 분석 리포트")
        report.append("=" * 60)
        report.append(f"\n📅 분석 시간: {stats.get('analyzed_at', 'N/A')}")
        report.append(f"📝 총 질문 수: {stats.get('total_queries', 0)}개")
        report.append(f"✅ 성공률: {stats.get('success_rate', 0):.1f}%")
        report.append(f"⏱️ 평균 처리 시간: {stats.get('avg_processing_time', 0):.2f}초")
        
        report.append("\n" + "=" * 60)
        report.append("🔥 자주 검색되는 키워드 TOP 10")
        report.append("-" * 40)
        for keyword, count in stats.get('top_keywords', [])[:10]:
            report.append(f"  • {keyword}: {count}회")
        
        report.append("\n" + "=" * 60)
        report.append("🏢 자주 검색되는 장비/위치 TOP 10")
        report.append("-" * 40)
        for entity, count in stats.get('top_entities', [])[:10]:
            report.append(f"  • {entity}: {count}회")
        
        report.append("\n" + "=" * 60)
        report.append("❓ 질문 유형 분포")
        report.append("-" * 40)
        for q_type, count in stats.get('question_types', {}).items():
            report.append(f"  • {q_type}: {count}회")
        
        if stats.get('error_patterns'):
            report.append("\n" + "=" * 60)
            report.append("⚠️ 주요 에러 패턴")
            report.append("-" * 40)
            for error, count in stats.get('error_patterns', []):
                report.append(f"  • {error}: {count}회")
        
        return "\n".join(report)


# 전역 로거 인스턴스
query_logger = QueryLogger()


if __name__ == "__main__":
    # 테스트 및 리포트 생성
    logger = QueryLogger()
    
    # 테스트 데이터 추가 (개발용)
    test_queries = [
        "CCU 장비 몇 대?",
        "2024년 중계차 보수 기안자 누구?",
        "HP 워크스테이션 시리얼번호",
        "광화문 3층 장비 목록",
        "SONY 카메라 몇 대 보유?",
        "신승만 담당 장비",
        "뷰파인더 케이블 구매 건",
        "무선 마이크 구매 내역"
    ]
    
    for query in test_queries:
        logger.log_query(
            query=query,
            answer="테스트 답변입니다.",
            mode='auto',
            success=True,
            processing_time=1.5
        )
    
    # 리포트 출력
    print(logger.generate_report())
    
    # 자주 묻는 질문
    print("\n" + "=" * 60)
    print("🎯 실제 자주 묻는 질문")
    print("-" * 40)
    for item in logger.get_frequent_queries(5):
        print(f"  • {item['query']} ({item['count']}회)")