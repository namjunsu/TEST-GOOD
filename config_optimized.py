"""
최적화된 설정 파일
==================

빠른 시작을 위한 설정
"""

import os
from pathlib import Path

# ============ 디렉토리 설정 ============
DOCS_DIR = Path("docs")

# ============ 성능 최적화 설정 ============

# 문서 로딩 제한 (개발/테스트용)
MAX_DOCUMENTS = int(os.getenv('MAX_DOCUMENTS', '100'))  # 최대 100개만 로드
LAZY_LOAD = True  # 지연 로딩 활성화
PARALLEL_WORKERS = 8  # 병렬 처리 워커 수

# 캐싱 설정
USE_CACHE = True
CACHE_DIR = ".cache"
CACHE_TTL = 3600 * 24  # 24시간

# 모델 설정 (경량화)
MODEL_NAME = "qwen2.5-7b-instruct-q4_k_m.gguf"
N_CTX = 2048  # 컨텍스트 감소 (4096 -> 2048)
N_BATCH = 128  # 배치 크기 감소 (256 -> 128)
MAX_TOKENS = 256  # 최대 토큰 감소 (512 -> 256)
N_GPU_LAYERS = 20  # GPU 레이어 감소
TEMPERATURE = 0.3
TOP_P = 0.85
TOP_K = 30
REPEAT_PENALTY = 1.15

# 메모리 최적화
LOW_VRAM = True
OFFLOAD_LAYERS = True
USE_MMAP = True
USE_MLOCK = False

# 검색 설정
SEARCH_TOP_K = 3  # 기본 검색 결과 수
MIN_RELEVANCE_SCORE = 0.3

# 로깅
LOG_LEVEL = "INFO"
VERBOSE = False

print(f"⚡ 최적화 모드: 최대 {MAX_DOCUMENTS}개 문서 로드")
