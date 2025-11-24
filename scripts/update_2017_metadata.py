#!/usr/bin/env python3
"""2017년 문서 메타데이터 업데이트 스크립트

OCR 재처리 결과를 기반으로 DB 메타데이터를 업데이트합니다.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
import re
from typing import Dict, List, Optional

class MetadataUpdater:
    """메타데이터 업데이트 관리자"""

    def __init__(self):
        self.db_path = 'metadata.db'
        self.report_path = Path('reports/ocr_reprocessing_2017.json')
        self.backup_created = False

    def create_backup(self):
        """DB 백업 생성"""
        if not self.backup_created:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"metadata.db.backup_{timestamp}"

            import shutil
            shutil.copy2(self.db_path, backup_path)

            print(f"✅ 백업 생성: {backup_path}")
            self.backup_created = True

    def load_ocr_results(self) -> Dict:
        """OCR 재처리 결과 로드"""
        if not self.report_path.exists():
            print(f"❌ OCR 결과 파일을 찾을 수 없습니다: {self.report_path}")
            print("먼저 scripts/enhanced_ocr_processor.py를 실행하세요.")
            return {}

        with open(self.report_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def validate_drafter(self, drafter: str) -> bool:
        """기안자 이름 유효성 검사"""
        if not drafter:
            return False

        # 한글 이름 (2-4자)
        if not re.match(r'^[가-힣]{2,4}$', drafter):
            return False

        # 알려진 기안자 목록과 비교 (선택적)
        known_drafters = self.get_known_drafters()
        if known_drafters and drafter not in known_drafters:
            # 유사한 이름 찾기 (오타 보정)
            similar = self.find_similar_drafter(drafter, known_drafters)
            if similar:
                print(f"  📝 '{drafter}' → '{similar}' (유사 이름 보정)")
                return True

        return True

    def get_known_drafters(self) -> set:
        """기존 기안자 목록 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT DISTINCT drafter
            FROM documents
            WHERE drafter IS NOT NULL AND drafter != ''
        """)
        drafters = set(row[0] for row in cursor.fetchall())
        conn.close()
        return drafters

    def find_similar_drafter(self, name: str, known_names: set) -> Optional[str]:
        """유사한 기안자 이름 찾기 (편집 거리 기반)"""
        def levenshtein_distance(s1, s2):
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)

            if len(s2) == 0:
                return len(s1)

            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        # 편집 거리가 1 이하인 이름 찾기
        for known in known_names:
            if levenshtein_distance(name, known) <= 1:
                return known

        return None

    def update_database(self, results: List[Dict]) -> Dict:
        """데이터베이스 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {
            'total': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'details': []
        }

        for result in results:
            if result['status'] != 'success':
                continue

            filename = result['filename']
            drafter = result['drafter']

            stats['total'] += 1

            # 기존 데이터 확인
            cursor.execute("""
                SELECT drafter FROM documents
                WHERE filename = ?
            """, (filename,))

            row = cursor.fetchone()

            if not row:
                print(f"  ⚠️ {filename}: DB에 없음")
                stats['skipped'] += 1
                stats['details'].append({
                    'filename': filename,
                    'action': 'skipped',
                    'reason': 'not_in_db'
                })
                continue

            current_drafter = row[0]

            if current_drafter:
                print(f"  ℹ️ {filename}: 기존 기안자 유지 ({current_drafter})")
                stats['skipped'] += 1
                stats['details'].append({
                    'filename': filename,
                    'action': 'skipped',
                    'reason': 'already_has_drafter',
                    'current': current_drafter
                })
                continue

            # 유효성 검사
            if not self.validate_drafter(drafter):
                print(f"  ❌ {filename}: 유효하지 않은 기안자 ({drafter})")
                stats['failed'] += 1
                stats['details'].append({
                    'filename': filename,
                    'action': 'failed',
                    'reason': 'invalid_drafter',
                    'drafter': drafter
                })
                continue

            # 업데이트
            try:
                cursor.execute("""
                    UPDATE documents
                    SET drafter = ?, updated_at = ?
                    WHERE filename = ?
                """, (drafter, datetime.now().isoformat(), filename))

                print(f"  ✅ {filename}: {drafter} 업데이트")
                stats['updated'] += 1
                stats['details'].append({
                    'filename': filename,
                    'action': 'updated',
                    'drafter': drafter
                })

            except Exception as e:
                print(f"  ❌ {filename}: 업데이트 실패 - {e}")
                stats['failed'] += 1
                stats['details'].append({
                    'filename': filename,
                    'action': 'failed',
                    'reason': str(e)
                })

        # 커밋
        conn.commit()
        conn.close()

        return stats

    def verify_updates(self) -> Dict:
        """업데이트 검증"""
        conn = sqlite3.connect(self.db_path)

        # 2017년 문서 통계
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN drafter IS NOT NULL AND drafter != '' THEN 1 ELSE 0 END) as with_drafter,
                SUM(CASE WHEN drafter IS NULL OR drafter = '' THEN 1 ELSE 0 END) as without_drafter
            FROM documents
            WHERE filename LIKE '2017-%'
        """)

        row = cursor.fetchone()
        stats = {
            'total': row[0],
            'with_drafter': row[1],
            'without_drafter': row[2],
            'success_rate': f"{(row[1]/max(row[0], 1)*100):.1f}%"
        }

        # 기안자별 분포
        cursor = conn.execute("""
            SELECT drafter, COUNT(*) as count
            FROM documents
            WHERE filename LIKE '2017-%'
                AND drafter IS NOT NULL AND drafter != ''
            GROUP BY drafter
            ORDER BY count DESC
            LIMIT 10
        """)

        stats['top_drafters'] = [
            {'drafter': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        conn.close()
        return stats

def main():
    """메인 실행"""
    print("=" * 60)
    print("📝 2017년 문서 메타데이터 업데이트")
    print("=" * 60)

    updater = MetadataUpdater()

    # 1. 백업 생성
    updater.create_backup()

    # 2. OCR 결과 로드
    print("\n📂 OCR 결과 로드 중...")
    ocr_data = updater.load_ocr_results()

    if not ocr_data:
        return

    print(f"  - 전체: {ocr_data.get('total', 0)}개")
    print(f"  - 성공: {ocr_data.get('success', 0)}개")
    print(f"  - 성공률: {ocr_data.get('success_rate', 'N/A')}")

    # 3. DB 업데이트
    print("\n🔄 데이터베이스 업데이트 중...")
    update_stats = updater.update_database(ocr_data.get('results', []))

    print("\n📊 업데이트 결과:")
    print(f"  - 전체 시도: {update_stats['total']}개")
    print(f"  - 업데이트: {update_stats['updated']}개")
    print(f"  - 건너뜀: {update_stats['skipped']}개")
    print(f"  - 실패: {update_stats['failed']}개")

    # 4. 검증
    print("\n✅ 최종 검증:")
    verify_stats = updater.verify_updates()

    print(f"  - 2017년 전체 문서: {verify_stats['total']}개")
    print(f"  - 기안자 있음: {verify_stats['with_drafter']}개")
    print(f"  - 기안자 없음: {verify_stats['without_drafter']}개")
    print(f"  - 완성도: {verify_stats['success_rate']}")

    if verify_stats['top_drafters']:
        print("\n📋 상위 기안자:")
        for item in verify_stats['top_drafters'][:5]:
            print(f"  - {item['drafter']}: {item['count']}개")

    # 5. 보고서 저장
    report = {
        'timestamp': datetime.now().isoformat(),
        'ocr_results': ocr_data,
        'update_stats': update_stats,
        'verification': verify_stats
    }

    output_path = Path('reports/2017_metadata_update.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ 업데이트 완료!")
    print(f"📁 보고서: {output_path}")
    print("=" * 60)

    # 인덱스 재생성 권고
    if update_stats['updated'] > 0:
        print("\n⚠️ 인덱스 재생성이 필요합니다:")
        print("  python scripts/reindex_atomic.py")

if __name__ == "__main__":
    main()