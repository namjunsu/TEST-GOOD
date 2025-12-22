#!/usr/bin/env python3
"""
LLM Preload Script
Preloads the LLM model at server startup to reduce first-query latency
"""
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 로깅 초기화 (2025-12-21: 추가)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)

from rag_system.active.llm_singleton import LLMSingleton

logger = logging.getLogger(__name__)


def preload_llm():
    """Preload the LLM model into memory"""

    logger.info("=" * 80)
    logger.info("🚀 Starting LLM Model Preload")
    logger.info("=" * 80)

    start_time = time.time()

    try:
        # Initialize LLM via singleton
        logger.info("📥 Loading LLM model into memory...")
        model_path = os.getenv("MODEL_PATH") or os.getenv("LLM_MODEL_PATH")

        if not model_path:
            raise ValueError("MODEL_PATH or LLM_MODEL_PATH not set in environment")

        generator = LLMSingleton.get_instance(model_path=model_path)

        # Do a test generation to ensure model is fully loaded
        logger.info("🔍 Testing model with warm-up query...")
        test_query = "안녕하세요"
        # generate_response requires context_chunks, so pass empty list for warmup
        inference_start = time.time()
        test_response = generator.generate_response(test_query, context_chunks=[])
        inference_time = time.time() - inference_start
        logger.info(f"   - Warm-up inference: {inference_time:.2f}s")

        load_time = time.time() - start_time

        logger.info(f"✅ LLM model preloaded successfully in {load_time:.2f} seconds")
        logger.info("📊 Model info:")
        logger.info(f"   - Model path: {model_path}")

        # test_response is a RAGResponse object
        response_text = test_response.answer if hasattr(test_response, "answer") else str(test_response)
        logger.info(f"   - Test response length: {len(response_text)} chars")

        # Print singleton stats
        stats = LLMSingleton.get_stats()
        logger.info(f"   - Load time: {stats['load_time']:.2f}s")
        logger.info(f"   - Usage count: {stats['usage_count']}")

        # GPU 메모리 상태 출력 (2025-12-21)
        try:
            import torch
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                logger.info(f"   - GPU Memory: {allocated:.1f}GB used / {total:.1f}GB total ({allocated / total * 100:.0f}%)")
        except Exception:
            pass  # GPU 정보 없으면 무시

        # Keep the model in memory (don't exit)
        return generator

    except Exception as e:
        logger.error(f"❌ Failed to preload LLM model: {e}")
        logger.error(f"Error details: {type(e).__name__}: {e!s}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def keep_alive(generator):
    """Keep the model warm with periodic test queries"""

    logger.info("🔄 Starting keep-alive routine (every 5 minutes)...")

    while True:
        time.sleep(300)  # Wait 5 minutes

        try:
            # Do a quick test query to keep model in GPU memory
            test_response = generator.generate_response("테스트", context_chunks=[])
            response_text = test_response.answer if hasattr(test_response, "answer") else str(test_response)
            logger.debug(f"Keep-alive ping successful: {len(response_text)} chars")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
            # Try to reinitialize
            logger.info("Attempting to reinitialize LLM...")
            generator = preload_llm()
            if not generator:
                logger.error("Failed to reinitialize LLM, exiting keep-alive")
                break


def main():
    """Main preload function"""

    # Check if LLM is enabled
    if os.getenv("LLM_ENABLED", "true").lower() != "true":
        logger.info("LLM is disabled in configuration, skipping preload")
        return

    # Preload the model
    generator = preload_llm()

    if generator:
        logger.info("=" * 80)
        logger.info("🎉 LLM Preload Complete - Model Ready for Queries")
        logger.info("=" * 80)

        # Optional: Keep the model warm
        # Uncomment the next line to enable keep-alive
        # keep_alive(generator)
    else:
        logger.error("=" * 80)
        logger.error("⚠️ LLM Preload Failed - First query will be slower")
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
