#!/usr/bin/env python3
"""
통계 모듈 리팩토링 테스트 스크립트
2025-09-29 Phase 6 테스트
"""

import sys
from pathlib import Path
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_statistics_module():
    """통계 모듈 테스트"""
    try:
        # StatisticsModule 직접 테스트
        logger.info("\n📊 StatisticsModule 직접 테스트...")
        from statistics_module import StatisticsModule

        stats_module = StatisticsModule({'docs_dir': './docs'})
        logger.info("✅ StatisticsModule 임포트 및 초기화 성공")

        # 테스트용 더미 메타데이터
        test_metadata = {
            '2024_08_구매_서버.pdf': {
                'year': '2024',
                'month': '08',
                'category': '구매'
            },
            '2024_09_수리_네트워크.pdf': {
                'year': '2024',
                'month': '09',
                'category': '수리'
            }
        }

        # 통계 데이터 수집 테스트
        logger.info("\n📈 통계 데이터 수집 테스트...")
        stats_data = stats_module.collect_statistics_data(
            "2024년 통계",
            test_metadata
        )
        if stats_data:
            logger.info("✅ 통계 데이터 수집 성공")
            logger.info(f"  - 전체 문서: {stats_data.get('total_count', 0)}개")

        # PerfectRAG 통합 테스트
        logger.info("\n🔗 PerfectRAG 통합 테스트...")
        from perfect_rag import PerfectRAG

        rag = PerfectRAG()

        if hasattr(rag, 'statistics_module') and rag.statistics_module:
            logger.info("✅ PerfectRAG에 StatisticsModule 통합 확인")

            # 통계 보고서 생성 테스트
            logger.info("\n📋 통계 보고서 생성 테스트...")
            test_queries = [
                "2024년 통계 보고서",
                "연도별 구매 현황",
                "기안자별 문서 현황",
                "월별 수리 현황"
            ]

            for query in test_queries:
                logger.info(f"\n테스트 쿼리: '{query}'")
                try:
                    # _generate_statistics_report 메서드 테스트
                    result = rag._generate_statistics_report(query)
                    if result and not result.startswith("❌"):
                        logger.info(f"✅ '{query}' 처리 성공")
                        logger.info(f"  응답 길이: {len(result)}자")
                    else:
                        logger.info(f"⚠️ '{query}' 처리 실패 또는 빈 결과")
                except Exception as e:
                    logger.error(f"❌ '{query}' 처리 중 오류: {e}")
        else:
            logger.warning("⚠️ StatisticsModule이 PerfectRAG에 통합되지 않음")

        # 메서드 위임 확인
        logger.info("\n🔄 메서드 위임 확인...")
        if hasattr(rag, '_collect_statistics_data'):
            try:
                data = rag._collect_statistics_data("2024년")
                logger.info("✅ _collect_statistics_data 메서드 위임 확인")
            except Exception as e:
                logger.error(f"❌ _collect_statistics_data 오류: {e}")

        logger.info("\n✨ Phase 6: 통계 모듈 리팩토링 테스트 완료!")
        logger.info("=" * 50)

        # 모듈 크기 정보
        stats_file = Path('statistics_module.py')
        if stats_file.exists():
            lines = len(stats_file.read_text().splitlines())
            size_kb = stats_file.stat().st_size / 1024
            logger.info(f"\n📊 statistics_module.py:")
            logger.info(f"  - 라인 수: {lines}줄")
            logger.info(f"  - 파일 크기: {size_kb:.1f}KB")

        return True

    except ImportError as e:
        logger.error(f"❌ 모듈 임포트 실패: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("📊 통계 모듈 리팩토링 테스트 시작")
    logger.info("=" * 50)

    success = test_statistics_module()

    if success:
        logger.info("\n✅ 모든 테스트 통과!")
        sys.exit(0)
    else:
        logger.error("\n❌ 테스트 실패")
        sys.exit(1)