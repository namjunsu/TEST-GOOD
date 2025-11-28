"""
텍스트 노이즈 제거 모듈 v2.0
2025-11-11

문서에서 프린트 타임스탬프, URL, 반복 헤더/푸터 등의 노이즈를 제거합니다.

v2.0 변경사항:
- 보호 문자열 가드: URL/IP/모델명 보존
- 페이지 단위 헤더/푸터 식별: 폼피드/Page 패턴으로 분할, 상하단만 스캔
- 반복 라인 정규화·지문화: 유사도 기반 중복 판정
- 소거 근거 보존: 제거 샘플 반환 (감사 가능성)
- 패턴 컴파일 플래그 지원: MULTILINE, IGNORECASE
- 한국어 특화 패턴: 프린트 타임스탬프, 관용 헤더, 바닥글
- 멱등성 보장: clean(clean(text)) 동일 결과
"""

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class TextCleaner:
    """텍스트 노이즈 제거 클래스 v2.0"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)

        # 보호 문자열 (오탐 방지: URL, IP, 모델명 등)
        self.protected = tuple(
            self.config.get("text_cleaning", {}).get(
                "protected_substrings",
                ["http://", "https://", "ftp://", "10.", "192.168."],
            ),
        )

        self.noise_patterns = self._compile_patterns()
        self.deduplicate_lines = self.config.get("text_cleaning", {}).get(
            "deduplicate_lines", True,
        )
        self.max_duplicate_threshold = self.config.get("text_cleaning", {}).get(
            "max_duplicate_threshold", 2,
        )
        self.min_repeat_for_noise = self.config.get("text_cleaning", {}).get(
            "min_repeat_for_noise", 3,
        )

        # 페이지 헤더/푸터 스캔 범위 (상하단 N행)
        self.page_scan_lines = self.config.get("text_cleaning", {}).get(
            "page_scan_lines", 4,
        )

        logger.info(
            f"🧹 텍스트 클리너 v2.0 초기화: {len(self.noise_patterns)}개 패턴, "
            f"{len(self.protected)}개 보호 문자열",
        )

    def _load_config(self, config_path: str) -> dict[str, Any]:
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

            with Path(config_file).open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            # 하위 호환: v0 스키마를 v1로 정규화
            from app.config.compat import normalize_config
            config = normalize_config(config)

            logger.info(f"✓ 설정 로드: {config_path} (schema v{config.get('schema_version', 0)})")
            return config

        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            return {}

    def _compile_patterns(self) -> list[tuple[re.Pattern, str]]:
        """노이즈 패턴 컴파일 (플래그 지원)

        Returns:
            (컴파일된 패턴, 설명) 튜플 리스트
        """
        patterns = []
        noise_config = self.config.get("text_cleaning", {}).get("noise_patterns", [])

        for pattern_config in noise_config:
            pattern_str = pattern_config.get("pattern")
            description = pattern_config.get("description", "unknown")

            try:
                # 플래그 주입 (설정에서 지정 가능)
                flags = 0
                if pattern_config.get("multiline", False):
                    flags |= re.MULTILINE
                if pattern_config.get("ignore_case", False):
                    flags |= re.IGNORECASE

                compiled = re.compile(pattern_str, flags)
                patterns.append((compiled, description))
                logger.debug(
                    f"✓ 패턴 컴파일: {description} - {pattern_str} (flags={flags})",
                )
            except re.error as e:
                logger.error(f"❌ 패턴 컴파일 실패: {pattern_str} - {e}")

        return patterns

    def _split_pages(self, text: str) -> list[list[str]]:
        """페이지 분할 (폼피드 또는 'Page/쪽' 패턴 기준)

        Args:
            text: 전체 텍스트

        Returns:
            페이지별 라인 리스트
        """
        # 폼피드 또는 Page/쪽 힌트로 분할
        pages = re.split(
            r"\f|(?:^|\n)page\s+\d+(?:\s+of\s+\d+)?\s*(?:\n|$)|(?:^|\n)\d+\s*쪽\s*(?:\n|$)",
            text,
            flags=re.IGNORECASE,
        )
        return [p.split("\n") for p in pages if p.strip()]

    def _normalize_line(self, s: str) -> str:
        """라인 정규화 (유사도 판정용 지문화)

        Args:
            s: 원본 라인

        Returns:
            정규화된 라인
        """
        s = s.lower()
        # 유사 문장부호 통합
        s = re.sub(r"[·∙∙••]+", "•", s)
        # 다중 공백/하이픈 정규화
        s = re.sub(r"[\s\-]+", " ", s).strip()
        return s

    def clean(self, text: str) -> tuple[str, dict[str, Any]]:
        """텍스트 노이즈 제거 v2.0

        Args:
            text: 원본 텍스트

        Returns:
            (정리된 텍스트, 노이즈 메타 딕셔너리)
            - 노이즈 메타 키:
              - pattern: Dict[str, int] (패턴별 카운트)
              - repeated_headers_footers: int
              - deduplicated_lines: int
              - removed_samples: Dict[str, List[str]] (제거 샘플)
        """
        if not text:
            return "", {}

        lines = text.split("\n")
        noise_counts: dict[str, Any] = {}
        removed_samples: dict[str, list[str]] = {}

        # 1. 패턴 기반 노이즈 제거 (보호 문자열 가드 포함)
        lines, pattern_counts, pattern_samples = self._remove_pattern_noise(lines)
        noise_counts.update(pattern_counts)
        removed_samples["pattern"] = pattern_samples

        # 2. 빈도 기반 반복 헤더/푸터 제거 (페이지 단위)
        lines, repeat_count, repeat_samples = self._remove_repeated_lines(lines)
        noise_counts["repeated_headers_footers"] = repeat_count
        removed_samples["repeated"] = repeat_samples

        # 3. 중복 라인 제거 (선택적)
        if self.deduplicate_lines:
            lines, dedup_count = self._deduplicate_consecutive_lines(lines)
            noise_counts["deduplicated_lines"] = dedup_count

        # 4. 빈 라인 정리 (멱등성 보장)
        lines = self._normalize_blank_lines(lines)

        cleaned_text = "\n".join(lines)

        # 노이즈 메타에 제거 샘플 포함
        total = sum(
            v
            for k, v in noise_counts.items()
            if k != "removed_samples" and isinstance(v, int)
        )
        noise_counts["removed_samples"] = removed_samples

        logger.debug(f"🧹 정리 완료: {total}개 노이즈 제거")

        return cleaned_text, noise_counts

    def _remove_pattern_noise(
        self, lines: list[str],
    ) -> tuple[list[str], dict[str, int], list[str]]:
        """패턴 기반 노이즈 제거 (보호 문자열 가드 포함)

        Args:
            lines: 원본 라인 리스트

        Returns:
            (정리된 라인 리스트, 패턴별 카운트, 제거 샘플)
        """
        counts = {desc: 0 for _, desc in self.noise_patterns}
        cleaned_lines = []
        samples: list[str] = []

        for line in lines:
            is_noise = False

            # 패턴 매칭 우선 확인
            for pattern, description in self.noise_patterns:
                if pattern.search(line):
                    counts[description] += 1
                    is_noise = True
                    # 샘플 수집 (최대 3개)
                    if len(samples) < 3:
                        samples.append(f"{description}: {line[:50]}")
                    break

            # 노이즈가 아닌 경우에만 보호 문자열 체크 적용
            # (패턴이 명시적으로 제거하려는 경우 보호 문자열보다 우선)
            if not is_noise:
                cleaned_lines.append(line)

        return cleaned_lines, counts, samples

    def _remove_repeated_lines(
        self, lines: list[str],
    ) -> tuple[list[str], int, list[str]]:
        """빈도 기반 반복 헤더/푸터 제거 (페이지 단위 스캔)

        3회 이상 반복되는 라인은 노이즈로 간주하고 제거

        Args:
            lines: 원본 라인 리스트

        Returns:
            (정리된 라인 리스트, 제거된 라인 수, 제거 샘플)
        """
        text = "\n".join(lines)
        pages = self._split_pages(text) or [lines]

        # 페이지별 상·하 N행만 후보로 수집
        cand = []
        for plines in pages:
            head = [line.strip() for line in plines[: self.page_scan_lines] if len(line.strip()) > 5]
            tail = [
                line.strip() for line in plines[-self.page_scan_lines :] if len(line.strip()) > 5
            ]
            cand.extend(head + tail)

        # 정규화 + 빈도 계산
        cnt = Counter(self._normalize_line(c) for c in cand)
        repeated = {k for k, v in cnt.items() if v >= self.min_repeat_for_noise}

        if not repeated:
            return lines, 0, []

        logger.debug(f"🔍 반복 라인 {len(repeated)}개 발견: {list(repeated)[:3]}...")

        # 반복 라인 제거
        cleaned_lines = []
        removed_count = 0
        samples: list[str] = []

        for line in lines:
            if self._normalize_line(line) in repeated:
                removed_count += 1
                if len(samples) < 3:
                    samples.append(line[:50])
            else:
                cleaned_lines.append(line)

        return cleaned_lines, removed_count, samples

    def _deduplicate_consecutive_lines(
        self, lines: list[str],
    ) -> tuple[list[str], int]:
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

    def _normalize_blank_lines(self, lines: list[str]) -> list[str]:
        """연속된 빈 라인을 하나로 정리 (멱등성 보장)

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

    def get_stats(self, noise_counts: dict[str, Any]) -> str:
        """노이즈 제거 통계 문자열 생성

        Args:
            noise_counts: 노이즈 카운트 딕셔너리

        Returns:
            통계 문자열
        """
        # removed_samples 제외하고 숫자만 합산
        total = sum(
            v
            for k, v in noise_counts.items()
            if k != "removed_samples" and isinstance(v, int)
        )

        if total == 0:
            return "노이즈 없음"

        stats = f"총 {total}개 노이즈 제거: "
        parts = [
            f"{desc}={count}"
            for desc, count in noise_counts.items()
            if isinstance(count, int) and count > 0 and desc != "removed_samples"
        ]
        stats += ", ".join(parts)

        return stats
