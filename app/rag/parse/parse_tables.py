"""
표(비용) 파싱 모듈
2025-10-26

문서에서 비용 표를 파싱하고 합계를 검증합니다.

기능:
- 헤더 자동 인식 (모델명, 수리내역, 수량, 단가, 합계 등)
- 숫자 정규화 (쉼표, 원화 기호, 공백 제거)
- 합계 교차 검증 (±1원 오차 허용)
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class TableParser:
    """표 파서"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.header_patterns = self.config.get("table_parsing", {}).get(
            "header_patterns", []
        )
        self.remove_chars = (
            self.config.get("table_parsing", {})
            .get("number_normalization", {})
            .get("remove_chars", [])
        )
        self.sum_tolerance = (
            self.config.get("table_parsing", {})
            .get("sum_validation", {})
            .get("tolerance", 1)
        )

        logger.info(f"📊 표 파서 초기화: {len(self.header_patterns)}개 헤더 패턴")

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

    def normalize_number(self, text: str) -> Optional[int]:
        """숫자 정규화

        Args:
            text: 숫자가 포함된 문자열 (예: "1,234,567원")

        Returns:
            정규화된 정수 (실패시 None)
        """
        if not text:
            return None

        # 제거할 문자 제거
        normalized = text
        for char in self.remove_chars:
            normalized = normalized.replace(char, "")

        # 탭, 개행 등 제거
        normalized = normalized.strip().replace("\t", "").replace("\n", "")

        try:
            return int(normalized)
        except ValueError:
            logger.debug(f"⚠️ 숫자 변환 실패: '{text}' → '{normalized}'")
            return None

    def detect_table_headers(self, text: str) -> List[str]:
        """표 헤더 감지

        Args:
            text: 문서 텍스트

        Returns:
            발견된 헤더 리스트
        """
        found_headers = []

        for header_pattern in self.header_patterns:
            # 대소문자 무시, 공백 허용 패턴
            pattern = re.compile(header_pattern, re.IGNORECASE)
            if pattern.search(text):
                found_headers.append(header_pattern)

        logger.debug(f"✓ 발견된 헤더: {found_headers}")
        return found_headers

    def extract_cost_table(self, text: str) -> Tuple[List[Dict[str, Any]], bool, str]:
        """비용 표 추출

        Args:
            text: 문서 텍스트

        Returns:
            (items, parse_success, status_message)
            - items: 항목 리스트 [{"name": ..., "quantity": ..., "unit_price": ..., "amount": ...}, ...]
            - parse_success: 파싱 성공 여부
            - status_message: 상태 메시지
        """
        items = []

        # 간단한 금액 패턴 추출 (더 정교한 로직 필요)
        # 예: "모델명    수량    단가    금액"
        #     "ABC-123   2      100,000  200,000원"

        amount_pattern = r"(\d{1,3}(?:,\d{3})*)\s*원?"
        amounts = re.findall(amount_pattern, text)

        if not amounts:
            return items, False, "금액 정보를 찾을 수 없습니다"

        # 금액을 정규화하여 항목 생성 (간단한 버전)
        for i, amount_str in enumerate(amounts):
            amount = self.normalize_number(amount_str)
            if amount is not None:
                items.append(
                    {
                        "name": f"항목 {i+1}",
                        "quantity": None,
                        "unit_price": None,
                        "amount": amount,
                    }
                )

        if items:
            return items, True, f"{len(items)}개 항목 추출"
        else:
            return items, False, "항목 추출 실패"

    def validate_sum(
        self, items: List[Dict[str, Any]], claimed_total: Optional[int] = None
    ) -> Tuple[bool, int, Optional[int]]:
        """합계 검증

        Args:
            items: 항목 리스트
            claimed_total: 문서에 명시된 합계 (선택)

        Returns:
            (match, calculated_total, claimed_total)
            - match: 합계 일치 여부
            - calculated_total: 계산된 합계
            - claimed_total: 문서 합계
        """
        # 계산된 합계
        calculated_total = sum(item.get("amount", 0) for item in items)

        # 문서 합계가 없으면 검증 불가
        if claimed_total is None:
            return True, calculated_total, None

        # ±tolerance 범위 내에서 일치 확인
        difference = abs(calculated_total - claimed_total)
        match = difference <= self.sum_tolerance

        if not match:
            logger.warning(
                f"⚠️ 합계 불일치: 계산={calculated_total:,}원, 문서={claimed_total:,}원, 차이={difference:,}원"
            )
        else:
            logger.debug(f"✓ 합계 일치: {calculated_total:,}원")

        return match, calculated_total, claimed_total

    def parse(self, text: str) -> Dict[str, Any]:
        """표 파싱 (전체 프로세스)

        Args:
            text: 문서 텍스트

        Returns:
            파싱 결과 딕셔너리
        """
        result = {
            "items": [],
            "total": 0,
            "claimed_total": None,
            "sum_match": None,
            "parse_status": "failed",
            "error_message": None,
        }

        try:
            # 1. 헤더 감지
            headers = self.detect_table_headers(text)

            if not headers:
                result["error_message"] = "표 헤더를 찾을 수 없습니다"
                result["parse_status"] = "failed"
                return result

            # 2. 비용 표 추출
            items, parse_success, status_msg = self.extract_cost_table(text)

            if not parse_success:
                result["error_message"] = status_msg
                result["parse_status"] = "partial"
                return result

            result["items"] = items

            # 3. 문서에서 합계 추출 (옵션)
            claimed_total = self._extract_claimed_total(text)
            result["claimed_total"] = claimed_total

            # 4. 합계 검증
            match, calculated_total, _ = self.validate_sum(items, claimed_total)
            result["total"] = calculated_total
            result["sum_match"] = match

            if match:
                result["parse_status"] = "success"
            else:
                result["parse_status"] = "partial"
                result["error_message"] = (
                    f"합계 불일치 (계산: {calculated_total:,}원, 문서: {claimed_total:,}원)"
                )

            logger.debug(
                f"📊 표 파싱 완료: {len(items)}개 항목, 합계={calculated_total:,}원"
            )

        except Exception as e:
            logger.error(f"❌ 표 파싱 실패: {e}")
            result["error_message"] = str(e)
            result["parse_status"] = "failed"

        return result

    def _extract_claimed_total(self, text: str) -> Optional[int]:
        """문서에서 합계 추출

        Args:
            text: 문서 텍스트

        Returns:
            추출된 합계 (없으면 None)
        """
        # 합계 패턴: "합계: 1,234,567원" 또는 "총액: 1,234,567원"
        total_patterns = [
            r"합계[:\s]+(\d{1,3}(?:,\d{3})*)\s*원?",
            r"총액[:\s]+(\d{1,3}(?:,\d{3})*)\s*원?",
            r"소계[:\s]+(\d{1,3}(?:,\d{3})*)\s*원?",
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                total_str = match.group(1)
                total = self.normalize_number(total_str)
                if total is not None:
                    logger.debug(f"✓ 문서 합계 발견: {total:,}원")
                    return total

        return None

    def format_cost_display(self, parsed_table: Dict[str, Any]) -> str:
        """비용 표 표시 형식 생성

        Args:
            parsed_table: 파싱된 표 데이터

        Returns:
            Markdown 형식의 비용 표 문자열
        """
        lines = []
        lines.append("**💰 비용 (VAT 별도)**")

        items = parsed_table.get("items", [])
        if not items:
            lines.append("- 비용 정보를 찾을 수 없습니다")
            return "\n".join(lines)

        # 항목별 비용
        for item in items:
            name = item.get("name", "항목")
            amount = item.get("amount", 0)
            lines.append(f"- {name}: ₩{amount:,}")

        # 합계
        total = parsed_table.get("total", 0)
        sum_match = parsed_table.get("sum_match")

        if sum_match is False:
            claimed_total = parsed_table.get("claimed_total", 0)
            lines.append(
                f"\n**합계:** ₩{total:,} ⚠️ (문서 합계: ₩{claimed_total:,}, 차이 있음)"
            )
        else:
            lines.append(f"\n**합계:** ₩{total:,}")

        return "\n".join(lines)
