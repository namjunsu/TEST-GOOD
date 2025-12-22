#!/usr/bin/env python3
"""
배치 추론 성능 테스트 스크립트

개별 추론 vs 배치 추론의 처리 시간을 비교합니다.
"""

import logging
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_individual_inference(llm, questions: list[str], contexts: list[list[dict]]) -> dict:
    """개별 추론 테스트

    Args:
        llm: LLM 인스턴스
        questions: 질의 리스트
        contexts: 컨텍스트 리스트

    Returns:
        성능 통계
    """
    logger.info(f"🔄 개별 추론 테스트 ({len(questions)}개 질의)")
    start_time = time.time()

    responses = []
    for i, (question, context) in enumerate(zip(questions, contexts)):
        logger.info(f"  [{i + 1}/{len(questions)}] 처리 중...")
        response = llm.generate_response(question, context)
        responses.append(response)

    total_time = time.time() - start_time
    avg_time = total_time / len(questions)

    return {
        "method": "individual",
        "count": len(questions),
        "total_time": round(total_time, 2),
        "avg_time": round(avg_time, 2),
        "throughput": round(len(questions) / total_time, 2),
        "responses": responses,
    }


def test_batch_inference(llm, questions: list[str], contexts: list[list[dict]]) -> dict:
    """배치 추론 테스트

    Args:
        llm: LLM 인스턴스
        questions: 질의 리스트
        contexts: 컨텍스트 리스트

    Returns:
        성능 통계
    """
    logger.info(f"⚡ 배치 추론 테스트 ({len(questions)}개 질의)")
    start_time = time.time()

    # 배치 메서드가 있는지 확인
    if not hasattr(llm, "generate_batch_responses"):
        logger.warning("⚠️ 배치 메서드 미지원 - 개별 처리로 대체")
        return test_individual_inference(llm, questions, contexts)

    responses = llm.generate_batch_responses(questions, contexts)
    total_time = time.time() - start_time
    avg_time = total_time / len(questions)

    return {
        "method": "batch",
        "count": len(questions),
        "total_time": round(total_time, 2),
        "avg_time": round(avg_time, 2),
        "throughput": round(len(questions) / total_time, 2),
        "responses": responses,
    }


def main():
    """메인 함수"""
    from rag_system.active.llm_singleton import LLMSingleton

    logger.info("=" * 80)
    logger.info("배치 추론 성능 테스트")
    logger.info("=" * 80)

    # 환경 설정
    os.environ["LLM_BACKEND"] = "qwen72b"
    os.environ["ENABLE_FLASH_ATTENTION"] = "true"

    # 테스트 데이터 준비
    test_questions = [
        "Flash Attention이란 무엇인가요?",
        "H100 GPU의 주요 특징은?",
        "배치 처리의 장점은?",
        "메모리 최적화 방법은?",
        "LLM 추론 속도를 높이는 방법은?",
    ]

    test_contexts = [
        [{"content": f"테스트 문서 {i + 1}입니다.", "metadata": {"source": f"test{i + 1}.txt", "page": 1}}]
        for i in range(len(test_questions))
    ]

    try:
        # LLM 로드
        logger.info("\n🤖 LLM 로딩 중...")
        llm = LLMSingleton.get_instance()

        # 1. 개별 추론 테스트
        logger.info("\n" + "=" * 80)
        stats_individual = test_individual_inference(llm, test_questions, test_contexts)

        # 2. 배치 추론 테스트
        logger.info("\n" + "=" * 80)
        stats_batch = test_batch_inference(llm, test_questions, test_contexts)

        # 3. 결과 비교
        logger.info("\n" + "=" * 80)
        logger.info("📊 성능 비교 결과")
        logger.info("=" * 80)

        logger.info("\n🔄 개별 추론:")
        logger.info(f"  - 총 시간: {stats_individual["total_time"]}초")
        logger.info(f"  - 평균 시간: {stats_individual["avg_time"]}초")
        logger.info(f"  - 처리량: {stats_individual["throughput"]} queries/sec")

        logger.info("\n⚡ 배치 추론:")
        logger.info(f"  - 총 시간: {stats_batch["total_time"]}초")
        logger.info(f"  - 평균 시간: {stats_batch["avg_time"]}초")
        logger.info(f"  - 처리량: {stats_batch["throughput"]} queries/sec")

        # 성능 향상률 계산
        time_saving = (stats_individual["total_time"] - stats_batch["total_time"]) / stats_individual["total_time"] * 100
        throughput_gain = (stats_batch["throughput"] - stats_individual["throughput"]) / stats_individual["throughput"] * 100

        logger.info("\n💰 성능 향상:")
        logger.info(f"  - 시간 절감: {time_saving:+.1f}%")
        logger.info(f"  - 처리량 증가: {throughput_gain:+.1f}%")

        if throughput_gain > 50:
            logger.info(f"\n🎉 배치 처리가 효과적입니다! (처리량 {throughput_gain:.1f}% 증가)")
        elif throughput_gain > 0:
            logger.info(f"\n✅ 배치 처리가 성능 향상에 기여합니다. (처리량 {throughput_gain:.1f}% 증가)")
        else:
            logger.warning("\n⚠️ 배치 처리가 느립니다. 배치 크기를 조정하거나 개별 처리를 사용하세요.")

        # 응답 품질 검증
        logger.info("\n📝 응답 품질 검증:")
        for i, (resp_ind, resp_batch) in enumerate(zip(stats_individual["responses"], stats_batch["responses"])):
            logger.info(f"\n질의 {i + 1}: {test_questions[i]}")
            logger.info(f"  - 개별 응답 길이: {len(resp_ind.answer)}자")
            logger.info(f"  - 배치 응답 길이: {len(resp_batch.answer)}자")

        logger.info("\n✅ 테스트 완료!")

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
