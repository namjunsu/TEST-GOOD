"""
Configuration management
"""

from dataclasses import dataclass
from pathlib import Path

@dataclass
class CacheConfig:
    max_size: int = 100
    max_metadata_cache: int = 500
    max_pdf_cache: int = 50
    ttl: int = 3600

@dataclass
class ParallelConfig:
    max_workers: int = 8
    timeout: int = 30
    batch_size: int = 10

@dataclass
class RAGConfig:
    docs_dir: Path = Path("docs")
    models_dir: Path = Path("models")
    cache: CacheConfig = None
    parallel: ParallelConfig = None

    def __post_init__(self):
        if self.cache is None:
            self.cache = CacheConfig()
        if self.parallel is None:
            self.parallel = ParallelConfig()
