"""
문서 유형(doctype) 분류기
- 룰 기반 분류 (키워드 매칭)
- 다중 매칭 시 우선순위 적용
- config/document_processing.yaml 설정 기반
"""

import re
from typing import Dict, List, Any, Tuple
import yaml
from pathlib import Path


class DocumentTypeClassifier:
    """문서 유형 분류기"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.enabled = self.config.get("enable_doctype_classification", True)

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            # 기본 설정 반환
            return self._get_default_config()

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환"""
        return {
            "enable_doctype_classification": True,
            "doctype": {
                "proposal": {
                    "enabled": True,
                    "keywords": ["기안서", "장비구매", "장비수리", "기안자", "시행일자", "품의서"],
                    "priority": 1,
                },
                "report": {
                    "enabled": True,
                    "keywords": ["보고서", "개요", "결론", "결재안", "검토의견", "장표", "그림"],
                    "priority": 2,
                },
                "review": {
                    "enabled": True,
                    "keywords": ["기술검토서", "검토서", "검토 의견", "비교표", "대안", "평가"],
                    "priority": 3,
                },
                "minutes": {
                    "enabled": True,
                    "keywords": ["회의록", "참석자", "안건", "결정사항", "To-Do", "Action Item", "조치사항"],
                    "priority": 4,
                },
            },
        }

    def classify(self, text: str, filename: str = "") -> Dict[str, Any]:
        """
        문서 유형 분류

        Args:
            text: 문서 텍스트 (전체 또는 앞부분 샘플)
            filename: 파일명 (추가 힌트용)

        Returns:
            {
                "doctype": "proposal"|"report"|"review"|"minutes"|"unknown",
                "confidence": 0.0~1.0,
                "reasons": ["매칭된 키워드들"]
            }
        """
        if not self.enabled:
            return {"doctype": "proposal", "confidence": 1.0, "reasons": ["기본값"]}

        # 텍스트 정규화
        normalized_text = self._normalize_text(text)
        normalized_filename = self._normalize_text(filename)

        # 각 doctype별 매칭 점수 계산
        scores = []
        doctype_config = self.config.get("doctype", {})

        for doctype_name, doctype_info in doctype_config.items():
            if not doctype_info.get("enabled", True):
                continue

            keywords = doctype_info.get("keywords", [])
            priority = doctype_info.get("priority", 999)

            # 매칭된 키워드 수 계산
            matched_keywords = []
            for keyword in keywords:
                normalized_keyword = self._normalize_text(keyword)
                # 텍스트와 파일명 모두에서 검색
                if normalized_keyword in normalized_text or normalized_keyword in normalized_filename:
                    matched_keywords.append(keyword)

            if matched_keywords:
                # 점수 = 매칭 키워드 수 / 전체 키워드 수
                score = len(matched_keywords) / len(keywords) if keywords else 0.0
                scores.append(
                    {
                        "doctype": doctype_name,
                        "score": score,
                        "priority": priority,
                        "matched": matched_keywords,
                    }
                )

        # 매칭된 것이 없으면 unknown
        if not scores:
            return {"doctype": "unknown", "confidence": 0.0, "reasons": []}

        # 우선순위 정렬 (점수 높은 순, 같으면 우선순위 낮은 순)
        scores.sort(key=lambda x: (-x["score"], x["priority"]))

        best = scores[0]
        return {
            "doctype": best["doctype"],
            "confidence": best["score"],
            "reasons": best["matched"],
        }

    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화 (공백, 대소문자 등)"""
        if not text:
            return ""

        # 공백 정규화
        normalized = re.sub(r"\s+", " ", text)

        # 소문자 변환 (한글은 영향 없음)
        normalized = normalized.lower()

        return normalized.strip()

    def get_doctype_name_korean(self, doctype: str) -> str:
        """doctype 코드 → 한글 이름"""
        mapping = {
            "proposal": "기안서",
            "report": "보고서",
            "review": "검토서",
            "minutes": "회의록",
            "unknown": "미분류",
        }
        return mapping.get(doctype, "미분류")


# 싱글톤 인스턴스
_classifier = None


def get_classifier() -> DocumentTypeClassifier:
    """분류기 싱글톤 반환"""
    global _classifier
    if _classifier is None:
        _classifier = DocumentTypeClassifier()
    return _classifier


def classify_document(text: str, filename: str = "") -> Dict[str, Any]:
    """문서 유형 분류 (편의 함수)"""
    classifier = get_classifier()
    return classifier.classify(text, filename)
