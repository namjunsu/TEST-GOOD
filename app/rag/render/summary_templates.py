"""
요약 템플릿 렌더링 모듈
2025-10-26

문서 요약을 고정된 4섹션 구조로 렌더링합니다.

구조:
1. 핵심 요약: 장애 요지, 조치, 리스크
2. 비용 (VAT 별도): 항목별 비용 및 합계
3. 메타: 기안자, 부서, 문서번호, 보존기간, 기안/시행일자
4. (노이즈 제거 완료)
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


class SummaryRenderer:
    """요약 템플릿 렌더러"""

    def __init__(self, config_path: str = "config/document_processing.yaml"):
        """초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.template_config = self.config.get('summary_template', {})
        self.sections = self.template_config.get('sections', [])
        self.output_format = self.template_config.get('output_format', 'markdown')

        logger.info(f"📝 요약 렌더러 초기화: {len(self.sections)}개 섹션")

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

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"✓ 설정 로드: {config_path}")
                return config

        except Exception as e:
            logger.error(f"❌ 설정 로드 실패: {e}")
            return {}

    def render(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str,
        cost_data: Optional[Dict[str, Any]] = None,
        risk: Optional[str] = None,
        doctype: Optional[str] = None,
        extra_sections: Optional[Dict[str, str]] = None
    ) -> str:
        """doctype별 요약 렌더링

        Args:
            filename: 파일명
            meta: 메타데이터 (parse_meta.py의 결과)
            summary: 핵심 요약 텍스트
            cost_data: 비용 데이터 (parse_tables.py의 결과, 선택)
            risk: 리스크 텍스트 (선택)
            doctype: 문서 유형 (proposal/report/review/minutes/unknown)
            extra_sections: 추가 섹션 데이터

        Returns:
            Markdown 형식의 요약 문자열
        """
        # doctype 기본값
        if not doctype:
            doctype = meta.get('doctype', 'proposal')

        # doctype별 렌더링 분기
        if doctype == 'proposal':
            return self._render_proposal(filename, meta, summary, cost_data, risk)
        elif doctype == 'report':
            return self._render_report(filename, meta, summary, extra_sections or {})
        elif doctype == 'review':
            return self._render_review(filename, meta, summary, extra_sections or {})
        elif doctype == 'minutes':
            return self._render_minutes(filename, meta, summary, extra_sections or {})
        else:
            # unknown은 기본 템플릿 사용
            return self._render_proposal(filename, meta, summary, cost_data, risk)

    def _render_proposal(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str,
        cost_data: Optional[Dict[str, Any]] = None,
        risk: Optional[str] = None
    ) -> str:
        """기안서 템플릿 (기존 4섹션)

        Args:
            filename: 파일명
            meta: 메타데이터
            summary: 핵심 요약
            cost_data: 비용 데이터
            risk: 리스크

        Returns:
            렌더링된 문자열
        """
        lines = []

        # 파일명
        lines.append(f"**📄 문서:** {filename}\n")

        # 1. 메타데이터 섹션
        lines.append(self._render_meta_section(meta))
        lines.append("")

        # 2. 핵심 요약 섹션
        lines.append(self._render_summary_section(summary))
        lines.append("")

        # 3. 비용 섹션 (있는 경우)
        if cost_data:
            lines.append(self._render_cost_section(cost_data))
            lines.append("")

        # 4. 리스크 섹션 (있는 경우)
        if risk:
            lines.append(self._render_risk_section(risk))
            lines.append("")

        return "\n".join(lines)

    def _render_report(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str,
        extra: Dict[str, str]
    ) -> str:
        """보고서 템플릿

        Args:
            filename: 파일명
            meta: 메타데이터
            summary: 핵심 발견사항
            extra: 추가 섹션 (conclusion, follow_up)

        Returns:
            렌더링된 문자열
        """
        lines = []

        # 파일명
        lines.append(f"**📄 문서:** {filename}\n")

        # 1. 메타데이터
        lines.append(self._render_meta_section(meta))
        lines.append("")

        # 2. 핵심 발견사항
        lines.append("**🔍 핵심 발견사항**")
        lines.append(summary)
        lines.append("")

        # 3. 결론 및 권고
        conclusion = extra.get('conclusion', '')
        if conclusion:
            lines.append("**📌 결론 및 권고**")
            lines.append(conclusion)
            lines.append("")

        # 4. 후속조치
        follow_up = extra.get('follow_up', '')
        if follow_up:
            lines.append("**🔜 후속조치**")
            lines.append(follow_up)
            lines.append("")

        return "\n".join(lines)

    def _render_review(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str,
        extra: Dict[str, str]
    ) -> str:
        """검토서 템플릿

        Args:
            filename: 파일명
            meta: 메타데이터
            summary: 요청사항
            extra: 추가 섹션 (evaluation, recommendation)

        Returns:
            렌더링된 문자열
        """
        lines = []

        # 파일명
        lines.append(f"**📄 문서:** {filename}\n")

        # 1. 메타데이터
        lines.append(self._render_meta_section(meta))
        lines.append("")

        # 2. 요청사항
        lines.append("**📝 요청사항**")
        lines.append(summary)
        lines.append("")

        # 3. 검토 항목별 평가
        evaluation = extra.get('evaluation', '')
        if evaluation:
            lines.append("**✅ 검토 항목별 평가**")
            lines.append(evaluation)
            lines.append("")

        # 4. 권고안
        recommendation = extra.get('recommendation', '')
        if recommendation:
            lines.append("**💡 권고안**")
            lines.append(recommendation)
            lines.append("")

        return "\n".join(lines)

    def _render_minutes(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str,
        extra: Dict[str, str]
    ) -> str:
        """회의록 템플릿

        Args:
            filename: 파일명
            meta: 메타데이터
            summary: 회의 개요
            extra: 추가 섹션 (decisions, action_items)

        Returns:
            렌더링된 문자열
        """
        lines = []

        # 파일명
        lines.append(f"**📄 문서:** {filename}\n")

        # 1. 메타데이터
        lines.append(self._render_meta_section(meta))
        lines.append("")

        # 2. 회의 개요
        lines.append("**📋 회의 개요**")
        lines.append(summary)
        lines.append("")

        # 3. 주요 결정사항
        decisions = extra.get('decisions', '')
        if decisions:
            lines.append("**✔️ 주요 결정사항**")
            lines.append(decisions)
            lines.append("")

        # 4. Action Items
        action_items = extra.get('action_items', '')
        if action_items:
            lines.append("**📌 Action Items (담당/기한)**")
            lines.append(action_items)
            lines.append("")

        return "\n".join(lines)

    def _render_meta_section(self, meta: Dict[str, Any]) -> str:
        """메타데이터 섹션 렌더링

        Args:
            meta: 메타데이터

        Returns:
            렌더링된 섹션 문자열
        """
        lines = []
        lines.append("**📋 문서 정보**")

        # 기안자/부서
        drafter = meta.get('drafter', '정보 없음')
        department = meta.get('department', '정보 없음')
        lines.append(f"- **기안자/부서:** {drafter} / {department}")

        # 날짜 (기안일자 / 시행일자)
        date_detail = meta.get('date_detail', '정보 없음')
        lines.append(f"- **기안일자 / 시행일자:** {date_detail}")

        # 카테고리
        category = meta.get('category', '미분류')
        lines.append(f"- **유형/카테고리:** {category}")

        # 문서번호 (선택)
        doc_number = meta.get('doc_number')
        if doc_number and doc_number != '정보 없음':
            lines.append(f"- **문서번호:** {doc_number}")

        # 보존기간 (선택)
        retention = meta.get('retention')
        if retention and retention != '정보 없음':
            lines.append(f"- **보존기간:** {retention}")

        return "\n".join(lines)

    def _render_summary_section(self, summary: str) -> str:
        """핵심 요약 섹션 렌더링

        Args:
            summary: 요약 텍스트

        Returns:
            렌더링된 섹션 문자열
        """
        lines = []
        lines.append("**✨ 핵심 요약**")
        lines.append(summary)

        return "\n".join(lines)

    def _render_cost_section(self, cost_data: Dict[str, Any]) -> str:
        """비용 섹션 렌더링

        Args:
            cost_data: 비용 데이터

        Returns:
            렌더링된 섹션 문자열
        """
        lines = []
        lines.append("**💰 비용 (VAT 별도)**")

        items = cost_data.get('items', [])
        if not items:
            lines.append("- 비용 정보를 찾을 수 없습니다")
            return "\n".join(lines)

        # 항목별 비용
        for item in items:
            name = item.get('name', '항목')
            amount = item.get('amount', 0)
            lines.append(f"- {name}: ₩{amount:,}")

        # 합계
        total = cost_data.get('total', 0)
        sum_match = cost_data.get('sum_match')

        if sum_match is False:
            claimed_total = cost_data.get('claimed_total', 0)
            lines.append(f"- **합계:** ₩{total:,} ⚠️ (문서 합계: ₩{claimed_total:,}, 차이 있음)")
        else:
            lines.append(f"- **합계:** ₩{total:,}")

        return "\n".join(lines)

    def _render_risk_section(self, risk: str) -> str:
        """리스크 섹션 렌더링

        Args:
            risk: 리스크 텍스트

        Returns:
            렌더링된 섹션 문자열
        """
        lines = []
        lines.append("**⚠️ 리스크**")
        lines.append(risk)

        return "\n".join(lines)

    def render_simple(
        self,
        filename: str,
        meta: Dict[str, Any],
        summary: str
    ) -> str:
        """간단한 요약 렌더링 (비용, 리스크 없음)

        Args:
            filename: 파일명
            meta: 메타데이터
            summary: 요약 텍스트

        Returns:
            Markdown 형식의 요약 문자열
        """
        return self.render(filename, meta, summary, cost_data=None, risk=None)
