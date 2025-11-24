#!/usr/bin/env python3
"""OCR 오류 패턴 보정 스크립트

자주 발생하는 OCR 오류를 정규식으로 보정합니다.
"""

import re
from pathlib import Path
from typing import Dict, Tuple

class OCRFixer:
    """OCR 오류 보정기"""

    def __init__(self):
        # OCR 오류 패턴과 올바른 텍스트 매핑
        self.replacements = {
            # DVR 관련
            r'\b0\b(?=\s*교체)': 'DVR',  # "0 교체" → "DVR 교체"
            r'ㅁ\\1': 'DVR',
            r'2\\3': 'DVR',
            r'20\\/3': 'DVR',
            r'\b2\b(?=\s*고장)': 'DVR',

            # 모델명
            r'58ㅁ442': 'SRN442',
            r'70ㅁ410': 'IDR410',

            # 기술 용어
            r'01911811': 'Digital',
            r'1060': 'Video',
            r'『600「061': 'Recorder',
            r'600006116': 'Corporate',
            r'51908': 'Signal',
            r'\b818\b': 'HDD',
            r'『411-1ㅁ0': 'Full-HD',
            r'싸10': 'SDI',
            r'ㅁ47041': 'CVBS',
            r'나4': 'HDMI',
            r'\^0회09': 'AUDIO',

            # 기타
            r'쿨장천': '김장천',
            r'죄만근': '최만근',
            r'&/5': 'A/S',
            r'카제': '부가세',
        }

    def fix_text(self, text: str) -> Tuple[str, int]:
        """텍스트 보정"""
        fixed_text = text
        fix_count = 0

        for pattern, replacement in self.replacements.items():
            matches = re.findall(pattern, fixed_text)
            if matches:
                fixed_text = re.sub(pattern, replacement, fixed_text)
                fix_count += len(matches)
                print(f"  ✅ '{pattern}' → '{replacement}' ({len(matches)}회)")

        return fixed_text, fix_count

def process_file(filepath: Path):
    """파일 처리"""
    print(f"\n📄 처리: {filepath.name}")
    print("-" * 60)

    # 원본 읽기
    with open(filepath, 'r', encoding='utf-8') as f:
        original_text = f.read()

    print(f"원본 크기: {len(original_text)} 문자")

    # 보정
    fixer = OCRFixer()
    fixed_text, fix_count = fixer.fix_text(original_text)

    if fix_count > 0:
        # 백업 생성
        backup_path = filepath.with_suffix('.txt.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_text)

        # 보정된 텍스트 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(fixed_text)

        print(f"\n✅ {fix_count}개 패턴 보정 완료")
        print(f"  - 백업: {backup_path}")

        # 키워드 확인
        keywords = ['DVR', 'SRN442', 'IDR410', 'HDD']
        print("\n🔍 주요 키워드 확인:")
        for kw in keywords:
            if kw in fixed_text:
                count = fixed_text.count(kw)
                print(f"  ✅ '{kw}' → {count}회")
    else:
        print("⚠️ 보정할 패턴 없음")

def main():
    """메인 실행"""
    # 문제가 있는 2017년 파일들 처리
    target_files = [
        'data/extracted/2017-12-21_방송_송출_보존용_DVR_교체_검토의_건.txt',
        'data/extracted/2017-12-14_송출_녹화용_DVR_수리의_건.txt',
    ]

    print("="*70)
    print("🔧 OCR 오류 보정 시작")
    print("="*70)

    for filepath in target_files:
        path = Path(filepath)
        if path.exists():
            process_file(path)
        else:
            print(f"\n❌ 파일 없음: {filepath}")

    print("\n" + "="*70)
    print("✅ 보정 완료!")
    print("다음 명령어로 인덱스 재생성 필요:")
    print("  python scripts/reindex_atomic.py")

if __name__ == "__main__":
    main()