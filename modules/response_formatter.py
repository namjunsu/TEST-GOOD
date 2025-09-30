#!/usr/bin/env python3
"""
고급 응답 포맷터 시스템

주요 기능:
- 템플릿 기반 포맷팅
- 다중 출력 형식 지원 (Plain, Markdown, HTML, JSON)
- 스타일 테마 시스템
- 국제화(i18n) 지원
- 포맷 캐싱 및 재사용
- 동적 레이아웃 생성
- 커스터마이징 가능한 컴포넌트
"""

import re
import json
import html
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from collections import OrderedDict
from datetime import datetime
from enum import Enum
from functools import lru_cache
import logging
import warnings

# 템플릿 캐시
TEMPLATE_CACHE = {}

class FormatType(Enum):
    """출력 형식 타입"""
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    TERMINAL = "terminal"  # ANSI 컬러 지원

class ThemeStyle(Enum):
    """테마 스타일"""
    DEFAULT = "default"
    MINIMAL = "minimal"
    DETAILED = "detailed"
    COMPACT = "compact"
    PROFESSIONAL = "professional"

@dataclass
class FormatConfig:
    """포맷 설정"""
    format_type: FormatType = FormatType.MARKDOWN
    theme: ThemeStyle = ThemeStyle.DEFAULT
    language: str = "ko"
    max_width: int = 80
    use_colors: bool = True
    use_emojis: bool = True
    use_tables: bool = True
    cache_enabled: bool = True
    custom_styles: Dict[str, Any] = field(default_factory=dict)

class Template:
    """간단한 템플릿 엔진"""

    def __init__(self, template_str: str):
        self.template = template_str
        self.compiled = self._compile(template_str)

    def _compile(self, template_str: str) -> Callable:
        """템플릿 컴파일"""
        # {{variable}} 형식을 파이썬 format으로 변환
        pattern = r'\{\{(\w+)\}\}'
        formatted = re.sub(pattern, r'{\1}', template_str)

        def render(**kwargs):
            try:
                return formatted.format(**kwargs)
            except KeyError as e:
                warnings.warn(f"Template variable missing: {e}")
                return formatted

        return render

    def render(self, **kwargs) -> str:
        """템플릿 렌더링"""
        return self.compiled(**kwargs)

class I18n:
    """국제화 지원"""

    TRANSLATIONS = {
        'ko': {
            'summary': '요약',
            'details': '상세 정보',
            'basic_info': '기본 정보',
            'author': '작성자',
            'date': '날짜',
            'department': '부서',
            'cost': '비용',
            'total': '총계',
            'analysis': '분석',
            'recommendation': '추천',
            'warning': '경고',
            'no_results': '검색 결과가 없습니다',
            'equipment': '장비',
            'status': '상태',
            'normal': '정상',
            'need_check': '점검 필요',
            'category': '카테고리',
            'comparison': '비교',
            'history': '이력',
            'conclusion': '결론'
        },
        'en': {
            'summary': 'Summary',
            'details': 'Details',
            'basic_info': 'Basic Information',
            'author': 'Author',
            'date': 'Date',
            'department': 'Department',
            'cost': 'Cost',
            'total': 'Total',
            'analysis': 'Analysis',
            'recommendation': 'Recommendation',
            'warning': 'Warning',
            'no_results': 'No results found',
            'equipment': 'Equipment',
            'status': 'Status',
            'normal': 'Normal',
            'need_check': 'Needs Check',
            'category': 'Category',
            'comparison': 'Comparison',
            'history': 'History',
            'conclusion': 'Conclusion'
        }
    }

    @classmethod
    def get(cls, key: str, lang: str = 'ko') -> str:
        """번역 문자열 가져오기"""
        return cls.TRANSLATIONS.get(lang, {}).get(key, key)

class StyleManager:
    """스타일 관리자"""

    THEMES = {
        ThemeStyle.DEFAULT: {
            'divider': '━' * 50,
            'section_marker': '▶',
            'bullet': '•',
            'emojis': {
                'doc': '📋',
                'info': '📝',
                'money': '💰',
                'chart': '📊',
                'warning': '⚠️',
                'check': '✅',
                'cross': '❌',
                'star': '⭐',
                'bulb': '💡',
                'link': '🔗'
            },
            'table': {
                'top_left': '┌',
                'top_right': '┐',
                'bottom_left': '└',
                'bottom_right': '┘',
                'horizontal': '─',
                'vertical': '│',
                'cross': '┼',
                't_down': '┬',
                't_up': '┴',
                't_right': '├',
                't_left': '┤'
            }
        },
        ThemeStyle.MINIMAL: {
            'divider': '-' * 50,
            'section_marker': '>',
            'bullet': '-',
            'emojis': {},  # No emojis
            'table': {
                'top_left': '+',
                'top_right': '+',
                'bottom_left': '+',
                'bottom_right': '+',
                'horizontal': '-',
                'vertical': '|',
                'cross': '+',
                't_down': '+',
                't_up': '+',
                't_right': '+',
                't_left': '+'
            }
        },
        ThemeStyle.PROFESSIONAL: {
            'divider': '═' * 50,
            'section_marker': '■',
            'bullet': '◆',
            'emojis': {
                'doc': '[DOC]',
                'info': '[INFO]',
                'money': '[COST]',
                'chart': '[STAT]',
                'warning': '[WARN]',
                'check': '[OK]',
                'cross': '[FAIL]',
                'star': '[IMPORTANT]',
                'bulb': '[TIP]',
                'link': '[LINK]'
            },
            'table': {
                'top_left': '╔',
                'top_right': '╗',
                'bottom_left': '╚',
                'bottom_right': '╝',
                'horizontal': '═',
                'vertical': '║',
                'cross': '╬',
                't_down': '╦',
                't_up': '╩',
                't_right': '╠',
                't_left': '╣'
            }
        }
    }

    @classmethod
    def get_theme(cls, theme: ThemeStyle) -> Dict:
        """테마 가져오기"""
        return cls.THEMES.get(theme, cls.THEMES[ThemeStyle.DEFAULT])

class ComponentBuilder:
    """컴포넌트 빌더 - 재사용 가능한 UI 컴포넌트"""

    def __init__(self, config: FormatConfig):
        self.config = config
        self.theme = StyleManager.get_theme(config.theme)

    def header(self, title: str, level: int = 1) -> str:
        """헤더 생성"""
        if self.config.format_type == FormatType.MARKDOWN:
            return f"{'#' * level} {title}\n"
        elif self.config.format_type == FormatType.HTML:
            return f"<h{level}>{html.escape(title)}</h{level}>\n"
        else:
            marker = self.theme['section_marker']
            return f"{marker} {title}\n"

    def divider(self) -> str:
        """구분선 생성"""
        if self.config.format_type == FormatType.MARKDOWN:
            return "\n---\n"
        elif self.config.format_type == FormatType.HTML:
            return "<hr />\n"
        else:
            return self.theme['divider'] + "\n"

    def bullet_list(self, items: List[str]) -> str:
        """불릿 리스트 생성"""
        if not items:
            return ""

        if self.config.format_type == FormatType.MARKDOWN:
            return "\n".join(f"- {item}" for item in items) + "\n"
        elif self.config.format_type == FormatType.HTML:
            items_html = "\n".join(f"  <li>{html.escape(item)}</li>" for item in items)
            return f"<ul>\n{items_html}\n</ul>\n"
        else:
            bullet = self.theme['bullet']
            return "\n".join(f"{bullet} {item}" for item in items) + "\n"

    def table(self, headers: List[str], rows: List[List[str]]) -> str:
        """테이블 생성"""
        if not headers or not rows:
            return ""

        if self.config.format_type == FormatType.MARKDOWN:
            return self._markdown_table(headers, rows)
        elif self.config.format_type == FormatType.HTML:
            return self._html_table(headers, rows)
        elif self.config.format_type == FormatType.JSON:
            return json.dumps([dict(zip(headers, row)) for row in rows], ensure_ascii=False, indent=2)
        else:
            return self._text_table(headers, rows)

    def _markdown_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """마크다운 테이블"""
        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        return "\n".join(lines) + "\n"

    def _html_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """HTML 테이블"""
        lines = ["<table border='1'>"]
        lines.append("  <thead>")
        lines.append("    <tr>")
        for header in headers:
            lines.append(f"      <th>{html.escape(header)}</th>")
        lines.append("    </tr>")
        lines.append("  </thead>")
        lines.append("  <tbody>")
        for row in rows:
            lines.append("    <tr>")
            for cell in row:
                lines.append(f"      <td>{html.escape(str(cell))}</td>")
            lines.append("    </tr>")
        lines.append("  </tbody>")
        lines.append("</table>")
        return "\n".join(lines) + "\n"

    def _text_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """텍스트 테이블 (박스 그리기)"""
        # 컬럼 너비 계산
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(header)
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(min(max_width + 2, 30))  # 최대 30자

        t = self.theme['table']
        lines = []

        # 상단 테두리
        top = t['top_left'] + t['t_down'].join(t['horizontal'] * w for w in col_widths) + t['top_right']
        lines.append(top)

        # 헤더
        header_cells = []
        for i, header in enumerate(headers):
            header_cells.append(header[:col_widths[i]-2].center(col_widths[i]))
        lines.append(t['vertical'] + t['vertical'].join(header_cells) + t['vertical'])

        # 중간선
        mid = t['t_right'] + t['cross'].join(t['horizontal'] * w for w in col_widths) + t['t_left']
        lines.append(mid)

        # 데이터
        for row in rows:
            row_cells = []
            for i in range(len(headers)):
                if i < len(row):
                    cell = str(row[i])[:col_widths[i]-2]
                    row_cells.append(" " + cell.ljust(col_widths[i]-1))
                else:
                    row_cells.append(" " * col_widths[i])
            lines.append(t['vertical'] + t['vertical'].join(row_cells) + t['vertical'])

        # 하단 테두리
        bottom = t['bottom_left'] + t['t_up'].join(t['horizontal'] * w for w in col_widths) + t['bottom_right']
        lines.append(bottom)

        return "\n".join(lines) + "\n"

    def emoji(self, key: str) -> str:
        """이모지 또는 대체 텍스트 반환"""
        if not self.config.use_emojis:
            return ""
        return self.theme.get('emojis', {}).get(key, '')

    def section(self, title: str, content: str, icon: Optional[str] = None) -> str:
        """섹션 생성"""
        output = []

        # 아이콘 및 제목
        if icon and self.config.use_emojis:
            emoji = self.emoji(icon)
            title_str = f"{emoji} {title}" if emoji else title
        else:
            title_str = title

        if self.config.format_type == FormatType.MARKDOWN:
            output.append(f"### {title_str}")
        elif self.config.format_type == FormatType.HTML:
            output.append(f"<div class='section'>")
            output.append(f"<h3>{html.escape(title_str)}</h3>")
        else:
            output.append(f"{self.theme['section_marker']} {title_str}")

        # 내용
        output.append(content)

        if self.config.format_type == FormatType.HTML:
            output.append("</div>")

        return "\n".join(output) + "\n"

class ResponseFormatter:
    """고급 응답 포맷터"""

    def __init__(self, config: Optional[FormatConfig] = None):
        self.config = config or FormatConfig()
        self.builder = ComponentBuilder(self.config)
        self.cache = OrderedDict() if self.config.cache_enabled else None
        self.logger = logging.getLogger(__name__)

    @lru_cache(maxsize=100)
    def _get_cached_format(self, cache_key: str) -> Optional[str]:
        """캐시된 포맷 가져오기"""
        if self.cache and cache_key in self.cache:
            return self.cache[cache_key]
        return None

    def _cache_format(self, cache_key: str, formatted: str):
        """포맷 캐싱"""
        if self.cache is not None:
            self.cache[cache_key] = formatted
            if len(self.cache) > 1000:
                self.cache.popitem(last=False)

    def format_document_summary(self, doc_info: Dict[str, Any],
                               query: str = "") -> str:
        """문서 요약 포맷팅"""
        # 캐시 키 생성
        if self.config.cache_enabled:
            cache_key = hashlib.md5(
                f"doc_{json.dumps(doc_info, sort_keys=True)}_{self.config.format_type.value}".encode()
            ).hexdigest()
            cached = self._get_cached_format(cache_key)
            if cached:
                return cached

        output = []
        lang = self.config.language

        # 헤더
        title = doc_info.get('제목', doc_info.get('title', I18n.get('summary', lang)))
        output.append(self.builder.header(title, 1))

        # 핵심 요약
        if doc_info.get('핵심요약'):
            content = self.builder.bullet_list(doc_info['핵심요약'][:3])
            output.append(self.builder.section(
                I18n.get('summary', lang),
                content,
                icon='star'
            ))

        # 기본 정보
        basic_info = []
        if doc_info.get('기안자'):
            basic_info.append(f"{I18n.get('author', lang)}: {doc_info['기안자']}")
        if doc_info.get('기안일자'):
            basic_info.append(f"{I18n.get('date', lang)}: {doc_info['기안일자']}")
        if doc_info.get('기안부서'):
            basic_info.append(f"{I18n.get('department', lang)}: {doc_info['기안부서']}")

        if basic_info:
            content = self.builder.bullet_list(basic_info)
            output.append(self.builder.section(
                I18n.get('basic_info', lang),
                content,
                icon='info'
            ))

        # 상세 내용 테이블
        if doc_info.get('상세내용'):
            details = doc_info['상세내용']
            if isinstance(details, list) and details:
                if isinstance(details[0], dict):
                    headers = list(details[0].keys())
                    rows = [[str(d.get(h, '')) for h in headers] for d in details]
                    table = self.builder.table(headers, rows)
                    output.append(self.builder.section(
                        I18n.get('details', lang),
                        table,
                        icon='doc'
                    ))

        # 비용 정보
        if doc_info.get('비용정보'):
            cost_items = [f"{item}: {cost}" for item, cost in doc_info['비용정보'].items()]
            content = self.builder.bullet_list(cost_items)
            output.append(self.builder.section(
                I18n.get('cost', lang),
                content,
                icon='money'
            ))

        output.append(self.builder.divider())

        result = "\n".join(output)

        # 캐싱
        if self.config.cache_enabled:
            self._cache_format(cache_key, result)

        return result

    def format_statistics_response(self, stats_data: Dict[str, Any],
                                  query_type: str = "") -> str:
        """통계 응답 포맷팅"""
        output = []
        lang = self.config.language

        # 제목
        title = stats_data.get('title', I18n.get('analysis', lang))
        output.append(self.builder.header(title, 1))

        # 총계
        if stats_data.get('총계'):
            total_str = f"{I18n.get('total', lang)}: {stats_data['총계']}"
            output.append(self.builder.section(
                total_str,
                "",
                icon='chart'
            ))

        # 테이블 데이터
        if stats_data.get('table_data') and stats_data.get('headers'):
            table = self.builder.table(
                stats_data['headers'],
                stats_data['table_data']
            )
            output.append(table)

        # 분석 결과
        if stats_data.get('분석'):
            analysis_items = [f"{k}: {v}" for k, v in stats_data['분석'].items()]
            content = self.builder.bullet_list(analysis_items)
            output.append(self.builder.section(
                I18n.get('analysis', lang),
                content,
                icon='chart'
            ))

        # 추천사항
        if stats_data.get('추천'):
            content = self.builder.bullet_list(stats_data['추천'])
            output.append(self.builder.section(
                I18n.get('recommendation', lang),
                content,
                icon='bulb'
            ))

        output.append(self.builder.divider())

        return "\n".join(output)

    def format_asset_search_response(self, assets: List[Dict],
                                    search_criteria: Dict) -> str:
        """자산 검색 결과 포맷팅"""
        output = []
        lang = self.config.language

        # 검색 조건
        criteria_str = self._format_search_criteria(search_criteria)
        output.append(self.builder.header(criteria_str, 1))

        if not assets:
            output.append(self.builder.section(
                I18n.get('no_results', lang),
                "",
                icon='cross'
            ))
        else:
            # 요약 통계
            total_count = len(assets)
            total_value = sum(self._parse_amount(a.get('취득가액', 0)) for a in assets)

            stats_str = f"{I18n.get('equipment', lang)}: {total_count:,} | {I18n.get('total', lang)}: {total_value:,}원"
            output.append(stats_str)
            output.append("")

            # 카테고리별 분류
            categories = self._categorize_assets(assets)

            for category, items in categories.items():
                if items:
                    # 카테고리 헤더
                    output.append(self.builder.header(f"{category} ({len(items)})", 2))

                    # 상위 5개 테이블
                    display_items = items[:5]
                    headers = ['품목', '모델', '구입일자', '상태']
                    rows = []

                    for item in display_items:
                        rows.append([
                            item.get('품목', ''),
                            item.get('모델', ''),
                            item.get('구입일자', ''),
                            item.get('상태', I18n.get('normal', lang))
                        ])

                    if rows:
                        table = self.builder.table(headers, rows)
                        output.append(table)

                        if len(items) > 5:
                            output.append(f"... +{len(items)-5} more\n")

            # 점검 필요 장비
            need_check = [a for a in assets if '점검' in str(a.get('비고', ''))]
            if need_check:
                warnings = [f"{item.get('품목', '')}: {item.get('비고', '')}"
                           for item in need_check[:3]]
                content = self.builder.bullet_list(warnings)
                output.append(self.builder.section(
                    I18n.get('need_check', lang),
                    content,
                    icon='warning'
                ))

        output.append(self.builder.divider())

        return "\n".join(output)

    def format_comparison_response(self, comparison_data: Dict) -> str:
        """비교 분석 결과 포맷팅"""
        output = []
        lang = self.config.language

        # 제목
        title = comparison_data.get('title', I18n.get('comparison', lang))
        output.append(self.builder.header(title, 1))

        # 비용 비교 테이블
        if comparison_data.get('cost_comparison'):
            headers = ['구분', '평균 비용', '횟수', '총 비용']
            rows = comparison_data['cost_comparison']
            table = self.builder.table(headers, rows)
            output.append(self.builder.section(
                I18n.get('cost', lang),
                table,
                icon='money'
            ))

        # 분석
        if comparison_data.get('analysis'):
            content = self.builder.bullet_list(comparison_data['analysis'])
            output.append(self.builder.section(
                I18n.get('analysis', lang),
                content,
                icon='chart'
            ))

        # 이력
        if comparison_data.get('history'):
            content = self.builder.bullet_list(comparison_data['history'])
            output.append(self.builder.section(
                I18n.get('history', lang),
                content,
                icon='link'
            ))

        # 추천
        if comparison_data.get('recommendation'):
            output.append(self.builder.section(
                I18n.get('recommendation', lang),
                comparison_data['recommendation'],
                icon='bulb'
            ))

        output.append(self.builder.divider())

        return "\n".join(output)

    def format_error(self, error_msg: str, details: Optional[Dict] = None) -> str:
        """에러 메시지 포맷팅"""
        output = []
        lang = self.config.language

        output.append(self.builder.section(
            I18n.get('warning', lang),
            error_msg,
            icon='warning'
        ))

        if details:
            detail_items = [f"{k}: {v}" for k, v in details.items()]
            content = self.builder.bullet_list(detail_items)
            output.append(content)

        return "\n".join(output)

    def format_json_response(self, data: Any) -> str:
        """JSON 형식으로 포맷팅"""
        if self.config.format_type == FormatType.JSON:
            return json.dumps(data, ensure_ascii=False, indent=2)
        else:
            # 다른 포맷에서도 JSON 표시 가능
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            if self.config.format_type == FormatType.MARKDOWN:
                return f"```json\n{json_str}\n```\n"
            elif self.config.format_type == FormatType.HTML:
                return f"<pre><code class='json'>{html.escape(json_str)}</code></pre>\n"
            else:
                return json_str

    def _format_search_criteria(self, criteria: Dict) -> str:
        """검색 조건 포맷팅"""
        parts = []
        lang = self.config.language

        if criteria.get('location'):
            parts.append(f"{criteria['location']} {I18n.get('equipment', lang)}")
        elif criteria.get('manager'):
            parts.append(f"{criteria['manager']} {I18n.get('equipment', lang)}")
        elif criteria.get('year'):
            parts.append(f"{criteria['year']} {I18n.get('equipment', lang)}")
        else:
            parts.append(I18n.get('equipment', lang))

        return " ".join(parts)

    def _categorize_assets(self, assets: List[Dict]) -> Dict[str, List]:
        """자산 카테고리 분류"""
        categories = {
            '카메라 시스템': [],
            '오디오 시스템': [],
            '조명 시스템': [],
            '모니터/디스플레이': [],
            '기타 장비': []
        }

        for asset in assets:
            item = asset.get('품목', '').lower()

            if any(k in item for k in ['카메라', 'ccu', '렌즈', 'eng']):
                categories['카메라 시스템'].append(asset)
            elif any(k in item for k in ['마이크', '오디오', '믹서', '인터컴']):
                categories['오디오 시스템'].append(asset)
            elif any(k in item for k in ['조명', 'led', '라이트']):
                categories['조명 시스템'].append(asset)
            elif any(k in item for k in ['모니터', '디스플레이', 'tv']):
                categories['모니터/디스플레이'].append(asset)
            else:
                categories['기타 장비'].append(asset)

        return {k: v for k, v in categories.items() if v}

    def _parse_amount(self, amount_str) -> int:
        """금액 파싱"""
        if isinstance(amount_str, (int, float)):
            return int(amount_str)

        if not amount_str:
            return 0

        amount_str = str(amount_str)
        amount_str = re.sub(r'[^0-9]', '', amount_str)

        try:
            return int(amount_str)
        except:
            return 0

    def extract_key_points(self, text: str, max_points: int = 3) -> List[str]:
        """핵심 포인트 추출"""
        points = []

        # 문장 분리
        sentences = re.split(r'[.!?]\s+', text)

        # 중요 키워드
        important_keywords = ['필요', '권장', '추천', '중요', '핵심', '결론', '총', '합계']

        for sentence in sentences:
            if any(keyword in sentence for keyword in important_keywords):
                if 10 < len(sentence) < 100:
                    points.append(sentence.strip())
                    if len(points) >= max_points:
                        break

        # 부족하면 처음 문장 추가
        if len(points) < max_points:
            for sentence in sentences:
                if 10 < len(sentence) < 100:
                    if sentence.strip() not in points:
                        points.append(sentence.strip())
                        if len(points) >= max_points:
                            break

        return points[:max_points]

    def set_config(self, config: FormatConfig):
        """설정 변경"""
        self.config = config
        self.builder = ComponentBuilder(config)

    def clear_cache(self):
        """캐시 클리어"""
        if self.cache:
            self.cache.clear()
        self._get_cached_format.cache_clear()

# 편의 함수들
def create_formatter(format_type: str = "markdown",
                    theme: str = "default",
                    language: str = "ko") -> ResponseFormatter:
    """포맷터 생성 헬퍼"""
    config = FormatConfig(
        format_type=FormatType(format_type.lower()),
        theme=ThemeStyle(theme.lower()),
        language=language
    )
    return ResponseFormatter(config)

def format_as_markdown(data: Dict, formatter_type: str = "document") -> str:
    """마크다운으로 포맷"""
    formatter = create_formatter("markdown")

    if formatter_type == "document":
        return formatter.format_document_summary(data)
    elif formatter_type == "statistics":
        return formatter.format_statistics_response(data, "")
    elif formatter_type == "comparison":
        return formatter.format_comparison_response(data)
    else:
        return formatter.format_json_response(data)

def format_as_html(data: Dict, formatter_type: str = "document") -> str:
    """HTML로 포맷"""
    formatter = create_formatter("html")

    if formatter_type == "document":
        return formatter.format_document_summary(data)
    elif formatter_type == "statistics":
        return formatter.format_statistics_response(data, "")
    elif formatter_type == "comparison":
        return formatter.format_comparison_response(data)
    else:
        return formatter.format_json_response(data)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Response Formatter Test")
    parser.add_argument('--format', choices=['plain', 'markdown', 'html', 'json'],
                       default='markdown', help='Output format')
    parser.add_argument('--theme', choices=['default', 'minimal', 'professional'],
                       default='default', help='Theme style')
    parser.add_argument('--lang', choices=['ko', 'en'], default='ko',
                       help='Language')
    parser.add_argument('--test', action='store_true', help='Run tests')
    args = parser.parse_args()

    if args.test:
        print("🧪 Response Formatter Test")
        print("=" * 50)

        # 테스트 데이터
        test_doc = {
            '제목': '2024년 장비 구매 계획',
            '핵심요약': [
                '총 5개 장비 구매 예정',
                '예산 2억원 책정',
                '3월까지 구매 완료 목표'
            ],
            '기안자': '김철수',
            '기안일자': '2024-01-15',
            '기안부서': '방송기술팀',
            '상세내용': [
                {'장비명': '카메라', '수량': 2, '단가': '5000만원'},
                {'장비명': '렌즈', '수량': 3, '단가': '1000만원'}
            ],
            '비용정보': {
                '카메라': '1억원',
                '렌즈': '3000만원',
                '기타': '7000만원'
            }
        }

        # 포맷터 생성
        config = FormatConfig(
            format_type=FormatType(args.format),
            theme=ThemeStyle(args.theme),
            language=args.lang
        )
        formatter = ResponseFormatter(config)

        # 문서 요약 테스트
        print("\n📋 Document Summary Test:")
        print("-" * 30)
        result = formatter.format_document_summary(test_doc)
        print(result)

        # 통계 테스트
        print("\n📊 Statistics Test:")
        print("-" * 30)
        stats_data = {
            'title': '2024년 구매 통계',
            '총계': '2억원',
            'headers': ['월', '건수', '금액'],
            'table_data': [
                ['1월', '3', '5000만원'],
                ['2월', '2', '3000만원'],
                ['3월', '5', '1.2억원']
            ],
            '분석': {
                '최다 구매월': '3월',
                '평균 구매액': '4000만원'
            },
            '추천': [
                '분산 구매로 리스크 관리',
                '대량 구매시 할인 협상'
            ]
        }
        result = formatter.format_statistics_response(stats_data)
        print(result)

        # 테이블 테스트
        print("\n📑 Table Test:")
        print("-" * 30)
        builder = ComponentBuilder(config)
        table = builder.table(
            ['ID', '이름', '부서', '직급'],
            [
                ['001', '김철수', '기술팀', '차장'],
                ['002', '이영희', '기획팀', '과장'],
                ['003', '박민수', '영업팀', '대리']
            ]
        )
        print(table)

        print("\n✅ Test completed")

    else:
        # 인터랙티브 모드
        print("Response Formatter Interactive Mode")
        print(f"Format: {args.format}, Theme: {args.theme}, Language: {args.lang}")
        print("Enter JSON data (end with Ctrl+D):")

        import sys
        input_data = sys.stdin.read()

        try:
            data = json.loads(input_data)

            config = FormatConfig(
                format_type=FormatType(args.format),
                theme=ThemeStyle(args.theme),
                language=args.lang
            )
            formatter = ResponseFormatter(config)

            if 'title' in data and 'table_data' in data:
                result = formatter.format_statistics_response(data)
            elif 'cost_comparison' in data:
                result = formatter.format_comparison_response(data)
            elif '제목' in data or 'title' in data:
                result = formatter.format_document_summary(data)
            else:
                result = formatter.format_json_response(data)

            print("\nFormatted Output:")
            print(result)

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
        except Exception as e:
            print(f"Error: {e}")