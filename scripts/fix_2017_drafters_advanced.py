#!/usr/bin/env python3
"""2017년 문서 기안자 고급 추출 스크립트

기존 텍스트 파일에서 더 정교한 패턴으로 기안자를 추출합니다.
"""

import sqlite3
import re
from pathlib import Path
from typing import Optional, List, Tuple
import json

class AdvancedDrafterExtractor:
    """고급 기안자 추출기"""

    def __init__(self):
        # 확장된 패턴 세트
        self.patterns = [
            # 기본 패턴
            (r'기안자\s*[:|]?\s*([가-힣]{2,4})', 'standard'),
            (r'기안자\s*\|\s*([가-힣]{2,4})', 'pipe'),

            # 공백/줄바꿈 변형
            (r'기\s*안\s*자\s*[:|]?\s*([가-힣]{2,4})', 'spaced'),
            (r'기안자\s+([가-힣]{2,4})\s+', 'whitespace'),

            # OCR 오류 패턴
            (r'기안[자차]\s*[:|]?\s*([가-힣]{2,4})', 'ocr_error1'),
            (r'기[안인]자\s*[:|]?\s*([가-힣]{2,4})', 'ocr_error2'),
            (r'[기키]안자\s*[:|]?\s*([가-힣]{2,4})', 'ocr_error3'),

            # 컨텍스트 기반
            (r'기안자[^가-힣]*([가-힣]{2,4})\s*보존', 'context1'),
            (r'기안자[^가-힣]*([가-힣]{2,4})\s*시행', 'context2'),
            (r'기안일자.*?\n.*?([가-힣]{2,4})', 'next_line'),

            # 테이블 형식
            (r'기안자\s*\|\s*([가-힣]{2,4})\s*\|', 'table'),
            (r'│\s*기안자\s*│\s*([가-힣]{2,4})\s*│', 'table2'),

            # 영문 혼재
            (r'drafter\s*[:|]?\s*([가-힣]{2,4})', 'english'),
            (r'작성자\s*[:|]?\s*([가-힣]{2,4})', 'author'),

            # 특수 케이스
            (r'([가-힣]{2,4})\s*\(기안\)', 'parenthesis'),
            (r'기안\s*:\s*([가-힣]{2,4})', 'colon_space'),
        ]

        # 제외할 단어들
        self.exclude_words = {
            '기안자', '시행자', '보존기간', '문서번호', '신청구분',
            '기안일자', '시행일자', '결재일자', '보존년한', '공개여부',
            '작성자', '결재자', '검토자', '승인자', '확인자',
            '년', '월', '일', '시', '분', '초',
            '장비구매', '수리기안', '기안서', '신청서', '요청서'
        }

        # 알려진 기안자 목록 (DB에서 로드)
        self.known_drafters = self._load_known_drafters()

    def _load_known_drafters(self) -> set:
        """DB에서 알려진 기안자 목록 로드"""
        try:
            conn = sqlite3.connect('metadata.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT drafter
                FROM documents
                WHERE drafter IS NOT NULL AND drafter != ''
            """)
            drafters = {row[0] for row in cursor.fetchall()}
            conn.close()
            return drafters
        except:
            return set()

    def extract_drafter(self, text: str, filename: str = "") -> Tuple[Optional[str], str, float]:
        """
        기안자 추출 (여러 전략 사용)

        Returns:
            (drafter, method, confidence)
        """

        # 전처리: 불필요한 공백 정리
        text = re.sub(r'\s+', ' ', text[:3000])  # 처음 3000자만 사용

        candidates = []

        # 1. 패턴 매칭
        for pattern, method in self.patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                match = match.strip()

                # 유효성 검증
                if self._is_valid_drafter(match):
                    # 신뢰도 계산
                    confidence = self._calculate_confidence(match, method, text)
                    candidates.append((match, method, confidence))

        # 2. 알려진 기안자와 매칭
        for known in self.known_drafters:
            if known in text[:1000]:  # 문서 앞부분에서만
                candidates.append((known, 'known_match', 0.9))

        # 3. 휴리스틱: 파일명에서 힌트
        if '하승범' in filename and '하승범' in text:
            candidates.append(('하승범', 'filename_hint', 0.85))

        # 최적 후보 선택
        if candidates:
            # 신뢰도로 정렬
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[0]

        return None, 'not_found', 0.0

    def _is_valid_drafter(self, name: str) -> bool:
        """기안자 이름 유효성 검증"""
        if not name or len(name) < 2 or len(name) > 4:
            return False

        if name in self.exclude_words:
            return False

        # 한글만 포함
        if not re.match(r'^[가-힣]+$', name):
            return False

        # 일반적인 한국 이름 패턴 (성+이름)
        if len(name) >= 3:
            # 첫 글자가 일반적인 성씨인지 체크
            common_surnames = '김이박최정강조윤장임한오서신권황안송류홍고문양손배백허유남심노하곽성차주우구신임전민유진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예경봉사부황목형계고'
            if name[0] not in common_surnames:
                return False

        return True

    def _calculate_confidence(self, name: str, method: str, text: str) -> float:
        """추출 신뢰도 계산"""
        confidence = 0.5  # 기본값

        # 방법별 가중치
        method_weights = {
            'standard': 0.9,
            'pipe': 0.85,
            'spaced': 0.7,
            'whitespace': 0.75,
            'ocr_error1': 0.6,
            'ocr_error2': 0.6,
            'ocr_error3': 0.55,
            'context1': 0.8,
            'context2': 0.8,
            'next_line': 0.65,
            'table': 0.85,
            'table2': 0.85,
            'english': 0.7,
            'author': 0.75,
            'parenthesis': 0.7,
            'colon_space': 0.8,
            'known_match': 0.9,
            'filename_hint': 0.85
        }

        confidence = method_weights.get(method, 0.5)

        # 알려진 기안자면 신뢰도 증가
        if name in self.known_drafters:
            confidence += 0.1

        # 이름이 여러 번 나타나면 신뢰도 증가
        occurrences = text.count(name)
        if occurrences > 1:
            confidence += min(0.1, occurrences * 0.02)

        return min(1.0, confidence)

def main():
    """메인 실행"""
    print("=" * 60)
    print("🔍 2017년 문서 고급 기안자 추출")
    print("=" * 60)

    extractor = AdvancedDrafterExtractor()
    print(f"✅ 알려진 기안자 {len(extractor.known_drafters)}명 로드")

    # DB 연결
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    # 2017년 기안자 누락 문서
    cursor.execute("""
        SELECT id, filename
        FROM documents
        WHERE (drafter IS NULL OR drafter = '')
        AND filename LIKE '2017-%'
        ORDER BY filename
        LIMIT 50
    """)

    docs = cursor.fetchall()
    print(f"📊 처리 대상: {len(docs)}개\n")

    results = []
    success_count = 0

    for doc_id, filename in docs:
        txt_file = Path('data/extracted') / filename.replace('.pdf', '.txt')

        if not txt_file.exists():
            print(f"⚠️  텍스트 없음: {filename[:40]}")
            continue

        with open(txt_file, 'r', encoding='utf-8') as f:
            text = f.read()

        drafter, method, confidence = extractor.extract_drafter(text, filename)

        if drafter and confidence >= 0.6:  # 신뢰도 임계값
            cursor.execute(
                "UPDATE documents SET drafter = ? WHERE id = ?",
                (drafter, doc_id)
            )
            print(f"✅ {filename[:40]}: {drafter} ({method}, {confidence:.2f})")
            success_count += 1
            results.append({
                'filename': filename,
                'drafter': drafter,
                'method': method,
                'confidence': confidence
            })
        else:
            print(f"❌ {filename[:40]}: 추출 실패")

    conn.commit()
    conn.close()

    # 결과 저장
    with open('reports/2017_drafter_extraction.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"📈 결과: {success_count}/{len(docs)} 성공")
    print(f"📄 상세 결과: reports/2017_drafter_extraction.json")

if __name__ == "__main__":
    main()