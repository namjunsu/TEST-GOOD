#!/usr/bin/env python3
"""
답변 품질 개선 모듈
더 상세하고 구조화된 답변 생성
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

class AnswerQualityImprover:
    """답변 품질 개선 클래스"""
    
    def format_pdf_summary(self, pdf_info: dict, query: str) -> str:
        """PDF 문서 요약을 더 상세하고 깔끔하게 포맷"""
        
        lines = []
        
        # 제목 및 기본 정보
        title = pdf_info.get('제목', pdf_info.get('filename', '문서'))
        lines.append(f"📄 **{title}**")
        lines.append("="*60)
        
        # 1. 기본 정보 섹션
        lines.append("\n### 📌 기본 정보")
        
        if '기안자' in pdf_info:
            lines.append(f"• **기안자**: {pdf_info['기안자']}")
        if '날짜' in pdf_info:
            lines.append(f"• **날짜**: {pdf_info['날짜']}")
        if '부서' in pdf_info:
            lines.append(f"• **부서**: {pdf_info['부서']}")
        
        # 2. 주요 내용 섹션
        lines.append("\n### 📝 주요 내용")
        
        # 개요 추출
        if '개요' in pdf_info:
            lines.append(f"\n**[1. 개요]**")
            overview = pdf_info['개요']
            # 그룹웨어 텍스트 제거
            overview = re.sub(r'gw\.channela[^\s]+', '', overview)
            lines.append(overview)
        elif '전체텍스트' in pdf_info:
            # 텍스트에서 개요 추출
            text = pdf_info['전체텍스트']
            if '개요' in text or '목적' in text:
                # 개요 부분 추출
                overview = self._extract_overview(text)
                if overview:
                    lines.append(f"\n**[개요]**")
                    lines.append(overview)
        
        # 내용 추출 (기안서인 경우)
        if '내용' in pdf_info:
            lines.append(f"\n**[2. 내용]**")
            content = pdf_info['내용']
            
            # 용도 추출
            if '용도' in content:
                용도_match = re.search(r'용도[:\s]*(.+?)(?:[-•]|$)', content, re.DOTALL)
                if 용도_match:
                    용도_text = 용도_match.group(1).strip()
                    용도_text = re.sub(r'\s+', ' ', 용도_text)[:1000]  # 300 -> 1000
                    lines.append(f"• **용도**: {용도_text}")
            
            # 주요 기능 추출
            if '주요 기능' in content:
                기능_match = re.search(r'주요 기능[:\s]*(.+?)(?:[-•]|운용|$)', content, re.DOTALL)
                if 기능_match:
                    기능_text = 기능_match.group(1).strip()
                    기능_text = re.sub(r'\s+', ' ', 기능_text)[:1000]  # 300 -> 1000
                    lines.append(f"• **주요 기능**: {기능_text}")
            
            # 둘 다 없으면 전체 내용 요약
            if '용도' not in content and '주요 기능' not in content and len(content) > 50:
                # 내용 정리
                content_clean = re.sub(r'\s+', ' ', content)
                lines.append(content_clean[:500] + "...")
        
        # 3. 세부 항목 (있는 경우)
        if '세부항목' in pdf_info and pdf_info['세부항목']:
            lines.append("\n### 🔍 세부 내역")
            
            # 항목별로 정리
            for item in pdf_info['세부항목'][:5]:  # 상위 5개만
                if isinstance(item, dict):
                    item_name = item.get('항목', item.get('name', ''))
                    item_value = item.get('내용', item.get('value', ''))
                    if item_name and item_value:
                        lines.append(f"• **{item_name}**: {item_value}")
        
        # 4. 기술 사양 (장비 관련인 경우)
        if any(word in query for word in ['사양', '스펙', '성능']):
            specs = self._extract_specifications(pdf_info)
            if specs:
                lines.append("\n### ⚙️ 기술 사양")
                for spec in specs:
                    lines.append(f"• {spec}")
        
        # 5. 비용 정보
        if '금액' in pdf_info or '비용내역' in pdf_info:
            lines.append("\n### 💰 비용 정보")
            
            if '비용내역' in pdf_info:
                for key, value in pdf_info['비용내역'].items():
                    lines.append(f"• **{key}**: {value}")
            elif '금액' in pdf_info:
                lines.append(f"• **총액**: {pdf_info['금액']}")
        
        # 6. 검토 의견이나 결론 (개선)
        if '검토의견' in pdf_info:
            lines.append("\n### 📋 검토 의견")
            opinion = pdf_info['검토의견']
            # 불필요한 텍스트 정리
            opinion = re.sub(r'gw\.channela.*?\.php.*?\d+/\d+', '', opinion)  # URL 제거
            opinion = re.sub(r'장비구매.*?기안서', '', opinion)  # 헤더 제거
            opinion = re.sub(r'\[페이지 \d+\]', '', opinion)  # 페이지 번호 제거
            opinion = re.sub(r'\d+\.\s*\d+\.\s*\d+\.\s*오[전후]\s*\d+:\d+', '', opinion)  # 날짜/시간 제거
            opinion = re.sub(r'\d+\.\s*별\s*$', '', opinion)  # 끝의 번호 제거
            opinion = re.sub(r'\s+', ' ', opinion).strip()  # 공백 정리
            
            if len(opinion) > 2000:  # 500 -> 2000자로 증가
                opinion = opinion[:2000] + "..."
            lines.append(opinion)
        elif '전체텍스트' in pdf_info:
            # 검토 의견이 없으면 전체 텍스트에서 찾기
            text = pdf_info['전체텍스트']
            review_match = re.search(r'검토\s*의견(.{50,2000})', text, re.IGNORECASE | re.DOTALL)  # 500 -> 2000
            if review_match:
                lines.append("\n### 📋 검토 의견")
                opinion = review_match.group(1).strip()
                opinion = re.sub(r'gw\.channela.*?\.php.*?\d+/\d+', '', opinion)
                opinion = re.sub(r'\[페이지 \d+\]', '', opinion)
                opinion = re.sub(r'\s+', ' ', opinion).strip()
                if len(opinion) > 2000:  # 500 -> 2000
                    opinion = opinion[:2000] + "..."
                lines.append(opinion)
        
        # 7. 추가 정보
        if '업체' in pdf_info:
            lines.append(f"\n• **납품업체**: {pdf_info['업체']}")
        
        # 출처
        lines.append(f"\n---")
        lines.append(f"📎 출처: {pdf_info.get('source', 'PDF 문서')}")
        
        return '\n'.join(lines)
    
    def format_asset_data(self, asset_data: List[Dict], query: str) -> str:
        """자산 데이터를 더 깔끔하게 포맷"""
        
        lines = []
        
        # 모델명 추출
        model_name = self._extract_model_from_query(query)
        if model_name:
            lines.append(f"📊 **{model_name} 장비 현황**")
        else:
            lines.append(f"📊 **장비 현황**")
        lines.append("="*60)
        
        # 전체 수량
        total_count = len(asset_data)
        lines.append(f"\n### 📈 전체 보유 수량: **{total_count}개**")
        
        # 제조사별 분류
        by_manufacturer = {}
        for item in asset_data:
            manufacturer = item.get('제조사', 'Unknown')
            if manufacturer not in by_manufacturer:
                by_manufacturer[manufacturer] = []
            by_manufacturer[manufacturer].append(item)
        
        if len(by_manufacturer) > 1:
            lines.append("\n### 🏭 제조사별 분포")
            for mfr, items in sorted(by_manufacturer.items()):
                lines.append(f"• **{mfr}**: {len(items)}개")
        
        # 위치별 분포
        by_location = {}
        for item in asset_data:
            location = item.get('위치', item.get('설치위치', 'Unknown'))
            if location and location != 'Unknown':
                if location not in by_location:
                    by_location[location] = 0
                by_location[location] += 1
        
        if by_location:
            lines.append("\n### 📍 설치 위치별 분포")
            for loc, count in sorted(by_location.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"• **{loc}**: {count}개")
        
        # 상세 목록 (처음 10개)
        lines.append("\n### 📋 상세 목록 (일부)")
        lines.append("```")
        
        for i, item in enumerate(asset_data[:10], 1):
            # 각 항목을 더 읽기 쉽게 포맷
            serial = item.get('시리얼', item.get('S/N', ''))
            location = item.get('위치', item.get('설치위치', ''))
            manager = item.get('담당자', '')
            purchase_date = item.get('구입일', '')
            
            line_parts = [f"[{i:02d}]"]
            
            if serial:
                line_parts.append(f"S/N: {serial}")
            if location:
                line_parts.append(f"위치: {location}")
            if manager:
                line_parts.append(f"담당: {manager}")
            if purchase_date:
                line_parts.append(f"구입: {purchase_date}")
            
            lines.append(" | ".join(line_parts))
        
        lines.append("```")
        
        if total_count > 10:
            lines.append(f"\n... 외 {total_count - 10}개 더 있음")
        
        # 추가 통계 정보
        lines.append("\n### 📊 추가 정보")
        
        # 구입연도 분포
        years = {}
        for item in asset_data:
            purchase = item.get('구입일', '')
            if purchase and len(purchase) >= 4:
                year = purchase[:4]
                if year.isdigit():
                    if year not in years:
                        years[year] = 0
                    years[year] += 1
        
        if years:
            lines.append("\n**구입연도별 분포:**")
            for year, count in sorted(years.items(), reverse=True)[:3]:
                lines.append(f"• {year}년: {count}개")
        
        # 출처
        lines.append(f"\n---")
        lines.append(f"📎 출처: 채널A 방송장비 자산 데이터베이스")
        
        return '\n'.join(lines)
    
    def _extract_overview(self, text: str) -> Optional[str]:
        """텍스트에서 개요 추출 - 개선된 버전"""
        
        # 개요 시작 패턴 찾기
        overview_patterns = [
            (r'개요[\s:\n]+', r'(?:검토|결론|세부|항목|비용|납품|기타)'),
            (r'목적[\s:\n]+', r'(?:검토|결론|세부|항목|비용|납품|기타)'),
            (r'배경[\s:\n]+', r'(?:검토|결론|세부|항목|비용|납품|기타)'),
            (r'내용[\s:\n]+', r'(?:검토|결론|세부|항목|비용|납품|기타)')
        ]
        
        for start_pattern, end_pattern in overview_patterns:
            match = re.search(start_pattern, text, re.IGNORECASE)
            if match:
                start_idx = match.end()
                # 다음 섹션까지의 텍스트 추출
                end_match = re.search(end_pattern, text[start_idx:], re.IGNORECASE)
                if end_match:
                    overview = text[start_idx:start_idx + end_match.start()].strip()
                else:
                    # 다음 섹션이 없으면 500자까지
                    overview = text[start_idx:start_idx + 1500].strip()  # 500 -> 1500
                
                # 정리
                overview = re.sub(r'\n+', ' ', overview)  # 줄바꿈을 공백으로
                overview = re.sub(r'\s+', ' ', overview)  # 연속 공백 제거
                
                if len(overview) > 1500:  # 500 -> 1500
                    overview = overview[:1500] + "..."
                    
                if len(overview) > 50:  # 최소 50자 이상
                    return overview
        
        # 패턴 매칭 실패시 첫 의미있는 문단 추출
        lines = text.split('\n')
        content_lines = []
        
        for line in lines[:30]:  # 처음 30줄 확인
            line = line.strip()
            # 의미있는 내용인지 확인
            if (len(line) > 30 and 
                not line.startswith('[') and 
                not line.startswith('페이지') and
                not re.match(r'^\d+[\.)]', line) and
                not '━' in line and
                not '=' in line):
                content_lines.append(line)
                
                # 충분한 내용이 모이면 반환
                if len(' '.join(content_lines)) > 200:
                    overview = ' '.join(content_lines)
                    if len(overview) > 500:
                        overview = overview[:500] + "..."
                    return overview
        
        # 내용이 부족하면 전체 합치기
        if content_lines:
            overview = ' '.join(content_lines)
            if len(overview) > 500:
                overview = overview[:500] + "..."
            return overview
        
        return None
    
    def _extract_specifications(self, pdf_info: dict) -> List[str]:
        """기술 사양 추출"""
        specs = []
        
        text = pdf_info.get('전체텍스트', '')
        
        # 사양 관련 패턴
        spec_patterns = [
            r'해상도[:\s]+([^\n,]+)',
            r'크기[:\s]+([^\n,]+)',
            r'무게[:\s]+([^\n,]+)',
            r'전원[:\s]+([^\n,]+)',
            r'소비전력[:\s]+([^\n,]+)',
            r'입력[:\s]+([^\n,]+)',
            r'출력[:\s]+([^\n,]+)'
        ]
        
        for pattern in spec_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                spec_name = pattern.split('[')[0]
                spec_value = match.group(1).strip()
                specs.append(f"**{spec_name}**: {spec_value}")
        
        return specs[:5]  # 최대 5개
    
    def _extract_model_from_query(self, query: str) -> Optional[str]:
        """질문에서 모델명 추출"""
        # 모델 패턴
        model_pattern = r'([A-Z]{2,}[-\s]?[A-Z0-9]+\d+)'
        match = re.search(model_pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None

# 테스트
if __name__ == "__main__":
    improver = AnswerQualityImprover()
    
    # 테스트 데이터
    test_pdf_info = {
        '제목': '미러클랩 카메라 삼각대 기술검토서',
        '기안자': '남준수',
        '날짜': '2025-07-17',
        '부서': '기술관리팀-보도기술관리파트',
        '개요': '미러클랩 기자 교육용으로 운영 중인 Miller DS20 삼각대의 다리 고정 잠금장치가 파손되어 대체 삼각대 구매를 위한 기술 검토서',
        '금액': '2,370,000원',
        '업체': 'Miller'
    }
    
    # PDF 요약 테스트
    print("="*80)
    print("📄 PDF 요약 개선 테스트")
    print("="*80)
    result = improver.format_pdf_summary(test_pdf_info, "미러클랩 카메라 삼각대 기술검토서 내용")
    print(result)
    
    # 자산 데이터 테스트
    test_asset_data = [
        {'모델': 'XDS-PD1000', '제조사': 'SONY', 'S/N': '12092', '위치': '뉴스부조', '구입일': '2011-10-19'},
        {'모델': 'XDS-PD1000', '제조사': 'SONY', 'S/N': '12097', '위치': '광화문', '구입일': '2011-10-19'},
        {'모델': 'XDS-PD1000', '제조사': 'SONY', 'S/N': '12094', '위치': '대형스튜디오', '구입일': '2011-10-19'},
        {'모델': 'XDS-PD1000', '제조사': 'SONY', 'S/N': '12095', '위치': '대형스튜디오', '구입일': '2011-10-19'},
    ]
    
    print("\n" + "="*80)
    print("📊 자산 데이터 개선 테스트")
    print("="*80)
    result = improver.format_asset_data(test_asset_data, "XDS-PD1000 장비 현황")
    print(result)