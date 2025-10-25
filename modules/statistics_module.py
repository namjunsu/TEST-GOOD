#!/usr/bin/env python3
"""
from app.core.logging import get_logger
통계 및 리포트 모듈 - Perfect RAG에서 분리된 통계/분석 기능
2025-09-29 리팩토링

이 모듈은 문서 통계 분석, 리포트 생성, 데이터 시각화 등
통계 관련 기능을 담당합니다.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime
import json

logger = get_logger(__name__)


class StatisticsModule:
    """통계 및 리포트 생성 통합 모듈"""

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}
        self.docs_dir = Path(self.config.get('docs_dir', './docs'))

        # 통계 데이터 캐시
        self.stats_cache = {}

    def collect_statistics_data(self, query: str, metadata_cache: Dict) -> Dict[str, Any]:
        """
        통계 데이터 수집 및 구조화

        Args:
            query: 사용자 쿼리
            metadata_cache: 메타데이터 캐시

        Returns:
            구조화된 통계 데이터
        """
        stats_data = {
            'title': '',
            'headers': [],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        # 연도 추출
        year_match = re.search(r'(20\d{2})', query)
        target_year = year_match.group(1) if year_match else None

        # 통계 타입별 처리
        if "연도별" in query and "구매" in query:
            return self._collect_yearly_purchase_stats(metadata_cache, target_year)
        elif "기안자별" in query:
            return self._collect_drafter_stats(metadata_cache, target_year)
        elif "월별" in query and "수리" in query:
            return self._collect_monthly_repair_stats(metadata_cache, target_year)
        elif "카테고리별" in query:
            return self._collect_category_stats(metadata_cache, target_year)
        else:
            # 기본: 전체 통계
            return self._collect_general_stats(metadata_cache, target_year)

    def _collect_yearly_purchase_stats(self, metadata_cache: Dict, target_year: Optional[str]) -> Dict:
        """연도별 구매 통계 수집"""
        stats_data = {
            'title': '연도별 구매 현황',
            'headers': ['연도', '건수', '총 금액', '주요 품목'],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        yearly_data = defaultdict(lambda: {'count': 0, 'total': 0, 'items': []})

        for filename, metadata in metadata_cache.items():
            if '구매' in filename or '구입' in filename:
                year = metadata.get('year', 'Unknown')
                if target_year and year != target_year:
                    continue

                yearly_data[year]['count'] += 1

                # 금액 처리
                if metadata.get('amount'):
                    amount = self._parse_amount(metadata['amount'])
                    yearly_data[year]['total'] += amount

                # 품목 처리
                if metadata.get('item'):
                    yearly_data[year]['items'].append(metadata['item'])

        # 테이블 데이터 생성
        total_amount = 0
        total_count = 0

        for year in sorted(yearly_data.keys()):
            data = yearly_data[year]
            total_amount += data['total']
            total_count += data['count']

            items_str = ', '.join(data['items'][:2])  # 상위 2개만
            if len(data['items']) > 2:
                items_str += f" 외 {len(data['items'])-2}건"

            stats_data['table_data'].append([
                year,
                f"{data['count']}건",
                f"{data['total']:,}원",
                items_str
            ])

        stats_data['total'] = f"총 {total_count}건, {total_amount:,}원"

        # 분석 추가
        if yearly_data:
            avg_per_year = total_amount / len(yearly_data)
            stats_data['analysis'] = {
                'average_per_year': f"{avg_per_year:,.0f}원",
                'total_years': len(yearly_data),
                'peak_year': max(yearly_data.items(), key=lambda x: x[1]['total'])[0]
            }

        return stats_data

    def _collect_drafter_stats(self, metadata_cache: Dict, target_year: Optional[str]) -> Dict:
        """기안자별 통계 수집"""
        stats_data = {
            'title': '기안자별 문서 현황',
            'headers': ['기안자', '건수', '구매', '수리', '기타'],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        drafter_data = defaultdict(lambda: {'total': 0, 'purchase': 0, 'repair': 0, 'other': 0})

        for filename, metadata in metadata_cache.items():
            if target_year and metadata.get('year') != target_year:
                continue

            drafter = metadata.get('drafter', 'Unknown')
            drafter_data[drafter]['total'] += 1

            if '구매' in filename or '구입' in filename:
                drafter_data[drafter]['purchase'] += 1
            elif '수리' in filename or '보수' in filename:
                drafter_data[drafter]['repair'] += 1
            else:
                drafter_data[drafter]['other'] += 1

        # 테이블 데이터 생성 (건수 기준 정렬)
        sorted_drafters = sorted(drafter_data.items(), key=lambda x: x[1]['total'], reverse=True)

        total_docs = 0
        for drafter, data in sorted_drafters[:10]:  # 상위 10명만
            total_docs += data['total']
            stats_data['table_data'].append([
                drafter,
                f"{data['total']}건",
                f"{data['purchase']}건",
                f"{data['repair']}건",
                f"{data['other']}건"
            ])

        stats_data['total'] = f"총 {len(drafter_data)}명, {total_docs}건"

        # 분석 추가
        if drafter_data:
            top_drafter = sorted_drafters[0][0] if sorted_drafters else 'N/A'
            stats_data['analysis'] = {
                'top_drafter': top_drafter,
                'total_drafters': len(drafter_data),
                'average_per_drafter': f"{total_docs/len(drafter_data):.1f}건"
            }

        return stats_data

    def _collect_monthly_repair_stats(self, metadata_cache: Dict, target_year: Optional[str]) -> Dict:
        """월별 수리 통계 수집"""
        stats_data = {
            'title': '월별 수리 현황',
            'headers': ['월', '건수', '총 비용', '주요 항목'],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        monthly_data = defaultdict(lambda: {'count': 0, 'total': 0, 'items': []})

        for filename, metadata in metadata_cache.items():
            if '수리' not in filename and '보수' not in filename:
                continue

            if target_year and metadata.get('year') != target_year:
                continue

            month = metadata.get('month', 'Unknown')
            monthly_data[month]['count'] += 1

            if metadata.get('amount'):
                amount = self._parse_amount(metadata['amount'])
                monthly_data[month]['total'] += amount

            if metadata.get('item'):
                monthly_data[month]['items'].append(metadata['item'])

        # 테이블 데이터 생성 (월 순서대로)
        total_amount = 0
        total_count = 0

        for month in range(1, 13):
            month_str = f"{month:02d}월"
            if month_str in monthly_data:
                data = monthly_data[month_str]
                total_amount += data['total']
                total_count += data['count']

                items_str = ', '.join(data['items'][:2])
                if len(data['items']) > 2:
                    items_str += f" 외 {len(data['items'])-2}건"

                stats_data['table_data'].append([
                    month_str,
                    f"{data['count']}건",
                    f"{data['total']:,}원",
                    items_str
                ])

        stats_data['total'] = f"총 {total_count}건, {total_amount:,}원"

        # 분석 추가
        if monthly_data:
            peak_month = max(monthly_data.items(), key=lambda x: x[1]['total'])[0]
            stats_data['analysis'] = {
                'peak_month': peak_month,
                'average_per_month': f"{total_amount/len(monthly_data):,.0f}원",
                'total_months': len(monthly_data)
            }

        return stats_data

    def _collect_category_stats(self, metadata_cache: Dict, target_year: Optional[str]) -> Dict:
        """카테고리별 통계 수집"""
        stats_data = {
            'title': '카테고리별 문서 현황',
            'headers': ['카테고리', '건수', '비율', '총 금액'],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        category_data = defaultdict(lambda: {'count': 0, 'total': 0})

        for filename, metadata in metadata_cache.items():
            if target_year and metadata.get('year') != target_year:
                continue

            # 카테고리 결정
            if '구매' in filename or '구입' in filename:
                category = '구매'
            elif '수리' in filename or '보수' in filename:
                category = '수리'
            elif '폐기' in filename:
                category = '폐기'
            elif '검토' in filename:
                category = '검토'
            else:
                category = '기타'

            category_data[category]['count'] += 1

            if metadata.get('amount'):
                amount = self._parse_amount(metadata['amount'])
                category_data[category]['total'] += amount

        # 테이블 데이터 생성
        total_count = sum(data['count'] for data in category_data.values())
        total_amount = sum(data['total'] for data in category_data.values())

        for category in sorted(category_data.keys()):
            data = category_data[category]
            percentage = (data['count'] / total_count * 100) if total_count > 0 else 0

            stats_data['table_data'].append([
                category,
                f"{data['count']}건",
                f"{percentage:.1f}%",
                f"{data['total']:,}원"
            ])

        stats_data['total'] = f"총 {total_count}건, {total_amount:,}원"

        # 분석 추가
        if category_data:
            top_category = max(category_data.items(), key=lambda x: x[1]['count'])[0]
            stats_data['analysis'] = {
                'top_category': top_category,
                'category_count': len(category_data),
                'average_per_category': f"{total_amount/len(category_data):,.0f}원"
            }

        return stats_data

    def _collect_general_stats(self, metadata_cache: Dict, target_year: Optional[str]) -> Dict:
        """전체 일반 통계 수집"""
        stats_data = {
            'title': f"{'전체' if not target_year else target_year + '년'} 문서 통계",
            'headers': ['항목', '값'],
            'table_data': [],
            'total': '',
            'analysis': {},
            'recommendations': []
        }

        total_docs = 0
        total_amount = 0
        categories = Counter()
        drafters = Counter()
        years = Counter()

        for filename, metadata in metadata_cache.items():
            if target_year and metadata.get('year') != target_year:
                continue

            total_docs += 1

            # 금액 합계
            if metadata.get('amount'):
                amount = self._parse_amount(metadata['amount'])
                total_amount += amount

            # 카테고리 카운트
            if '구매' in filename:
                categories['구매'] += 1
            elif '수리' in filename:
                categories['수리'] += 1
            elif '폐기' in filename:
                categories['폐기'] += 1
            else:
                categories['기타'] += 1

            # 기안자 카운트
            if metadata.get('drafter'):
                drafters[metadata['drafter']] += 1

            # 연도 카운트
            if metadata.get('year'):
                years[metadata['year']] += 1

        # 테이블 데이터 생성
        stats_data['table_data'] = [
            ['총 문서 수', f"{total_docs}건"],
            ['총 금액', f"{total_amount:,}원"],
            ['평균 금액', f"{total_amount/total_docs:,.0f}원" if total_docs > 0 else "0원"],
            ['가장 많은 카테고리', f"{categories.most_common(1)[0][0]} ({categories.most_common(1)[0][1]}건)" if categories else "N/A"],
            ['가장 활발한 기안자', f"{drafters.most_common(1)[0][0]} ({drafters.most_common(1)[0][1]}건)" if drafters else "N/A"],
            ['문서 연도 범위', f"{min(years.keys())} ~ {max(years.keys())}" if years else "N/A"]
        ]

        stats_data['total'] = f"총 {total_docs}건 분석 완료"

        # 분석 추가
        stats_data['analysis'] = {
            'total_documents': total_docs,
            'total_amount': total_amount,
            'categories': dict(categories),
            'top_drafters': dict(drafters.most_common(5))
        }

        return stats_data

    def generate_statistics_report(self, query: str, metadata_cache: Dict,
                                  formatter=None) -> str:
        """
        통계 리포트 생성

        Args:
            query: 사용자 쿼리
            metadata_cache: 메타데이터 캐시
            formatter: 응답 포맷터 (선택적)

        Returns:
            포맷된 통계 리포트
        """
        try:
            # 통계 데이터 수집
            stats_data = self.collect_statistics_data(query, metadata_cache)

            # 포맷터가 있으면 사용
            if formatter:
                return formatter.format_statistics_response(stats_data, query)

            # 기본 포맷팅
            return self._format_basic_report(stats_data)

        except Exception as e:
            logger.error(f"통계 리포트 생성 오류: {e}")
            return f"통계 생성 중 오류가 발생했습니다: {str(e)}"

    def _format_basic_report(self, stats_data: Dict) -> str:
        """기본 텍스트 형식 리포트 생성"""
        report = []

        # 제목
        report.append(f"## {stats_data['title']}")
        report.append("")

        # 테이블
        if stats_data['headers'] and stats_data['table_data']:
            # 헤더
            report.append(" | ".join(stats_data['headers']))
            report.append(" | ".join(["---"] * len(stats_data['headers'])))

            # 데이터
            for row in stats_data['table_data']:
                report.append(" | ".join(map(str, row)))

        report.append("")

        # 총계
        if stats_data['total']:
            report.append(f"**{stats_data['total']}**")
            report.append("")

        # 분석
        if stats_data['analysis']:
            report.append("### 분석 결과")
            for key, value in stats_data['analysis'].items():
                if isinstance(value, dict):
                    report.append(f"- {key}:")
                    for sub_key, sub_value in value.items():
                        report.append(f"  - {sub_key}: {sub_value}")
                else:
                    report.append(f"- {key}: {value}")
            report.append("")

        # 추천사항
        if stats_data.get('recommendations'):
            report.append("### 추천사항")
            for rec in stats_data['recommendations']:
                report.append(f"- {rec}")

        return "\n".join(report)

    def _parse_amount(self, amount_str: str) -> int:
        """금액 문자열을 숫자로 파싱"""
        if isinstance(amount_str, (int, float)):
            return int(amount_str)

        # 문자열에서 숫자만 추출
        numbers = re.findall(r'\d+', str(amount_str).replace(',', ''))
        if numbers:
            return int(''.join(numbers))
        return 0

    def analyze_trends(self, metadata_cache: Dict, period: str = 'yearly') -> Dict:
        """
        트렌드 분석

        Args:
            metadata_cache: 메타데이터 캐시
            period: 분석 기간 ('yearly', 'monthly', 'quarterly')

        Returns:
            트렌드 분석 결과
        """
        trends = {
            'period': period,
            'data': defaultdict(lambda: {'count': 0, 'amount': 0}),
            'growth_rate': {},
            'forecast': {}
        }

        for filename, metadata in metadata_cache.items():
            if period == 'yearly':
                key = metadata.get('year', 'Unknown')
            elif period == 'monthly':
                year = metadata.get('year', '')
                month = metadata.get('month', '')
                key = f"{year}-{month}"
            else:  # quarterly
                year = metadata.get('year', '')
                month = metadata.get('month', '01')
                quarter = (int(month.split('월')[0]) - 1) // 3 + 1 if month else 1
                key = f"{year}-Q{quarter}"

            trends['data'][key]['count'] += 1

            if metadata.get('amount'):
                amount = self._parse_amount(metadata['amount'])
                trends['data'][key]['amount'] += amount

        # 성장률 계산
        sorted_periods = sorted(trends['data'].keys())
        for i in range(1, len(sorted_periods)):
            prev_period = sorted_periods[i-1]
            curr_period = sorted_periods[i]

            prev_count = trends['data'][prev_period]['count']
            curr_count = trends['data'][curr_period]['count']

            if prev_count > 0:
                growth_rate = ((curr_count - prev_count) / prev_count) * 100
                trends['growth_rate'][curr_period] = f"{growth_rate:.1f}%"

        return trends

    def get_summary_statistics(self, metadata_cache: Dict) -> Dict:
        """
        요약 통계 반환

        Args:
            metadata_cache: 메타데이터 캐시

        Returns:
            요약 통계
        """
        return {
            'total_documents': len(metadata_cache),
            'unique_drafters': len(set(m.get('drafter', 'Unknown') for m in metadata_cache.values())),
            'date_range': self._get_date_range(metadata_cache),
            'categories': self._count_categories(metadata_cache),
            'top_keywords': self._get_top_keywords(metadata_cache)
        }

    def _get_date_range(self, metadata_cache: Dict) -> str:
        """날짜 범위 반환"""
        years = [m.get('year') for m in metadata_cache.values() if m.get('year')]
        if years:
            return f"{min(years)} ~ {max(years)}"
        return "N/A"

    def _count_categories(self, metadata_cache: Dict) -> Dict:
        """카테고리별 개수 반환"""
        categories = Counter()
        for filename in metadata_cache.keys():
            if '구매' in filename:
                categories['구매'] += 1
            elif '수리' in filename:
                categories['수리'] += 1
            elif '폐기' in filename:
                categories['폐기'] += 1
            else:
                categories['기타'] += 1
        return dict(categories)

    def _get_top_keywords(self, metadata_cache: Dict, top_n: int = 10) -> List[str]:
        """상위 키워드 추출"""
        keywords = Counter()
        for metadata in metadata_cache.values():
            if metadata.get('keywords'):
                for keyword in metadata['keywords'].split(','):
                    keywords[keyword.strip()] += 1

        return [k for k, _ in keywords.most_common(top_n)]