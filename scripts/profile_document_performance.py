#!/usr/bin/env python3
"""Document 모드 성능 프로파일링 스크립트

681초 걸리는 쿼리를 다시 실행하여 단계별 시간 측정
"""

import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import get_logger
from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


def main():
    """성능 프로파일링 실행"""

    # 테스트 쿼리 (이전에 681초 걸렸던 쿼리)
    test_query = "주조정실 마스터스위처 교체 검토 이 문서 내용 알려줘"

    logger.info("=" * 80)
    logger.info(f"🔍 Document 모드 성능 프로파일링 시작")
    logger.info(f"📝 쿼리: {test_query}")
    logger.info("=" * 80)

    try:
        # RAG 파이프라인 초기화
        logger.info("⚙️ RAG 파이프라인 초기화 중...")
        pipeline = RAGPipeline()

        # 쿼리 실행 (시간 측정)
        logger.info("🚀 쿼리 실행 중...")
        overall_start = time.perf_counter()

        result = pipeline.query(test_query)

        overall_time = time.perf_counter() - overall_start

        logger.info("=" * 80)
        logger.info(f"✅ 쿼리 완료!")
        logger.info(f"⏱️ 전체 실행 시간: {overall_time:.2f}초 ({overall_time/60:.2f}분)")
        logger.info(f"📊 모드: {result.get('mode', 'UNKNOWN')}")
        logger.info(f"📝 응답 길이: {len(result.get('text', ''))} chars")
        logger.info(f"📄 파일: {result.get('files', [])}")
        logger.info("=" * 80)

        # 응답 미리보기
        answer_preview = result.get('text', '')[:300]
        logger.info(f"📖 응답 미리보기:\n{answer_preview}...")

        return 0

    except KeyboardInterrupt:
        logger.warning("⚠️ 사용자에 의해 중단됨")
        return 1

    except Exception as e:
        logger.exception(f"❌ 프로파일링 실패: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
