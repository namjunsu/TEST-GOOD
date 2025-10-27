#!/usr/bin/env python3
"""
고급 메타데이터 추출기 - PDF에서 구조화된 정보 추출
"""

from app.core.logging import get_logger
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path

logger = get_logger(__name__)


class MetadataExtractor:
    """PDF 메타데이터 추출기"""

    def __init__(self):
        # 확장된 패턴 정의
        self.patterns = {
            # 날짜 패턴 (우선순위 순)
            'dates': [
                # 표준 형식
                (r'(\d{4})[년\-\.\/](\d{1,2})[월\-\.\/](\d{1,2})', 'ymd'),
                (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', 'ymd'),
                (r'(\d{4})-(\d{2})-(\d{2})', 'ymd'),

                # 한국어 형식
                (r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', 'ymd'),
                (r'(\d{2,4})년도?\s*(\d{1,2})월', 'ym'),

                # 역순 형식
                (r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', 'dmy'),

                # 연도만
                (r'(20\d{2}|19\d{2})년도?', 'y'),
            ],

            # 금액 패턴 (더 정확한 매칭)
            'amounts': [
                # 정확한 금액 표시
                (r'총[\s]*금액[\s]*:?[\s]*([0-9,]+)[\s]*원', 'total'),
                (r'합계[\s]*:?[\s]*([0-9,]+)[\s]*원', 'total'),
                (r'계약금액[\s]*:?[\s]*([0-9,]+)[\s]*원', 'contract'),
                (r'결제금액[\s]*:?[\s]*([0-9,]+)[\s]*원', 'payment'),

                # 일반 금액
                (r'([0-9]{1,3}(?:,[0-9]{3})+)[\s]*원', 'general'),
                (r'￦[\s]*([0-9,]+)', 'general'),
                (r'KRW[\s]*([0-9,]+)', 'general'),

                # 부가세 포함
                (r'부가세포함[\s]*([0-9,]+)', 'vat_included'),
                (r'VAT포함[\s]*([0-9,]+)', 'vat_included'),
            ],

            # 부서/조직
            'departments': [
                # 방송국 부서
                (r'(카메라|조명|음향|영상|스튜디오|중계|편집|송출)[\s]*(부|팀|실)?', 'tech'),
                (r'(제작[1-9]|보도|교양|예능|드라마|스포츠|시사)[\s]*(부|국|팀)?', 'prod'),
                (r'(기술|제작|경영|편성|심의|홍보)[\s]*(본부|국|센터)', 'div'),

                # 일반 부서
                (r'부서[\s]*:[\s]*([가-힣]+(?:부|팀|실|과))', 'general'),
                (r'소속[\s]*:[\s]*([가-힣]+)', 'general'),
                (r'담당[\s]*:[\s]*([가-힣]+)', 'general'),
            ],

            # 문서 유형 (세분화)
            'doc_types': {
                '구매': {
                    'keywords': ['구매', '구입', '발주', '조달', '입찰', '계약서', '견적'],
                    'priority': 1
                },
                '수리': {
                    'keywords': ['수리', '정비', 'A/S', '고장', '수선', '보수', '유지보수'],
                    'priority': 2
                },
                '임대': {
                    'keywords': ['임대', '임차', '렌탈', '대여', '리스'],
                    'priority': 3
                },
                '신청': {
                    'keywords': ['신청서', '요청서', '의뢰서', '신청', '요청'],
                    'priority': 4
                },
                '보고': {
                    'keywords': ['보고서', '보고', '결과', '분석', '현황', '실적'],
                    'priority': 5
                },
                '회의': {
                    'keywords': ['회의록', '회의', '미팅', '협의', '논의'],
                    'priority': 6
                },
                '검수': {
                    'keywords': ['검수', '검사', '시험', '테스트', '점검'],
                    'priority': 7
                }
            },

            # 기안자 (문서 작성자)
            'drafter': [
                (r'기안자[\s]*:?[\s]*([가-힣]{2,4})', 'drafter'),
                (r'작성자[\s]*:?[\s]*([가-힣]{2,4})', 'drafter'),
                (r'기안[\s]*:?[\s]*([가-힣]{2,4})', 'drafter'),
            ],

            # 담당자/연락처
            'contacts': [
                (r'담당자?[\s]*:?[\s]*([가-힣]{2,4})', 'name'),
                (r'연락처[\s]*:?[\s]*([\d\-]+)', 'phone'),
                (r'전화[\s]*:?[\s]*([\d\-]+)', 'phone'),
                (r'(010|011|016|017|018|019)[\-\s]?\d{3,4}[\-\s]?\d{4}', 'mobile'),
                (r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', 'email'),
            ],

            # 제품/장비 정보
            'equipment': [
                (r'(모델|Model)[\s]*:?[\s]*([A-Z0-9\-]+)', 'model'),
                (r'(시리얼|Serial|S/N)[\s]*:?[\s]*([A-Z0-9\-]+)', 'serial'),
                (r'(제조사|Manufacturer)[\s]*:?[\s]*([가-힣A-Za-z]+)', 'maker'),

                # 특정 장비명
                (r'(카메라|렌즈|조명|마이크|믹서|스위처|모니터|삼각대)', 'equipment'),
                (r'(DVR|NVR|VTR|CCU|서버|스토리지)', 'equipment'),
            ],

            # 프로젝트/프로그램
            'projects': [
                (r'프로그램[\s]*:[\s]*([가-힣\s]+)', 'program'),
                (r'방송[\s]*프로그램[\s]*:[\s]*([가-힣\s]+)', 'program'),
                (r'프로젝트[\s]*:[\s]*([가-힣A-Za-z0-9\s]+)', 'project'),
                (r'《([^》]+)》', 'program'),  # 프로그램명 괄호
                (r'【([^】]+)】', 'program'),
            ],

            # 계약/결재 정보
            'approval': [
                (r'결재일[\s]*:?[\s]*(\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2})', 'approval_date'),
                (r'계약번호[\s]*:?[\s]*([A-Z0-9\-]+)', 'contract_no'),
                (r'문서번호[\s]*:?[\s]*([A-Z0-9\-]+)', 'doc_no'),
                (r'품의번호[\s]*:?[\s]*([A-Z0-9\-]+)', 'request_no'),
            ]
        }

        # 회사/업체 리스트 (자주 나오는 업체)
        self.known_companies = [
            '삼성', 'LG', '소니', 'Sony', '파나소닉', 'Panasonic',
            '캐논', 'Canon', '니콘', 'Nikon', '후지', 'Fuji',
            'ARRI', 'RED', 'Blackmagic', 'DJI', 'Atomos',
            '한국방송', 'KBS', 'MBC', 'SBS', 'EBS', 'JTBC'
        ]

    def extract_all(self, text: str, filename: str = "") -> Dict[str, Any]:
        """
        모든 메타데이터 추출

        Args:
            text: PDF 텍스트
            filename: 파일명 (추가 정보 추출용)

        Returns:
            추출된 메타데이터 딕셔너리
        """
        # 텍스트 정규화
        text = self._normalize_text(text)
        combined_text = text + " " + filename

        metadata = {
            'dates': self._extract_dates(combined_text),
            'amounts': self._extract_amounts(text),
            'department': self._extract_department(combined_text),
            'doc_type': self._extract_doc_type(combined_text),
            'drafter': self._extract_drafter(text),
            'contacts': self._extract_contacts(text),
            'equipment': self._extract_equipment(text),
            'projects': self._extract_projects(text),
            'approval': self._extract_approval(text),
            'companies': self._extract_companies(text),

            # 요약 정보
            'summary': {}
        }

        # 요약 정보 생성
        metadata['summary'] = self._create_summary(metadata)

        return metadata

    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화"""
        # 불필요한 공백 정리
        text = re.sub(r'\s+', ' ', text)
        # 특수문자 정규화
        text = text.replace('．', '.')
        text = text.replace('，', ',')
        text = text.replace('：', ':')
        return text

    def _extract_dates(self, text: str) -> Dict[str, Any]:
        """날짜 정보 추출"""
        dates = {
            'main_date': None,
            'year': None,
            'all_dates': []
        }

        for pattern, date_type in self.patterns['dates']:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    if date_type == 'ymd':
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                        date_str = f"{year:04d}-{month:02d}-{day:02d}"

                    elif date_type == 'ym':
                        year = int(match.group(1))
                        month = int(match.group(2))
                        date_str = f"{year:04d}-{month:02d}"

                    elif date_type == 'y':
                        year = int(match.group(1))
                        date_str = f"{year:04d}"

                    elif date_type == 'dmy':
                        day = int(match.group(1))
                        month = int(match.group(2))
                        year = int(match.group(3))
                        date_str = f"{year:04d}-{month:02d}-{day:02d}"

                    else:
                        continue

                    # 연도 범위 체크 (1990-2030)
                    if year < 100:
                        year = 2000 + year if year < 30 else 1900 + year

                    if 1990 <= year <= 2030:
                        dates['all_dates'].append({
                            'date': date_str,
                            'year': year,
                            'type': date_type,
                            'position': match.start()
                        })

                        if not dates['year']:
                            dates['year'] = year

                        if not dates['main_date'] and date_type in ['ymd', 'dmy']:
                            dates['main_date'] = date_str

                except (ValueError, IndexError):
                    continue

        # 날짜 정렬 (최신 날짜 우선)
        if dates['all_dates']:
            dates['all_dates'].sort(key=lambda x: x['date'], reverse=True)

        return dates

    def _extract_amounts(self, text: str) -> Dict[str, Any]:
        """금액 정보 추출"""
        amounts = {
            'total': None,
            'contract': None,
            'all_amounts': []
        }

        for pattern, amount_type in self.patterns['amounts']:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    amount_str = match.group(1).replace(',', '')
                    amount = int(amount_str)

                    if amount > 0:  # 0원 제외
                        amounts['all_amounts'].append({
                            'amount': amount,
                            'type': amount_type,
                            'formatted': f"{amount:,}원",
                            'position': match.start()
                        })

                        # 특정 유형 금액 저장
                        if amount_type == 'total' and not amounts['total']:
                            amounts['total'] = amount
                        elif amount_type == 'contract' and not amounts['contract']:
                            amounts['contract'] = amount

                except (ValueError, IndexError):
                    continue

        # 금액 정렬 (큰 금액 우선)
        if amounts['all_amounts']:
            amounts['all_amounts'].sort(key=lambda x: x['amount'], reverse=True)

            # 총액이 없으면 최대 금액을 총액으로
            if not amounts['total'] and amounts['all_amounts']:
                amounts['total'] = amounts['all_amounts'][0]['amount']

        return amounts

    def _extract_department(self, text: str) -> Optional[str]:
        """부서 정보 추출"""
        for pattern, dept_type in self.patterns['departments']:
            match = re.search(pattern, text)
            if match:
                dept = match.group(1)
                # 부/팀/실 등이 없으면 추가
                if dept and not any(suffix in dept for suffix in ['부', '팀', '실', '과', '센터', '본부']):
                    if dept_type == 'tech':
                        dept += '부'
                return dept
        return None

    def _extract_doc_type(self, text: str) -> Optional[str]:
        """문서 유형 추출"""
        text_lower = text.lower()

        # 우선순위에 따라 검사
        doc_types_sorted = sorted(
            self.patterns['doc_types'].items(),
            key=lambda x: x[1]['priority']
        )

        for doc_type, info in doc_types_sorted:
            for keyword in info['keywords']:
                if keyword in text_lower:
                    return doc_type

        return None

    def _extract_drafter(self, text: str) -> Optional[str]:
        """기안자 정보 추출"""
        for pattern, drafter_type in self.patterns['drafter']:
            match = re.search(pattern, text)
            if match:
                drafter = match.group(1)
                # 2-4자 한글 이름만 허용
                if drafter and 2 <= len(drafter) <= 4:
                    return drafter
        return None

    def _extract_contacts(self, text: str) -> Dict[str, List[str]]:
        """연락처 정보 추출"""
        contacts = {
            'names': [],
            'phones': [],
            'emails': []
        }

        for pattern, contact_type in self.patterns['contacts']:
            matches = re.finditer(pattern, text)
            for match in matches:
                value = match.group(1) if match.lastindex else match.group(0)

                if contact_type == 'name' and value not in contacts['names']:
                    contacts['names'].append(value)
                elif contact_type in ['phone', 'mobile'] and value not in contacts['phones']:
                    contacts['phones'].append(value)
                elif contact_type == 'email' and value not in contacts['emails']:
                    contacts['emails'].append(value.lower())

        return contacts

    def _extract_equipment(self, text: str) -> List[Dict[str, str]]:
        """장비 정보 추출"""
        equipment = []
        found_items = set()

        for pattern, eq_type in self.patterns['equipment']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if match.lastindex and match.lastindex > 1:
                    item = match.group(2)
                else:
                    item = match.group(1) if match.lastindex else match.group(0)

                if item and item not in found_items:
                    equipment.append({
                        'name': item,
                        'type': eq_type
                    })
                    found_items.add(item)

        return equipment

    def _extract_projects(self, text: str) -> List[str]:
        """프로젝트/프로그램 정보 추출"""
        projects = []
        found_projects = set()

        for pattern, proj_type in self.patterns['projects']:
            matches = re.finditer(pattern, text)
            for match in matches:
                project = match.group(1).strip()
                if project and project not in found_projects:
                    projects.append(project)
                    found_projects.add(project)

        return projects

    def _extract_approval(self, text: str) -> Dict[str, str]:
        """결재 정보 추출"""
        approval = {}

        for pattern, approval_type in self.patterns['approval']:
            match = re.search(pattern, text)
            if match:
                approval[approval_type] = match.group(1)

        return approval

    def _extract_companies(self, text: str) -> List[str]:
        """회사/업체명 추출"""
        companies = []

        for company in self.known_companies:
            if company in text:
                companies.append(company)

        # 추가로 "주식회사", "(주)" 패턴 찾기
        company_patterns = [
            r'([가-힣]+)\s*주식회사',
            r'주식회사\s*([가-힣]+)',
            r'\(주\)\s*([가-힣]+)',
            r'([가-힣]+)\s*\(주\)',
        ]

        for pattern in company_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                company = match.group(1)
                if company and company not in companies:
                    companies.append(company)

        return companies

    def _create_summary(self, metadata: Dict) -> Dict:
        """메타데이터 요약 생성"""
        summary = {}

        # 주요 날짜
        if metadata['dates']['main_date']:
            summary['date'] = metadata['dates']['main_date']
        elif metadata['dates']['year']:
            summary['year'] = metadata['dates']['year']

        # 주요 금액
        if metadata['amounts']['total']:
            summary['amount'] = metadata['amounts']['total']

        # 부서
        if metadata['department']:
            summary['department'] = metadata['department']

        # 문서 유형
        if metadata['doc_type']:
            summary['doc_type'] = metadata['doc_type']

        # 기안자
        if metadata['drafter']:
            summary['drafter'] = metadata['drafter']

        # 담당자
        if metadata['contacts']['names']:
            summary['contact'] = metadata['contacts']['names'][0]

        # 장비
        if metadata['equipment']:
            summary['equipment_count'] = len(metadata['equipment'])

        # 회사
        if metadata['companies']:
            summary['main_company'] = metadata['companies'][0]

        return summary


# 테스트 함수
def test_extractor():
    """메타데이터 추출기 테스트"""
    extractor = MetadataExtractor()

    # 테스트 텍스트
    test_text = """
    문서번호: KBS-2024-0312

    카메라부 장비 구매 계약서

    1. 계약일자: 2024년 3월 15일
    2. 계약금액: 총 150,000,000원 (부가세포함)
    3. 납품업체: 주식회사 소니코리아
    4. 담당자: 김철수 (010-1234-5678)
    5. 장비내역:
       - FX9 카메라 시스템 (S/N: FX9-2024-001)
       - 렌즈 세트

    프로그램: 《뉴스9》 스튜디오 개선 프로젝트
    """

    # 메타데이터 추출
    metadata = extractor.extract_all(test_text, "2024_카메라부_구매계약서.pdf")

    # 결과 출력
    print("추출된 메타데이터:")
    print("- 날짜:", metadata['dates']['main_date'])
    print("- 금액:", metadata['amounts']['total'])
    print("- 부서:", metadata['department'])
    print("- 문서유형:", metadata['doc_type'])
    print("- 담당자:", metadata['contacts']['names'])
    print("- 회사:", metadata['companies'])
    print("- 장비:", metadata['equipment'])
    print("- 프로그램:", metadata['projects'])
    print("\n요약:", metadata['summary'])

    return metadata


if __name__ == "__main__":
    test_extractor()