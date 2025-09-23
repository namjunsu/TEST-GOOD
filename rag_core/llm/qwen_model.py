"""
Qwen LLM 모델 모듈
==================

Qwen2.5-7B 모델 관리 및 텍스트 생성을 담당합니다.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional
from threading import Lock
from llama_cpp import Llama

from ..config import RAGConfig
from ..exceptions import LLMException, handle_errors

logger = logging.getLogger(__name__)


class QwenLLM:
    """Qwen LLM 싱글톤 클래스"""

    _instance = None
    _lock = Lock()

    def __new__(cls, config: Optional[RAGConfig] = None):
        """싱글톤 인스턴스 생성"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[RAGConfig] = None):
        """
        Args:
            config: RAG 설정 객체
        """
        # 이미 초기화된 경우 스킵
        if hasattr(self, 'initialized'):
            return

        self.config = config or RAGConfig()
        self.model = None
        self.model_path = None
        self.usage_stats = {
            'total_calls': 0,
            'total_tokens': 0,
            'total_time': 0.0
        }

        # 초기화
        self._load_model()
        self.initialized = True

    def _load_model(self) -> None:
        """모델 로드"""
        try:
            # 모델 경로 설정
            self.model_path = self.config.models_dir / self.config.model_name

            if not self.model_path.exists():
                raise LLMException(f"Model file not found: {self.model_path}")

            logger.info(f"Loading Qwen model from {self.model_path}")
            start_time = time.time()

            # Llama.cpp로 모델 로드
            self.model = Llama(
                model_path=str(self.model_path),
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                n_threads=os.cpu_count(),
                verbose=False,
                seed=42
            )

            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f} seconds")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise LLMException(f"Model loading failed: {e}")

    @handle_errors(default_return="")
    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repeat_penalty: Optional[float] = None,
        stop: Optional[List[str]] = None
    ) -> str:
        """
        텍스트 생성

        Args:
            prompt: 입력 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 생성 온도
            top_p: Top-p 샘플링
            top_k: Top-k 샘플링
            repeat_penalty: 반복 페널티
            stop: 중단 토큰

        Returns:
            생성된 텍스트
        """
        if not self.model:
            raise LLMException("Model not loaded")

        # 기본값 설정
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature
        top_p = top_p or self.config.top_p
        top_k = top_k or self.config.top_k
        repeat_penalty = repeat_penalty or self.config.repeat_penalty

        # 통계 기록 시작
        start_time = time.time()

        try:
            # 생성
            response = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repeat_penalty=repeat_penalty,
                stop=stop or ["</s>", "\n\n"],
                echo=False
            )

            # 텍스트 추출
            generated_text = response['choices'][0]['text']

            # 후처리
            generated_text = self._post_process(generated_text)

            # 통계 업데이트
            elapsed_time = time.time() - start_time
            self.usage_stats['total_calls'] += 1
            self.usage_stats['total_tokens'] += response.get('usage', {}).get('total_tokens', 0)
            self.usage_stats['total_time'] += elapsed_time

            logger.info(
                f"Generated {len(generated_text)} characters in {elapsed_time:.2f}s"
            )

            return generated_text

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise LLMException(f"Text generation failed: {e}")

    def stream_generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Generator[str, None, None]:
        """
        스트리밍 텍스트 생성

        Args:
            prompt: 입력 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 생성 온도
            **kwargs: 추가 파라미터

        Yields:
            생성된 텍스트 청크
        """
        if not self.model:
            raise LLMException("Model not loaded")

        # 기본값 설정
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature or self.config.temperature

        try:
            # 스트리밍 생성
            stream = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=kwargs.get('top_p', self.config.top_p),
                top_k=kwargs.get('top_k', self.config.top_k),
                repeat_penalty=kwargs.get('repeat_penalty', self.config.repeat_penalty),
                stop=kwargs.get('stop', ["</s>", "\n\n"]),
                stream=True,
                echo=False
            )

            for chunk in stream:
                if chunk and 'choices' in chunk:
                    text = chunk['choices'][0].get('text', '')
                    if text:
                        # 후처리
                        text = self._post_process(text)
                        yield text

        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise LLMException(f"Streaming failed: {e}")

    def _post_process(self, text: str) -> str:
        """
        생성된 텍스트 후처리

        Args:
            text: 원본 텍스트

        Returns:
            후처리된 텍스트
        """
        # 중국어 제거
        text = self._remove_chinese(text)

        # 공백 정리
        text = ' '.join(text.split())

        # 특수 토큰 제거
        special_tokens = ['<|im_start|>', '<|im_end|>', '<|endoftext|>']
        for token in special_tokens:
            text = text.replace(token, '')

        return text.strip()

    def _remove_chinese(self, text: str) -> str:
        """
        중국어 텍스트 제거

        Args:
            text: 원본 텍스트

        Returns:
            중국어가 제거된 텍스트
        """
        import re

        # 중국어 문자 범위
        chinese_pattern = r'[\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df\u2a700-\u2b73f\u2b740-\u2b81f\u2b820-\u2ceaf\uf900-\ufaff\u2f800-\u2fa1f]+'

        # 중국어 제거
        text = re.sub(chinese_pattern, '', text)

        return text

    def get_model_info(self) -> Dict:
        """
        모델 정보 반환

        Returns:
            모델 정보 딕셔너리
        """
        if not self.model:
            return {'status': 'not_loaded'}

        return {
            'status': 'ready',
            'model_path': str(self.model_path),
            'n_ctx': self.config.n_ctx,
            'n_gpu_layers': self.config.n_gpu_layers,
            'usage_stats': self.usage_stats
        }

    def reset_stats(self) -> None:
        """사용 통계 초기화"""
        self.usage_stats = {
            'total_calls': 0,
            'total_tokens': 0,
            'total_time': 0.0
        }
        logger.info("Usage statistics reset")

    def unload_model(self) -> None:
        """모델 언로드"""
        if self.model:
            del self.model
            self.model = None
            logger.info("Model unloaded")

    @classmethod
    def get_instance(cls, config: Optional[RAGConfig] = None) -> 'QwenLLM':
        """
        싱글톤 인스턴스 반환

        Args:
            config: RAG 설정 객체

        Returns:
            QwenLLM 인스턴스
        """
        return cls(config)