"""
PDF Processor 테스트
====================

PDF 문서 처리 모듈의 단위 테스트입니다.
"""

import unittest
from pathlib import Path
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.config import RAGConfig
from rag_core.document.pdf_processor import PDFProcessor
from rag_core.exceptions import PDFExtractionException


class TestPDFProcessor(unittest.TestCase):
    """PDF 처리 테스트 클래스"""

    def setUp(self):
        """테스트 설정"""
        self.config = RAGConfig()
        self.processor = PDFProcessor(self.config)
        self.test_pdf_dir = Path("docs/year_2024")

    def test_extract_text(self):
        """텍스트 추출 테스트"""
        # 테스트 PDF 찾기
        pdf_files = list(self.test_pdf_dir.glob("*.pdf"))
        if not pdf_files:
            self.skipTest("No test PDF files found")

        test_file = pdf_files[0]
        text = self.processor.extract_text(test_file)

        # 검증
        self.assertIsNotNone(text, "Text should not be None")
        self.assertIsInstance(text, str, "Text should be string")
        self.assertGreater(len(text), 0, "Text should not be empty")

    def test_extract_metadata(self):
        """메타데이터 추출 테스트"""
        pdf_files = list(self.test_pdf_dir.glob("*.pdf"))
        if not pdf_files:
            self.skipTest("No test PDF files found")

        test_file = pdf_files[0]
        metadata = self.processor.extract_metadata(test_file)

        # 필수 필드 검증
        required_fields = ['filename', 'path', 'size', 'pages']
        for field in required_fields:
            self.assertIn(field, metadata, f"Metadata should contain {field}")

        # 값 검증
        self.assertGreater(metadata['size'], 0, "File size should be positive")
        self.assertGreaterEqual(metadata['pages'], 0, "Page count should be non-negative")

    def test_parse_filename(self):
        """파일명 파싱 테스트"""
        test_cases = [
            ("2024-01-15_장비_구매_요청.pdf", {"date": "2024-01-15", "year": "2024", "category": "purchase"}),
            ("2023_연간_수리_보고서.pdf", {"year": "2023", "category": "repair"}),
            ("장비_폐기_신청_2022.pdf", {"year": "2022", "category": "disposal"})
        ]

        for filename, expected in test_cases:
            result = self.processor._parse_filename(filename)
            for key, value in expected.items():
                self.assertEqual(result.get(key), value, f"Failed for {filename}: {key}")

    def test_invalid_pdf(self):
        """잘못된 PDF 처리 테스트"""
        invalid_path = Path("nonexistent.pdf")
        text = self.processor.extract_text(invalid_path)
        # handle_errors 데코레이터 덕분에 빈 문자열 반환
        self.assertEqual(text, "", "Should return empty string for invalid file")

    def test_batch_processing(self):
        """배치 처리 테스트"""
        pdf_files = list(self.test_pdf_dir.glob("*.pdf"))[:3]  # 최대 3개
        if not pdf_files:
            self.skipTest("No test PDF files found")

        results = self.processor.process_batch(pdf_files)

        # 결과 검증
        self.assertEqual(len(results), len(pdf_files), "Should process all files")
        for result in results:
            self.assertIn('path', result)
            self.assertIn('success', result)
            if result['success']:
                self.assertIn('text', result)
                self.assertIn('metadata', result)


class TestConfig(unittest.TestCase):
    """설정 테스트 클래스"""

    def test_default_config(self):
        """기본 설정 테스트"""
        config = RAGConfig()
        self.assertEqual(config.n_ctx, 8192)
        self.assertEqual(config.temperature, 0.3)
        self.assertEqual(config.chunk_size, 1000)

    def test_config_validation(self):
        """설정 유효성 검증 테스트"""
        config = RAGConfig()

        # 잘못된 온도 설정
        config.temperature = 2.0
        with self.assertRaises(ValueError):
            config.validate()

        # 잘못된 청크 설정
        config.temperature = 0.5  # 정상값으로 복구
        config.chunk_size = 100
        config.chunk_overlap = 200
        with self.assertRaises(ValueError):
            config.validate()

    def test_config_save_load(self):
        """설정 저장/로드 테스트"""
        # 설정 생성 및 저장
        config1 = RAGConfig(temperature=0.7, max_tokens=1000)
        test_path = "test_config.json"
        config1.save(test_path)

        # 로드 및 검증
        config2 = RAGConfig.from_file(test_path)
        self.assertEqual(config2.temperature, 0.7)
        self.assertEqual(config2.max_tokens, 1000)

        # 테스트 파일 삭제
        Path(test_path).unlink(missing_ok=True)


def run_tests():
    """테스트 실행 함수"""
    # 테스트 스위트 생성
    suite = unittest.TestSuite()

    # PDF 처리 테스트 추가
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPDFProcessor))

    # 설정 테스트 추가
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfig))

    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 결과 반환
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)