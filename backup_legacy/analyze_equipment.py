#!/usr/bin/env python3
"""
문서에서 장비명 추출 및 분석
"""

from pathlib import Path
import re
from collections import Counter

def analyze_equipment_names():
    """PDF 파일명에서 장비명 추출"""
    
    docs_dir = Path('docs')
    equipment_counter = Counter()
    
    # 장비 관련 키워드 패턴
    equipment_patterns = [
        r'카메라', r'렌즈', r'마이크', r'모니터', r'스위처',
        r'DVR', r'CCU', r'트라이포[드트]', r'페데스탈',
        r'프롬프터', r'인터컴', r'헤드셋', r'스테디캠',
        r'짐[밸벌]', r'헬리캠', r'드론', r'조명', r'램프',
        r'필터', r'컨버터', r'분배기', r'라우터', r'서버',
        r'NLE', r'에디우스', r'워크스테이션', r'셋톱박스',
        r'UPS', r'배터리', r'충전기', r'케이블', r'커넥터',
        r'스피커', r'앰프', r'믹서', r'오디오', r'무선',
        r'IFB', r'ENG', r'EFP', r'SxS', r'메모리',
        r'하드', r'SSD', r'백업', r'스토리지', r'아카이브',
        r'자막기', r'CG', r'그래픽', r'비디오', r'광케이블',
        r'BNC', r'SDI', r'HDMI', r'발전기', r'중계차',
        r'스튜디오', r'부조', r'주조', r'소모품'
    ]
    
    # 모든 PDF 파일 검사
    pdf_files = list(docs_dir.rglob('*.pdf'))
    print(f"\n📊 총 {len(pdf_files)}개 PDF 문서 분석")
    print("="*60)
    
    for pdf_path in pdf_files:
        filename = pdf_path.name.lower()
        
        # 각 패턴 검사
        for pattern in equipment_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                # 정규화된 장비명 저장
                normalized = pattern.replace(r'[드트]', '드').replace(r'[밸벌]', '벌')
                normalized = normalized.replace(r'\\', '')
                equipment_counter[normalized] += 1
    
    # 결과 출력
    print("\n🔍 문서에서 발견된 장비명 빈도 (상위 30개)")
    print("="*60)
    
    for equipment, count in equipment_counter.most_common(30):
        print(f"  • {equipment:15s}: {count:3d}개 문서")
    
    # 현재 perfect_rag.py에 없는 장비명 찾기
    current_equipment = ['dvr', 'ccu', '카메라', '렌즈', '모니터', '스위처',
                        '마이크', '믹서', '스피커', '앰프', '프로젝터']
    
    print("\n✨ 추가하면 좋을 새로운 장비명:")
    print("="*60)
    
    new_equipment = []
    for equipment, count in equipment_counter.most_common():
        if count >= 3:  # 3개 이상 문서에서 나타난 장비만
            eq_lower = equipment.lower()
            if eq_lower not in current_equipment and equipment not in current_equipment:
                new_equipment.append(equipment)
    
    for eq in new_equipment[:20]:  # 상위 20개만
        print(f"  • {eq}")
    
    # 추천 코드 생성
    print("\n📝 perfect_rag.py에 추가할 코드:")
    print("="*60)
    
    all_equipment = current_equipment + new_equipment[:15]
    print("equipment_names = [")
    for i, eq in enumerate(all_equipment):
        if i % 5 == 0 and i > 0:
            print()
        print(f"    '{eq.lower()}',", end="")
    print("\n]")

if __name__ == "__main__":
    analyze_equipment_names()