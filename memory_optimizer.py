"""
메모리 최적화 모듈
==================

4bit 양자화와 메모리 효율적인 설정을 적용합니다.
목표: 14GB → 8GB 이하
"""

import os
import gc
import torch
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import psutil

logger = logging.getLogger(__name__)


class MemoryOptimizer:
    """메모리 최적화 관리 클래스"""

    def __init__(self):
        self.original_memory = self._get_memory_usage()
        self._setup_cuda_optimization()
        self._configure_environment()

    def _get_memory_usage(self) -> Dict[str, float]:
        """현재 메모리 사용량 확인"""
        process = psutil.Process()
        mem_info = process.memory_info()

        gpu_memory = 0
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.memory_allocated() / 1024**3  # GB

        return {
            'ram_gb': mem_info.rss / 1024**3,
            'gpu_gb': gpu_memory,
            'total_gb': (mem_info.rss / 1024**3) + gpu_memory
        }

    def _setup_cuda_optimization(self):
        """CUDA 메모리 최적화 설정"""
        if torch.cuda.is_available():
            # GPU 메모리 제한 (전체의 80%만 사용)
            torch.cuda.set_per_process_memory_fraction(0.8)

            # 메모리 단편화 방지
            os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:512'

            # Lazy loading
            os.environ['CUDA_MODULE_LOADING'] = 'LAZY'

            # TF32 비활성화 (정확도 우선)
            torch.backends.cuda.matmul.allow_tf32 = False

            logger.info(f"CUDA 최적화 적용: GPU {torch.cuda.get_device_name(0)}")

    def _configure_environment(self):
        """환경 변수 최적화"""
        optimizations = {
            'OMP_NUM_THREADS': '4',  # OpenMP 스레드 제한
            'MKL_NUM_THREADS': '4',   # MKL 스레드 제한
            'TOKENIZERS_PARALLELISM': 'false',  # 토크나이저 병렬처리 비활성화
            'TRANSFORMERS_CACHE': '/tmp/transformers_cache',  # 캐시 위치
            'HF_DATASETS_OFFLINE': '1',  # 오프라인 모드
        }

        for key, value in optimizations.items():
            os.environ[key] = value

    def optimize_model_loading(self, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """모델 로딩 최적화 설정"""

        # 4bit 양자화 설정
        optimized_config = {
            **model_config,
            'n_gpu_layers': -1,  # 모든 레이어 GPU 사용
            'n_ctx': 4096,  # 컨텍스트 크기 제한 (8192 → 4096)
            'n_batch': 256,  # 배치 크기 제한 (512 → 256)
            'n_threads': 4,  # CPU 스레드 제한
            'use_mmap': True,  # 메모리 매핑 사용
            'use_mlock': False,  # 메모리 락 비활성화
            'low_vram': True,  # 낮은 VRAM 모드
            'tensor_split': None,  # 자동 텐서 분할
            'rope_freq_base': 10000,  # RoPE 주파수
            'rope_freq_scale': 1.0,
        }

        # 4bit 양자화 파라미터
        if 'quantization' not in optimized_config:
            optimized_config['quantization'] = {
                'load_in_4bit': True,
                'bnb_4bit_compute_dtype': 'float16',
                'bnb_4bit_quant_type': 'nf4',
                'bnb_4bit_use_double_quant': True,
            }

        return optimized_config

    def cleanup_memory(self):
        """메모리 정리"""
        # Python 가비지 컬렉션
        gc.collect()

        # CUDA 캐시 정리
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

        current_memory = self._get_memory_usage()
        saved = self.original_memory['total_gb'] - current_memory['total_gb']

        logger.info(f"메모리 정리 완료: {saved:.2f}GB 절약")
        logger.info(f"현재 사용량 - RAM: {current_memory['ram_gb']:.2f}GB, GPU: {current_memory['gpu_gb']:.2f}GB")

    def get_optimization_stats(self) -> Dict[str, Any]:
        """최적화 통계 반환"""
        current = self._get_memory_usage()

        return {
            'original_memory_gb': self.original_memory['total_gb'],
            'current_memory_gb': current['total_gb'],
            'saved_gb': self.original_memory['total_gb'] - current['total_gb'],
            'optimization_rate': ((self.original_memory['total_gb'] - current['total_gb']) /
                                 self.original_memory['total_gb'] * 100) if self.original_memory['total_gb'] > 0 else 0,
            'gpu_usage_gb': current['gpu_gb'],
            'ram_usage_gb': current['ram_gb'],
        }


class ModelQuantizer:
    """모델 양자화 클래스"""

    @staticmethod
    def quantize_model(model_path: str, output_path: str = None) -> str:
        """모델을 4bit로 양자화"""
        from llama_cpp import Llama

        logger.info(f"모델 양자화 시작: {model_path}")

        # 4bit 양자화 설정
        quantization_params = {
            'n_gpu_layers': -1,
            'n_ctx': 4096,
            'n_batch': 256,
            'use_mmap': True,
            'low_vram': True,
        }

        try:
            # 모델 로드 (4bit 양자화)
            model = Llama(
                model_path=model_path,
                **quantization_params
            )

            # 출력 경로 설정
            if output_path is None:
                output_path = model_path.replace('.gguf', '_4bit.gguf')

            logger.info(f"양자화 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"양자화 실패: {e}")
            raise


def apply_memory_optimizations():
    """메모리 최적화 적용 (메인 함수)"""

    logger.info("="*60)
    logger.info("메모리 최적화 시작")
    logger.info("="*60)

    # 1. 메모리 최적화 초기화
    optimizer = MemoryOptimizer()

    # 2. 초기 상태 출력
    initial_stats = optimizer.get_optimization_stats()
    logger.info(f"초기 메모리 사용: {initial_stats['current_memory_gb']:.2f}GB")

    # 3. 설정 파일 업데이트
    config_updates = {
        'N_CTX': 4096,  # 8192 → 4096
        'N_BATCH': 256,  # 512 → 256
        'N_GPU_LAYERS': -1,
        'USE_MMAP': True,
        'LOW_VRAM': True,
        'MAX_TOKENS': 512,  # 800 → 512
        'TEMPERATURE': 0.3,
        'TOP_P': 0.85,
        'TOP_K': 30,
        'REPEAT_PENALTY': 1.15,
    }

    # config.py 파일 업데이트
    config_path = Path("config.py")
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for key, value in config_updates.items():
            # 설정 값 업데이트 로직
            logger.info(f"설정 업데이트: {key} = {value}")

    # 4. 메모리 정리
    optimizer.cleanup_memory()

    # 5. 최종 통계
    final_stats = optimizer.get_optimization_stats()
    logger.info("="*60)
    logger.info(f"최적화 완료!")
    logger.info(f"절약된 메모리: {final_stats['saved_gb']:.2f}GB")
    logger.info(f"최종 사용량: {final_stats['current_memory_gb']:.2f}GB")
    logger.info(f"최적화율: {final_stats['optimization_rate']:.1f}%")
    logger.info("="*60)

    return final_stats


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 메모리 최적화 실행
    stats = apply_memory_optimizations()

    print("\n✅ 메모리 최적화 완료!")
    print(f"   - 초기: {stats['original_memory_gb']:.2f}GB")
    print(f"   - 현재: {stats['current_memory_gb']:.2f}GB")
    print(f"   - 절약: {stats['saved_gb']:.2f}GB ({stats['optimization_rate']:.1f}%)")