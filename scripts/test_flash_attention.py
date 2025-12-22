#!/usr/bin/env python3
"""
Flash Attention 메모리 절감 테스트 스크립트

Flash Attention 활성화 전후의 GPU 메모리 사용량을 비교합니다.
"""

import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_memory_usage(enable_flash_attn: bool) -> dict:
    """메모리 사용량 측정

    Args:
        enable_flash_attn: Flash Attention 활성화 여부

    Returns:
        메모리 통계 딕셔너리
    """
    import torch

    from rag_system.active.llm_singleton import LLMSingleton

    # 환경변수 설정
    os.environ["ENABLE_FLASH_ATTENTION"] = "true" if enable_flash_attn else "false"
    os.environ["LLM_BACKEND"] = "qwen72b"

    # 기존 인스턴스 정리
    LLMSingleton.clear()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    # 메모리 초기 상태
    before_load = torch.cuda.memory_allocated() / 1024**3

    # LLM 로드
    logger.info(f"{'✅' if enable_flash_attn else '❌'} Flash Attention: {enable_flash_attn}")
    llm = LLMSingleton.get_instance()

    # 메모리 로드 후 상태
    after_load = torch.cuda.memory_allocated() / 1024**3
    peak_memory = torch.cuda.max_memory_allocated() / 1024**3

    # 간단한 추론 테스트
    test_context = [
        {
            "content": "테스트 문서입니다. Flash Attention의 메모리 효율성을 측정합니다.",
            "metadata": {"source": "test.txt", "page": 1}
        }
    ]

    logger.info("추론 테스트 시작...")
    response = llm.generate_response("Flash Attention이란 무엇인가요?", test_context)

    # 추론 후 메모리
    after_inference = torch.cuda.memory_allocated() / 1024**3
    peak_after_inference = torch.cuda.max_memory_allocated() / 1024**3

    stats = {
        "flash_attention": enable_flash_attn,
        "before_load_gb": round(before_load, 2),
        "after_load_gb": round(after_load, 2),
        "peak_memory_gb": round(peak_memory, 2),
        "after_inference_gb": round(after_inference, 2),
        "peak_after_inference_gb": round(peak_after_inference, 2),
        "model_memory_gb": round(after_load - before_load, 2),
        "inference_memory_gb": round(after_inference - after_load, 2),
        "response_length": len(response.answer),
        "generation_time": round(response.generation_time, 2),
    }

    # 정리
    LLMSingleton.clear()
    torch.cuda.empty_cache()

    return stats


def main():
    """메인 함수"""
    logger.info("=" * 80)
    logger.info("Flash Attention 메모리 절감 테스트")
    logger.info("=" * 80)

    try:
        # 1. Flash Attention OFF 테스트
        logger.info("\n[1단계] Flash Attention OFF 테스트")
        stats_off = test_memory_usage(enable_flash_attn=False)

        # 2. Flash Attention ON 테스트
        logger.info("\n[2단계] Flash Attention ON 테스트")
        stats_on = test_memory_usage(enable_flash_attn=True)

        # 3. 비교 결과 출력
        logger.info("\n" + "=" * 80)
        logger.info("📊 테스트 결과 비교")
        logger.info("=" * 80)

        logger.info("\n⚙️ Flash Attention OFF:")
        logger.info(f"  - 모델 메모리: {stats_off["model_memory_gb"]} GB")
        logger.info(f"  - 추론 메모리: {stats_off["inference_memory_gb"]} GB")
        logger.info(f"  - 피크 메모리: {stats_off["peak_after_inference_gb"]} GB")
        logger.info(f"  - 생성 시간: {stats_off["generation_time"]}초")

        logger.info("\n⚡ Flash Attention ON:")
        logger.info(f"  - 모델 메모리: {stats_on["model_memory_gb"]} GB")
        logger.info(f"  - 추론 메모리: {stats_on["inference_memory_gb"]} GB")
        logger.info(f"  - 피크 메모리: {stats_on["peak_after_inference_gb"]} GB")
        logger.info(f"  - 생성 시간: {stats_on["generation_time"]}초")

        # 메모리 절감률 계산
        model_saving = (stats_off["model_memory_gb"] - stats_on["model_memory_gb"]) / stats_off["model_memory_gb"] * 100
        inference_saving = (stats_off["inference_memory_gb"] - stats_on["inference_memory_gb"]) / stats_off["inference_memory_gb"] * 100
        peak_saving = (stats_off["peak_after_inference_gb"] - stats_on["peak_after_inference_gb"]) / stats_off["peak_after_inference_gb"] * 100

        logger.info("\n💰 메모리 절감:")
        logger.info(f"  - 모델 메모리: {model_saving:+.1f}%")
        logger.info(f"  - 추론 메모리: {inference_saving:+.1f}%")
        logger.info(f"  - 피크 메모리: {peak_saving:+.1f}%")

        # 속도 비교
        speed_change = (stats_on["generation_time"] - stats_off["generation_time"]) / stats_off["generation_time"] * 100
        logger.info(f"  - 생성 속도: {speed_change:+.1f}%")

        logger.info("\n✅ 테스트 완료!")

        # 기대치 검증
        if peak_saving < 10:
            logger.warning("⚠️ 메모리 절감이 10% 미만입니다. Flash Attention이 제대로 활성화되었는지 확인하세요.")
        else:
            logger.info(f"🎉 Flash Attention이 성공적으로 적용되었습니다! (피크 메모리 {peak_saving:.1f}% 절감)")

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
