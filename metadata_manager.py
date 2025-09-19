#!/usr/bin/env python3
"""
문서 메타데이터 관리 시스템
- JSON 기반 경량 DB
- 빠른 검색 지원
- 자동 업데이트 기능
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import re
from datetime import datetime

class MetadataManager:
    def __init__(self, db_path: str = "document_metadata.json"):
        self.db_path = Path(db_path)
        self.metadata = self.load_metadata()

    def load_metadata(self) -> Dict:
        """메타데이터 DB 로드"""
        if self.db_path.exists():
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_metadata(self):
        """메타데이터 DB 저장"""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def add_document(self, filename: str, **kwargs):
        """문서 메타데이터 추가/업데이트"""
        if filename not in self.metadata:
            self.metadata[filename] = {}

        # 기본 정보 추가
        self.metadata[filename].update(kwargs)
        self.metadata[filename]['last_updated'] = datetime.now().isoformat()

        # 자동 저장
        self.save_metadata()

    def get_document(self, filename: str) -> Optional[Dict]:
        """문서 메타데이터 조회"""
        return self.metadata.get(filename)

    def search_by_drafter(self, drafter_name: str) -> List[str]:
        """기안자로 검색"""
        results = []
        for filename, data in self.metadata.items():
            if data.get('drafter') and drafter_name in data['drafter']:
                results.append(filename)
        return results

    def search_by_field(self, field: str, value: str) -> List[str]:
        """특정 필드로 검색"""
        results = []
        for filename, data in self.metadata.items():
            if field in data and value in str(data[field]):
                results.append(filename)
        return results

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """텍스트에서 메타데이터 자동 추출"""
        metadata = {}

        # 기안자 추출
        patterns = {
            'drafter': [
                r'기안자[\s:：]*([가-힣]{2,4})',
                r'작성자[\s:：]*([가-힣]{2,4})',
                r'담당자[\s:：]*([가-힣]{2,4})'
            ],
            'department': [
                r'기안부서[\s:：]*([^\n]+)',
                r'부서[\s:：]*([^\n]+)',
                r'소속[\s:：]*([^\n]+)'
            ],
            'date': [
                r'기안일자[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
                r'작성일[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
                r'날짜[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})'
            ],
            'amount': [
                r'금액[\s:：]*([0-9,]+)원',
                r'총액[\s:：]*([0-9,]+)원',
                r'([0-9,]+)원'  # 금액 패턴
            ]
        }

        for field, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text)
                if match:
                    metadata[field] = match.group(1).strip()
                    break

        # 문서 타입 자동 분류
        if '긴급' in text:
            metadata['priority'] = 'high'
        elif '검토' in text:
            metadata['type'] = '검토서'
        elif '구매' in text:
            metadata['type'] = '구매기안'
        elif '수리' in text or '보수' in text:
            metadata['type'] = '수리/보수'

        return metadata

    def get_statistics(self) -> Dict:
        """전체 통계"""
        stats = {
            'total_documents': len(self.metadata),
            'documents_with_drafter': 0,
            'documents_with_amount': 0,
            'drafters': {},
            'departments': {},
            'types': {}
        }

        for filename, data in self.metadata.items():
            if data.get('drafter'):
                stats['documents_with_drafter'] += 1
                drafter = data['drafter']
                stats['drafters'][drafter] = stats['drafters'].get(drafter, 0) + 1

            if data.get('amount'):
                stats['documents_with_amount'] += 1

            if data.get('department'):
                dept = data['department']
                stats['departments'][dept] = stats['departments'].get(dept, 0) + 1

            if data.get('type'):
                doc_type = data['type']
                stats['types'][doc_type] = stats['types'].get(doc_type, 0) + 1

        return stats


# 테스트 및 초기 데이터
if __name__ == "__main__":
    manager = MetadataManager()

    # 샘플 데이터 추가 (실제 문서 기반)
    sample_data = [
        {
            "filename": "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf",
            "drafter": "최새름",
            "department": "기술관리팀-보도기술관리파트",
            "type": "긴급보수",
            "amount": "2,446,000",
            "priority": "high"
        },
        {
            "filename": "2025-01-14_채널A_불용_방송_장비_폐기_요청의_건.pdf",
            "drafter": "남준수",
            "department": "기술관리팀",
            "type": "폐기요청",
            "date": "2025-01-14"
        },
        {
            "filename": "2023-12-06_오픈스튜디오_무선마이크_수신_장애_조치_기안서.pdf",
            "drafter": "최새름",
            "department": "기술관리팀",
            "type": "장애조치",
            "date": "2023-12-06"
        },
        {
            "filename": "2023-11-02_영상취재팀_트라이포드_수리_건.pdf",
            "drafter": "유인혁",
            "department": "영상취재팀",
            "type": "수리/보수",
            "date": "2023-11-02"
        },
        {
            "filename": "2024-11-14_뉴스_스튜디오_지미집_Control_Box_수리_건.pdf",
            "drafter": "남준수",
            "department": "기술관리팀",
            "type": "수리/보수",
            "date": "2024-11-14"
        },
        {
            "filename": "2019-05-31_Audio_Patch_Cable_구매.pdf",
            "drafter": "유인혁",
            "department": "기술관리팀",
            "type": "구매기안",
            "date": "2019-05-31"
        }
    ]

    # 데이터 추가
    for data in sample_data:
        filename = data.pop('filename')
        manager.add_document(filename, **data)

    print("✅ 메타데이터 DB 생성 완료!")
    print(f"📊 총 {len(manager.metadata)}개 문서 정보 저장")

    # 통계 출력
    stats = manager.get_statistics()
    print("\n📈 통계:")
    print(f"  - 기안자 정보 있는 문서: {stats['documents_with_drafter']}개")
    print(f"  - 금액 정보 있는 문서: {stats['documents_with_amount']}개")

    print("\n👥 기안자별 문서:")
    for drafter, count in stats['drafters'].items():
        print(f"  - {drafter}: {count}개")

    # 테스트 검색
    print("\n🔍 최새름 기안자 문서 검색:")
    results = manager.search_by_drafter("최새름")
    for doc in results:
        print(f"  - {doc}")