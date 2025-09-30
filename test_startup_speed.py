#!/usr/bin/env python3
"""시작 속도 테스트"""
import time
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def test_startup():
    """캐시와 함께 시작 속도 테스트"""
    logger.info("⚡ 시작 속도 테스트")
    logger.info("=" * 60)

    try:
        # 시작 시간 측정
        start_time = time.time()

        # 로그 숨기기
        sys.stdout = open('/dev/null', 'w')
        sys.stderr = open('/dev/null', 'w')

        from perfect_rag import PerfectRAG
        rag = PerfectRAG()

        # 로그 복원
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        init_time = time.time() - start_time
        logger.info(f"✅ 초기화 완료: {init_time:.2f}초")

        # 간단한 테스트 쿼리
        query_start = time.time()
        response = rag.answer("시스템 테스트")
        query_time = time.time() - query_start

        if response:
            logger.info(f"✅ 응답 성공: {query_time:.2f}초")
        else:
            logger.info(f"⚠️  빈 응답: {query_time:.2f}초")

        # 통계 출력
        logger.info("=" * 60)
        logger.info("📊 성능 요약:")
        logger.info(f"  • 초기화 시간: {init_time:.2f}초")
        logger.info(f"  • 첫 응답 시간: {query_time:.2f}초")
        logger.info(f"  • 총 시간: {init_time + query_time:.2f}초")

        if init_time < 10:
            logger.info("  • 상태: ✨ 매우 빠름!")
        elif init_time < 30:
            logger.info("  • 상태: ✅ 양호")
        else:
            logger.info("  • 상태: ⚠️  개선 필요")

        logger.info("=" * 60)
        return True

    except Exception as e:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        logger.error(f"❌ 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    test_startup()