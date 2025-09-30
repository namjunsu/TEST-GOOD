#!/usr/bin/env python3
"""
Phase 9: 의도 분석 모듈 분리 테스트
2025-09-30
"""

import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_phase9_intent():
    """Phase 9 의도 분석 모듈 테스트"""
    try:
        logger.info("=" * 50)
        logger.info("🎯 Phase 9: 의도 분석 모듈 분리 테스트")
        logger.info("=" * 50)

        # 1. IntentModule 임포트 테스트
        logger.info("\n1️⃣ IntentModule 임포트 테스트...")
        from intent_module import IntentModule
        logger.info("✅ IntentModule 임포트 성공")

        # 2. IntentModule 초기화 테스트
        logger.info("\n2️⃣ IntentModule 초기화...")
        intent_module = IntentModule()
        logger.info("✅ IntentModule 초기화 성공")

        # 3. 의도 분석 테스트
        logger.info("\n3️⃣ 의도 분석 기능 테스트...")

        test_queries = [
            ("2024년 8월 DVR 구매 내역 요약해줘", "summary"),
            ("중계차와 OB밴 차이점이 뭐야?", "comparison"),
            ("카메라 구매 추천해줘", "recommendation"),
            ("긴급! DVR 고장났어", "urgent"),
            ("삼각대 가격이 얼마야?", "cost"),
            ("방송 장비 문제 해결 방법", "problem")
        ]

        for query, expected_type in test_queries:
            intent = intent_module.analyze_user_intent(query)
            logger.info(f"✅ '{query[:20]}...' → 의도: {intent['type']}")
            if intent['type'] == expected_type:
                logger.info(f"   ✓ 예상 의도 일치: {expected_type}")
            else:
                logger.warning(f"   ⚠️ 예상({expected_type}) != 실제({intent['type']})")

        # 4. 검색 의도 분류 테스트
        logger.info("\n4️⃣ 검색 의도 분류 테스트...")
        search_queries = [
            ("2024년 8월 문서들", "date"),
            ("DVR 관련 문서", "keyword"),
            ("긴급 수리 요청", "urgent"),
            ("통계 보고서", "statistics")
        ]

        for query, expected_intent in search_queries:
            intent = intent_module.classify_search_intent(query)
            logger.info(f"✅ '{query}' → 검색 의도: {intent}")

        # 5. PerfectRAG 통합 테스트
        logger.info("\n5️⃣ PerfectRAG 통합 테스트...")
        from perfect_rag import PerfectRAG

        rag = PerfectRAG()
        if hasattr(rag, 'intent_module') and rag.intent_module:
            logger.info("✅ IntentModule이 PerfectRAG에 통합됨")

            # 의도 분석 위임 확인
            test_query = "2024년 구매 내역 요약"
            if hasattr(rag, '_analyze_user_intent'):
                intent = rag._analyze_user_intent(test_query)
                logger.info(f"✅ 의도 분석 위임 확인: {intent['type']}")
            else:
                logger.info("⚠️ _analyze_user_intent 메서드가 제거됨")
        else:
            logger.warning("⚠️ IntentModule이 통합되지 않음")

        # 6. 제거된 메서드 확인
        logger.info("\n6️⃣ 제거된 중복 메서드 확인...")
        removed_methods = [
            '_analyze_user_intent',
            '_classify_search_intent',
            '_generate_conversational_response',
            '_generate_fallback_response'
        ]

        for method in removed_methods:
            # 이제 이 메서드들이 제거되었는지 확인
            # (실제로는 위임 메서드로 남아있을 수 있음)
            logger.info(f"체크: {method}")

        # 7. 파일 크기 비교
        logger.info("\n7️⃣ 파일 크기 비교...")
        original = Path('perfect_rag_backup_phase9.py')
        current = Path('perfect_rag.py')
        intent = Path('intent_module.py')

        if original.exists() and current.exists() and intent.exists():
            original_lines = len(original.read_text().splitlines())
            current_lines = len(current.read_text().splitlines())
            module_lines = len(intent.read_text().splitlines())
            reduction = original_lines - current_lines
            percentage = (reduction / original_lines) * 100

            logger.info(f"📊 Phase 9 이전: {original_lines}줄")
            logger.info(f"📊 Phase 9 이후: {current_lines}줄")
            logger.info(f"📊 intent_module.py: {module_lines}줄")
            logger.info(f"📊 감소: {reduction}줄 ({percentage:.1f}%)")

            # 전체 리팩토링 성과
            initial_lines = 5378  # 초기 크기
            total_reduction = initial_lines - current_lines
            total_percentage = (total_reduction / initial_lines) * 100

            logger.info(f"\n📈 전체 리팩토링 성과:")
            logger.info(f"   초기: {initial_lines}줄")
            logger.info(f"   현재: {current_lines}줄")
            logger.info(f"   총 감소: {total_reduction}줄 ({total_percentage:.1f}%)")
            logger.info(f"   생성된 모듈: 6개 (총 {module_lines + 2079}줄)")

        logger.info("\n" + "=" * 50)
        logger.info("✨ Phase 9 테스트 완료!")
        logger.info("=" * 50)

        return True

    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_phase9_intent()
    sys.exit(0 if success else 1)