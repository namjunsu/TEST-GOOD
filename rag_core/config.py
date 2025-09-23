"""
설정 관리 모듈
==============

RAG 시스템의 모든 설정을 중앙에서 관리합니다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import json


@dataclass
class RAGConfig:
    """RAG 시스템 설정 클래스"""

    # 경로 설정
    docs_dir: Path = Path("docs")
    models_dir: Path = Path("models")
    cache_dir: Path = Path(".cache")
    logs_dir: Path = Path("logs")

    # LLM 설정
    model_name: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    n_ctx: int = 8192
    n_gpu_layers: int = -1
    temperature: float = 0.3
    max_tokens: int = 800
    top_p: float = 0.85
    top_k: int = 30
    repeat_penalty: float = 1.15

    # 검색 설정
    search_top_k: int = 10
    min_relevance_score: float = 0.3
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    rerank_top_k: int = 5

    # 캐시 설정
    cache_enabled: bool = True
    cache_ttl: int = 3600  # seconds
    cache_max_size: int = 1000

    # 문서 처리 설정
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100
    ocr_enabled: bool = True
    ocr_language: str = "kor+eng"

    # 성능 설정
    batch_size: int = 10
    num_workers: int = 4
    use_gpu: bool = True
    memory_limit_gb: float = 14.0

    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def __post_init__(self):
        """초기화 후 처리 (테스트 모드 확인 등)"""
        # 테스트 모드 확인
        if os.environ.get('RAG_TEST_MODE') == 'true':
            self.n_gpu_layers = 0  # CPU만 사용
            self.n_ctx = 2048  # 컨텍스트 크기 줄임
            self.search_top_k = 3  # 검색 결과 줄임
            self.batch_size = 1  # 배치 크기 줄임

    @classmethod
    def from_file(cls, config_path: str = "config.json") -> "RAGConfig":
        """파일에서 설정 로드"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return cls(**config_data)
        return cls()

    def save(self, config_path: str = "config.json") -> None:
        """설정을 파일로 저장"""
        config_data = {
            k: str(v) if isinstance(v, Path) else v
            for k, v in self.__dict__.items()
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

    def validate(self) -> bool:
        """설정 유효성 검증"""
        # 경로 검증
        if not self.docs_dir.exists():
            self.docs_dir.mkdir(parents=True, exist_ok=True)

        if not self.models_dir.exists():
            raise ValueError(f"Models directory not found: {self.models_dir}")

        # 값 범위 검증
        if not 0 < self.temperature <= 1:
            raise ValueError(f"Invalid temperature: {self.temperature}")

        if self.chunk_size <= self.chunk_overlap:
            raise ValueError("chunk_size must be greater than chunk_overlap")

        return True