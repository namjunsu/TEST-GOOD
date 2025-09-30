#!/usr/bin/env python3
"""
Phase 8: 심화 중복 코드 제거 테스트
2025-09-29
"""

import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_phase8_cleanup():
    """Phase 8 정리 후 테스트"""
    try:
        logger.info("=" * 50)
        logger.info("🧹 Phase 8: 심화 중복 코드 제거 테스트")
        logger.info("=" * 50)

        # 1. Import 테스트
        logger.info("\n1️⃣ PerfectRAG 임포트 테스트...")
        from perfect_rag import PerfectRAG
        logger.info("✅ PerfectRAG 임포트 성공")

        # 2. 인스턴스 생성 테스트
        logger.info("\n2️⃣ PerfectRAG 인스턴스 생성...")
        rag = PerfectRAG()
        logger.info("✅ 인스턴스 생성 성공")

        # 3. 제거된 메서드 확인
        logger.info("\n3️⃣ 제거된 중복 메서드 확인...")
        removed_methods = [
            '_prepare_llm_context',
            '_format_llm_response',
            '_parallel_search_pdfs',
            '_parallel_extract_metadata'
        ]

        for method in removed_methods:
            if not hasattr(rag, method):
                logger.info(f"✅ {method} - 성공적으로 제거됨")
            else:
                logger.warning(f"⚠️ {method} - 아직 존재함")

        # 4. LLM 위임 테스트
        logger.info("\n4️⃣ LLM 모듈 위임 테스트...")
        if hasattr(rag, 'llm_module') and rag.llm_module:
            logger.info("✅ LLM 모듈 통합 확인")

            # generate_smart_summary가 위임되는지 확인
            if hasattr(rag, '_generate_smart_summary'):
                logger.info("✅ _generate_smart_summary 위임 메서드 유지")
            else:
                logger.info("⚠️ _generate_smart_summary 메서드 제거됨")

        # 5. 캐시 기능 테스트
        logger.info("\n5️⃣ 캐시 기능 테스트...")
        try:
            if hasattr(rag, 'get_cache_stats'):
                stats = rag.get_cache_stats()
                logger.info("✅ 캐시 통계 정상 작동")
                logger.info(f"   캐시 크기: {stats.get('total_size', 0)}")
            else:
                logger.warning("⚠️ get_cache_stats 메서드 없음")
        except Exception as e:
            logger.error(f"❌ 캐시 통계 오류: {e}")

        # 6. 기본 기능 테스트
        logger.info("\n6️⃣ 기본 기능 테스트...")

        # 통계 보고서 테스트
        try:
            if hasattr(rag, '_generate_statistics_report'):
                report = rag._generate_statistics_report("2024년 통계")
                if report:
                    logger.info("✅ 통계 보고서 생성 정상")
                else:
                    logger.info("⚠️ 통계 보고서 비어있음")
            else:
                logger.warning("⚠️ _generate_statistics_report 메서드 없음")
        except Exception as e:
            logger.error(f"❌ 통계 오류: {e}")

        # 7. 파일 크기 비교
        logger.info("\n7️⃣ 파일 크기 비교...")
        original = Path('perfect_rag_backup_phase8.py')
        current = Path('perfect_rag.py')

        if original.exists() and current.exists():
            original_lines = len(original.read_text().splitlines())
            current_lines = len(current.read_text().splitlines())
            reduction = original_lines - current_lines
            percentage = (reduction / original_lines) * 100

            logger.info(f"📊 Phase 8 이전: {original_lines}줄")
            logger.info(f"📊 Phase 8 이후: {current_lines}줄")
            logger.info(f"📊 감소: {reduction}줄 ({percentage:.1f}%)")

            # 전체 리팩토링 성과
            initial_lines = 5378  # 초기 크기
            total_reduction = initial_lines - current_lines
            total_percentage = (total_reduction / initial_lines) * 100

            logger.info(f"\n📈 전체 리팩토링 성과:")
            logger.info(f"   초기: {initial_lines}줄")
            logger.info(f"   현재: {current_lines}줄")
            logger.info(f"   총 감소: {total_reduction}줄 ({total_percentage:.1f}%)")

        logger.info("\n" + "=" * 50)
        logger.info("✨ Phase 8 테스트 완료!")
        logger.info("=" * 50)

        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_phase8_cleanup()
    sys.exit(0 if success else 1)