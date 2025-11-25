#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""메타데이터 검증 및 동기화 상태 점검 스크립트

정기적으로 실행하여 메타데이터 품질을 모니터링합니다.
"""

import sqlite3
import pickle
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json

class MetadataValidator:
    """메타데이터 검증 클래스"""

    def __init__(self, db_path='metadata.db', index_path='var/index/bm25_index.pkl'):
        self.db_path = db_path
        self.index_path = index_path
        self.report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'issues': defaultdict(list),
            'recommendations': []
        }

    def validate_db_metadata(self):
        """DB 메타데이터 검증"""
        print("\n📊 DB 메타데이터 검증")
        print("=" * 60)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 전체 문서 수
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]
        self.report['summary']['total_documents'] = total_docs

        # NULL 또는 빈 drafter
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE drafter IS NULL OR drafter = '' OR drafter = '-'
        """)
        missing_drafters = cursor.fetchone()[0]
        self.report['summary']['missing_drafters'] = missing_drafters

        # 비정상 drafter 패턴
        cursor.execute("""
            SELECT drafter, COUNT(*) as cnt
            FROM documents
            WHERE drafter IS NOT NULL AND drafter != ''
            GROUP BY drafter
            HAVING LENGTH(drafter) < 2 OR LENGTH(drafter) > 5
        """)
        abnormal_drafters = cursor.fetchall()

        # 날짜 형식 문제
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE date IS NULL OR date = ''
            OR date NOT LIKE '20__-__-__'
        """)
        date_issues = cursor.fetchone()[0]
        self.report['summary']['date_issues'] = date_issues

        # 카테고리 누락
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE category IS NULL OR category = ''
        """)
        missing_category = cursor.fetchone()[0]
        self.report['summary']['missing_category'] = missing_category

        print(f"📈 전체 문서: {total_docs}개")
        print(f"❌ 기안자 누락: {missing_drafters}개 ({missing_drafters/total_docs*100:.1f}%)")
        print(f"⚠️  비정상 기안자: {len(abnormal_drafters)}개")
        print(f"❌ 날짜 형식 문제: {date_issues}개")
        print(f"❌ 카테고리 누락: {missing_category}개")

        # 문제 문서 상세 정보
        if missing_drafters > 0:
            cursor.execute("""
                SELECT id, filename
                FROM documents
                WHERE drafter IS NULL OR drafter = '' OR drafter = '-'
                LIMIT 10
            """)
            for doc_id, filename in cursor.fetchall():
                self.report['issues']['missing_drafter'].append({
                    'id': doc_id,
                    'filename': filename
                })

        conn.close()
        return self.report

    def check_db_index_sync(self):
        """DB와 BM25 인덱스 동기화 검증"""
        print("\n🔄 DB-인덱스 동기화 검증")
        print("=" * 60)

        # DB 문서 목록
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM documents")
        db_files = set(row[0] for row in cursor.fetchall())
        conn.close()

        # BM25 인덱스 문서 목록
        with open(self.index_path, 'rb') as f:
            idx = pickle.load(f)

        index_files = set()
        if 'metadata' in idx:
            for meta in idx['metadata']:
                if isinstance(meta, dict) and 'filename' in meta:
                    index_files.add(meta['filename'])

        # 비교
        only_in_db = db_files - index_files
        only_in_index = index_files - db_files

        self.report['summary']['db_count'] = len(db_files)
        self.report['summary']['index_count'] = len(index_files)
        self.report['summary']['only_in_db'] = len(only_in_db)
        self.report['summary']['only_in_index'] = len(only_in_index)

        print(f"📚 DB 문서: {len(db_files)}개")
        print(f"📑 인덱스 문서: {len(index_files)}개")

        if only_in_db:
            print(f"⚠️  DB에만 존재: {len(only_in_db)}개")
            for filename in list(only_in_db)[:5]:
                print(f"    - {filename}")
                self.report['issues']['only_in_db'].append(filename)

        if only_in_index:
            print(f"⚠️  인덱스에만 존재: {len(only_in_index)}개")
            for filename in list(only_in_index)[:5]:
                print(f"    - {filename}")
                self.report['issues']['only_in_index'].append(filename)

        if not only_in_db and not only_in_index:
            print("✅ DB와 인덱스 완전 동기화!")

        return self.report

    def analyze_extraction_failures(self):
        """추출 실패 패턴 분석"""
        print("\n🔍 추출 실패 패턴 분석")
        print("=" * 60)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # drafter가 없는 문서들의 텍스트 샘플 분석
        cursor.execute("""
            SELECT id, filename
            FROM documents
            WHERE drafter IS NULL OR drafter = ''
            LIMIT 20
        """)

        failed_patterns = defaultdict(int)

        for doc_id, filename in cursor.fetchall():
            txt_file = Path('data/extracted') / filename.replace('.pdf', '.txt')

            if txt_file.exists():
                try:
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        content = f.read()[:1000]

                    # 패턴 검사
                    if '기안자' not in content:
                        failed_patterns['no_drafter_keyword'] += 1
                    elif re.search(r'기안자\s*[:|]\s*$', content):
                        failed_patterns['empty_drafter_field'] += 1
                    elif re.search(r'기안자.*\d{4}', content):
                        failed_patterns['date_instead_of_name'] += 1
                    else:
                        failed_patterns['unknown_pattern'] += 1
                except Exception:
                    failed_patterns['read_error'] += 1
            else:
                failed_patterns['no_text_file'] += 1

        print("실패 패턴 분석:")
        self.report['issues']['extraction_patterns'] = {}
        for pattern, count in failed_patterns.items():
            print(f"  - {pattern}: {count}개")
            self.report['issues']['extraction_patterns'][pattern] = count

        conn.close()
        return self.report

    def generate_recommendations(self):
        """개선 권장사항 생성"""
        print("\n💡 권장사항")
        print("=" * 60)

        recommendations = []

        # 기안자 누락 비율이 높으면
        if self.report['summary'].get('missing_drafters', 0) > self.report['summary'].get('total_documents', 1) * 0.1:
            recommendations.append({
                'priority': 'HIGH',
                'issue': 'drafter_missing',
                'action': 'scripts/fix_missing_drafters.py 실행 권장',
                'impact': f"{self.report['summary']['missing_drafters']}개 문서 영향"
            })

        # DB-인덱스 불일치
        if self.report['summary'].get('only_in_db', 0) > 0 or self.report['summary'].get('only_in_index', 0) > 0:
            recommendations.append({
                'priority': 'HIGH',
                'issue': 'sync_mismatch',
                'action': 'scripts/reindex_atomic.py 실행 권장',
                'impact': f"불일치 {self.report['summary'].get('only_in_db', 0) + self.report['summary'].get('only_in_index', 0)}개"
            })

        # 날짜 형식 문제
        if self.report['summary'].get('date_issues', 0) > 0:
            recommendations.append({
                'priority': 'MEDIUM',
                'issue': 'date_format',
                'action': '날짜 형식 정규화 스크립트 실행 필요',
                'impact': f"{self.report['summary']['date_issues']}개 문서"
            })

        self.report['recommendations'] = recommendations

        for rec in recommendations:
            print(f"[{rec['priority']}] {rec['issue']}")
            print(f"  → {rec['action']}")
            print(f"  → 영향: {rec['impact']}")

        if not recommendations:
            print("✅ 모든 검증 통과! 추가 조치 불필요")

        return self.report

    def save_report(self):
        """보고서 저장"""
        report_dir = Path('reports/metadata')
        report_dir.mkdir(parents=True, exist_ok=True)

        # JSON 보고서
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f'metadata_validation_{timestamp}.json'

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, ensure_ascii=False, indent=2)

        print(f"\n📄 보고서 저장: {report_file}")

        # 최신 보고서 심링크
        latest_link = report_dir / 'latest.json'
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(report_file.name)

        return report_file

def main():
    """메인 실행"""
    print("=" * 60)
    print("🔍 메타데이터 검증 시작")
    print("=" * 60)

    validator = MetadataValidator()

    # 1. DB 메타데이터 검증
    validator.validate_db_metadata()

    # 2. DB-인덱스 동기화 검증
    validator.check_db_index_sync()

    # 3. 추출 실패 패턴 분석
    validator.analyze_extraction_failures()

    # 4. 권장사항 생성
    validator.generate_recommendations()

    # 5. 보고서 저장
    report_file = validator.save_report()

    print("\n" + "=" * 60)
    print("✅ 검증 완료!")
    print("=" * 60)

    # 요약 출력
    summary = validator.report['summary']
    print(f"\n📊 요약:")
    print(f"  - 전체 문서: {summary.get('total_documents', 0)}개")
    print(f"  - 문제 문서: {summary.get('missing_drafters', 0) + summary.get('date_issues', 0)}개")
    print(f"  - 동기화 상태: {'✅ 정상' if summary.get('only_in_db', 0) == 0 and summary.get('only_in_index', 0) == 0 else '⚠️ 불일치'}")
    print(f"  - 권장사항: {len(validator.report.get('recommendations', []))}개")

    return validator.report

if __name__ == "__main__":
    main()