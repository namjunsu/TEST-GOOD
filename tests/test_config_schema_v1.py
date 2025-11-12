"""
테스트: 문서 처리 설정 스키마 v1
=============================

커버리지:
1. app.config.compat.normalize_config (v0 → v1 변환)
2. app.rag.parse.doctype (weight, negative_keywords)
3. app.rag.parse.parse_meta (author_stoplist normalize/match)
4. scripts.ingest_from_docs (ocr_mode 3-state)
"""

import pytest
from app.config.compat import normalize_config, is_legacy_config, validate_ocr_mode


class TestCompatNormalize:
    """app.config.compat.normalize_config 테스트"""

    def test_ocr_mode_off(self):
        """OCR off 모드 변환"""
        cfg = {"ingestion": {"ocr_enabled": False, "ocr_fallback": False}}
        result = normalize_config(cfg)
        assert result["ingestion"]["ocr_mode"] == "off"

    def test_ocr_mode_fallback(self):
        """OCR fallback 모드 변환"""
        cfg = {"ingestion": {"ocr_enabled": False, "ocr_fallback": True}}
        result = normalize_config(cfg)
        assert result["ingestion"]["ocr_mode"] == "fallback"

    def test_ocr_mode_force(self):
        """OCR force 모드 변환"""
        cfg = {"ingestion": {"ocr_enabled": True, "ocr_fallback": False}}
        result = normalize_config(cfg)
        assert result["ingestion"]["ocr_mode"] == "force"

    def test_doctype_defaults(self):
        """Doctype 기본값 보정"""
        cfg = {"doctype": {"proposal": {"enabled": True, "keywords": ["기안서"]}}}
        result = normalize_config(cfg)
        assert result["doctype"]["proposal"]["weight"] == 1.0
        assert result["doctype"]["proposal"]["negative_keywords"] == []

    def test_author_stoplist_list_to_dict(self):
        """Author stoplist 리스트 → dict 변환"""
        cfg = {"metadata": {"author_stoplist": ["BNC", "LED"]}}
        result = normalize_config(cfg)
        assert isinstance(result["metadata"]["author_stoplist"], dict)
        assert result["metadata"]["author_stoplist"]["normalize"] is True
        assert result["metadata"]["author_stoplist"]["match"] == "exact_token"
        assert result["metadata"]["author_stoplist"]["values"] == ["BNC", "LED"]

    def test_schema_version_upgrade(self):
        """Schema version 0 → 1 업그레이드"""
        cfg = {}
        result = normalize_config(cfg)
        assert result["schema_version"] == 1

    def test_v1_config_passthrough(self):
        """v1 설정은 그대로 통과"""
        cfg = {
            "schema_version": 1,
            "ingestion": {"ocr_mode": "fallback"},
        }
        result = normalize_config(cfg)
        assert result["schema_version"] == 1
        assert result["ingestion"]["ocr_mode"] == "fallback"


class TestDoctypeClassifier:
    """app.rag.parse.doctype 테스트"""

    def test_weight_applied(self):
        """Weight가 스코어에 반영되는지 확인"""
        from app.rag.parse.doctype import DocumentTypeClassifier

        dtc = DocumentTypeClassifier()

        # review는 weight=1.2
        text = "기술검토서입니다. 비교표를 참고하세요. 검토 의견은 다음과 같습니다."
        result = dtc.classify(text, "")

        # review로 분류되어야 함 (weight 가중치 적용)
        assert result["doctype"] == "review"
        assert result["confidence"] > 0.7

    def test_negative_keywords_penalty(self):
        """Negative keywords가 점수 감점에 적용되는지 확인"""
        from app.rag.parse.doctype import DocumentTypeClassifier

        dtc = DocumentTypeClassifier()

        # 기안서 키워드 + 보고서 키워드 (negative)
        text1 = "기안서입니다. 장비구매 요청합니다."
        result1 = dtc.classify(text1, "")

        text2 = "기안서입니다. 장비구매 요청합니다. 보고서 첨부합니다."
        result2 = dtc.classify(text2, "")

        # text2는 negative keyword로 인해 보고서로 분류되어야 함
        assert result1["doctype"] == "proposal"
        assert result2["doctype"] != "proposal"

    def test_korean_pattern_matching(self):
        """한국어 조사가 있어도 매칭되는지 확인"""
        from app.rag.parse.doctype import DocumentTypeClassifier

        dtc = DocumentTypeClassifier()

        tests = [
            ("회의록입니다", "minutes"),
            ("보고서 제출", "report"),
            ("검토서입니다", "review"),
        ]

        for text, expected in tests:
            result = dtc.classify(text, "")
            assert result["doctype"] == expected, f"Failed for: {text}"


class TestAuthorStoplist:
    """app.rag.parse.parse_meta author stoplist 테스트"""

    def test_stoplist_exact_match(self):
        """정확한 매칭"""
        from app.rag.parse.parse_meta import MetaParser

        parser = MetaParser()
        assert parser._is_in_stoplist("BNC") is True
        assert parser._is_in_stoplist("홍길동") is False

    def test_stoplist_normalize_case(self):
        """대소문자 정규화"""
        from app.rag.parse.parse_meta import MetaParser

        parser = MetaParser()
        assert parser._is_in_stoplist("bnc") is True
        assert parser._is_in_stoplist("Bnc") is True

    def test_stoplist_normalize_space(self):
        """공백 정규화"""
        from app.rag.parse.parse_meta import MetaParser

        parser = MetaParser()
        assert parser._is_in_stoplist("B NC") is True
        assert parser._is_in_stoplist(" BNC ") is True

    def test_stoplist_valid_authors(self):
        """정상 작성자는 통과"""
        from app.rag.parse.parse_meta import MetaParser

        parser = MetaParser()
        valid_authors = ["홍길동", "김철수", "이영희"]
        for author in valid_authors:
            assert parser._is_in_stoplist(author) is False


class TestOCRRouting:
    """scripts.ingest_from_docs OCR 모드 테스트"""

    def test_ocr_mode_off(self):
        """OCR off 모드"""
        from scripts.ingest_from_docs import DocumentIngester, OCR_MODE_OFF

        ingester = DocumentIngester(ocr_mode="off", dry_run=True)
        assert ingester.ocr_mode == OCR_MODE_OFF
        assert ingester.ocr_enabled is False

    def test_ocr_mode_fallback(self):
        """OCR fallback 모드"""
        from scripts.ingest_from_docs import DocumentIngester, OCR_MODE_FALLBACK

        ingester = DocumentIngester(ocr_mode="fallback", dry_run=True)
        assert ingester.ocr_mode == OCR_MODE_FALLBACK
        assert ingester.ocr_enabled is True

    def test_ocr_mode_force(self):
        """OCR force 모드"""
        from scripts.ingest_from_docs import DocumentIngester, OCR_MODE_FORCE

        ingester = DocumentIngester(ocr_mode="force", dry_run=True)
        assert ingester.ocr_mode == OCR_MODE_FORCE
        assert ingester.ocr_enabled is True

    def test_ocr_enabled_backward_compat(self):
        """v0 호환: ocr_enabled=True → fallback 모드"""
        from scripts.ingest_from_docs import DocumentIngester, OCR_MODE_FALLBACK

        ingester = DocumentIngester(ocr_enabled=True, dry_run=True)
        assert ingester.ocr_mode == OCR_MODE_FALLBACK
        assert ingester.ocr_enabled is True

    def test_ocr_mode_priority(self):
        """ocr_mode가 ocr_enabled보다 우선"""
        from scripts.ingest_from_docs import DocumentIngester, OCR_MODE_FORCE

        ingester = DocumentIngester(
            ocr_mode="force", ocr_enabled=False, dry_run=True
        )
        assert ingester.ocr_mode == OCR_MODE_FORCE
        assert ingester.ocr_enabled is True  # force != off


class TestValidateOCRMode:
    """validate_ocr_mode 함수 테스트"""

    def test_valid_modes(self):
        """유효한 OCR 모드"""
        assert validate_ocr_mode("off") is True
        assert validate_ocr_mode("fallback") is True
        assert validate_ocr_mode("force") is True

    def test_invalid_modes(self):
        """유효하지 않은 OCR 모드"""
        assert validate_ocr_mode("invalid") is False
        assert validate_ocr_mode("") is False
        assert validate_ocr_mode(None) is False


class TestIsLegacyConfig:
    """is_legacy_config 함수 테스트"""

    def test_v0_config(self):
        """v0 설정 감지"""
        cfg = {"ingestion": {"ocr_enabled": False}}
        assert is_legacy_config(cfg) is True

    def test_v1_config(self):
        """v1 설정 감지"""
        cfg = {"schema_version": 1}
        assert is_legacy_config(cfg) is False
