"""
쿼리 모드 라우터
2025-10-26

질의 의도를 분석하여 Q&A 모드 vs 문서 미리보기 모드를 결정합니다.

규칙:
- Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모드 우선
- 파일명만 있고 Q&A 의도가 없으면 미리보기 모드
"""

import re
from enum import Enum
from pathlib import Path
import yaml
from typing import Dict, Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryMode(Enum):
    """쿼리 모드"""

    QA = "qa"  # 질답 모드 (RAG 파이프라인)
    PREVIEW = "preview"  # 문서 미리보기 모드 (파일 전문)


class QueryRouter:
    """쿼리 모드 라우터"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.qa_keywords = self.config.get("mode_routing", {}).get(
            "qa_intent_keywords", []
        )
        self.preview_keywords = self.config.get("mode_routing", {}).get(
            "preview_only_keywords", []
        )
        self.filename_pattern = self.config.get("mode_routing", {}).get(
            "filename_pattern", r"\S+\.pdf"
        )

        logger.info(
            f"📋 모드 라우터 초기화: QA 키워드 {len(self.qa_keywords)}개, 미리보기 키워드 {len(self.preview_keywords)}개"
        )

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드

        Args:
            config_path: 설정 파일 경로

        Returns:
            설정 딕셔너리
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"⚠️ 설정 파일 없음: {config_path}, 기본값 사용")
                return {}

            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                logger.info(f"✓ 설정 로드: {config_path}")
                return config

        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            return {}

    def classify_mode(self, query: str) -> QueryMode:
        """쿼리 모드 분류

        Args:
            query: 사용자 질의

        Returns:
            QueryMode.QA 또는 QueryMode.PREVIEW
        """
        query_lower = query.lower()

        # 1. Q&A 의도 키워드 체크 (최우선)
        has_qa_intent = any(keyword in query_lower for keyword in self.qa_keywords)

        # 2. 파일명 패턴 체크
        has_filename = (
            re.search(self.filename_pattern, query, re.IGNORECASE) is not None
        )

        # 3. 미리보기 전용 키워드 체크
        has_preview_intent = any(
            keyword in query_lower for keyword in self.preview_keywords
        )

        # 결정 로직
        if has_qa_intent:
            # Q&A 의도가 있으면 파일명이 있어도 Q&A 모드
            logger.info("🎯 모드 결정: Q&A (의도 키워드 감지)")
            return QueryMode.QA

        elif has_filename and has_preview_intent:
            # 파일명 + 미리보기 전용 키워드 → 미리보기 모드
            logger.info("🎯 모드 결정: PREVIEW (파일명 + 미리보기 키워드)")
            return QueryMode.PREVIEW

        elif has_filename and not has_qa_intent:
            # 파일명만 있고 Q&A 의도 없음 → 미리보기 모드
            logger.info("🎯 모드 결정: PREVIEW (파일명만 존재)")
            return QueryMode.PREVIEW

        else:
            # 기본: Q&A 모드
            logger.info("🎯 모드 결정: Q&A (기본)")
            return QueryMode.QA

    def get_routing_reason(self, query: str) -> str:
        """모드 라우팅 이유 반환 (로깅용)

        Args:
            query: 사용자 질의

        Returns:
            라우팅 이유 문자열
        """
        query_lower = query.lower()

        has_qa_intent = any(keyword in query_lower for keyword in self.qa_keywords)
        has_filename = (
            re.search(self.filename_pattern, query, re.IGNORECASE) is not None
        )
        has_preview_intent = any(
            keyword in query_lower for keyword in self.preview_keywords
        )

        detected_qa_keywords = [kw for kw in self.qa_keywords if kw in query_lower]
        detected_preview_keywords = [
            kw for kw in self.preview_keywords if kw in query_lower
        ]

        reason_parts = []

        if has_filename:
            reason_parts.append("filename_detected")

        if has_qa_intent:
            reason_parts.append(f"qa_keywords({','.join(detected_qa_keywords)})")

        if has_preview_intent:
            reason_parts.append(
                f"preview_keywords({','.join(detected_preview_keywords)})"
            )

        if not reason_parts:
            reason_parts.append("default_qa")

        return "|".join(reason_parts)
