#!/usr/bin/env python3
"""문서 카테고리 자동 분류 시스템

파일명과 텍스트 내용을 기반으로 문서 카테고리를 자동으로 분류합니다.
"""

import sqlite3
import re
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict

class DocumentCategorizer:
    """문서 카테고리 자동 분류기"""

    def __init__(self):
        # 카테고리별 키워드 정의
        self.category_rules = {
            'purchase': {
                'keywords': ['구매', '구입', '도입', '신청서', '견적', '발주'],
                'patterns': [r'구매\s*건', r'도입\s*건', r'구매\s*신청'],
                'weight': 1.0
            },
            'repair': {
                'keywords': ['수리', '고장', '교체', '정비', '점검', '오버홀'],
                'patterns': [r'수리\s*건', r'교체\s*건', r'수리\s*요청'],
                'weight': 1.0
            },
            'review': {
                'keywords': ['검토', '기술검토', '검토서', '검토의'],
                'patterns': [r'검토의?\s*건', r'기술\s*검토', r'검토\s*보고서'],
                'weight': 0.9
            },
            'proposal': {
                'keywords': ['기안서', '제안서', '계획서', '기안'],
                'patterns': [r'기안서', r'제안서'],
                'weight': 0.8
            },
            'report': {
                'keywords': ['보고서', '결과', '분석', '평가', '현황'],
                'patterns': [r'보고서', r'결과\s*보고', r'현황\s*보고'],
                'weight': 0.85
            },
            'equipment': {
                'keywords': ['장비', '카메라', '마이크', '조명', '케이블', 'DVR', 'ENG', '트라이포드'],
                'patterns': [r'장비\s*(구매|수리)', r'카메라\s*(구매|수리)'],
                'weight': 0.7
            },
            'studio': {
                'keywords': ['스튜디오', '부조정실', '주조정실', '방송실'],
                'patterns': [r'스튜디오\s*', r'부조정실\s*', r'주조정실\s*'],
                'weight': 0.7
            },
            'broadcast': {
                'keywords': ['방송', '송출', '중계', '생중계', '편집'],
                'patterns': [r'방송\s*(장비|시스템)', r'송출\s*'],
                'weight': 0.6
            },
            'consumable': {
                'keywords': ['소모품', '소포품', '액세서리', '악세사리', '부품'],
                'patterns': [r'소모품\s*신청', r'소포품\s*신청'],
                'weight': 0.8
            },
            'system': {
                'keywords': ['시스템', '서버', '네트워크', 'IT', '소프트웨어'],
                'patterns': [r'시스템\s*(구축|업그레이드)', r'서버\s*'],
                'weight': 0.7
            }
        }

        # 복합 카테고리 매핑
        self.composite_categories = {
            ('equipment', 'purchase'): 'equipment_purchase',
            ('equipment', 'repair'): 'equipment_repair',
            ('studio', 'equipment'): 'studio_equipment',
            ('broadcast', 'equipment'): 'broadcast_equipment',
            ('consumable', 'purchase'): 'consumable_purchase'
        }

    def categorize_document(self, filename: str, text: str = "") -> Dict[str, any]:
        """문서 카테고리 분류"""

        results = defaultdict(float)
        matched_keywords = defaultdict(list)

        # 파일명 분석 (가중치 높음)
        filename_lower = filename.lower()
        for category, rules in self.category_rules.items():
            # 키워드 매칭
            for keyword in rules['keywords']:
                if keyword.lower() in filename_lower:
                    results[category] += rules['weight'] * 1.5  # 파일명은 가중치 1.5배
                    matched_keywords[category].append(f"filename:{keyword}")

            # 패턴 매칭
            for pattern in rules['patterns']:
                if re.search(pattern, filename, re.IGNORECASE):
                    results[category] += rules['weight'] * 1.8
                    matched_keywords[category].append(f"filename_pattern:{pattern}")

        # 텍스트 내용 분석 (처음 1000자)
        if text:
            text_sample = text[:1000].lower()
            for category, rules in self.category_rules.items():
                # 키워드 매칭
                for keyword in rules['keywords']:
                    count = text_sample.count(keyword.lower())
                    if count > 0:
                        results[category] += rules['weight'] * min(count * 0.3, 1.0)
                        matched_keywords[category].append(f"text:{keyword}({count})")

                # 패턴 매칭
                for pattern in rules['patterns']:
                    matches = re.findall(pattern, text_sample, re.IGNORECASE)
                    if matches:
                        results[category] += rules['weight'] * 0.5
                        matched_keywords[category].append(f"text_pattern:{pattern}")

        # 상위 카테고리 선택
        if not results:
            return {
                'primary_category': 'unknown',
                'secondary_category': None,
                'confidence': 0.0,
                'keywords': []
            }

        # 정렬하여 상위 2개 선택
        sorted_categories = sorted(results.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_categories[0][0]
        secondary = sorted_categories[1][0] if len(sorted_categories) > 1 and sorted_categories[1][1] > 0.5 else None

        # 복합 카테고리 확인
        if primary and secondary:
            composite_key = (primary, secondary) if (primary, secondary) in self.composite_categories else (secondary, primary)
            if composite_key in self.composite_categories:
                final_category = self.composite_categories[composite_key]
            else:
                final_category = primary
        else:
            final_category = primary

        # 신뢰도 계산
        max_score = sorted_categories[0][1]
        confidence = min(max_score / 3.0, 1.0)  # 정규화

        return {
            'primary_category': final_category,
            'secondary_category': secondary,
            'confidence': confidence,
            'keywords': matched_keywords.get(primary, []),
            'scores': dict(sorted_categories[:3])  # 상위 3개 점수
        }

def main():
    """메인 실행"""
    print("=" * 60)
    print("📂 문서 카테고리 자동 분류")
    print("=" * 60)

    categorizer = DocumentCategorizer()

    # DB 연결
    conn = sqlite3.connect('metadata.db')
    cursor = conn.cursor()

    # 카테고리가 없는 문서 조회
    cursor.execute("""
        SELECT id, filename
        FROM documents
        WHERE category IS NULL OR category = ''
        ORDER BY filename
    """)

    docs = cursor.fetchall()
    print(f"📊 처리 대상: {len(docs)}개 문서\n")

    # 카테고리별 통계
    category_stats = defaultdict(int)
    success_count = 0

    for doc_id, filename in docs:
        # 텍스트 파일 읽기 (있으면)
        text = ""
        txt_file = Path('data/extracted') / filename.replace('.pdf', '.txt')
        if txt_file.exists():
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    text = f.read()
            except:
                pass

        # 카테고리 분류
        result = categorizer.categorize_document(filename, text)

        if result['confidence'] >= 0.3:  # 신뢰도 임계값
            category = result['primary_category']

            # DB 업데이트
            cursor.execute(
                "UPDATE documents SET category = ? WHERE id = ?",
                (category, doc_id)
            )

            category_stats[category] += 1
            success_count += 1

            # 상위 20개만 출력
            if success_count <= 20:
                print(f"✅ {filename[:40]:<40} → {category:15} (신뢰도: {result['confidence']:.2f})")
        else:
            category_stats['unknown'] += 1

    # 나머지 요약 출력
    if len(docs) > 20:
        print(f"\n... 외 {len(docs) - 20}개 문서 처리")

    # 커밋
    conn.commit()

    # 통계 출력
    print("\n" + "=" * 60)
    print("📊 카테고리별 분류 결과:")
    for category, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category:20}: {count:4}개")

    print("\n" + "=" * 60)
    print(f"✅ 완료: {success_count}/{len(docs)}개 분류 성공")

    # 검증: 카테고리 분포
    cursor.execute("""
        SELECT category, COUNT(*) as cnt
        FROM documents
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY cnt DESC
    """)

    print("\n📈 전체 카테고리 분포:")
    for category, count in cursor.fetchall()[:10]:
        print(f"  {category:20}: {count:4}개")

    conn.close()

if __name__ == "__main__":
    main()