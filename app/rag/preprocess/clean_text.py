"""
텍스트 노이즈 제거 모듈
2025-10-26

문서에서 프린트 타임스탬프, URL, 반복 헤더/푸터 등의 노이즈를 제거합니다.
"""

import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Tuple
import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class TextCleaner:
    """텍스트 노이즈 제거 클래스"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.noise_patterns = self._compile_patterns()
        self.deduplicate_lines = self.config.get("text_cleaning", {}).get(
            "deduplicate_lines", True
        )
        self.max_duplicate_threshold = self.config.get("text_cleaning", {}).get(
            "max_duplicate_threshold", 2
        )
        self.min_repeat_for_noise = self.config.get("text_cleaning", {}).get(
            "min_repeat_for_noise", 3
        )

        logger.info(
            f"🧹 텍스트 클리너 초기화: {len(self.noise_patterns)}개 노이즈 패턴 로드"
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

    def _compile_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """노이즈 패턴 컴파일

        Returns:
            (컴파일된 패턴, 설명) 튜플 리스트
        """
        patterns = []
        noise_config = self.config.get("text_cleaning", {}).get("noise_patterns", [])

        for pattern_config in noise_config:
            pattern_str = pattern_config.get("pattern")
            description = pattern_config.get("description", "unknown")

            try:
                compiled = re.compile(pattern_str)
                patterns.append((compiled, description))
                logger.debug(f"✓ 패턴 컴파일: {description} - {pattern_str}")
            except re.error as e:
                logger.error(f"❌ 패턴 컴파일 실패: {pattern_str} - {e}")

        return patterns

    def clean(self, text: str) -> Tuple[str, Dict[str, int]]:
        """텍스트 노이즈 제거

        Args:
            text: 원본 텍스트

        Returns:
            (정리된 텍스트, 노이즈 카운트 딕셔너리)
        """
        if not text:
            return "", {}

        lines = text.split("\n")
        noise_counts = {}

        # 1. 패턴 기반 노이즈 제거
        lines, pattern_counts = self._remove_pattern_noise(lines)
        noise_counts.update(pattern_counts)

        # 2. 빈도 기반 반복 헤더/푸터 제거
        lines, repeat_count = self._remove_repeated_lines(lines)
        noise_counts["repeated_headers_footers"] = repeat_count

        # 3. 중복 라인 제거 (선택적)
        if self.deduplicate_lines:
            lines, dedup_count = self._deduplicate_consecutive_lines(lines)
            noise_counts["deduplicated_lines"] = dedup_count

        # 4. 빈 라인 정리 (연속된 빈 라인을 하나로)
        lines = self._normalize_blank_lines(lines)

        cleaned_text = "\n".join(lines)

        logger.debug(f"🧹 정리 완료: {sum(noise_counts.values())}개 노이즈 제거")

        return cleaned_text, noise_counts

    def _remove_pattern_noise(
        self, lines: List[str]
    ) -> Tuple[List[str], Dict[str, int]]:
        """패턴 기반 노이즈 제거

        Args:
            lines: 원본 라인 리스트

        Returns:
            (정리된 라인 리스트, 패턴별 카운트)
        """
        counts = {desc: 0 for _, desc in self.noise_patterns}
        cleaned_lines = []

        for line in lines:
            is_noise = False

            for pattern, description in self.noise_patterns:
                if pattern.search(line):
                    counts[description] += 1
                    is_noise = True
                    break

            if not is_noise:
                cleaned_lines.append(line)

        return cleaned_lines, counts

    def _remove_repeated_lines(self, lines: List[str]) -> Tuple[List[str], int]:
        """빈도 기반 반복 헤더/푸터 제거

        3회 이상 반복되는 라인은 노이즈로 간주하고 제거

        Args:
            lines: 원본 라인 리스트

        Returns:
            (정리된 라인 리스트, 제거된 라인 수)
        """
        # 빈 라인과 너무 짧은 라인은 제외
        non_empty_lines = [line.strip() for line in lines if len(line.strip()) > 5]

        # 빈도 계산
        line_counts = Counter(non_empty_lines)

        # 반복 라인 식별 (min_repeat_for_noise회 이상)
        repeated_lines = {
            line
            for line, count in line_counts.items()
            if count >= self.min_repeat_for_noise
        }

        if not repeated_lines:
            return lines, 0

        logger.debug(
            f"🔍 반복 라인 {len(repeated_lines)}개 발견: {list(repeated_lines)[:3]}..."
        )

        # 반복 라인 제거
        cleaned_lines = []
        removed_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped in repeated_lines:
                removed_count += 1
            else:
                cleaned_lines.append(line)

        return cleaned_lines, removed_count

    def _deduplicate_consecutive_lines(self, lines: List[str]) -> Tuple[List[str], int]:
        """연속된 중복 라인 제거

        동일한 라인이 연속해서 나타나면 max_duplicate_threshold개까지만 유지

        Args:
            lines: 원본 라인 리스트

        Returns:
            (정리된 라인 리스트, 제거된 라인 수)
        """
        if not lines:
            return lines, 0

        cleaned_lines = []
        removed_count = 0
        current_line = None
        consecutive_count = 0

        for line in lines:
            if line == current_line:
                consecutive_count += 1
                if consecutive_count <= self.max_duplicate_threshold:
                    cleaned_lines.append(line)
                else:
                    removed_count += 1
            else:
                current_line = line
                consecutive_count = 1
                cleaned_lines.append(line)

        return cleaned_lines, removed_count

    def _normalize_blank_lines(self, lines: List[str]) -> List[str]:
        """연속된 빈 라인을 하나로 정리

        Args:
            lines: 원본 라인 리스트

        Returns:
            정리된 라인 리스트
        """
        cleaned_lines = []
        prev_blank = False

        for line in lines:
            is_blank = not line.strip()

            if is_blank:
                if not prev_blank:
                    cleaned_lines.append("")
                prev_blank = True
            else:
                cleaned_lines.append(line)
                prev_blank = False

        # 앞뒤 빈 라인 제거
        while cleaned_lines and not cleaned_lines[0].strip():
            cleaned_lines.pop(0)
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        return cleaned_lines

    def get_stats(self, noise_counts: Dict[str, int]) -> str:
        """노이즈 제거 통계 문자열 생성

        Args:
            noise_counts: 노이즈 카운트 딕셔너리

        Returns:
            통계 문자열
        """
        total = sum(noise_counts.values())
        if total == 0:
            return "노이즈 없음"

        stats = f"총 {total}개 노이즈 제거: "
        parts = [f"{desc}={count}" for desc, count in noise_counts.items() if count > 0]
        stats += ", ".join(parts)

        return stats
