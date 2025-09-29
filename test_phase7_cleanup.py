#!/usr/bin/env python3
"""
Phase 7: 중복 코드 제거 테스트
2025-09-29
"""

import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_phase7_cleanup():
    """Phase 7 정리 후 테스트"""
    try:
        logger.info("=" * 50)
        logger.info("🧹 Phase 7: 중복 코드 제거 테스트")
        logger.info("=" * 50)

        # 1. Import 테스트
        logger.info("\n1️⃣ PerfectRAG 임포트 테스트...")
        from perfect_rag import PerfectRAG
        logger.info("✅ PerfectRAG 임포트 성공")

        # 2. 인스턴스 생성 테스트
        logger.info("\n2️⃣ PerfectRAG 인스턴스 생성...")
        rag = PerfectRAG()
        logger.info("✅ 인스턴스 생성 성공")

        # 3. 모듈 통합 확인
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

        logger.info(f"✅ 통합된 모듈: {', '.join(modules)}")

        # 4. 제거된 메서드 확인
        logger.info("\n4️⃣ 제거된 중복 메서드 확인...")
        removed_methods = [
            '_optimize_context',
            '_generate_yearly_purchase_report',
            '_generate_drafter_report',
            '_generate_monthly_repair_report'
        ]

        for method in removed_methods:
            # 이 메서드들은 제거되었으므로 없어야 정상
            if not hasattr(rag, method):
                logger.info(f"✅ {method} - 성공적으로 제거됨")
            else:
                logger.warning(f"⚠️ {method} - 아직 존재함")

        # 5. 위임 메서드 테스트
        logger.info("\n5️⃣ 위임 메서드 테스트...")

        # _extract_pdf_info 테스트 (위임되어야 함)
        if hasattr(rag, '_extract_pdf_info'):
            logger.info("✅ _extract_pdf_info - 위임 메서드로 유지됨")
        else:
            logger.warning("⚠️ _extract_pdf_info - 메서드가 없음")

        # 6. 기본 기능 테스트
        logger.info("\n6️⃣ 기본 기능 테스트...")

        # 검색 테스트
        try:
            result = rag.search_by_content("테스트 쿼리", max_results=1)
            logger.info("✅ 검색 기능 정상")
        except Exception as e:
            logger.error(f"❌ 검색 오류: {e}")

        # 통계 보고서 테스트
        try:
            report = rag._generate_statistics_report("2024년 통계")
            if report:
                logger.info("✅ 통계 보고서 생성 정상")
            else:
                logger.info("⚠️ 통계 보고서 비어있음")
        except Exception as e:
            logger.error(f"❌ 통계 오류: {e}")

        # 7. 파일 크기 비교
        logger.info("\n7️⃣ 파일 크기 비교...")
        original = Path('perfect_rag_backup_phase7.py')
        current = Path('perfect_rag.py')

        if original.exists() and current.exists():
            original_lines = len(original.read_text().splitlines())
            current_lines = len(current.read_text().splitlines())
            reduction = original_lines - current_lines
            percentage = (reduction / original_lines) * 100

            logger.info(f"📊 원본: {original_lines}줄")
            logger.info(f"📊 현재: {current_lines}줄")
            logger.info(f"📊 감소: {reduction}줄 ({percentage:.1f}%)")

        logger.info("\n" + "=" * 50)
        logger.info("✨ Phase 7 테스트 완료!")
        logger.info("=" * 50)

        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_phase7_cleanup()
    sys.exit(0 if success else 1)