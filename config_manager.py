"""
ConfigManager - YAML 기반 중앙 설정 관리 시스템
config.yaml 파일을 읽어서 설정을 관리하고 기존 config.py와 호환성 유지
"""

import yaml
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """YAML 설정 파일을 관리하는 싱글톤 클래스"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """config.yaml 파일 로드"""
        config_path = Path(__file__).parent / "config.yaml"

        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
                    logger.info(f"✅ config.yaml 로드 완료: {config_path}")
            else:
                logger.warning(f"⚠️ config.yaml 파일이 없습니다. 기본값 사용: {config_path}")
                self._config = self._get_default_config()
                # 기본 설정 파일 생성
                self._save_config()
        except Exception as e:
            logger.error(f"❌ config.yaml 로드 실패: {e}")
            self._config = self._get_default_config()

    def _save_config(self):
        """현재 설정을 config.yaml에 저장"""
        config_path = Path(__file__).parent / "config.yaml"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"✅ config.yaml 저장 완료: {config_path}")
        except Exception as e:
            logger.error(f"❌ config.yaml 저장 실패: {e}")

    def _get_default_config(self) -> Dict:
        """기본 설정값 반환 (config.py 호환)"""
        return {
            "system": {
                "name": "AI-CHAT RAG System",
                "version": "3.2.0",
                "environment": "production"
            },
            "cache": {
                "response": {
                    "enabled": True,
                    "max_size": 100,
                    "ttl": 3600,
                    "enable_lru": True
                }
            },
            "models": {
                "qwen": {
                    "path": "models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
                    "context_window": 8192,
                    "gpu_layers": -1,
                    "temperature": 0.3
                }
            },
            "paths": {
                "documents_dir": "./docs",
                "models_dir": "./models",
                "logs_dir": "./logs"
            },
            "limits": {
                "max_text_length": 10000,
                "max_pdf_pages": 10,
                "chunk_size": 1000,
                "chunk_overlap": 200
            }
        }

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        점 표기법으로 중첩된 설정 값 가져오기
        예: config.get('models.qwen.temperature', 0.3)
        """
        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> bool:
        """
        점 표기법으로 설정 값 업데이트
        예: config.set('cache.response.ttl', 7200)
        """
        keys = key_path.split('.')
        target = self._config

        # 마지막 키 전까지 탐색
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        # 값 설정
        target[keys[-1]] = value

        # 파일에 저장
        self._save_config()
        return True

    def get_all(self) -> Dict:
        """전체 설정 딕셔너리 반환"""
        return self._config.copy()

    def reload(self):
        """설정 파일 다시 로드"""
        self._load_config()

    # 기존 config.py와의 호환성을 위한 속성들
    @property
    def DOCS_DIR(self) -> str:
        return self.get('paths.documents_dir', './docs')

    @property
    def QWEN_MODEL_PATH(self) -> str:
        return self.get('models.qwen.path', './models/qwen2.5-7b-instruct-q5_k_m.gguf')

    @property
    def N_CTX(self) -> int:
        return self.get('models.qwen.context_window', 8192)

    @property
    def N_GPU_LAYERS(self) -> int:
        return self.get('models.qwen.gpu_layers', -1)

    @property
    def TEMPERATURE(self) -> float:
        return self.get('models.qwen.temperature', 0.3)

    @property
    def MAX_TOKENS(self) -> int:
        return self.get('models.qwen.max_tokens', 2048)

    @property
    def N_BATCH(self) -> int:
        return self.get('models.qwen.batch_size', 512)

    @property
    def CACHE_TTL(self) -> int:
        return self.get('cache.response.ttl', 3600)

    @property
    def MAX_CACHE_SIZE(self) -> int:
        return self.get('cache.response.max_size', 100)

    @property
    def CHUNK_SIZE(self) -> int:
        return self.get('limits.chunk_size', 1000)

    @property
    def CHUNK_OVERLAP(self) -> int:
        return self.get('limits.chunk_overlap', 200)

    @property
    def MAX_TEXT_LENGTH(self) -> int:
        return self.get('limits.max_text_length', 10000)

    @property
    def MAX_PDF_PAGES(self) -> int:
        return self.get('limits.max_pdf_pages', 10)

    def get_manufacturers(self) -> list:
        """제조사 목록 반환"""
        return self.get('patterns.manufacturers', [
            "SONY", "HARRIS", "HP", "TOSHIBA", "PANASONIC",
            "CANON", "NIKON", "DELL", "APPLE", "SAMSUNG", "LG"
        ])

    def get_model_pattern(self) -> str:
        """모델 패턴 정규식 반환"""
        return self.get('patterns.model_regex', r'\b[A-Z]{2,}[-\s]?\d+')


# 싱글톤 인스턴스 생성
config_manager = ConfigManager()

# 기존 config.py와의 호환성을 위한 전역 변수들
DOCS_DIR = config_manager.DOCS_DIR
QWEN_MODEL_PATH = config_manager.QWEN_MODEL_PATH
N_CTX = config_manager.N_CTX
N_GPU_LAYERS = config_manager.N_GPU_LAYERS
TEMPERATURE = config_manager.TEMPERATURE
MAX_TOKENS = config_manager.MAX_TOKENS
N_BATCH = config_manager.N_BATCH
CACHE_TTL = config_manager.CACHE_TTL
MAX_CACHE_SIZE = config_manager.MAX_CACHE_SIZE
CHUNK_SIZE = config_manager.CHUNK_SIZE
CHUNK_OVERLAP = config_manager.CHUNK_OVERLAP


# 편의 함수
def get_config(key: str, default: Any = None) -> Any:
    """설정 값 가져오기"""
    return config_manager.get(key, default)

def set_config(key: str, value: Any) -> bool:
    """설정 값 설정하기"""
    return config_manager.set(key, value)

def reload_config():
    """설정 다시 로드"""
    config_manager.reload()