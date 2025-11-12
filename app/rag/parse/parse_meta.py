"""
메타데이터 파싱 모듈 v1.5
2025-11-11

문서 날짜와 카테고리를 표준화합니다.

v1.5 변경사항:
- 설정 핫리로드 (mtime 기반)
- 날짜 정규화 커버리지 확대 (YYYY/MM/DD, YYYY년 M월 D일, YYYYMMDD 등)
- 파일명에서 날짜 폴백
- 작성자 검증 유연화 (영문/혼성 이름 지원, 부서명/직함 오검출 차단)
- 카테고리 분류 근거(reasons) 반환
- 로그 가시성 개선 (INFO 요약 + DEBUG 상세)
- 타입 계약 강화

규칙:
- 날짜: 기안일자 우선, 시행일자 폴백, 둘 다 표시, 파일명 힌트 지원
- 카테고리: 규칙 기반 분류, "정보 없음" 대신 "미분류" 사용
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetaParser:
    """메타데이터 파서"""

    def __init__(
        self,
        config_path: str = "config/document_processing.yaml",
        reload_secs: int = 10,
    ):
        """초기화

        Args:
            config_path: 설정 파일 경로
            reload_secs: 설정 재로드 체크 주기 (초)
        """
        self._config_path = Path(config_path)
        self._reload_secs = reload_secs
        self._last_load_ts = 0.0
        self._config_mtime = 0.0

        # 초기 설정 로드
        self.config = self._load_config(self._config_path)
        self._update_config_attrs()

        logger.info(
            f"📋 메타 파서 초기화: date_priority={len(self.date_priority)}, "
            f"author_fields={len(self.author_fields)}, stoplist={len(self.author_stoplist)}, "
            f"category_rules={len(self.category_rules)}"
        )

    def _update_config_attrs(self):
        """설정에서 속성 업데이트"""
        # metadata 섹션에서 설정 로드
        metadata_config = self.config.get("metadata", {}) or {}

        # 날짜 우선순위 (config에서 로드, 없으면 기본값)
        self.date_priority = metadata_config.get(
            "date_priority",
            ["시행일자", "기안일자", "작성일자", "보고일자", "회의일자"],
        )

        # 작성자 필드 우선순위
        self.author_fields = metadata_config.get(
            "author_fields", ["기안자", "작성자", "보고자", "검토자"]
        )

        # 부서 필드 우선순위
        self.department_fields = metadata_config.get(
            "department_fields", ["기안부서", "소속", "부서"]
        )

        # 작성자 Stoplist (기안자 오검출 방지)
        self.author_stoplist = metadata_config.get("author_stoplist", [])

        # 카테고리 규칙 (이전 호환성 유지)
        meta_parsing = self.config.get("meta_parsing", {}) or {}
        self.category_rules = meta_parsing.get("category_rules", {})
        self.default_category = meta_parsing.get("default_category", "미분류")

    def _hot_reload_if_needed(self):
        """필요시 설정 핫리로드 (mtime 기반)"""
        now = time.time()
        if now - self._last_load_ts < self._reload_secs:
            return

        if self._config_path.exists():
            try:
                mtime = self._config_path.stat().st_mtime
                if mtime > self._config_mtime:
                    self.config = self._load_config(self._config_path)
                    self._update_config_attrs()
                    logger.info("🔄 MetaParser 설정 핫리로드 완료")
            except Exception as e:
                logger.warning(f"⚠️ 핫리로드 실패: {e}")
        self._last_load_ts = now

    def _validate_author(self, author: str) -> bool:
        """작성자 이름 검증 (한글 2~4음절 + 영문/혼성 + Stoplist + 부서/직함 차단)

        Args:
            author: 작성자 후보 문자열

        Returns:
            검증 통과 여부
        """
        if not author or not isinstance(author, str):
            return False

        a = author.strip()

        # Stoplist 체크
        if a in self.author_stoplist:
            logger.debug(f"작성자 Stoplist 제외: {a}")
            return False

        # 부서/직함 키워드 제외 (오검출 차단)
        deny_tokens = ("팀", "부", "실", "국", "대표", "이사", "차장", "과장", "담당")
        if any(tok in a for tok in deny_tokens):
            logger.debug(f"작성자 부서/직함 키워드 제외: {a}")
            return False

        import re

        # 한글 2~4음절
        if re.fullmatch(r"[가-힣]{2,4}", a):
            return True

        # 영문/이니셜 허용: J. Kim, Lee JH, LEE, JH 등
        if re.fullmatch(r"[A-Za-z][A-Za-z.\- ,]{1,30}", a):
            return True

        logger.debug(f"작성자 패턴 불일치: {a}")
        return False

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """설정 파일 로드

        Args:
            config_path: 설정 파일 경로

        Returns:
            설정 딕셔너리
        """
        try:
            if not config_path.exists():
                logger.warning(f"⚠️ 설정 파일 없음: {config_path}, 기본값 사용")
                self._config_mtime = 0.0
                self._last_load_ts = time.time()
                return {}

            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            self._config_mtime = config_path.stat().st_mtime
            self._last_load_ts = time.time()
            logger.info(f"✓ 설정 로드: {config_path}")
            return cfg

        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            self._last_load_ts = time.time()
            return {}

    def parse_dates(self, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """날짜 파싱 및 표준화

        Args:
            metadata: 문서 메타데이터 (기안일자, 시행일자, 작성일자 등 포함)

        Returns:
            (display_date, date_detail)
            - display_date: 우선순위에 따른 대표 날짜 (YYYY-MM-DD)
            - date_detail: "기안일자 / 시행일자" 형식
        """
        self._hot_reload_if_needed()

        # 우선순위에 따라 대표 날짜 선택
        display_date = None
        for date_key in self.date_priority:
            if date_key in metadata and metadata[date_key]:
                raw_date = metadata[date_key]
                # 날짜 정규화 (범위, 시간 제거, 형식 표준화)
                display_date = self._normalize_date(raw_date)
                break

        # 기안일자와 시행일자를 모두 표시
        draft_date = metadata.get("기안일자") or metadata.get("date")
        action_date = metadata.get("시행일자")

        # 각 날짜도 정규화
        if draft_date:
            draft_date = self._normalize_date(draft_date)
        if action_date:
            action_date = self._normalize_date(action_date)

        # 파일명 힌트 (없을 때만)
        if not (display_date and display_date != "정보 없음"):
            fname = metadata.get("filename") or ""
            import re

            # 파일명에서 날짜 패턴 추출: YYYY-MM-DD or YYYY_MM_DD or YYYY.MM.DD
            m = re.search(r"\b(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?([0-3]\d)\b", fname)
            if m:
                display_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                logger.debug(f"파일명에서 날짜 추출: {display_date} from {fname}")

        if draft_date and action_date:
            date_detail = f"{draft_date} / {action_date}"
        elif draft_date:
            date_detail = draft_date
        elif action_date:
            date_detail = action_date
        else:
            date_detail = display_date or "정보 없음"

        display_date = display_date or "정보 없음"

        return display_date, date_detail

    def _normalize_date(self, date_str: str) -> str:
        """날짜 문자열 정규화 (YYYY-MM-DD 형식)

        확장 지원 포맷:
        - YYYY/MM/DD, YYYY.MM.DD
        - YYYY년 M월 D일
        - YY-MM-DD, YY. M. D.
        - YYYYMMDD
        - 범위 (~, -, 혼용) → 앞 날짜 채택
        - 괄호/주석 제거

        Args:
            date_str: 원본 날짜 문자열

        Returns:
            정규화된 날짜 (YYYY-MM-DD) 또는 원본
        """
        if not date_str or not isinstance(date_str, str):
            return date_str

        import re
        from datetime import datetime

        s = date_str.strip()

        # 주석/괄호 제거
        s = re.sub(r"[(){}\[\]]", " ", s)

        # 범위 → 앞 날짜 채택 (구분자 혼용: ~, -)
        range_match = re.search(
            r"(\d{2,4}[./-]?\d{1,2}[./-]?\d{1,2})\s*[~\-]\s*\d{2,4}[./-]?\d{1,2}[./-]?\d{1,2}",
            s,
        )
        if range_match:
            s = range_match.group(1)

        # 시간 제거
        s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?", "", s)

        # YYYY년 M월 D일 → YYYY-MM-DD
        m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
        if m:
            y, mm, dd = m.groups()
            return f"{y}-{mm.zfill(2)}-{dd.zfill(2)}"

        # 24. 10. 24 → 2024-10-24 (20YY 가정)
        m = re.search(r"\b(\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\b", s)
        if m:
            yy, mm, dd = m.groups()
            yyyy = f"20{yy}"
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"

        # 2024/10/24 or 2024.10.24 → 2024-10-24
        s = re.sub(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", r"\1-\2-\3", s)

        # 20241024 → 2024-10-24
        m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", s)
        if m:
            y, mm, dd = m.groups()
            return f"{y}-{mm}-{dd}"

        # YY-MM-DD → 20YY-MM-DD
        m = re.search(r"\b(\d{2})-(\d{1,2})-(\d{1,2})\b", s)
        if m:
            yy, mm, dd = m.groups()
            return f"20{yy}-{mm.zfill(2)}-{dd.zfill(2)}"

        # YYYY-M-D → 패딩
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
        if m:
            y, mm, dd = m.groups()
            return f"{y}-{mm.zfill(2)}-{dd.zfill(2)}"

        # 최종 검증
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            logger.debug(f"날짜 정규화 실패 (원본 반환): {date_str}")
            return date_str

    def classify_category(
        self, title: str = "", content: str = "", filename: str = ""
    ) -> Tuple[str, str]:
        """카테고리 분류 (근거 포함)

        Args:
            title: 문서 제목
            content: 문서 내용
            filename: 파일명

        Returns:
            (category, source)
            - category: 분류된 카테고리
            - source: 분류 방법 ("rule", "ml", "default")
        """
        search_text_title = (title or "").lower()
        search_text_file = (filename or "").lower()
        search_text_body = (content or "")[:500].lower()

        matched: List[Tuple[str, str, str]] = []  # (category, source, keyword)

        def match_rules(rules: List[Dict[str, Any]], source_name: str):
            """규칙 매칭 헬퍼"""
            for rule in rules:
                for kw in rule.get("keywords", []):
                    kw_lower = kw.lower()
                    search_text = (
                        search_text_title
                        if source_name == "title"
                        else search_text_file
                        if source_name == "filename"
                        else search_text_body
                    )
                    if kw_lower in search_text:
                        matched.append((rule.get("category", ""), source_name, kw))

        # 1. 문서 유형 규칙
        doc_type_rules = self.category_rules.get("document_type", [])
        match_rules(doc_type_rules, "title")
        match_rules(doc_type_rules, "filename")
        match_rules(doc_type_rules, "content")

        # 2. 장비 분류 규칙
        equipment_rules = self.category_rules.get("equipment_type", [])
        match_rules(equipment_rules, "title")
        match_rules(equipment_rules, "filename")
        match_rules(equipment_rules, "content")

        # 3. 카테고리 조합 및 근거 로깅
        if matched:
            cats_order = []
            reasons = []
            for cat, src, kw in matched:
                if cat and cat not in cats_order:
                    cats_order.append(cat)
                reasons.append({"category": cat, "source": src, "keyword": kw})

            combined = " / ".join(cats_order)
            # 디버그 로그 (근거 포함)
            logger.debug(f"✓ 카테고리 매칭: {combined} | reasons={reasons}")
            return combined, "rule"

        # 4. 기본 카테고리
        return self.default_category, "default"

    def parse(
        self, metadata: Dict[str, Any], title: str = "", content: str = ""
    ) -> Dict[str, Any]:
        """메타데이터 파싱 및 표준화 (v1.5)

        Args:
            metadata: 원본 메타데이터
            title: 문서 제목
            content: 문서 내용

        Returns:
            표준화된 메타데이터 (키 존재 보장)
        """
        self._hot_reload_if_needed()

        # 날짜 파싱
        display_date, date_detail = self.parse_dates(metadata)

        # 작성자 추출 (우선순위 순서대로)
        author = None
        for field in self.author_fields:
            if field in metadata and metadata[field]:
                candidate = metadata[field]
                # 작성자 검증 (한글 2~4음절 + 영문 + Stoplist + 부서/직함 차단)
                if self._validate_author(candidate):
                    author = candidate
                    break
        author = author or metadata.get("drafter") or "정보 없음"

        # 부서 추출 (우선순위 순서대로)
        department = None
        for field in self.department_fields:
            if field in metadata and metadata[field]:
                department = metadata[field]
                break
        department = department or metadata.get("department") or "정보 없음"

        # 카테고리 분류
        filename = metadata.get("filename", "")
        category, category_source = self.classify_category(title, content, filename)

        # 표준화된 메타데이터 구성 (키 존재 보장)
        out = {
            "drafter": author,
            "department": department,
            "doc_number": metadata.get("doc_number")
            or metadata.get("문서번호")
            or "정보 없음",
            "retention": metadata.get("retention")
            or metadata.get("보존기간")
            or "정보 없음",
            "display_date": display_date,
            "date_detail": date_detail,
            "category": category if category != "정보 없음" else self.default_category,
            "category_source": category_source,
            "filename": filename,
        }

        # 로그 가시성: INFO 요약 + DEBUG 상세
        logger.info(
            "메타 파싱 요약 | drafter=%s dept=%s date=%s category=%s(source=%s) file=%s",
            out["drafter"],
            out["department"],
            out["date_detail"],
            out["category"],
            out["category_source"],
            out["filename"],
        )
        logger.debug("메타 파싱 상세 | raw=%s | std=%s", metadata, out)

        return out

    def format_meta_display(self, parsed_meta: Dict[str, Any]) -> str:
        """메타데이터 표시 형식 생성

        Args:
            parsed_meta: 파싱된 메타데이터

        Returns:
            Markdown 형식의 메타데이터 문자열
        """
        lines = []
        lines.append(
            f"**기안자/부서:** {parsed_meta['drafter']} / {parsed_meta['department']}"
        )
        lines.append(f"**기안일자 / 시행일자:** {parsed_meta['date_detail']}")
        lines.append(f"**유형/카테고리:** {parsed_meta['category']}")

        # 선택적 필드
        if parsed_meta.get("doc_number") and parsed_meta["doc_number"] != "정보 없음":
            lines.append(f"**문서번호:** {parsed_meta['doc_number']}")

        if parsed_meta.get("retention") and parsed_meta["retention"] != "정보 없음":
            lines.append(f"**보존기간:** {parsed_meta['retention']}")

        return "\n".join(lines)
