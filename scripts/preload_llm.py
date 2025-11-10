#!/usr/bin/env python3
"""
LLM Preload Script
Preloads the LLM model at server startup to reduce first-query latency
"""
import os
import sys
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from rag_system.llm_singleton import LLMSingleton

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
        model_path = os.getenv('MODEL_PATH') or os.getenv('LLM_MODEL_PATH')

        if not model_path:
            raise ValueError("MODEL_PATH or LLM_MODEL_PATH not set in environment")

        generator = LLMSingleton.get_instance(model_path=model_path)

        # Do a test generation to ensure model is fully loaded
        logger.info("🔍 Testing model with warm-up query...")
        test_query = "안녕하세요"
        # generate_response requires context_chunks, so pass empty list for warmup
        test_response = generator.generate_response(test_query, context_chunks=[])

        load_time = time.time() - start_time

        logger.info(f"✅ LLM model preloaded successfully in {load_time:.2f} seconds")
        logger.info(f"📊 Model info:")
        logger.info(f"   - Model path: {model_path}")

        # test_response is a RAGResponse object
        response_text = test_response.answer if hasattr(test_response, 'answer') else str(test_response)
        logger.info(f"   - Test response length: {len(response_text)} chars")

        # Print singleton stats
        stats = LLMSingleton.get_stats()
        logger.info(f"   - Load time: {stats['load_time']:.2f}s")
        logger.info(f"   - Usage count: {stats['usage_count']}")

        # Keep the model in memory (don't exit)
        return generator

    except Exception as e:
        logger.error(f"❌ Failed to preload LLM model: {e}")
        logger.error(f"Error details: {type(e).__name__}: {str(e)}")
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
            response_text = test_response.answer if hasattr(test_response, 'answer') else str(test_response)
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