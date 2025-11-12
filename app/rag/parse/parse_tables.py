"""
표(비용) 파싱 모듈 v2.0
2025-11-11

문서에서 비용 표를 파싱하고 합계를 검증합니다.

v2.0 변경사항:
- 숫자 정규화 고도화: 만/억 표기 지원 (1.2만, 3억 5천만)
- 헤더 탐지 강화: 유사도 기반 라인 위치 탐지, 열 맵핑
- 행 단위 파싱: 이름/수량/단가/금액 구조화 추출
- VAT 교차 검증: amount + vat = total 검증
- 상대/절대 허용치 병행

기능:
- 헤더 자동 인식 (모델명, 수리내역, 수량, 단가, 합계 등)
- 숫자 정규화 (쉼표, 원화 기호, 만/억 표기, VAT)
- 합계 교차 검증 (±1원 절대 오차 + ±1% 상대 오차)
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

# 숫자 패턴 (만/억 지원)
_KR_NUM = re.compile(
    r"""
    (?P<num>[\d,]+(?:\.\d+)?)
    \s*
    (?P<unit>원|만원|억|억원|KRW|₩)?
""",
    re.VERBOSE,
)

_KR_HUMAN = re.compile(
    r"""
    (?:
      (?P<eok>\d+(?:\.\d+)?)\s*억
      (?:\s*(?P<man>\d+(?:\.\d+)?)\s*만)?|
      (?P<justman>\d+(?:\.\d+)?)\s*만
    )
""",
    re.VERBOSE,
)


def _to_won_from_human(m: re.Match) -> Optional[int]:
    """자연어 숫자 표현을 원(₩)으로 변환

    Args:
        m: 정규식 매치 객체 ("3.5억 1.2만" 등)

    Returns:
        정수 원 (실패시 None)
    """
    eok = m.group("eok")
    man = m.group("man")
    justman = m.group("justman")
    val = 0.0
    if eok:
        val += float(eok) * 100_000_000
        if man:
            val += float(man) * 10_000
    elif justman:
        val += float(justman) * 10_000
    return int(round(val)) if val > 0 else None


class TableParser:
    """표 파서 v2.0"""

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
        """숫자 정규화 (만/억 표기 지원)

        지원 포맷:
        - 일반: 1,234,567원, 1234567, ₩1,234,567
        - 만 단위: 1.2만, 123만원
        - 억 단위: 3.5억, 2억 1,500만
        - 혼합: 3억 5천만 (천만=0000만 자동 변환)

        Args:
            text: 숫자가 포함된 문자열

        Returns:
            정규화된 정수 (실패시 None)
        """
        if not text:
            return None

        s = (text or "").strip()

        # 1) "3억 5천만" 계열 간단 정규화
        s = s.replace("천만", "0000만").replace("백만", "000000")
        # 공백 정규화 (단, 숫자 사이 공백은 제거: "1 234 567" → "1234567")
        s = re.sub(r"(\d)\s+(\d)", r"\1\2", s)  # 숫자 사이 공백 제거
        s = re.sub(r"\s+", " ", s)  # 나머지 공백은 1개로

        # 2) 자연어 단위 우선 (3.5억 1.2만)
        m = _KR_HUMAN.search(s)
        if m:
            v = _to_won_from_human(m)
            if v:
                return v

        # 3) 숫자+단위 (1.2만원, 3억)
        m = _KR_NUM.search(s)
        if m:
            raw = m.group("num").replace(",", "")
            unit = (m.group("unit") or "").strip()
            try:
                base = float(raw)
                if unit in ("억", "억원"):
                    return int(round(base * 100_000_000))
                if unit in ("만원",):
                    return int(round(base * 10_000))
                # 원/KRW/₩ 혹은 단위 없음 → 원으로 처리
                return int(round(base))
            except ValueError:
                pass

        # 4) 최후: 모든 비숫자 제거 후 시도 (공백 구분자 포함)
        # "1 234 567" → "1234567"
        digits = re.sub(r"[^\d]", "", s)
        if digits and digits.isdigit():
            try:
                return int(digits)
            except ValueError:
                pass

        logger.debug(f"⚠️ 숫자 변환 실패: '{text}'")
        return None

    def _tokenize_row(self, line: str) -> List[str]:
        """행을 셀로 분할 (|, 탭, 2칸 이상 공백 구분자 지원)

        Args:
            line: 표 행 문자열

        Returns:
            셀 리스트
        """
        # |, 탭, 2칸 이상 공백 모두 구분자로 취급
        tmp = re.sub(r"[|]", " ", line)
        tmp = re.sub(r"\t", " ", tmp)
        tmp = re.sub(r"\s{2,}", "  ", tmp)  # 열 간격 유지
        return [c.strip() for c in tmp.split("  ") if c.strip()]

    def _colmap(self, cells: List[str]) -> Dict[str, int]:
        """헤더 셀을 표준 키로 맵핑

        Args:
            cells: 헤더 셀 리스트

        Returns:
            {"name": 0, "qty": 1, ...} 형태의 열 인덱스 맵
        """
        mapping = {}
        for i, c in enumerate(cells):
            if re.search(r"(품목|모델|품명)", c):
                mapping["name"] = i
            elif "수량" in c:
                mapping["qty"] = i
            elif "단가" in c:
                mapping["unit_price"] = i
            elif re.search(r"(금액|합계)", c):
                mapping["amount"] = i
        return mapping

    def _best_header_row(self, lines: List[str]) -> Tuple[int, List[str]]:
        """config 패턴과 가장 유사한 라인을 헤더로 탐지 (유사도 기반)

        Args:
            lines: 문서 라인 리스트

        Returns:
            (헤더 라인 인덱스, 헤더 셀 리스트)
        """
        candidates = []
        patterns = self.header_patterns or [
            r"(품목|모델|품명)",
            r"(수량)",
            r"(단가)",
            r"(금액|합계)",
            r"(비고|규격|사양)",
        ]

        for i, line in enumerate(lines[:300]):  # 앞쪽만 스캔
            cells = self._tokenize_row(line)
            if not (2 <= len(cells) <= 10):
                continue

            score = 0.0
            # 패턴 매칭 스코어
            for pat in patterns:
                if re.search(pat, line):
                    score += 1.0

            # 유사도 스코어 (오탈자 허용)
            for cell in cells:
                for key in ("수량", "단가", "금액", "합계", "품목", "모델", "품명"):
                    sim = SequenceMatcher(None, cell, key).ratio()
                    score = max(score, sim)

            if score >= 0.7:
                candidates.append((i, cells, score))

        if not candidates:
            return -1, []

        candidates.sort(key=lambda x: x[2], reverse=True)
        idx, cells, _ = candidates[0]
        logger.debug(f"✓ 헤더 라인 발견: idx={idx}, cells={cells}")
        return idx, cells

    def detect_table_headers(self, text: str) -> List[str]:
        """표 헤더 감지 (이전 호환성 유지)

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

    def _infer_amount(
        self,
        qty: Optional[int],
        unit_price: Optional[int],
        amount: Optional[int],
    ) -> Optional[int]:
        """금액 유도 (qty × unit_price = amount)

        Args:
            qty: 수량
            unit_price: 단가
            amount: 금액

        Returns:
            유도된 금액 (실패시 None)
        """
        if amount is None and qty is not None and unit_price is not None:
            return qty * unit_price
        return amount

    def _parse_rows(
        self, lines: List[str], start_idx: int, header_cells: List[str]
    ) -> List[Dict[str, Any]]:
        """헤더 아래 행들을 파싱하여 아이템 리스트 생성

        Args:
            lines: 문서 라인 리스트
            start_idx: 헤더 라인 인덱스
            header_cells: 헤더 셀 리스트

        Returns:
            항목 리스트
        """
        mapping = self._colmap(header_cells)
        out = []

        for line in lines[start_idx + 1 :]:
            if not line.strip():  # 빈줄까지를 표로 간주
                if out:
                    break
                else:
                    continue

            cells = self._tokenize_row(line)
            if len(cells) < 2:  # 행 종료 추정
                if out:
                    break
                else:
                    continue

            rec = {
                "name": None,
                "quantity": None,
                "unit_price": None,
                "amount": None,
            }

            # 이름
            if "name" in mapping and mapping["name"] < len(cells):
                rec["name"] = cells[mapping["name"]]
            else:
                rec["name"] = cells[0]

            # 수량
            if "qty" in mapping and mapping["qty"] < len(cells):
                rec["quantity"] = self.normalize_number(cells[mapping["qty"]])

            # 단가
            if "unit_price" in mapping and mapping["unit_price"] < len(cells):
                rec["unit_price"] = self.normalize_number(
                    cells[mapping["unit_price"]]
                )

            # 금액
            if "amount" in mapping and mapping["amount"] < len(cells):
                rec["amount"] = self.normalize_number(cells[mapping["amount"]])

            rec["amount"] = self._infer_amount(
                rec["quantity"], rec["unit_price"], rec["amount"]
            )

            # 행 유효성(이름 또는 금액 존재)
            if rec["name"] or rec["amount"]:
                out.append(rec)

            # 표 종료 휴리스틱: "합계/총액" 라인 도달 시 종료
            if re.search(r"(합계|총액)", line):
                break

        return out

    def extract_cost_table(
        self, text: str
    ) -> Tuple[List[Dict[str, Any]], bool, str]:
        """비용 표 추출 (v2.0 행 단위 파싱)

        Args:
            text: 문서 텍스트

        Returns:
            (items, parse_success, status_message)
            - items: 항목 리스트 [{"name": ..., "quantity": ..., "unit_price": ..., "amount": ...}, ...]
            - parse_success: 파싱 성공 여부
            - status_message: 상태 메시지
        """
        lines = text.splitlines()
        h_idx, h_cells = self._best_header_row(lines)

        if h_idx < 0:
            return [], False, "표 헤더를 찾을 수 없습니다"

        items = self._parse_rows(lines, h_idx, h_cells)

        if not items:
            return [], False, "항목 추출 실패"

        return items, True, f"{len(items)}개 항목 추출"

    def _extract_vat(self, text: str) -> Optional[int]:
        """문서에서 VAT(부가세) 추출

        Args:
            text: 문서 텍스트

        Returns:
            추출된 VAT (없으면 None)
        """
        patterns = [
            r"(?:부가세|VAT|세액)\s*[:\s]+([\d,\.]+)\s*(원|만원|억|억원|KRW|₩)?",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                vat_str = "".join([g for g in m.groups() if g])
                vat = self.normalize_number(vat_str)
                if vat is not None:
                    logger.debug(f"✓ VAT 발견: {vat:,}원")
                    return vat
        return None

    def validate_sum(
        self,
        items: List[Dict[str, Any]],
        claimed_total: Optional[int] = None,
        vat: Optional[int] = None,
        rel_tol: float = 0.01,
    ) -> Tuple[bool, int, Optional[int]]:
        """합계 검증 (절대/상대 허용치 + VAT 교차 검증)

        Args:
            items: 항목 리스트
            claimed_total: 문서에 명시된 합계 (선택)
            vat: 부가세 (선택)
            rel_tol: 상대 허용치 (기본 1%)

        Returns:
            (match, calculated_total, claimed_total)
            - match: 합계 일치 여부
            - calculated_total: 계산된 합계
            - claimed_total: 문서 합계
        """
        # 계산된 합계
        calc = sum(item.get("amount", 0) or 0 for item in items)

        # 문서 합계와 VAT가 모두 없으면 검증 불가
        if claimed_total is None and vat is None:
            return True, calc, None

        ok = True

        # 1) 절대 허용치 검증
        if claimed_total is not None:
            diff = abs(calc - claimed_total)
            abs_ok = diff <= self.sum_tolerance
            rel_ok = diff <= int(claimed_total * rel_tol)
            ok = ok and (abs_ok or rel_ok)

            if not ok:
                logger.warning(
                    f"⚠️ 합계 불일치: 계산={calc:,}원, 문서={claimed_total:,}원, 차이={diff:,}원"
                )

        # 2) VAT 교차 검증 (amount + vat = total)
        if claimed_total is not None and vat is not None:
            total_with_vat = calc + vat
            diff_with_vat = abs(total_with_vat - claimed_total)
            vat_ok = diff_with_vat <= max(
                self.sum_tolerance, int(claimed_total * rel_tol)
            )
            ok = ok and vat_ok

            if not vat_ok:
                logger.warning(
                    f"⚠️ VAT 포함 합계 불일치: 계산+VAT={total_with_vat:,}원, 문서={claimed_total:,}원"
                )

        if ok:
            logger.debug(f"✓ 합계 검증 통과: {calc:,}원")

        return ok, calc, claimed_total

    def parse(self, text: str) -> Dict[str, Any]:
        """표 파싱 v2.0 (전체 프로세스)

        Args:
            text: 문서 텍스트

        Returns:
            파싱 결과 딕셔너리 (키 보장):
            - items: List[Dict] (항목 리스트)
            - total: int (계산된 합계)
            - claimed_total: Optional[int] (문서 합계)
            - vat: Optional[int] (부가세)
            - sum_match: Optional[bool] (합계 일치 여부)
            - parse_status: str ("success", "partial", "failed")
            - error_message: Optional[str]
            - reasons: List[str] (파싱 과정 추적)
        """
        res = {
            "items": [],
            "total": 0,
            "claimed_total": None,
            "vat": None,
            "sum_match": None,
            "parse_status": "failed",
            "error_message": None,
            "reasons": [],
        }

        try:
            lines = text.splitlines()
            h_idx, h_cells = self._best_header_row(lines)

            if h_idx < 0:
                res["error_message"] = "표 헤더를 찾을 수 없습니다"
                res["reasons"].append("header_not_found")
                return res

            # 1. 항목 추출
            items = self._parse_rows(lines, h_idx, h_cells)
            if not items:
                res["parse_status"] = "partial"
                res["error_message"] = "항목 추출 실패"
                res["reasons"].append("items_empty")
                return res

            res["items"] = items
            res["reasons"].append(f"extracted_{len(items)}_items")

            # 2. 합계/VAT 추출
            res["claimed_total"] = self._extract_claimed_total(text)
            res["vat"] = self._extract_vat(text)

            # 3. 합계 검증
            match, calc_total, _ = self.validate_sum(
                items, res["claimed_total"], res["vat"]
            )
            res["total"] = calc_total
            res["sum_match"] = match
            res["parse_status"] = "success" if match else "partial"

            if not match and res["claimed_total"] is not None:
                res["error_message"] = (
                    f"합계 불일치 (계산: {calc_total:,}원, 문서: {res['claimed_total']:,}원)"
                )
                res["reasons"].append("sum_mismatch")

            logger.debug(
                "📊 표 파싱: %d개 항목, total=%s, claimed=%s, vat=%s, match=%s",
                len(items),
                f"{calc_total:,}",
                f"{res['claimed_total']:,}" if res["claimed_total"] else None,
                f"{res['vat']:,}" if res["vat"] else None,
                match,
            )

            return res

        except Exception as e:
            logger.error("❌ 표 파싱 실패: %s", e, exc_info=True)
            res["error_message"] = str(e)
            res["parse_status"] = "failed"
            res["reasons"].append(f"exception:{type(e).__name__}")
            return res

    def _extract_claimed_total(self, text: str) -> Optional[int]:
        """문서에서 합계 추출 (만/억 지원)

        Args:
            text: 문서 텍스트

        Returns:
            추출된 합계 (없으면 None)
        """
        # 합계 패턴 (만/억 지원)
        patterns = [
            r"(?:총\s?액|총계|합계)\s*[:\s]+([\d,\.]+)\s*(원|만원|억|억원|KRW|₩)?",
            r"(?:총\s?금액|결제금액)\s*[:\s]+([\d,\.]+)\s*(원|만원|억|억원|KRW|₩)?",
            r"소계\s*[:\s]+([\d,\.]+)\s*(원|만원|억|억원|KRW|₩)?",
        ]

        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                total_str = "".join([g for g in m.groups() if g])
                total = self.normalize_number(total_str)
                if total is not None:
                    logger.debug(f"✓ 문서 합계 발견: {total:,}원")
                    return total

        return None

    def format_cost_display(self, parsed_table: Dict[str, Any]) -> str:
        """비용 표 표시 형식 생성 (VAT 포함)

        Args:
            parsed_table: 파싱된 표 데이터

        Returns:
            Markdown 형식의 비용 표 문자열
        """
        lines = []
        lines.append("**💰 비용**")

        items = parsed_table.get("items", [])
        if not items:
            lines.append("- 비용 정보를 찾을 수 없습니다")
            return "\n".join(lines)

        # 항목별 비용
        for item in items:
            name = item.get("name", "항목")
            amount = item.get("amount", 0)
            qty = item.get("quantity")
            unit_price = item.get("unit_price")

            if qty and unit_price:
                lines.append(
                    f"- {name}: ₩{unit_price:,} × {qty} = ₩{amount:,}"
                )
            else:
                lines.append(f"- {name}: ₩{amount:,}")

        # 소계
        total = parsed_table.get("total", 0)
        lines.append(f"\n**소계:** ₩{total:,}")

        # VAT
        vat = parsed_table.get("vat")
        if vat:
            lines.append(f"**VAT (10%):** ₩{vat:,}")
            lines.append(f"**총액:** ₩{total + vat:,}")

        # 검증 경고
        sum_match = parsed_table.get("sum_match")
        if sum_match is False:
            claimed_total = parsed_table.get("claimed_total", 0)
            lines.append(
                f"\n⚠️ **검증:** 문서 합계 ₩{claimed_total:,}와 차이 있음"
            )

        return "\n".join(lines)
