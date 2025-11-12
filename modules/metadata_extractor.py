#!/usr/bin/env python3
"""
고급 메타데이터 추출기 v1.4
- 정규식 사전 컴파일 / 날짜·금액 정밀 추출 / 연락처·장비·회사명 보강
- 통합: amount_parser_v2 (상/하한 가드, 라인아이템 우선)
"""

from app.core.logging import get_logger
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# 강화된 금액 파서 임포트
from modules.amount_parser_v2 import (
    select_document_amount,
    validate_amount,
    extract_amount_candidates
)

logger = get_logger(__name__)

_KR_MOBILE = re.compile(r'(01[016789])[-\s\.]?\d{3,4}[-\s\.]?\d{4}')
_EMAIL = re.compile(r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})')

def _norm_space(s: str) -> str:
    s = s.replace('\u3000', ' ')
    s = re.sub(r'\s+', ' ', s)
    s = s.replace('．', '.').replace('，', ',').replace('：', ':').strip()
    return s

def _to_kr_mobile(s: str) -> str:
    # 01012345678 → 010-1234-5678
    d = re.sub(r'\D', '', s)
    if len(d) == 11 and d.startswith('01'):
        return f'{d[:3]}-{d[3:7]}-{d[7:]}'
    if len(d) == 10 and d.startswith('02'):
        return f'02-{d[2:6]}-{d[6:]}'
    return s

@dataclass
class ExtractedDates:
    main_date: Optional[str]
    year: Optional[int]
    all_dates: List[Dict[str, Any]]

class MetadataExtractor:
    """PDF 메타데이터 추출기"""

    def __init__(self):
        # === 날짜 패턴(컴파일) ===
        self._date_patterns = [
            (re.compile(r'(\d{4})[년\-\.\/](\d{1,2})[월\-\.\/](\d{1,2})'), 'ymd'),
            (re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})'), 'ymd'),
            (re.compile(r'(\d{4})-(\d{2})-(\d{2})'), 'ymd'),
            (re.compile(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'), 'ymd'),
            (re.compile(r'(\d{2,4})년도?\s*(\d{1,2})월'), 'ym'),
            (re.compile(r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})'), 'dmy'),
            (re.compile(r'(20\d{2}|19\d{2})년도?'), 'y'),
        ]

        # === 금액 패턴 (DEPRECATED: v1.4부터 amount_parser_v2 사용) ===
        # 이전 정규식 기반 파서는 number concatenation 문제로 인해 폐기
        # 새로운 파서는 라인아이템 우선 + 상/하한 가드 적용
        # self._amount_patterns = [...]  # 더 이상 사용하지 않음

        # === 부서/조직 ===
        self._dept_patterns = [
            (re.compile(r'(카메라|조명|음향|영상|스튜디오|중계|편집|송출)(?:\s*(부|팀|실))?'), 'tech'),
            (re.compile(r'(제작[1-9]|보도|교양|예능|드라마|스포츠|시사)(?:\s*(부|국|팀))?'), 'prod'),
            (re.compile(r'(기술|제작|경영|편성|심의|홍보)\s*(본부|국|센터)'), 'div'),
            (re.compile(r'부서\s*:\s*([가-힣A-Za-z]+(?:부|팀|실|과|센터|본부))'), 'general'),
            (re.compile(r'소속\s*:\s*([가-힣A-Za-z]+)'), 'general'),
            (re.compile(r'담당\s*:\s*([가-힣A-Za-z]+)'), 'general'),
        ]

        # === 문서유형 키워드(소문자 비교) ===
        self._doctype = [
            ('구매', 1, ['구매','구입','발주','조달','입찰','계약서','견적']),
            ('수리', 2, ['수리','정비','a/s','as','고장','수선','보수','유지보수']),
            ('임대', 3, ['임대','임차','렌탈','대여','리스']),
            ('신청', 4, ['신청서','요청서','의뢰서','신청','요청']),
            ('보고', 5, ['보고서','보고','결과','분석','현황','실적']),
            ('회의', 6, ['회의록','회의','미팅','협의','논의']),
            ('검수', 7, ['검수','검사','시험','테스트','점검']),
        ]

        # === 기안자 ===
        self._drafter_patterns = [
            re.compile(r'기안자\s*[:\s]*([가-힣]{2,4})'),
            re.compile(r'작성자\s*[:\s]*([가-힣]{2,4})'),
            re.compile(r'기안\s*[:\s]*([가-힣]{2,4})'),
        ]

        # === 연락처 ===
        self._contact_name = re.compile(r'담당자?\s*[:\s]*([가-힣A-Za-z]{2,20})')

        # === 장비/모델/시리얼 ===
        self._equip_patterns = [
            (re.compile(r'\b(?:모델|model)\s*[:\s]*([A-Z0-9][A-Z0-9_\-]{2,})', re.I), 'model'),
            (re.compile(r'\b(?:시리얼|serial|s\/n)\s*[:\s]*([A-Z0-9][A-Z0-9_\-]{2,})', re.I), 'serial'),
            (re.compile(r'(카메라|렌즈|조명|마이크|믹서|스위처|모니터|삼각대)'), 'equipment'),
            (re.compile(r'(?:DVR|NVR|VTR|CCU|서버|스토리지)', re.I), 'equipment'),
        ]

        # === 프로젝트/프로그램 ===
        self._proj_patterns = [
            re.compile(r'프로그램\s*:\s*([가-힣A-Za-z0-9\s\-\_\(\)]+)'),
            re.compile(r'방송\s*프로그램\s*:\s*([가-힣A-Za-z0-9\s\-\_\(\)]+)'),
            re.compile(r'프로젝트\s*:\s*([가-힣A-Za-z0-9\s\-\_\(\)]+)'),
            re.compile(r'《([^》]+)》'), re.compile(r'【([^】]+)】'),
        ]

        # === 결재/번호 ===
        self._approval_patterns = [
            (re.compile(r'결재일\s*[:\s]*(\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2})'), 'approval_date'),
            (re.compile(r'계약번호\s*[:\s]*([A-Z0-9\-]+)', re.I), 'contract_no'),
            (re.compile(r'문서번호\s*[:\s]*([A-Z0-9\-]+)', re.I), 'doc_no'),
            (re.compile(r'품의번호\s*[:\s]*([A-Z0-9\-]+)', re.I), 'request_no'),
        ]

        # === 업체 키워드 ===
        self._known_companies = [
            '삼성','lg','소니','sony','파나소닉','panasonic','캐논','canon','니콘','nikon','후지','fuji',
            'arri','red','blackmagic','dji','atomos','hanwha','techwin','hanwha vision','tvlogic','ross','panasonic',
            'kbs','mbc','sbs','ebs','jtbc','channel a','채널a','채널에이'
        ]
        # (주) 변형
        self._company_variants = [
            re.compile(r'([가-힣A-Za-z]+)\s*주식회사'),
            re.compile(r'주식회사\s*([가-힣A-Za-z]+)'),
            re.compile(r'\(주\)\s*([가-힣A-Za-z]+)'),
            re.compile(r'([가-힣A-Za-z]+)\s*\(주\)'),
            re.compile(r'([가-힣A-Za-z]+)\s*(?:코리아|코퍼레이션|테크윈|비전)', re.I),
        ]

    # ==== Public API ====
    def extract_all(self, text: str, filename: str = "") -> Dict[str, Any]:
        text = _norm_space(text)
        base = f"{text} {filename}"

        dates = self._extract_dates(base)
        amounts = self._extract_amounts(text)
        department = self._extract_department(base)
        doc_type = self._extract_doc_type(base)
        drafter = self._extract_drafter(text)
        contacts = self._extract_contacts(text)
        equipment = self._extract_equipment(text)
        projects = self._extract_projects(text)
        approval = self._extract_approval(text)
        companies = self._extract_companies(base)

        summary: Dict[str, Any] = {}
        if dates.main_date:
            summary['date'] = dates.main_date
        elif dates.year:
            summary['year'] = dates.year
        if amounts.get('total'):
            summary['amount'] = amounts['total']
        if department:
            summary['department'] = department
        if doc_type:
            summary['doc_type'] = doc_type
        if drafter:
            summary['drafter'] = drafter
        if contacts['names']:
            summary['contact'] = contacts['names'][0]
        if equipment:
            summary['equipment_count'] = len(equipment)
        if companies:
            summary['main_company'] = companies[0]

        return {
            'dates': dates.__dict__,
            'amounts': amounts,
            'department': department,
            'doc_type': doc_type,
            'drafter': drafter,
            'contacts': contacts,
            'equipment': equipment,
            'projects': projects,
            'approval': approval,
            'companies': companies,
            'summary': summary,
        }

    # ==== Extractors ====
    def _extract_dates(self, text: str) -> ExtractedDates:
        found: List[Dict[str, Any]] = []
        year_hint: Optional[int] = None

        for rx, typ in self._date_patterns:
            for m in rx.finditer(text):
                try:
                    if typ == 'ymd':
                        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    elif typ == 'ym':
                        y, mo, d = int(m.group(1)), int(m.group(2)), 1
                    elif typ == 'y':
                        y, mo, d = int(m.group(1)), 1, 1
                    elif typ == 'dmy':
                        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    else:
                        continue

                    # 2자리 연도 교정 후 문자열 생성
                    if y < 100:
                        y = 2000 + y if y < 30 else 1900 + y

                    if 1990 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31:
                        date_str = f'{y:04d}-{mo:02d}-{d:02d}'
                        found.append({'date': date_str, 'year': y, 'type': typ, 'position': m.start()})
                        if not year_hint:
                            year_hint = y
                except Exception:
                    continue

        # 최신일자 우선
        found.sort(key=lambda x: x['date'], reverse=True)
        main_date = None
        for item in found:
            if item['type'] in ('ymd', 'dmy'):
                main_date = item['date']; break

        return ExtractedDates(main_date=main_date, year=year_hint, all_dates=found)

    def _extract_amounts(self, text: str) -> Dict[str, Any]:
        """
        금액 추출 (v2: 강화된 파서 사용)
        - 라인아이템 우선 (unit × qty)
        - 상/하한 가드 (100k-50M)
        - 문서 단위 스코프 보장
        """
        res = {'total': None, 'contract': None, 'all_amounts': []}

        # 1) 강화된 파서로 문서 금액 추출 (doc_id는 임시값, filename이나 hash 사용 가능)
        doc_id = f"meta_extract_{hash(text[:100]) % 100000}"
        raw_amount = select_document_amount(doc_id, text)

        # 2) 최종 검증
        validated_amount, is_valid = validate_amount(raw_amount, context="metadata_extractor")

        if is_valid and validated_amount:
            res['total'] = validated_amount
            res['all_amounts'].append({
                'amount': validated_amount,
                'type': 'validated_total',
                'formatted': f'₩{validated_amount:,}',
                'position': 0
            })
            logger.info(f"Amount extracted: ₩{validated_amount:,} (validated)")
        else:
            # 폴백: 후보만 수집 (검증 실패 시)
            candidates = extract_amount_candidates(text)
            if candidates:
                for c in candidates:
                    res['all_amounts'].append({
                        'amount': c.value,
                        'type': 'candidate',
                        'formatted': f'₩{c.value:,}',
                        'position': c.start
                    })
                res['all_amounts'].sort(key=lambda x: x['amount'], reverse=True)

            logger.warning(f"Amount validation failed for doc_id={doc_id}, raw={raw_amount}")

        return res

    def _extract_department(self, text: str) -> Optional[str]:
        for rx, t in self._dept_patterns:
            m = rx.search(text)
            if m:
                dept = m.group(1)
                if dept and not any(s in dept for s in ['부','팀','실','과','센터','본부']):
                    if t == 'tech':
                        dept += '부'
                return dept
        return None

    def _extract_doc_type(self, text: str) -> Optional[str]:
        t = text.lower()
        for name, prio, kws in sorted(self._doctype, key=lambda x: x[1]):
            for kw in kws:
                if kw in t:
                    return name
        return None

    def _extract_drafter(self, text: str) -> Optional[str]:
        for rx in self._drafter_patterns:
            m = rx.search(text)
            if m:
                nm = m.group(1)
                if 2 <= len(nm) <= 4:
                    return nm
        return None

    def _extract_contacts(self, text: str) -> Dict[str, List[str]]:
        names, phones, emails = [], [], []
        for m in self._contact_name.finditer(text):
            v = m.group(1)
            if v not in names:
                names.append(v)
        for m in _KR_MOBILE.finditer(text):
            v = _to_kr_mobile(m.group(0))
            if v not in phones:
                phones.append(v)
        for m in _EMAIL.finditer(text):
            v = m.group(1).lower()
            if v not in emails:
                emails.append(v)
        return {'names': names, 'phones': phones, 'emails': emails}

    def _extract_equipment(self, text: str) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        seen = set()
        for rx, kind in self._equip_patterns:
            for m in rx.finditer(text):
                val = m.group(1)
                if not val:
                    continue
                key = (kind, val.lower())
                if key in seen:
                    continue
                seen.add(key)
                items.append({'name': val, 'type': kind})
        return items

    def _extract_projects(self, text: str) -> List[str]:
        out, seen = [], set()
        for rx in self._proj_patterns:
            for m in rx.finditer(text):
                v = _norm_space(m.group(1))
                if v and v not in seen:
                    seen.add(v); out.append(v)
        return out

    def _extract_approval(self, text: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for rx, key in self._approval_patterns:
            m = rx.search(text)
            if m:
                out[key] = m.group(1)
        return out

    def _extract_companies(self, text: str) -> List[str]:
        t = text.lower()
        out, seen = [], set()
        for c in self._known_companies:
            if c in t and c not in seen:
                seen.add(c); out.append(c)
        for rx in self._company_variants:
            for m in rx.finditer(text):
                v = m.group(1).strip()
                if v and v.lower() not in seen:
                    seen.add(v.lower()); out.append(v)
        return out
