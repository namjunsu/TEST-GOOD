"""
응답 포맷터 - 구조화된 답변 생성
"""

import re
from typing import Dict, List, Any, Optional
from datetime import datetime

class ResponseFormatter:
    """구조화된 답변 포맷 생성"""
    
    def __init__(self):
        self.divider = "━" * 50
        self.table_styles = {
            'simple': {'top': '─', 'mid': '─', 'bot': '─', 'left': '│', 'right': '│'},
            'double': {'top': '═', 'mid': '─', 'bot': '═', 'left': '║', 'right': '║'},
        }
    
    def format_document_summary(self, doc_info: Dict[str, Any], 
                               query: str = "") -> str:
        """문서 요약을 구조화된 형식으로 포맷"""
        output = []
        
        # 헤더
        output.append(self.divider)
        title = doc_info.get('제목', '문서 요약')
        output.append(f"📋 {title}")
        output.append("")
        
        # 3줄 핵심 요약
        if doc_info.get('핵심요약'):
            output.append("📌 **핵심 요약 (3줄)**")
            for line in doc_info['핵심요약'][:3]:
                output.append(f"• {line}")
            output.append("")
        
        # 기본 정보 섹션
        if any(k in doc_info for k in ['기안자', '기안일자', '기안부서']):
            output.append("📝 **기본 정보**")
            if doc_info.get('기안자'):
                output.append(f"• 기안자: {doc_info['기안자']}")
            if doc_info.get('기안일자'):
                output.append(f"• 기안일자: {doc_info['기안일자']}")
            if doc_info.get('기안부서'):
                output.append(f"• 기안부서: {doc_info['기안부서']}")
            output.append("")
        
        # 주요 내용 - 표 형식
        if doc_info.get('상세내용'):
            output.append("🔧 **주요 내용**")
            output.append(self._create_simple_table(doc_info['상세내용']))
            output.append("")
        
        # 비용 정보
        if doc_info.get('비용정보'):
            output.append("💰 **비용 정보**")
            for item, cost in doc_info['비용정보'].items():
                output.append(f"• {item}: {cost}")
            output.append("")
        
        # 검토 의견
        if doc_info.get('검토의견'):
            output.append("💡 **검토 의견**")
            for opinion in doc_info['검토의견']:
                output.append(f"• {opinion}")
            output.append("")
        
        # 관련 정보
        if doc_info.get('관련정보'):
            output.append("📎 **관련 정보**")
            for info in doc_info['관련정보']:
                output.append(f"• {info}")
        
        output.append(self.divider)
        
        return "\n".join(output)
    
    def format_statistics_response(self, stats_data: Dict[str, Any], 
                                  query_type: str) -> str:
        """통계 데이터를 구조화된 형식으로 포맷"""
        output = []
        
        output.append(self.divider)
        output.append(f"📊 {stats_data.get('title', '통계 분석 결과')}")
        output.append("")
        
        # 총계 정보
        if stats_data.get('총계'):
            output.append(f"💰 **총 {stats_data.get('항목', '금액')}**: {stats_data['총계']}")
            output.append("")
        
        # 메인 테이블
        if stats_data.get('table_data'):
            output.append(self._create_detailed_table(
                headers=stats_data.get('headers', []),
                rows=stats_data.get('table_data', [])
            ))
            output.append("")
        
        # 추가 분석
        if stats_data.get('분석'):
            output.append("📈 **분석 결과**")
            for key, value in stats_data['분석'].items():
                output.append(f"• {key}: {value}")
            output.append("")
        
        # 추천 사항
        if stats_data.get('추천'):
            output.append("🎯 **추천 사항**")
            for rec in stats_data['추천']:
                output.append(f"• {rec}")
        
        output.append(self.divider)
        
        return "\n".join(output)
    
    def format_asset_search_response(self, assets: List[Dict], 
                                    search_criteria: Dict) -> str:
        """자산 검색 결과를 구조화된 형식으로 포맷"""
        output = []
        
        output.append(self.divider)
        
        # 검색 조건 표시
        criteria_str = self._format_search_criteria(search_criteria)
        output.append(f"📍 {criteria_str}")
        output.append("")
        
        # 요약 통계
        if assets:
            total_count = len(assets)
            total_value = sum(self._parse_amount(a.get('취득가액', 0)) for a in assets)
            
            output.append(f"📊 **총 장비**: {total_count:,}대 | **총 자산가치**: {total_value:,}원")
            output.append("")
            
            # 카테고리별 분류
            categories = self._categorize_assets(assets)
            
            for category, items in categories.items():
                if items:
                    output.append(f"**{category}** ({len(items)}대)")
                    
                    # 상위 5개만 표시
                    table_data = []
                    for item in items[:5]:
                        table_data.append([
                            item.get('품목', ''),
                            item.get('모델', ''),
                            item.get('구입일자', ''),
                            item.get('상태', '정상')
                        ])
                    
                    if table_data:
                        headers = ['품목', '모델', '구입년도', '상태']
                        output.append(self._create_detailed_table(headers, table_data))
                        
                        if len(items) > 5:
                            output.append(f"  ... 외 {len(items)-5}개")
                    output.append("")
            
            # 점검 필요 장비
            need_check = [a for a in assets if '점검' in str(a.get('비고', ''))]
            if need_check:
                output.append("⚠️ **점검 필요 장비**")
                for item in need_check[:3]:
                    output.append(f"• {item.get('품목', '')}: {item.get('비고', '')}")
                output.append("")
        else:
            output.append("❌ 검색 결과가 없습니다.")
        
        output.append(self.divider)
        
        return "\n".join(output)
    
    def format_comparison_response(self, comparison_data: Dict) -> str:
        """비교 분석 결과를 구조화된 형식으로 포맷"""
        output = []
        
        output.append(self.divider)
        output.append(f"📊 {comparison_data.get('title', '비교 분석')}")
        output.append("")
        
        # 비용 비교 테이블
        if comparison_data.get('cost_comparison'):
            output.append("💰 **비용 비교**")
            headers = ['구분', '평균 비용', '횟수', '총 비용']
            rows = comparison_data['cost_comparison']
            output.append(self._create_detailed_table(headers, rows))
            output.append("")
        
        # 경제성 분석
        if comparison_data.get('analysis'):
            output.append("📈 **경제성 분석**")
            for point in comparison_data['analysis']:
                output.append(f"• {point}")
            output.append("")
        
        # 이력 데이터
        if comparison_data.get('history'):
            output.append("🔧 **관련 이력**")
            for item in comparison_data['history']:
                output.append(f"• {item}")
            output.append("")
        
        # 추천
        if comparison_data.get('recommendation'):
            output.append("💡 **추천**")
            output.append(comparison_data['recommendation'])
        
        output.append(self.divider)
        
        return "\n".join(output)
    
    def _create_simple_table(self, data: List[Dict]) -> str:
        """간단한 표 생성"""
        if not data:
            return ""
        
        lines = []
        lines.append("```")
        
        # 헤더
        if isinstance(data[0], dict):
            headers = list(data[0].keys())
            header_line = " | ".join(headers)
            lines.append(header_line)
            lines.append("-" * len(header_line))
            
            # 데이터 행
            for row in data:
                row_line = " | ".join(str(row.get(h, '')) for h in headers)
                lines.append(row_line)
        else:
            for item in data:
                lines.append(str(item))
        
        lines.append("```")
        return "\n".join(lines)
    
    def _create_detailed_table(self, headers: List[str], 
                              rows: List[List]) -> str:
        """상세 표 생성 (박스 그리기)"""
        if not headers or not rows:
            return ""
        
        # 각 컬럼의 최대 너비 계산
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(header)
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(max_width + 2)  # 패딩 추가
        
        lines = []
        
        # 상단 테두리
        top_line = "┌" + "┬".join("─" * w for w in col_widths) + "┐"
        lines.append(top_line)
        
        # 헤더
        header_cells = []
        for i, header in enumerate(headers):
            header_cells.append(header.center(col_widths[i]))
        header_line = "│" + "│".join(header_cells) + "│"
        lines.append(header_line)
        
        # 헤더 구분선
        mid_line = "├" + "┼".join("─" * w for w in col_widths) + "┤"
        lines.append(mid_line)
        
        # 데이터 행
        for row in rows:
            row_cells = []
            for i in range(len(headers)):
                if i < len(row):
                    cell = str(row[i])[:col_widths[i]-2]  # 너무 긴 텍스트 자르기
                    row_cells.append(" " + cell.ljust(col_widths[i]-1))
                else:
                    row_cells.append(" " * col_widths[i])
            row_line = "│" + "│".join(row_cells) + "│"
            lines.append(row_line)
        
        # 하단 테두리
        bottom_line = "└" + "┴".join("─" * w for w in col_widths) + "┘"
        lines.append(bottom_line)
        
        return "\n".join(lines)
    
    def _format_search_criteria(self, criteria: Dict) -> str:
        """검색 조건을 문자열로 포맷"""
        parts = []
        
        if criteria.get('location'):
            parts.append(f"{criteria['location']} 장비 현황")
        elif criteria.get('manager'):
            parts.append(f"{criteria['manager']} 관리 장비")
        elif criteria.get('year'):
            parts.append(f"{criteria['year']}년 장비")
        else:
            parts.append("장비 검색 결과")
        
        return " ".join(parts)
    
    def _categorize_assets(self, assets: List[Dict]) -> Dict[str, List]:
        """자산을 카테고리별로 분류"""
        categories = {
            '🎥 카메라 시스템': [],
            '🎙️ 오디오 시스템': [],
            '💡 조명 시스템': [],
            '📺 모니터/디스플레이': [],
            '🔌 기타 장비': []
        }
        
        for asset in assets:
            item = asset.get('품목', '').lower()
            
            if any(k in item for k in ['카메라', 'ccu', '렌즈', 'eng']):
                categories['🎥 카메라 시스템'].append(asset)
            elif any(k in item for k in ['마이크', '오디오', '믹서', '인터컴']):
                categories['🎙️ 오디오 시스템'].append(asset)
            elif any(k in item for k in ['조명', 'led', '라이트']):
                categories['💡 조명 시스템'].append(asset)
            elif any(k in item for k in ['모니터', '디스플레이', 'tv']):
                categories['📺 모니터/디스플레이'].append(asset)
            else:
                categories['🔌 기타 장비'].append(asset)
        
        # 빈 카테고리 제거
        return {k: v for k, v in categories.items() if v}
    
    def _parse_amount(self, amount_str) -> int:
        """금액 문자열을 숫자로 변환"""
        if isinstance(amount_str, (int, float)):
            return int(amount_str)
        
        if not amount_str:
            return 0
        
        # 문자열에서 숫자만 추출
        amount_str = str(amount_str)
        amount_str = re.sub(r'[^0-9]', '', amount_str)
        
        try:
            return int(amount_str)
        except:
            return 0
    
    def extract_key_points(self, text: str, max_points: int = 3) -> List[str]:
        """텍스트에서 핵심 포인트 추출"""
        points = []
        
        # 문장 분리
        sentences = re.split(r'[.!?]\s+', text)
        
        # 중요 키워드가 포함된 문장 우선
        important_keywords = ['필요', '권장', '추천', '중요', '핵심', '결론', '총', '합계']
        
        for sentence in sentences:
            if any(keyword in sentence for keyword in important_keywords):
                if len(sentence) > 10 and len(sentence) < 100:
                    points.append(sentence.strip())
                    if len(points) >= max_points:
                        break
        
        # 부족하면 처음 문장들 추가
        if len(points) < max_points:
            for sentence in sentences:
                if len(sentence) > 10 and len(sentence) < 100:
                    if sentence.strip() not in points:
                        points.append(sentence.strip())
                        if len(points) >= max_points:
                            break
        
        return points[:max_points]