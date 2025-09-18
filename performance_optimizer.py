#!/usr/bin/env python3
"""
RAG 시스템 성능 최적화 스크립트
Phase 1: 즉시 적용 가능한 개선사항
"""

import os
import sys
import time
from pathlib import Path

def optimize_llm_singleton():
    """LLM 싱글톤 패턴 최적화"""
    print("🔧 LLM 싱글톤 최적화 중...")
    
    # llm_singleton.py 백업
    singleton_path = Path("rag_system/llm_singleton.py")
    if singleton_path.exists():
        backup_path = singleton_path.with_suffix('.py.bak')
        singleton_path.rename(backup_path)
        print(f"  ✅ 백업 생성: {backup_path}")
    
    # 개선된 싱글톤 코드 작성
    optimized_code = '''"""
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
'''
    
    # 파일 저장
    with open(singleton_path, 'w', encoding='utf-8') as f:
        f.write(optimized_code)
    
    print("  ✅ LLM 싱글톤 최적화 완료")
    return True

def optimize_cache_key():
    """캐시 키 생성 최적화"""
    print("🔧 캐시 키 생성 최적화 중...")
    
    cache_optimizer = '''
# perfect_rag.py의 _get_cache_key 메서드 개선
import re

def _get_enhanced_cache_key(self, query: str, mode: str) -> str:
    """향상된 캐시 키 생성 - 유사 질문도 캐시 히트"""
    
    # 1. 쿼리 정규화
    normalized = query.strip().lower()
    
    # 2. 조사 제거 (한국어 특화)
    particles = ['은', '는', '이', '가', '을', '를', '의', '와', '과', '로', '으로', '에', '에서']
    for particle in particles:
        normalized = normalized.replace(particle + ' ', ' ')
    
    # 3. 공백 정규화
    normalized = ' '.join(normalized.split())
    
    # 4. 핵심 키워드만 추출
    keywords = []
    for word in normalized.split():
        if len(word) >= 2:  # 2글자 이상만
            keywords.append(word)
    
    # 5. 정렬하여 순서 무관하게
    keywords.sort()
    
    # 6. 해시 생성
    cache_str = f"{mode}:{'_'.join(keywords)}"
    return hashlib.md5(cache_str.encode()).hexdigest()
'''
    
    print("  ✅ 캐시 키 최적화 코드 준비 완료")
    return cache_optimizer

def optimize_context_window():
    """동적 컨텍스트 윈도우 관리"""
    print("🔧 동적 컨텍스트 관리 추가...")
    
    dynamic_context = '''
def _get_optimal_context_size(self, query: str, doc_count: int) -> int:
    """쿼리와 문서 수에 따른 최적 컨텍스트 크기 결정"""
    
    query_len = len(query)
    
    # 간단한 쿼리 (20자 미만)
    if query_len < 20 and doc_count <= 3:
        return 4096
    
    # 중간 복잡도 (20-50자)
    elif query_len < 50 and doc_count <= 5:
        return 8192
    
    # 복잡한 쿼리 또는 많은 문서
    else:
        return 16384

def _smart_truncate_context(self, text: str, max_tokens: int = 8000) -> str:
    """스마트 컨텍스트 절단"""
    
    # 토큰 수 추정 (한글 1.5자 = 1토큰 기준)
    estimated_tokens = len(text) / 1.5
    
    if estimated_tokens <= max_tokens:
        return text
    
    # 문장 단위로 절단
    sentences = text.split('.')
    result = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = len(sentence) / 1.5
        if current_tokens + sentence_tokens > max_tokens:
            break
        result.append(sentence)
        current_tokens += sentence_tokens
    
    return '.'.join(result) + '.'
'''
    
    print("  ✅ 동적 컨텍스트 관리 코드 준비 완료")
    return dynamic_context

def create_performance_config():
    """성능 최적화 설정 파일 생성"""
    print("🔧 성능 설정 파일 생성 중...")
    
    config_content = '''# performance_config.yaml
# RAG 시스템 성능 최적화 설정

llm:
  max_tokens: 800      # 기존 1200에서 축소
  temperature: 0.3     # 기존 0.7에서 축소 (더 결정적)
  top_p: 0.85         # 기존 0.9에서 축소
  repeat_penalty: 1.15 # 반복 방지 강화
  batch_size: 256     # 기존 512에서 축소

cache:
  response_ttl: 7200   # 2시간 (기존 1시간)
  max_size: 500       # 기존 200에서 증가
  similarity_threshold: 0.85  # 유사 쿼리 캐시 히트

search:
  max_documents: 30    # 기존 50에서 축소
  timeout: 20         # 기존 30초에서 축소
  min_relevance: 0.6  # 관련성 임계값

parallel:
  pdf_workers: 4      # PDF 병렬 처리 워커
  chunk_size: 5       # 청크 크기
  
memory:
  max_document_length: 8000  # 문서당 최대 길이
  cache_documents: true      # 문서 캐싱 활성화
  
optimization:
  use_singleton: true        # LLM 싱글톤 사용
  use_streaming: false       # 스트리밍 응답 (추후 구현)
  use_dynamic_context: true  # 동적 컨텍스트
'''
    
    # 설정 파일 저장
    config_path = Path("performance_config.yaml")
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print(f"  ✅ 성능 설정 파일 생성: {config_path}")
    return True

def main():
    """메인 최적화 실행"""
    print("="*50)
    print("🚀 RAG 시스템 성능 최적화 Phase 1")
    print("="*50)
    
    start_time = time.time()
    
    # 1. LLM 싱글톤 최적화
    optimize_llm_singleton()
    
    # 2. 캐시 키 최적화 (코드 출력)
    cache_code = optimize_cache_key()
    print("\n📝 perfect_rag.py에 추가할 캐시 최적화 코드:")
    print("-"*40)
    print(cache_code)
    print("-"*40)
    
    # 3. 동적 컨텍스트 관리 (코드 출력)
    context_code = optimize_context_window()
    print("\n📝 perfect_rag.py에 추가할 컨텍스트 관리 코드:")
    print("-"*40)
    print(context_code)
    print("-"*40)
    
    # 4. 성능 설정 파일 생성
    create_performance_config()
    
    elapsed = time.time() - start_time
    
    print("\n" + "="*50)
    print(f"✅ Phase 1 최적화 완료 ({elapsed:.1f}초)")
    print("="*50)
    
    print("\n📋 적용 방법:")
    print("1. llm_singleton.py는 자동으로 교체됨")
    print("2. perfect_rag.py에 위 코드들을 추가")
    print("3. performance_config.yaml 설정 적용")
    print("\n⚡ 예상 성능 향상:")
    print("- LLM 로딩: 7.73초 → 0.1초 (재사용 시)")
    print("- 응답 시간: 140초 → 30-50초")
    print("- 캐시 히트율: 30% → 70%+")

if __name__ == "__main__":
    main()
