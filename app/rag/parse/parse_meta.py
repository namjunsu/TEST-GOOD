"""
메타데이터 파싱 모듈
2025-10-26

문서 날짜와 카테고리를 표준화합니다.

규칙:
- 날짜: 기안일자 우선, 시행일자 폴백, 둘 다 표시
- 카테고리: 규칙 기반 분류, "정보 없음" 대신 "미분류" 사용
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetaParser:
    """메타데이터 파서"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)

        # metadata 섹션에서 설정 로드
        metadata_config = self.config.get("metadata", {})

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
        self.category_rules = self.config.get("meta_parsing", {}).get(
            "category_rules", {}
        )
        self.default_category = self.config.get("meta_parsing", {}).get(
            "default_category", "미분류"
        )

        logger.info(
            f"📋 메타 파서 초기화: 날짜 우선순위 {len(self.date_priority)}개, 작성자 필드 {len(self.author_fields)}개, Stoplist {len(self.author_stoplist)}개, 카테고리 규칙 {len(self.category_rules)}개"
        )

    def _validate_author(self, author: str) -> bool:
        """작성자 이름 검증 (한글 2~4음절 + Stoplist)

        Args:
            author: 작성자 후보 문자열

        Returns:
            검증 통과 여부
        """
        if not author or not author.strip():
            return False

        author = author.strip()

        # Stoplist 체크
        if author in self.author_stoplist:
            logger.debug(f"작성자 Stoplist 제외: {author}")
            return False

        # 한글 2~4음절만 허용 (공백 없이)
        import re

        pattern = r"^[가-힣]{2,4}$"
        if not re.match(pattern, author):
            logger.debug(f"작성자 패턴 불일치 (한글 2~4음절 아님): {author}")
            return False

        return True

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

    def parse_dates(self, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """날짜 파싱 및 표준화

        Args:
            metadata: 문서 메타데이터 (기안일자, 시행일자, 작성일자 등 포함)

        Returns:
            (display_date, date_detail)
            - display_date: 우선순위에 따른 대표 날짜 (YYYY-MM-DD)
            - date_detail: "기안일자 / 시행일자" 형식
        """
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

        Args:
            date_str: 원본 날짜 문자열

        Returns:
            정규화된 날짜 (YYYY-MM-DD) 또는 원본
        """
        if not date_str or not isinstance(date_str, str):
            return date_str

        import re
        from datetime import datetime

        date_str = date_str.strip()

        # 1. 범위 형식 처리 (YYYY-MM-DD ~ YYYY-MM-DD → 앞 날짜 채택)
        range_pattern = r"(\d{4}-\d{1,2}-\d{1,2})\s*~\s*\d{4}-\d{1,2}-\d{1,2}"
        range_match = re.search(range_pattern, date_str)
        if range_match:
            date_str = range_match.group(1)

        # 2. 시간 제거 (YYYY-MM-DD HH:MM:SS → YYYY-MM-DD)
        date_str = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?", "", date_str)

        # 3. YY. M. D. 형식 → YYYY-MM-DD
        # 예: "24. 10. 24" → "2024-10-24"
        yy_pattern = r"(\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})"
        yy_match = re.search(yy_pattern, date_str)
        if yy_match:
            yy, mm, dd = yy_match.groups()
            # 2자리 연도를 4자리로 변환 (20YY로 가정)
            yyyy = f"20{yy}"
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"

        # 4. YYYY-M-D 또는 YYYY.M.D → YYYY-MM-DD
        date_str = re.sub(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", r"\1-\2-\3", date_str)

        # 5. 패딩 (YYYY-M-D → YYYY-MM-DD)
        padding_pattern = r"(\d{4})-(\d{1,2})-(\d{1,2})"
        padding_match = re.search(padding_pattern, date_str)
        if padding_match:
            yyyy, mm, dd = padding_match.groups()
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"

        # 6. 검증 및 반환
        try:
            # YYYY-MM-DD 형식 검증
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            # 파싱 실패 시 원본 반환
            logger.debug(f"날짜 정규화 실패 (원본 반환): {date_str}")
            return date_str

    def classify_category(
        self, title: str = "", content: str = "", filename: str = ""
    ) -> Tuple[str, str]:
        """카테고리 분류

        Args:
            title: 문서 제목
            content: 문서 내용
            filename: 파일명

        Returns:
            (category, source)
            - category: 분류된 카테고리
            - source: 분류 방법 ("rule", "ml", "default")
        """
        # 분류 대상 텍스트 (제목 > 파일명 > 내용)
        search_text = f"{title} {filename} {content[:500]}"
        search_text = search_text.lower()

        matched_categories = []

        # 1. 문서 유형 규칙 적용 (우선순위 1)
        doc_type_rules = self.category_rules.get("document_type", [])
        for rule in doc_type_rules:
            keywords = rule.get("keywords", [])
            category = rule.get("category", "")

            if any(kw in search_text for kw in keywords):
                matched_categories.append(category)
                logger.debug(f"✓ 문서 유형 매칭: {category} (키워드: {keywords})")

        # 2. 장비 분류 규칙 적용 (우선순위 2)
        equipment_rules = self.category_rules.get("equipment_type", [])
        for rule in equipment_rules:
            keywords = rule.get("keywords", [])
            category = rule.get("category", "")

            if any(kw in search_text for kw in keywords):
                matched_categories.append(category)
                logger.debug(f"✓ 장비 분류 매칭: {category} (키워드: {keywords})")

        # 3. 카테고리 조합
        if matched_categories:
            # 중복 제거하고 순서 유지
            unique_categories = list(dict.fromkeys(matched_categories))
            combined_category = " / ".join(unique_categories)
            return combined_category, "rule"

        # 4. ML 분류 (향후 구현)
        # TODO: ML 기반 카테고리 분류 추가

        # 5. 기본 카테고리
        return self.default_category, "default"

    def parse(
        self, metadata: Dict[str, Any], title: str = "", content: str = ""
    ) -> Dict[str, Any]:
        """메타데이터 파싱 및 표준화

        Args:
            metadata: 원본 메타데이터
            title: 문서 제목
            content: 문서 내용

        Returns:
            표준화된 메타데이터
        """
        # 날짜 파싱
        display_date, date_detail = self.parse_dates(metadata)

        # 작성자 추출 (우선순위 순서대로)
        author = None
        for field in self.author_fields:
            if field in metadata and metadata[field]:
                candidate = metadata[field]
                # 작성자 검증 (한글 2~4음절 + Stoplist)
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

        # 표준화된 메타데이터 구성
        standardized = {
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
            "category": category,
            "category_source": category_source,
            "filename": filename,
        }

        # "정보 없음"을 미분류로 변경 (카테고리만)
        if standardized["category"] == "정보 없음":
            standardized["category"] = self.default_category

        logger.debug(
            f"📋 메타 파싱 완료: author={author}, category={category} (source={category_source}), date={date_detail}"
        )

        return standardized

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
