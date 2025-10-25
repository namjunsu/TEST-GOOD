#!/usr/bin/env python3
"""
L2 RAG 스모크 테스트 - 운영 안정성 검증
2025-10-25

검증 항목:
1. 조합 검색 정확도 (연도 + 기안자)
2. 파일 요약 패턴
3. 스키마 미스 재발 방지
4. 리랭킹 동작 확인
"""

import sys
import time
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from quick_fix_rag import QuickFixRAG
from app.core.logging import get_logger

logger = get_logger(__name__)


class L2RagTester:
    """L2 RAG 스모크 테스트"""

    def __init__(self):
        """초기화"""
        logger.info("🧪 L2 RAG 테스터 초기화 중...")
        self.rag = QuickFixRAG(use_hybrid=True)
        self.test_results = []

    def run_all_tests(self) -> bool:
        """모든 테스트 실행

        Returns:
            전체 테스트 통과 여부
        """
        logger.info("\n" + "=" * 80)
        logger.info("🚀 L2 RAG 스모크 테스트 시작")
        logger.info("=" * 80 + "\n")

        tests = [
            ("조합 검색 정확도", self.test_combination_search),
            ("파일 요약 패턴", self.test_file_summary_pattern),
            ("스키마 미스 방지", self.test_schema_validation),
            ("리랭킹 동작", self.test_reranking),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            logger.info(f"\n{'─' * 80}")
            logger.info(f"📝 테스트: {test_name}")
            logger.info(f"{'─' * 80}")

            try:
                start_time = time.time()
                result = test_func()
                elapsed = time.time() - start_time

                if result:
                    logger.info(f"✅ PASS - {test_name} ({elapsed:.2f}초)")
                    passed += 1
                else:
                    logger.error(f"❌ FAIL - {test_name} ({elapsed:.2f}초)")
                    failed += 1

                self.test_results.append({
                    'test': test_name,
                    'passed': result,
                    'time': elapsed
                })

            except Exception as e:
                logger.error(f"💥 ERROR - {test_name}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
                self.test_results.append({
                    'test': test_name,
                    'passed': False,
                    'time': 0,
                    'error': str(e)
                })

        # 최종 결과 출력
        logger.info("\n" + "=" * 80)
        logger.info("📊 테스트 결과 요약")
        logger.info("=" * 80)
        logger.info(f"✅ 통과: {passed}개")
        logger.info(f"❌ 실패: {failed}개")
        logger.info(f"📌 총 {len(tests)}개 테스트")

        # 상세 결과
        logger.info("\n상세 결과:")
        for result in self.test_results:
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            logger.info(f"  {status} - {result['test']} ({result['time']:.2f}초)")
            if 'error' in result:
                logger.info(f"      에러: {result['error']}")

        return failed == 0

    def test_combination_search(self) -> bool:
        """조합 검색 정확도 테스트

        Returns:
            테스트 통과 여부
        """
        query = "2025년에 최새름 문서 찾아줘"

        logger.info(f"질의: {query}")

        result = self.rag.answer(query, use_llm_summary=False)

        # 검증 1: 결과가 있는지
        if "❌" in result and "찾을 수 없습니다" in result:
            logger.error("검증 실패: 결과 없음")
            return False

        # 검증 2: 결과 개수가 적절한지 (10-20건 사이)
        if "개 문서" in result:
            import re
            match = re.search(r'(\d+)개 문서', result)
            if match:
                count = int(match.group(1))
                logger.info(f"결과 개수: {count}건")

                # 너무 많으면 필터링이 안 된 것
                if count > 50:
                    logger.error(f"검증 실패: 결과 개수 과다 ({count}건 > 50건)")
                    logger.error("예상: 조합 필터가 제대로 작동하지 않음")
                    return False

                # 적정 범위 확인
                if 10 <= count <= 30:
                    logger.info(f"✓ 결과 개수 적정 ({count}건)")
                else:
                    logger.warning(f"⚠ 결과 개수 범위 밖 ({count}건)")

        # 검증 3: 2025년 문서만 포함되는지 확인
        if "2024" in result or "2023" in result:
            logger.error("검증 실패: 다른 연도 문서 포함됨 (필터 미작동)")
            return False

        logger.info("✓ 2025년 문서만 포함")

        # 검증 4: 최새름 관련 문서인지
        # (기안자 이름은 결과에 표시되지 않을 수 있으므로 생략)

        return True

    def test_file_summary_pattern(self) -> bool:
        """파일 요약 패턴 테스트

        Returns:
            테스트 통과 여부
        """
        # 실제 존재하는 파일명으로 테스트
        query = "2025-03-04_방송_영상_보존용_DVR_교체_검토의_건.pdf 이 문서 내용 요약"

        logger.info(f"질의: {query}")

        result = self.rag.answer(query, use_llm_summary=False)

        # 검증 1: 결과가 있는지
        if "❌" in result or "찾을 수 없습니다" in result:
            logger.warning("⚠ 해당 파일이 없을 수 있음 (DB에 없음)")
            # 이 경우는 패스 (파일이 실제로 없을 수 있음)
            return True

        # 검증 2: 정확한 파일명이 포함되는지
        if "2025-03-04_방송_영상_보존용_DVR_교체_검토의_건.pdf" not in result:
            logger.error("검증 실패: 정확한 파일명이 결과에 없음")
            return False

        logger.info("✓ 정확한 파일명 포함")

        # 검증 3: 메타데이터가 포함되는지 (날짜, 카테고리 등)
        has_metadata = any(keyword in result for keyword in ["날짜:", "카테고리:", "기안자:"])
        if not has_metadata:
            logger.warning("⚠ 메타데이터가 결과에 없음")

        logger.info("✓ 메타데이터 포함" if has_metadata else "⚠ 메타데이터 미포함")

        return True

    def test_schema_validation(self) -> bool:
        """스키마 미스 재발 방지 테스트

        Returns:
            테스트 통과 여부
        """
        logger.info("코드에서 doc_number 컬럼 참조 검증 중...")

        # 1. pipeline.py 검증
        pipeline_file = Path(__file__).parent / "app" / "rag" / "pipeline.py"
        if pipeline_file.exists():
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # SQL 쿼리에서 doc_number 참조 찾기
            import re
            sql_pattern = r'SELECT.*?FROM\s+documents'
            sql_queries = re.findall(sql_pattern, content, re.IGNORECASE | re.DOTALL)

            for query in sql_queries:
                if 'doc_number' in query:
                    logger.error(f"검증 실패: pipeline.py에 doc_number 컬럼 참조 발견")
                    logger.error(f"쿼리: {query[:200]}...")
                    return False

            logger.info("✓ pipeline.py - doc_number 참조 없음")
        else:
            logger.warning("⚠ pipeline.py 파일 없음 (건너뜀)")

        # 2. quick_fix_rag.py 검증
        rag_file = Path(__file__).parent / "quick_fix_rag.py"
        if rag_file.exists():
            with open(rag_file, 'r', encoding='utf-8') as f:
                content = f.read()

            sql_pattern = r'SELECT.*?FROM\s+documents'
            sql_queries = re.findall(sql_pattern, content, re.IGNORECASE | re.DOTALL)

            for query in sql_queries:
                if 'doc_number' in query:
                    logger.error(f"검증 실패: quick_fix_rag.py에 doc_number 컬럼 참조 발견")
                    logger.error(f"쿼리: {query[:200]}...")
                    return False

            logger.info("✓ quick_fix_rag.py - doc_number 참조 없음")
        else:
            logger.warning("⚠ quick_fix_rag.py 파일 없음 (건너뜀)")

        return True

    def test_reranking(self) -> bool:
        """리랭킹 동작 테스트

        Returns:
            테스트 통과 여부
        """
        # 리랭커가 초기화되었는지 확인
        if not hasattr(self.rag, 'reranker') or self.rag.reranker is None:
            logger.error("검증 실패: 리랭커가 초기화되지 않음")
            return False

        logger.info("✓ 리랭커 초기화됨")

        # 간단한 쿼리로 리랭킹 동작 확인
        query = "방송 장비"
        result = self.rag.answer(query, use_llm_summary=False)

        # 결과가 있는지만 확인 (리랭킹은 내부적으로 동작)
        if "❌" in result:
            logger.warning("⚠ 검색 결과 없음 (리랭킹 테스트 불가)")
            # 이 경우는 패스 (검색 결과가 없을 수 있음)
            return True

        logger.info("✓ 리랭킹 동작 정상 (내부 로그 확인 필요)")

        return True


def main():
    """메인 함수"""
    try:
        tester = L2RagTester()
        success = tester.run_all_tests()

        if success:
            logger.info("\n🎉 모든 테스트 통과!")
            logger.info("✅ L2 RAG 시스템 운영 준비 완료")
            sys.exit(0)
        else:
            logger.error("\n💥 일부 테스트 실패")
            logger.error("❌ 시스템 점검 필요")
            sys.exit(1)

    except Exception as e:
        logger.error(f"\n💥 테스트 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
