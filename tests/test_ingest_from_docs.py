"""
문서 투입 인덱싱 테스트
"""

import pytest
from pathlib import Path
import shutil
import tempfile


@pytest.fixture
def temp_dirs():
    """임시 디렉토리 생성"""
    temp_root = Path(tempfile.mkdtemp())
    incoming = temp_root / "incoming"
    processed = temp_root / "processed"
    rejected = temp_root / "rejected"
    quarantine = temp_root / "quarantine"
    extracted = temp_root / "extracted"

    for d in [incoming, processed, rejected, quarantine, extracted]:
        d.mkdir(parents=True)

    yield {
        "root": temp_root,
        "incoming": incoming,
        "processed": processed,
        "rejected": rejected,
        "quarantine": quarantine,
        "extracted": extracted,
    }

    # 정리
    shutil.rmtree(temp_root)


def test_duplicate_detection(temp_dirs):
    """중복 판정(hash+정규화) 테스트"""
    # TODO: 실제 PDF 파일로 중복 테스트
    # 1. 동일 파일 2번 투입 → 1번만 처리
    # 2. 파일명만 다른 동일 파일 (복사본.pdf) → 중복 감지
    pass


def test_proposal_parsing_success(temp_dirs):
    """기안서 메타·비용표 파싱 성공 테스트"""
    # TODO: 실제 기안서 PDF로 테스트
    # 1. 메타데이터 추출 (날짜, 기안자, 부서)
    # 2. 비용표 파싱 성공
    # 3. doctype=proposal 분류
    pass


def test_report_doctype_classification(temp_dirs):
    """보고서 doctype 분류·요약 템플릿 적용 테스트"""
    # TODO: 보고서 PDF로 테스트
    # 1. "보고서" 키워드로 doctype=report 분류
    # 2. 요약 템플릿이 보고서 형식 사용
    pass


def test_broken_pdf_rejected(temp_dirs):
    """미지원/깨진 PDF → rejected/ 이동 테스트"""
    # TODO: 깨진 PDF 파일로 테스트
    # 1. 텍스트 추출 실패
    # 2. rejected/ 폴더로 이동
    pass


def test_ocr_fallback():
    """OCR off일 때 실패, on일 때 성공 케이스"""
    # TODO: 이미지 기반 PDF로 테스트
    # 1. ocr=False → 텍스트 추출 실패
    # 2. ocr=True → OCR 폴백으로 추출 성공
    pass


def test_metadb_upsert_and_snippet():
    """메타DB 업서트 및 목록뷰 스니펫 생성 테스트"""
    # TODO: 실제 파일로 테스트
    # 1. 메타DB에 문서 추가
    # 2. doctype, display_date, claimed_total, sum_match 필드 확인
    # 3. 목록 조회 시 스니펫 정상 생성
    pass


def test_dry_run_mode():
    """드라이런 모드 테스트"""
    # TODO: dry-run 모드 테스트
    # 1. 파일 이동 없음
    # 2. DB 업서트 없음
    # 3. 리포트만 생성
    pass
