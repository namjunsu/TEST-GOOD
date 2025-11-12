"""
문서 유형(doctype) 분류기 v2.0
- 룰 기반 분류 (가중치 스코어링)
- 파일명 신호 강화 (×2 가중치)
- 음수 키워드 지원
- 핫리로드 (mtime 기반 자동 재적용)
- 근거 리포트 강화 (source, span, pattern)
- config/document_processing.yaml 설정 기반

v2.0 주요 개선사항:
- NFKC 정규화 (전각/반각, 한글/영문 혼용 대응)
- 가중치 스코어링 (본문 ×1, 파일명 ×2, 키워드 가중치)
- 음수 키워드로 오분류 억제
- 정규식 패턴 컴파일 (단어 경계, 유사표기)
- 동점 해소 (점수 → 우선순위 → 파일명 히트 → 키워드 다양성)
- 핫리로드 (10초 간격 mtime 체크)
"""

import re
import unicodedata
import time
from typing import Dict, Any, List, Tuple, Optional
import yaml
from pathlib import Path


class DocumentTypeClassifier:
    """문서 유형 분류기 v2.0"""

    def __init__(
        self,
        config_path: str = "config/document_processing.yaml",
        reload_secs: int = 10,
    ):
        """
        Args:
            config_path: 설정 파일 경로
            reload_secs: 핫리로드 체크 간격 (초)
        """
        self.config_path = config_path
        self._reload_secs = reload_secs
        self._last_load_ts = 0.0
        self._config_mtime = 0.0
        self.config = self._load_config()
        self.enabled = self.config.get("enable_doctype_classification", True)

        # 미리 컴파일된 정규식 (가중치/음수 키워드 포함)
        self._compiled = self._compile_rules(self.config.get("doctype", {}))

    # ---------- 설정 로드/핫리로드 ----------
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드 (mtime 추적)"""
        cfg_file = Path(self.config_path)
        if not cfg_file.exists():
            return self._get_default_config()

        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            # 하위 호환: v0 스키마를 v1로 정규화
            from app.config.compat import normalize_config
            cfg = normalize_config(cfg)

            # 필수 루트 키 보정
            if "doctype" not in cfg:
                cfg["doctype"] = self._get_default_config()["doctype"]

            self._config_mtime = cfg_file.stat().st_mtime
            self._last_load_ts = time.time()
            return cfg
        except Exception:
            return self._get_default_config()

    def _hot_reload_if_needed(self):
        """핫리로드: mtime 변경 시 설정 재적용"""
        now = time.time()
        if now - self._last_load_ts < self._reload_secs:
            return

        cfg_file = Path(self.config_path)
        if cfg_file.exists() and cfg_file.stat().st_mtime > self._config_mtime:
            self.config = self._load_config()
            self.enabled = self.config.get("enable_doctype_classification", True)
            self._compiled = self._compile_rules(self.config.get("doctype", {}))

    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환 (음수 키워드, 가중치 포함)"""
        return {
            "enable_doctype_classification": True,
            "doctype": {
                "proposal": {
                    "enabled": True,
                    "keywords": [
                        "기안서",
                        "장비구매",
                        "장비수리",
                        "기안자",
                        "시행일자",
                        "품의서",
                    ],
                    "neg_keywords": [],  # 음수 키워드 (이 단어가 있으면 점수 감점)
                    "priority": 1,
                    "weight": 1.0,
                },
                "report": {
                    "enabled": True,
                    "keywords": [
                        "보고서",
                        "개요",
                        "결론",
                        "결재안",
                        "검토의견",
                        "장표",
                        "그림",
                    ],
                    "neg_keywords": [],
                    "priority": 2,
                    "weight": 1.0,
                },
                "review": {
                    "enabled": True,
                    "keywords": [
                        "기술검토서",
                        "검토서",
                        "검토 의견",
                        "비교표",
                        "대안",
                        "평가",
                    ],
                    "neg_keywords": [],
                    "priority": 3,
                    "weight": 1.1,  # 검토서 가중치 상승 (더 중요)
                },
                "minutes": {
                    "enabled": True,
                    "keywords": [
                        "회의록",
                        "참석자",
                        "안건",
                        "결정사항",
                        "To-Do",
                        "Action Item",
                        "조치사항",
                    ],
                    "neg_keywords": [],
                    "priority": 4,
                    "weight": 1.0,
                },
            },
            # 스코어링 파라미터
            "score": {
                "filename_boost": 2.0,  # 파일명 히트 가중치 (본문보다 2배)
                "body_weight": 1.0,  # 본문 히트 가중치
                "deny_penalty": 2.0,  # 음수 키워드 패널티
            },
        }

    # ---------- 텍스트 정규화 ----------
    def _normalize_text(self, text: str) -> str:
        """
        텍스트 정규화 (NFKC + 공백/기호 통일)

        - NFKC: 전각/반각, 한글 자모 통일
        - _/- → 공백
        - 연속 공백 → 단일 공백
        - 소문자 변환
        """
        if not text:
            return ""

        # NFKC 정규화 (전각 → 반각, 한글 자모 통일)
        t = unicodedata.normalize("NFKC", text)

        # 언더스코어/하이픈 → 공백
        t = t.replace("_", " ").replace("-", " ")

        # 연속 공백 → 단일 공백
        t = re.sub(r"\s+", " ", t)

        # 소문자 변환
        return t.lower().strip()

    # ---------- 키워드 컴파일 ----------
    def _compile_rules(self, doctype_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        키워드를 정규식으로 컴파일

        - 단어 경계 추가 (\\b 또는 lookbehind/lookahead)
        - 유사표기 허용 (공백/하이픈 임의)
        """

        def pattern(keyword: str) -> str:
            """키워드 → 정규식 패턴"""
            k = self._normalize_text(keyword)
            # 이스케이프
            k = re.escape(k)
            # 공백 → \\s* (0개 이상의 공백 허용)
            k = k.replace(r"\ ", r"\s*")
            # 단어 경계 (한글/영문 모두 대응)
            return rf"(?<!\w){k}(?!\w)"

        compiled = {}
        for name, info in doctype_cfg.items():
            if not info.get("enabled", True):
                continue

            kws = [
                re.compile(pattern(k), re.IGNORECASE)
                for k in info.get("keywords", [])
            ]
            neg = [
                re.compile(pattern(k), re.IGNORECASE)
                for k in info.get("neg_keywords", [])
            ]

            compiled[name] = {
                "keywords": kws,
                "neg_keywords": neg,
                "priority": info.get("priority", 999),
                "weight": float(info.get("weight", 1.0)),
            }

        return compiled

    # ---------- 매칭 유틸 ----------
    def _match_all(
        self, patterns: List[re.Pattern], text: str
    ) -> List[Tuple[int, int, str]]:
        """
        모든 패턴 매칭 수행

        Returns:
            [(start, end, pattern_str), ...]
        """
        hits = []
        for p in patterns:
            for m in p.finditer(text):
                hits.append((m.start(), m.end(), p.pattern))
        return hits

    def classify(self, text: str, filename: str = "") -> Dict[str, Any]:
        """
        문서 유형 분류

        Args:
            text: 문서 텍스트 (전체 또는 앞부분 샘플)
            filename: 파일명 (추가 힌트용, 파일명 신호 강화)

        Returns:
            {
                "doctype": "proposal"|"report"|"review"|"minutes"|"unknown",
                "confidence": 0.0~1.0,
                "reasons": [
                    {"source": "body"|"filename"|"deny", "span": [s, e], "pattern": "..."},
                    ...
                ]
            }
        """
        # 핫리로드 체크
        self._hot_reload_if_needed()

        if not self.enabled:
            return {"doctype": "proposal", "confidence": 1.0, "reasons": ["기본값"]}

        # 텍스트 정규화
        norm_body = self._normalize_text(text)
        norm_name = self._normalize_text(filename)

        if not norm_body and not norm_name:
            return {"doctype": "unknown", "confidence": 0.0, "reasons": []}

        # 스코어링 파라미터
        sc = self.config.get("score", {})
        body_w = float(sc.get("body_weight", 1.0))
        name_b = float(sc.get("filename_boost", 2.0))
        deny_pen = float(sc.get("deny_penalty", 2.0))

        scored = []
        for name, rule in self._compiled.items():
            kws = rule["keywords"]
            negs = rule["neg_keywords"]
            pri = rule["priority"]
            weight = rule["weight"]

            # 본문 히트
            body_hits = self._match_all(kws, norm_body)
            # 파일명 히트
            name_hits = self._match_all(kws, norm_name)
            # 음수 키워드 히트
            neg_hits = self._match_all(negs, norm_body + " " + norm_name)

            # 스코어 계산:
            # (본문 히트 수 × body_w + 파일명 히트 수 × name_b) × weight - 음수 × deny_pen
            score_raw = (
                (len(body_hits) * body_w) + (len(name_hits) * name_b)
            ) * weight - (len(neg_hits) * deny_pen)

            if score_raw <= 0:
                continue

            # 근거 리포트 생성
            reasons = []
            for s, e, patt in body_hits:
                reasons.append({"source": "body", "span": [s, e], "pattern": patt})
            for s, e, patt in name_hits:
                reasons.append({"source": "filename", "span": [s, e], "pattern": patt})
            for s, e, patt in neg_hits:
                reasons.append({"source": "deny", "span": [s, e], "pattern": patt})

            scored.append(
                {
                    "doctype": name,
                    "score": score_raw,
                    "priority": pri,
                    "filename_hits": len(name_hits),
                    "unique_kw": len(
                        {r["pattern"] for r in reasons if r["source"] != "deny"}
                    ),
                    "reasons": reasons,
                }
            )

        if not scored:
            return {"doctype": "unknown", "confidence": 0.0, "reasons": []}

        # 정렬: 점수↓ → priority↑ → 파일명 히트↓ → 고유 키워드 다양성↓
        scored.sort(
            key=lambda x: (
                -x["score"],
                x["priority"],
                -x["filename_hits"],
                -x["unique_kw"],
            )
        )
        top = scored[0]

        # confidence 정규화 (0~1): score / (score + 1)
        conf = float(top["score"] / (top["score"] + 1.0))

        return {
            "doctype": top["doctype"],
            "confidence": round(conf, 4),
            "reasons": top["reasons"],
        }

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
