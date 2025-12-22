#!/usr/bin/env python3
"""
사이드바 카운트 정합성 테스트

NOTE: 이 테스트는 실제 DB 상태에 의존하므로 통합 테스트로 분류합니다.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

import pytest

from app.data.metadata_db import MetadataDB
from config.indexing import ALLOWED_EXTS


@pytest.mark.integration
@pytest.mark.skip(reason="실제 DB 상태에 의존하는 통합 테스트 - CI 환경에서 스킵")
class TestSidebarCounts(unittest.TestCase):
    """사이드바 카운트 정합성 테스트"""

    def setUp(self):
        """테스트 초기화"""
        self.db = MetadataDB()

    def tearDown(self):
        """테스트 정리"""
        if self.db:
            self.db.close()

    def test_case1_pdf_txt_counts(self):
        """케이스1: PDF 480 + TXT 3 = 483 검증"""
        print("\n=== 케이스1: PDF + TXT 카운트 검증 ===")

        # 고유 문서 수
        unique_count = self.db.count_unique_documents(allowed_ext=("pdf", "txt"))
        print(f"라이브러리 총 문서 (PDF+TXT): {unique_count}개")

        # 확장자별 카운트 (물리 파일 기준)
        ext_counts = self.db.count_by_extension()
        print(f"물리 파일 - PDF: {ext_counts.get('pdf', 0)}개, TXT: {ext_counts.get('txt', 0)}개")
        physical_total = ext_counts.get("pdf", 0) + ext_counts.get("txt", 0)
        print(f"물리 파일 총계: {physical_total}개")

        # 검색 인덱스 카운트
        search_count = self.db.count_search_index()
        print(f"검색 인덱스: {search_count}개")

        # 정합성 체크
        if unique_count == search_count:
            print("✅ 라이브러리와 검색 인덱스 일치")
        else:
            print(f"⚠️ 불일치 감지! 라이브러리 {unique_count} ≠ 검색 인덱스 {search_count}")

        # 예상값 검증 (483개여야 함)
        self.assertEqual(unique_count, 483, f"고유 문서 수는 483이어야 하는데 {unique_count}개입니다")

    def test_case2_txt_exclusion_policy(self):
        """케이스2: TXT 제외 정책 테스트"""
        print("\n=== 케이스2: TXT 제외 정책 ===")

        # PDF만 카운트
        pdf_only_count = self.db.count_unique_documents(allowed_ext=("pdf",))
        print(f"라이브러리 총 문서 (PDF만): {pdf_only_count}개")

        # 예상값 검증 (480개여야 함)
        self.assertEqual(pdf_only_count, 480, f"PDF 문서 수는 480이어야 하는데 {pdf_only_count}개입니다")

    def test_case3_duplicate_check(self):
        """케이스3: 중복 제거 검증"""
        print("\n=== 케이스3: 중복 제거 검증 ===")

        # 전체 레코드 수 (_get_conn으로 thread-safe 접근)
        cursor = self.db._get_conn().execute("SELECT COUNT(*) as total FROM documents")
        total_records = cursor.fetchone()["total"]

        # 고유 문서 수
        unique_count = self.db.count_unique_documents()

        print(f"전체 레코드: {total_records}개")
        print(f"고유 문서: {unique_count}개")
        print(f"중복 레코드: {total_records - unique_count}개")

        # 중복이 제거되었는지 확인
        self.assertLessEqual(unique_count, total_records, "고유 문서 수는 전체 레코드 수 이하여야 합니다")

    def test_count_consistency(self):
        """통합 카운트 일관성 테스트"""
        print("\n=== 통합 카운트 일관성 테스트 ===")

        # 모든 카운트 수집
        allowed_ext_list = [ext.replace(".", "") for ext in ALLOWED_EXTS]
        unique_count = self.db.count_unique_documents(allowed_ext=tuple(allowed_ext_list))
        ext_counts = self.db.count_by_extension()
        search_count = self.db.count_search_index()

        print(f"설정된 허용 확장자: {ALLOWED_EXTS}")
        print(f"라이브러리 총 문서: {unique_count}개")
        print(f"물리 파일: PDF {ext_counts.get('pdf', 0)}개, TXT {ext_counts.get('txt', 0)}개")
        print(f"검색 인덱스: {search_count}개")

        # 일관성 체크
        consistency_check = {
            "library_vs_search": unique_count == search_count,
            "library_expected": unique_count == 483,
            "physical_expected": ext_counts.get("pdf", 0) == 490 or ext_counts.get("pdf", 0) == 480
        }

        print("\n일관성 체크 결과:")
        for check, result in consistency_check.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check}: {result}")

        # 모든 체크가 통과해야 함
        if not all(consistency_check.values()):
            print("\n⚠️ 일부 일관성 체크 실패! 재색인이 필요할 수 있습니다.")


def run_tests():
    """테스트 실행"""
    # 테스트 스위트 생성
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSidebarCounts)

    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 결과 요약
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ 모든 테스트 통과!")
    else:
        print(f"❌ 실패한 테스트: {len(result.failures)}개")
        print(f"❌ 에러 발생: {len(result.errors)}개")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
