#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""향상된 OCR 처리기 - 2017년 문서 재처리"""

import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter, ImageEnhance
import cv2
import numpy as np
from pathlib import Path
import json
from typing import Dict, List, Optional
import re
import time

class EnhancedOCRProcessor:
    """향상된 OCR 처리기"""

    def __init__(self):
        # 다양한 Tesseract 설정 시도
        self.configs = [
            r'--oem 3 --psm 6 -l kor+eng',  # 기본
            r'--oem 1 --psm 6 -l kor',      # LSTM only
            r'--oem 3 --psm 3 -l kor+eng',  # 자동 페이지 분할
            r'--oem 3 --psm 11 -l kor+eng', # 희소 텍스트
        ]

    def extract_text_simple(self, pdf_path: Path) -> str:
        """간단한 OCR (전처리 최소화)"""
        try:
            # 중간 해상도로 변환
            images = convert_from_path(pdf_path, dpi=200, fmt='png')

            all_text = []
            for image in images:
                # 기본 OCR 수행
                text = pytesseract.image_to_string(image, lang='kor')
                if text:
                    all_text.append(text)

            return "\n\n".join(all_text)
        except Exception as e:
            print(f"  ❌ 간단한 OCR 실패: {e}")
            return ""

    def extract_text_enhanced(self, pdf_path: Path) -> str:
        """향상된 OCR (다양한 설정 시도)"""
        try:
            images = convert_from_path(pdf_path, dpi=300, fmt='png')

            all_text = []

            for i, image in enumerate(images):
                best_text = ""
                best_length = 0

                # 여러 설정으로 시도
                for config in self.configs:
                    try:
                        text = pytesseract.image_to_string(image, config=config)
                        if len(text) > best_length:
                            best_text = text
                            best_length = len(text)
                    except:
                        continue

                if best_text:
                    all_text.append(best_text)

            return "\n\n".join(all_text)
        except Exception as e:
            print(f"  ❌ 향상된 OCR 실패: {e}")
            return ""

    def extract_drafter(self, text: str) -> Optional[str]:
        """기안자 추출 (다양한 패턴)"""

        # 텍스트 정리
        text = text.replace('\n', ' ').replace('  ', ' ')

        patterns = [
            # 표준 패턴
            r'기안자\s*[:|]?\s*([가-힣]{2,4})',
            r'기\s*안\s*자\s*[:|]?\s*([가-힣]{2,4})',

            # OCR 오류 보정
            r'기안[자지]\s*[:|]?\s*([가-힣]{2,4})',
            r'[기키][안간][자지]\s*[:|]?\s*([가-힣]{2,4})',

            # 작성자/담당자
            r'작성자\s*[:|]?\s*([가-힣]{2,4})',
            r'담당자\s*[:|]?\s*([가-힣]{2,4})',
            r'신청자\s*[:|]?\s*([가-힣]{2,4})',

            # 테이블 형식
            r'기안자\s*\|\s*([가-힣]{2,4})',
            r'([가-힣]{2,4})\s*\|\s*기안',

            # 기안자 주변 텍스트
            r'기안자\s+([가-힣]{2,4})\s+',
            r'기안자\s*([가-힣]{2,4})\s*보존',
            r'기안자\s*([가-힣]{2,4})\s*기안일',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                # 가장 빈번한 이름 선택
                from collections import Counter
                name_counts = Counter(matches)
                most_common = name_counts.most_common(1)[0][0]

                # 유효성 검사
                if 2 <= len(most_common) <= 4 and re.match(r'^[가-힣]+$', most_common):
                    return most_common

        return None

    def extract_date(self, text: str) -> Optional[str]:
        """날짜 추출"""

        # 다양한 날짜 패턴
        patterns = [
            r'(20\d{2}[-./]\d{1,2}[-./]\d{1,2})',
            r'(20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)',
            r'기안일자\s*[:|]?\s*(20\d{2}[-./]\d{1,2}[-./]\d{1,2})',
            r'시행일자\s*[:|]?\s*(20\d{2}[-./]\d{1,2}[-./]\d{1,2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                # 날짜 형식 정규화
                date_str = re.sub(r'[년월일]', '', date_str)
                date_str = re.sub(r'[./]', '-', date_str)
                return date_str

        return None

    def extract_department(self, text: str) -> Optional[str]:
        """부서 추출"""

        patterns = [
            r'(기술기획팀|영상취재팀|편집팀|제작팀|보도국|경영지원팀|콘텐츠팀)',
            r'기안부서\s*[:|]?\s*([가-힣]+팀)',
            r'부서\s*[:|]?\s*([가-힣]+[팀국부])',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

def main():
    """2017년 문서 재처리"""

    processor = EnhancedOCRProcessor()

    # 2017년 문서 목록
    docs_dir = Path('docs/year_2017')
    pdf_files = list(docs_dir.glob('*.pdf'))

    print(f"📚 2017년 문서 {len(pdf_files)}개 재처리 시작")
    print("=" * 60)

    results = []
    success_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] {pdf_path.name}")

        # 간단한 OCR 먼저 시도
        text = processor.extract_text_simple(pdf_path)

        # 텍스트가 너무 짧으면 향상된 OCR 시도
        if len(text) < 100:
            print("  ⚠️ 텍스트 부족, 향상된 OCR 시도...")
            text = processor.extract_text_enhanced(pdf_path)

        if text:
            # 메타데이터 추출
            drafter = processor.extract_drafter(text)
            date = processor.extract_date(text)
            department = processor.extract_department(text)

            if drafter:
                print(f"  ✅ 기안자: {drafter}")
                success_count += 1
            else:
                print(f"  ⚠️ 기안자 추출 실패")

            if date:
                print(f"  📅 날짜: {date}")

            if department:
                print(f"  🏢 부서: {department}")

            results.append({
                'filename': pdf_path.name,
                'drafter': drafter,
                'date': date,
                'department': department,
                'text_length': len(text),
                'status': 'success' if drafter else 'no_drafter'
            })
        else:
            print(f"  ❌ OCR 실패")
            results.append({
                'filename': pdf_path.name,
                'drafter': None,
                'date': None,
                'department': None,
                'text_length': 0,
                'status': 'ocr_failed'
            })

        # 5개마다 중간 저장
        if i % 5 == 0:
            output_path = Path('reports/ocr_reprocessing_2017.json')
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'total': len(pdf_files),
                    'processed': i,
                    'success': success_count,
                    'success_rate': f"{(success_count/i*100):.1f}%",
                    'results': results
                }, f, ensure_ascii=False, indent=2)

    # 최종 결과 저장
    output_path = Path('reports/ocr_reprocessing_2017.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(pdf_files),
            'success': success_count,
            'success_rate': f"{(success_count/len(pdf_files)*100):.1f}%",
            'results': results
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ 재처리 완료!")
    print(f"  - 전체: {len(pdf_files)}개")
    print(f"  - 성공: {success_count}개")
    print(f"  - 성공률: {(success_count/len(pdf_files)*100):.1f}%")
    print(f"  - 보고서: {output_path}")

if __name__ == "__main__":
    main()