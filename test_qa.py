#!/usr/bin/env python3
"""실제 질의응답 테스트"""
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def test_qa():
    """실제 질의응답 테스트"""
    logger.info("🤖 질의응답 테스트 시작")
    logger.info("=" * 60)

    # 테스트 질문들
    test_questions = [
        "2017년에 구매한 카메라 관련 장비는?",
        "문자 발생기 구매 내역을 알려줘",
        "ENG 카메라 렌즈 수리 건에 대해 설명해줘",
        "헬리캠 구매 기안서 내용은?",
        "트라이포드 수리 관련 정보"
    ]

    try:
        # RAG 시스템 초기화
        logger.info("📦 RAG 시스템 초기화 중...")
        start = time.time()

        from perfect_rag import PerfectRAG
        rag = PerfectRAG()

        init_time = time.time() - start
        logger.info(f"✅ 초기화 완료: {init_time:.2f}초\n")

        # 각 질문 테스트
        for i, question in enumerate(test_questions, 1):
            logger.info(f"질문 {i}: {question}")
            logger.info("-" * 40)

            start = time.time()
            try:
                response = rag.answer(question)
                elapsed = time.time() - start

                if response:
                    # 응답 미리보기 (첫 200자)
                    preview = response[:200] + "..." if len(response) > 200 else response
                    logger.info(f"✅ 응답 성공 ({elapsed:.2f}초)")
                    logger.info(f"응답: {preview}")
                else:
                    logger.info(f"⚠️ 빈 응답 ({elapsed:.2f}초)")
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"❌ 오류 발생 ({elapsed:.2f}초): {e}")

            logger.info("")

        logger.info("=" * 60)
        logger.info("✅ 질의응답 테스트 완료")
        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        return False

if __name__ == "__main__":
    test_qa()