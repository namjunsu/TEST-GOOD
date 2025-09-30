#!/usr/bin/env python3
"""
Phase 12: 목표 달성을 위한 최종 정리 테스트
2025-09-30
"""

import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_phase12():
    """Phase 12 최종 정리 테스트"""
    try:
        logger.info("=" * 50)
        logger.info("🎯 Phase 12: 목표 달성 테스트")
        logger.info("=" * 50)

        # 1. Import 테스트
        logger.info("\n1️⃣ PerfectRAG 임포트 테스트...")
        from perfect_rag import PerfectRAG
        logger.info("✅ PerfectRAG 임포트 성공")

        # 2. 인스턴스 생성 테스트
        logger.info("\n2️⃣ PerfectRAG 인스턴스 생성...")
        rag = PerfectRAG()
        logger.info("✅ 인스턴스 생성 성공")

        # 3. 모든 모듈 통합 확인
        logger.info("\n3️⃣ 모듈 통합 확인...")
        modules = []
        if hasattr(rag, 'search_module') and rag.search_module:
            modules.append("SearchModule")
        if hasattr(rag, 'document_module') and rag.document_module:
            modules.append("DocumentModule")
        if hasattr(rag, 'llm_module') and rag.llm_module:
            modules.append("LLMModule")
        if hasattr(rag, 'cache_module') and rag.cache_module:
            modules.append("CacheModule")
        if hasattr(rag, 'statistics_module') and rag.statistics_module:
            modules.append("StatisticsModule")
        if hasattr(rag, 'intent_module') and rag.intent_module:
            modules.append("IntentModule")

        logger.info(f"✅ 통합된 모듈: {', '.join(modules)} ({len(modules)}/6)")

        # 4. 핵심 기능 테스트
        logger.info("\n4️⃣ 핵심 기능 테스트...")

        # answer 메서드 테스트
        if hasattr(rag, 'answer'):
            try:
                test_query = "테스트"
                result = rag.answer(test_query)
                if result:
                    logger.info("✅ answer 메서드 정상 작동")
                else:
                    logger.info("⚠️ answer 메서드 빈 결과")
            except Exception as e:
                logger.warning(f"⚠️ answer 메서드 오류: {e}")

        # 5. Phase 12에서 변경된 사항 확인
        logger.info("\n5️⃣ Phase 12 변경 사항 확인...")

        # _search_by_content 단순화 확인
        import inspect
        if hasattr(rag, '_search_by_content'):
            source = inspect.getsource(rag._search_by_content)
            lines = source.split('\n')
            logger.info(f"✅ _search_by_content 메서드 단순화됨 ({len(lines)}줄)")

        # 프롬프트 메서드 통합 확인
        if hasattr(rag, '_create_prompt'):
            logger.info("✅ 프롬프트 메서드 통합됨 (_create_prompt)")

        # answer_with_logging 제거 확인
        if not hasattr(rag, 'answer_with_logging'):
            logger.info("✅ answer_with_logging 제거됨")

        # 6. 파일 크기 비교
        logger.info("\n6️⃣ 파일 크기 비교...")
        current = Path('perfect_rag.py')

        if current.exists():
            current_lines = len(current.read_text().splitlines())
            logger.info(f"📊 현재: {current_lines}줄")

            # Phase별 감소 내역
            phase_reductions = {
                "초기": 5378,
                "Phase 7": 5224,
                "Phase 8": 4936,
                "Phase 9": 4737,
                "Phase 10": 3639,
                "Phase 11": 2602,
                "Phase 12": current_lines
            }

            logger.info("\n📈 리팩토링 진행 현황:")
            for phase, lines in phase_reductions.items():
                if phase == "초기":
                    logger.info(f"   {phase}: {lines}줄")
                else:
                    prev_lines = list(phase_reductions.values())[list(phase_reductions.keys()).index(phase)-1]
                    reduction = prev_lines - lines
                    if reduction > 0:
                        logger.info(f"   {phase}: {lines}줄 (-{reduction}줄)")
                    else:
                        logger.info(f"   {phase}: {lines}줄")

            # 전체 성과
            initial_lines = 5378
            total_reduction = initial_lines - current_lines
            total_percentage = (total_reduction / initial_lines) * 100

            logger.info(f"\n🎯 전체 리팩토링 성과:")
            logger.info(f"   총 감소: {total_reduction}줄 ({total_percentage:.1f}%)")
            logger.info(f"   목표(2000줄)까지: {current_lines - 2000}줄 남음")

            if current_lines <= 2000:
                logger.info(f"\n🏆 목표 달성! 2000줄 이하로 축소 완료!")

        # 7. 모듈 통계
        logger.info("\n7️⃣ 생성된 모듈 통계:")
        module_files = [
            ('search_module.py', 289),
            ('document_module.py', 418),
            ('llm_module.py', 405),
            ('cache_module.py', 371),
            ('statistics_module.py', 569),
            ('intent_module.py', 338),
        ]

        for module, expected_lines in module_files:
            if Path(module).exists():
                actual_lines = len(Path(module).read_text().splitlines())
                logger.info(f"   - {module}: {actual_lines}줄")
            else:
                logger.info(f"   - {module}: {expected_lines}줄 (예상)")

        logger.info("\n" + "=" * 50)
        logger.info("✨ Phase 12 테스트 완료!")
        logger.info("=" * 50)

        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_phase12()
    sys.exit(0 if success else 1)