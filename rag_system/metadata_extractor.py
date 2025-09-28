"""
메타데이터 추출 모듈
복수 정규식 패턴으로 문서 정보 추출, 파일명 fallback 지원
"""

import re
import logging
import time
import hashlib
from functools import lru_cache
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

@dataclass
class DocumentMetadata:
    """문서 메타데이터 구조"""
    # 필수 필드
    file_path: str
    filename: str
    doc_type: str
    date: Optional[str] = None
    
    # 선택 필드
    author: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    amount: Optional[int] = None
    equipment: Optional[List[str]] = None
    vendor: Optional[str] = None
    
    # 메타 정보
    extraction_method: Optional[Dict[str, str]] = None  # 각 필드별 추출 방법 기록
    confidence: Optional[Dict[str, float]] = None       # 각 필드별 신뢰도
    
    def __post_init__(self):
        if self.equipment is None:
            self.equipment = []
        if self.extraction_method is None:
            self.extraction_method = {}
        if self.confidence is None:
            self.confidence = {}

class MetadataExtractor:
    # 신뢰도 상수
    CONFIDENCE_HIGH = 0.9
    CONFIDENCE_MEDIUM = 0.8
    CONFIDENCE_LOW = 0.7
    CONFIDENCE_FALLBACK = 0.6
    CONFIDENCE_MINIMAL = 0.1
    
    # 길이 제한 상수
    AUTHOR_MIN_LENGTH = 2
    AUTHOR_MAX_LENGTH = 20
    TITLE_MIN_LENGTH = 5
    TITLE_MAX_LENGTH = 100
    VENDOR_MIN_LENGTH = 2
    VENDOR_MAX_LENGTH = 50
    DEPT_MIN_LENGTH = 3
    DEPT_MAX_LENGTH = 30
    
    # 금액 범위 상수
    AMOUNT_MIN = 1000  # 천원
    AMOUNT_MAX = 1000000000  # 10억원
    
    # 유효성 검사 패턴
    NUMERIC_ONLY_PATTERN = r'^[\d\s\-]+$'
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._setup_patterns()
        self._compile_patterns()

        # 성능 통계
        self.extraction_count = 0
        self.total_extraction_time = 0.0
        self.pattern_hits = {}
        self.pattern_misses = {}
    
    def _setup_patterns(self):
        """정규식 패턴들 설정"""
        
        # 날짜 패턴 (우선순위 순)
        self.date_patterns = [
            # 기안일자/검토일자 명시적 패턴
            (r'(?:기안일자|검토일자|작성일자|시행일자)\s*[:：]?\s*(20\d{2})[-./\s](0?[1-9]|1[0-2])[-./\s](0?[1-9]|[12]\d|3[01])', 'explicit_label'),
            # 일반적인 날짜 패턴
            (r'(20\d{2})[-./](0?[1-9]|1[0-2])[-./](0?[1-9]|[12]\d|3[01])', 'date_format'),
            # 한국식 날짜
            (r'(20\d{2})\s*년\s*(0?[1-9]|1[0-2])\s*월\s*(0?[1-9]|[12]\d|3[01])\s*일', 'korean_format'),
        ]
        
        # 기안자/검토자/작성자 패턴 (강화된 버전)
        self.author_patterns = [
            # 표 형식에서 기안자 추출 (가장 일반적)
            (r'기안자\s*([가-힣]{2,4})', 'table_author'),
            (r'작성자\s*([가-힣]{2,4})', 'table_writer'),
            (r'검토자\s*([가-힣]{2,4})', 'table_reviewer'),
            (r'신청자\s*([가-힣]{2,4})', 'table_requester'),
            # 콜론 형식
            (r'(?:기안자|작성자|검토자|신청자)\s*[:：]\s*([가-힣A-Za-z]{2,20})', 'labeled_author'),
            (r'기안\s*:\s*([가-힣A-Za-z]{2,20})', 'colon_format'),
            (r'담당\s*:\s*([가-힣A-Za-z]{2,20})', 'manager_format'),
            # 추가 패턴들
            (r'기안일자\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+시행자\s+([가-힣]{2,4})', 'datetime_author'),
        ]
        
        # 부서 패턴
        self.department_patterns = [
            (r'(?:기안부서|소속|부서명?)\s*[:：]?\s*([가-힣\-\s]{%d,%d})' % (self.DEPT_MIN_LENGTH, self.DEPT_MAX_LENGTH), 'labeled_dept'),
            (r'(기술관리팀|방송기술|영상편집팀|영상취재팀)', 'broadcast_teams'),
        ]
        
        # 금액 패턴 (원화 정규화 포함)
        self.amount_patterns = [
            (r'(?:총액|합계|금액|총\s*금액)\s*[:：]?\s*[₩\s]*([0-9,]+)\s*원?', 'total_amount'),
            (r'검토\s*금액\s*[:：]?\s*[₩\s]*([0-9,]+)\s*원?', 'review_amount'),
            (r'([0-9,]+)\s*원\s*(?:\(|$)', 'amount_with_won'),
        ]
        
        # 업체/벤더 패턴
        self.vendor_patterns = [
            (r'(?:업체명|납품업체|공급사|제조사|벤더)\s*[:：]?\s*([\w가-힣&().\-\s]{%d,%d})' % (self.VENDOR_MIN_LENGTH, self.VENDOR_MAX_LENGTH), 'labeled_vendor'),
            (r'(?:견적서|납품)\s*:\s*([\w가-힣&().\-\s]{%d,%d})' % (self.VENDOR_MIN_LENGTH, min(30, self.VENDOR_MAX_LENGTH)), 'quote_vendor'),
        ]
        
        # 장비명 패턴
        self.equipment_patterns = [
            (r'([A-Z]+-[0-9A-Z]+)', 'model_code'),  # ECM-77BC 같은 모델명
            (r'(워크스테이션|모니터|마이크|카메라|트라이포드|짐벌|드론)', 'equipment_name'),
            (r'(HP\s+Z\d+|LG\s+\d+\w+|삼성\s+\w+)', 'brand_model'),
        ]
        
        # 문서 유형 키워드 매핑
        self.doc_type_keywords = {
            '기안서': ['기안서', '결재', '품의', '신청서', '요청서'],
            '검토서': ['검토서', '검토의견', '기술검토', '검토'],
            '견적서': ['견적서', 'quotation', '견적', '견적금액', '가격'],
        }

    def _compile_patterns(self):
        """정규식 패턴 컴파일 (성능 최적화)"""
        # 날짜 패턴 컴파일
        self.compiled_date_patterns = [(re.compile(p), m) for p, m in self.date_patterns]

        # 기안자 패턴 컴파일
        self.compiled_author_patterns = [(re.compile(p), m) for p, m in self.author_patterns]

        # 부서 패턴 컴파일
        self.compiled_dept_patterns = [(re.compile(p), m) for p, m in self.department_patterns]

        # 금액 패턴 컴파일
        self.compiled_amount_patterns = [(re.compile(p), m) for p, m in self.amount_patterns]

        # 업체 패턴 컴파일
        self.compiled_vendor_patterns = [(re.compile(p), m) for p, m in self.vendor_patterns]

        # 장비 패턴 컴파일
        self.compiled_equipment_patterns = [(re.compile(p, re.IGNORECASE), m) for p, m in self.equipment_patterns]

        # 유효성 검사 패턴 컴파일
        self.compiled_numeric_only = re.compile(self.NUMERIC_ONLY_PATTERN)

        total_patterns = (len(self.compiled_date_patterns) + len(self.compiled_author_patterns) +
                         len(self.compiled_dept_patterns) + len(self.compiled_amount_patterns) +
                         len(self.compiled_vendor_patterns) + len(self.compiled_equipment_patterns))
        self.logger.info(f"패턴 컴파일 완료: 총 {total_patterns}개")

    def extract_metadata(self, text: str, file_path: str) -> DocumentMetadata:
        """텍스트에서 메타데이터 추출 (캐싱됨)"""
        # 캐시 키 생성
        cache_key = hashlib.md5(f"{text[:1000]}{file_path}".encode()).hexdigest()
        return self._extract_metadata_cached(cache_key, text, file_path)

    @lru_cache(maxsize=256)
    def _extract_metadata_cached(self, cache_key: str, text: str, file_path: str) -> DocumentMetadata:
        """실제 메타데이터 추출 (캐싱됨)"""
        start_time = time.time()
        filename = Path(file_path).name

        # 임시 문서 유형 추출
        temp_doc_type = self._extract_doc_type(text, filename)

        metadata = DocumentMetadata(
            file_path=file_path,
            filename=filename,
            doc_type=temp_doc_type
        )
        
        # 1. 문서 유형 신뢰도 설정
        metadata.extraction_method['doc_type'] = 'keyword_matching'
        metadata.confidence['doc_type'] = self.CONFIDENCE_HIGH
        
        # 2. 날짜 추출 (본문 우선, 파일명 fallback)
        date_result = self._extract_date(text, filename)
        metadata.date = date_result[0]
        metadata.extraction_method['date'] = date_result[1]
        metadata.confidence['date'] = date_result[2]
        
        # 3. 기안자 추출
        author_result = self._extract_author(text)
        if author_result[0]:
            metadata.author = author_result[0]
            metadata.extraction_method['author'] = author_result[1]
            metadata.confidence['author'] = author_result[2]
        
        # 4. 부서 추출
        dept_result = self._extract_department(text)
        if dept_result[0]:
            metadata.department = dept_result[0]
            metadata.extraction_method['department'] = dept_result[1]
            metadata.confidence['department'] = dept_result[2]
        
        # 5. 제목 추출
        title_result = self._extract_title(text)
        if title_result[0]:
            metadata.title = title_result[0]
            metadata.extraction_method['title'] = title_result[1]
            metadata.confidence['title'] = title_result[2]
        
        # 6. 금액 추출
        amount_result = self._extract_amount(text)
        if amount_result[0]:
            metadata.amount = amount_result[0]
            metadata.extraction_method['amount'] = amount_result[1]
            metadata.confidence['amount'] = amount_result[2]
        
        # 7. 업체명 추출
        vendor_result = self._extract_vendor(text)
        if vendor_result[0]:
            metadata.vendor = vendor_result[0]
            metadata.extraction_method['vendor'] = vendor_result[1]
            metadata.confidence['vendor'] = vendor_result[2]
        
        # 8. 장비명 추출
        equipment_result = self._extract_equipment(text)
        metadata.equipment = equipment_result[0]
        metadata.extraction_method['equipment'] = equipment_result[1]
        metadata.confidence['equipment'] = equipment_result[2]

        # 성능 통계 업데이트
        self.extraction_count += 1
        self.total_extraction_time += time.time() - start_time

        self.logger.info(f"메타데이터 추출 완료: {filename}")
        return metadata
    
    def _extract_doc_type(self, text: str, filename: str) -> str:
        """문서 유형 추출"""
        # 파일명에서 먼저 확인
        filename_lower = filename.lower()
        for doc_type, keywords in self.doc_type_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower:
                    return doc_type
        
        # 본문에서 확인
        text_lower = text.lower()
        for doc_type, keywords in self.doc_type_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return doc_type
        
        return '기타'
    
    def _extract_date(self, text: str, filename: str) -> Tuple[Optional[str], str, float]:
        """날짜 추출 (본문 우선, 파일명 fallback)"""
        # 1. 본문에서 날짜 추출 시도
        for pattern, method in self.compiled_date_patterns:
            matches = pattern.findall(text)
            if matches:
                if isinstance(matches[0], tuple):
                    # 그룹이 여러 개인 경우
                    year, month, day = matches[0]
                else:
                    # 단일 매치인 경우
                    date_str = matches[0]
                    date_match = re.match(r'(\d{4})[-./](\d{1,2})[-./](\d{1,2})', date_str)
                    if date_match:
                        year, month, day = date_match.groups()
                    else:
                        continue
                
                # 날짜 정규화
                try:
                    normalized_date = f"{year}-{int(month):02d}-{int(day):02d}"
                    confidence = self.CONFIDENCE_HIGH if method == 'explicit_label' else self.CONFIDENCE_LOW
                    return normalized_date, f'text_{method}', confidence
                except ValueError:
                    continue
        
        # 2. 파일명에서 날짜 추출 (fallback)
        filename_date_match = re.search(r'(20\d{2})[-_](0?[1-9]|1[0-2])[-_](0?[1-9]|[12]\d|3[01])', filename)
        if filename_date_match:
            year, month, day = filename_date_match.groups()
            try:
                normalized_date = f"{year}-{int(month):02d}-{int(day):02d}"
                return normalized_date, 'filename_fallback', self.CONFIDENCE_MEDIUM
            except ValueError:
                pass
        
        # 3. 현재 날짜로 fallback (최후 수단)
        return datetime.now().strftime('%Y-%m-%d'), 'current_date_fallback', self.CONFIDENCE_MINIMAL
    
    def _extract_author(self, text: str) -> Tuple[Optional[str], str, float]:
        """기안자/작성자 추출"""
        for pattern, method in self.compiled_author_patterns:
            matches = pattern.findall(text)
            if matches:
                author = matches[0].strip()
                # 유효성 검사
                if self._is_valid_name(author, self.AUTHOR_MIN_LENGTH, self.AUTHOR_MAX_LENGTH):
                    confidence = self.CONFIDENCE_HIGH if 'labeled' in method else self.CONFIDENCE_LOW
                    return author, method, confidence
        
        return None, '', 0.0
    
    def _extract_department(self, text: str) -> Tuple[Optional[str], str, float]:
        """부서명 추출"""
        for pattern, method in self.compiled_dept_patterns:
            matches = pattern.findall(text)
            if matches:
                dept = matches[0].strip()
                if len(dept) >= self.DEPT_MIN_LENGTH:
                    confidence = self.CONFIDENCE_MEDIUM if 'labeled' in method else self.CONFIDENCE_HIGH
                    return dept, method, confidence
        
        return None, '', 0.0
    
    def _extract_title(self, text: str) -> Tuple[Optional[str], str, float]:
        """제목 추출"""
        # 제목 패턴들
        title_patterns = [
            (r'제목\s*[:：]?\s*(.{5,100})', 'labeled_title'),
            (r'^\s*(.{10,80})\s*검토[의서]?\s*건', 'review_title'),
            (r'^\s*(.{10,80})\s*구매\s*검토', 'purchase_title'),
        ]
        
        for pattern, method in title_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            if matches:
                title = matches[0].strip()
                # 제목 정리 (불필요한 문자 제거)
                title = re.sub(r'[^\w가-힣\s\-&().]', ' ', title)
                title = ' '.join(title.split())  # 공백 정리
                
                if self.TITLE_MIN_LENGTH <= len(title) <= self.TITLE_MAX_LENGTH:
                    return title, method, self.CONFIDENCE_MEDIUM
        
        return None, '', 0.0
    
    def _extract_amount(self, text: str) -> Tuple[Optional[int], str, float]:
        """금액 추출 및 정수 변환"""
        for pattern, method in self.compiled_amount_patterns:
            matches = pattern.findall(text)
            if matches:
                amount_str = matches[0].replace(',', '').replace(' ', '')
                try:
                    amount = int(amount_str)
                    if self.AMOUNT_MIN <= amount <= self.AMOUNT_MAX:
                        confidence = self.CONFIDENCE_HIGH if 'total' in method else self.CONFIDENCE_LOW
                        return amount, method, confidence
                except ValueError:
                    continue
        
        return None, '', 0.0
    
    def _extract_vendor(self, text: str) -> Tuple[Optional[str], str, float]:
        """업체명 추출"""
        for pattern, method in self.compiled_vendor_patterns:
            matches = pattern.findall(text)
            if matches:
                vendor = matches[0].strip()
                # 업체명 정리
                vendor = re.sub(r'\s+', ' ', vendor)
                vendor = vendor.strip('()')
                
                if self._is_valid_name(vendor, self.VENDOR_MIN_LENGTH, self.VENDOR_MAX_LENGTH):
                    confidence = self.CONFIDENCE_MEDIUM if 'labeled' in method else self.CONFIDENCE_FALLBACK
                    return vendor, method, confidence
        
        return None, '', 0.0
    
    def _extract_equipment(self, text: str) -> Tuple[List[str], str, float]:
        """장비명/제품명 추출"""
        equipment_list = []
        methods_used = []

        for pattern, method in self.compiled_equipment_patterns:
            matches = pattern.findall(text)
            for match in matches:
                equipment = match.strip()
                if equipment and equipment not in equipment_list:
                    equipment_list.append(equipment)
                    methods_used.append(method)
        
        if equipment_list:
            combined_method = ', '.join(set(methods_used))
            confidence = self.CONFIDENCE_MEDIUM
            return equipment_list, combined_method, confidence
        
        return [], '', 0.0
    
    def to_dict(self, metadata: DocumentMetadata) -> Dict[str, Any]:
        """메타데이터를 딕셔너리로 변환"""
        return asdict(metadata)
    
    def from_dict(self, data: Dict[str, Any]) -> DocumentMetadata:
        """딕셔너리에서 메타데이터 복원"""
        return DocumentMetadata(**data)
    
    def _is_valid_name(self, text: str, min_length: int, max_length: int) -> bool:
        """이름/텍스트 유효성 검사 헬퍼 메서드"""
        if not text:
            return False
        text_length = len(text)
        if not (min_length <= text_length <= max_length):
            return False
        # 숫자, 공백, 대시만으로 구성된 경우 제외
        if self.compiled_numeric_only.match(text):
            return False
        return True

    def get_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        stats = {
            'extraction_count': self.extraction_count,
            'total_extraction_time': self.total_extraction_time,
            'avg_extraction_time': self.total_extraction_time / self.extraction_count if self.extraction_count > 0 else 0.0,
            'pattern_hits': dict(self.pattern_hits),
            'pattern_misses': dict(self.pattern_misses),
            'cache_info': self._extract_metadata_cached.cache_info() if hasattr(self._extract_metadata_cached, 'cache_info') else None
        }
        return stats

# 테스트 함수
def test_metadata_extractor():
    """메타데이터 추출기 테스트"""
    extractor = MetadataExtractor()
    
    # 테스트 샘플
    test_samples = [
        {
            'text': """
            장비구매/수리 기안서
            기안부서: 기술관리팀-보도기술관리파트
            기안자: 남준수
            기안일자: 2025-01-09
            제목: 광화문 스튜디오 모니터 & 스탠드 교체 검토서
            총액: 9,760,000원
            납품업체: 미디어메이트
            """,
            'filename': '2025-01-09_광화문 스튜디오 모니터 & 스탠드 교체 검토서.pdf'
        },
        {
            'text': """
            영상편집팀 NLE 워크스테이션 교체 검토의 건
            기안자: 노규민
            기안일자: 2022-02-03
            총 금액: 179,300,000원
            HP Z8 Workstation
            """,
            'filename': '2022-02-03_영상편집팀 NLE 워크스테이션 교체 검토의 건.pdf'
        }
    ]
    
    for i, sample in enumerate(test_samples):
        print(f"\n=== 테스트 {i+1}: {sample['filename']} ===")
        metadata = extractor.extract_metadata(sample['text'], sample['filename'])
        
        print(f"문서 유형: {metadata.doc_type}")
        print(f"날짜: {metadata.date} (방법: {metadata.extraction_method.get('date', 'N/A')})")
        print(f"기안자: {metadata.author} (방법: {metadata.extraction_method.get('author', 'N/A')})")
        print(f"부서: {metadata.department}")
        print(f"제목: {metadata.title}")
        print(f"금액: {metadata.amount:,}원" if metadata.amount else "금액: N/A")
        print(f"업체: {metadata.vendor}")
        print(f"장비: {metadata.equipment}")

if __name__ == "__main__":
    test_metadata_extractor()