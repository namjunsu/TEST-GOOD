#!/usr/bin/env python3
"""
DB 기반 질문 프리셋 검증 스크립트

reports/askable_queries_verified.csv의 모든 질문을
scenario_validation.py 방식으로 자동 검증합니다.

출력:
- reports/askable_queries_validation_YYYYMMDD_HHMMSS.json
- reports/askable_queries_validation_YYYYMMDD_HHMMSS.md
"""

import sys
import os
import csv
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
# Force load .env with override=True to ensure environment values are injected
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=True)

# Clear any cached LLM instances before starting
from rag_system.llm_singleton import LLMSingleton
LLMSingleton.clear()

from app.rag.pipeline import RAGPipeline
from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryValidator:
    """질문 프리셋 검증기"""

    def __init__(self, csv_path: str = "reports/askable_queries_verified.csv"):
        self.csv_path = csv_path
        self.pipeline = RAGPipeline()
        self.results = []

    def load_queries(self) -> List[Dict[str, Any]]:
        """CSV에서 질문 로드"""
        queries = []

        with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                query = {
                    'query': row['query'],
                    'category': row['category'],
                    'expected_mode': row['expected_mode'],
                    'expected_citations': row['expected_citations'].lower() == 'true',
                    'difficulty': row['difficulty'],
                    'metadata': json.loads(row.get('metadata', '{}'))
                }
                queries.append(query)

        return queries

    def validate_query(self, query_data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """단일 질문 검증"""
        query_text = query_data['query']

        print(f"\n{'='*80}")
        print(f"🧪 질문 {index}: {query_text}")
        print(f"   카테고리: {query_data['category']}")
        print(f"   예상 모드: {query_data['expected_mode']}")
        print("=" * 80)

        start_time = time.time()

        try:
            # RAG 파이프라인 호출
            response = self.pipeline.query(query_text)
            elapsed = time.time() - start_time

            # 결과 분석
            actual_mode = response.metrics.get('mode', 'unknown')
            has_citations = len(response.source_docs) > 0 or len(response.evidence_chunks) > 0
            top_score = response.metrics.get('top_score', 0.0)

            # 답변 미리보기
            answer_preview = response.answer[:200] + "..." if len(response.answer) > 200 else response.answer

            print(f"\n📊 결과:")
            print(f"  모드: {actual_mode}")
            print(f"  최고 점수: {top_score:.3f}")
            print(f"  출처 개수: {len(response.source_docs)}")
            print(f"  응답 시간: {elapsed:.2f}초")
            print(f"\n💬 답변 미리보기:")
            print(f"  {answer_preview}")

            if response.source_docs:
                print(f"\n📚 출처:")
                for i, doc in enumerate(response.source_docs[:3], 1):
                    print(f"  {i}. {doc}")

            # 검증
            mode_match = actual_mode == query_data['expected_mode']
            citation_match = has_citations == query_data['expected_citations']

            status = "✅ PASS" if (mode_match and citation_match) else "❌ FAIL"

            if not mode_match:
                print(f"\n⚠️  모드 불일치: 예상={query_data['expected_mode']}, 실제={actual_mode}")
            if not citation_match:
                print(f"\n⚠️  출처 인용 불일치: 예상={query_data['expected_citations']}, 실제={has_citations}")

            print(f"\n{status}")

            result = {
                'index': index,
                'query': query_text,
                'category': query_data['category'],
                'status': 'PASS' if (mode_match and citation_match) else 'FAIL',
                'expected_mode': query_data['expected_mode'],
                'actual_mode': actual_mode,
                'expected_citations': query_data['expected_citations'],
                'has_citations': has_citations,
                'top_score': top_score,
                'latency': elapsed,
                'answer_length': len(response.answer),
                'source_docs': response.source_docs,
                'mode_match': mode_match,
                'citation_match': citation_match
            }

            self.results.append(result)
            return result

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

            result = {
                'index': index,
                'query': query_text,
                'category': query_data['category'],
                'status': 'ERROR',
                'error': str(e)
            }
            self.results.append(result)
            return result

    def generate_report(self) -> Dict[str, Any]:
        """검증 리포트 생성"""
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        errors = sum(1 for r in self.results if r['status'] == 'ERROR')
        total = len(self.results)

        # 카테고리별 통계
        by_category = {}
        for r in self.results:
            cat = r['category']
            if cat not in by_category:
                by_category[cat] = {'total': 0, 'passed': 0, 'failed': 0, 'errors': 0}

            by_category[cat]['total'] += 1
            if r['status'] == 'PASS':
                by_category[cat]['passed'] += 1
            elif r['status'] == 'FAIL':
                by_category[cat]['failed'] += 1
            else:
                by_category[cat]['errors'] += 1

        # 평균 지표
        valid_results = [r for r in self.results if r['status'] != 'ERROR']
        avg_latency = sum(r.get('latency', 0) for r in valid_results) / len(valid_results) if valid_results else 0
        avg_score = sum(r.get('top_score', 0) for r in valid_results) / len(valid_results) if valid_results else 0

        report = {
            'timestamp': datetime.now().isoformat(),
            'total': total,
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'success_rate': f"{passed/total*100:.1f}%" if total > 0 else "0%",
            'avg_latency': f"{avg_latency:.2f}s",
            'avg_score': f"{avg_score:.3f}",
            'by_category': by_category,
            'results': self.results
        }

        return report

    def export_json_report(self, report: Dict[str, Any], output_path: str):
        """JSON 리포트 저장"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"✅ JSON 리포트 저장: {output_path}")

    def export_markdown_report(self, report: Dict[str, Any], output_path: str):
        """Markdown 리포트 저장"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# AI-CHAT 질문 프리셋 검증 리포트\n\n")
            f.write(f"**검증 일시**: {report['timestamp']}\n")
            f.write(f"**총 질문 수**: {report['total']}개\n\n")

            f.write("## 📊 전체 결과 요약\n\n")
            f.write(f"- ✅ **PASS**: {report['passed']}개\n")
            f.write(f"- ❌ **FAIL**: {report['failed']}개\n")
            f.write(f"- 🔥 **ERROR**: {report['errors']}개\n")
            f.write(f"- 📈 **성공률**: {report['success_rate']}\n\n")

            f.write("## ⏱️ 성능 지표\n\n")
            f.write(f"- **평균 응답 시간**: {report['avg_latency']}\n")
            f.write(f"- **평균 검색 점수**: {report['avg_score']}\n\n")

            f.write("## 📋 카테고리별 통계\n\n")
            f.write("| 카테고리 | 전체 | PASS | FAIL | ERROR | 성공률 |\n")
            f.write("|----------|------|------|------|-------|--------|\n")

            for cat, stats in sorted(report['by_category'].items()):
                success_rate = f"{stats['passed']/stats['total']*100:.1f}%" if stats['total'] > 0 else "0%"
                f.write(f"| {cat} | {stats['total']} | {stats['passed']} | {stats['failed']} | {stats['errors']} | {success_rate} |\n")

            # 실패/에러 상세
            if report['failed'] > 0 or report['errors'] > 0:
                f.write("\n## ❌ 실패/에러 상세\n\n")
                for r in report['results']:
                    if r['status'] != 'PASS':
                        f.write(f"### [{r['index']}] {r['query']}\n\n")
                        f.write(f"- **카테고리**: {r['category']}\n")
                        f.write(f"- **상태**: {r['status']}\n")

                        if r['status'] == 'FAIL':
                            f.write(f"- **예상 모드**: {r['expected_mode']}\n")
                            f.write(f"- **실제 모드**: {r['actual_mode']}\n")
                            f.write(f"- **모드 일치**: {'❌' if not r.get('mode_match') else '✅'}\n")
                            f.write(f"- **출처 인용 일치**: {'❌' if not r.get('citation_match') else '✅'}\n")
                        elif 'error' in r:
                            f.write(f"- **에러**: {r['error']}\n")

                        f.write("\n")

            # 전체 결과 테이블
            f.write("\n## 📝 전체 결과 상세\n\n")
            f.write("| # | 질문 | 카테고리 | 예상 모드 | 실제 모드 | 출처 | 점수 | 시간(s) | 상태 |\n")
            f.write("|---|------|----------|----------|----------|------|------|---------|------|\n")

            for r in report['results']:
                if r['status'] != 'ERROR':
                    citations = "✅" if r.get('has_citations') else "❌"
                    score = f"{r.get('top_score', 0):.3f}"
                    latency = f"{r.get('latency', 0):.2f}"
                    status_icon = "✅" if r['status'] == 'PASS' else "❌"

                    query_short = r['query'][:30] + "..." if len(r['query']) > 30 else r['query']
                    f.write(f"| {r['index']} | {query_short} | {r['category']} | {r['expected_mode']} | {r.get('actual_mode', 'N/A')} | {citations} | {score} | {latency} | {status_icon} |\n")

        print(f"✅ Markdown 리포트 저장: {output_path}")


def main():
    print("=" * 80)
    print("🚀 AI-CHAT 질문 프리셋 검증")
    print("=" * 80)
    print(f"시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"MODE: {os.getenv('MODE', 'AUTO')}")
    print(f"RAG_MIN_SCORE: {os.getenv('RAG_MIN_SCORE', '0.35')}")

    # Validator 초기화
    validator = QueryValidator()

    # 질문 로드
    print("\n📚 질문 프리셋 로드 중...")
    queries = validator.load_queries()
    print(f"   로드 완료: {len(queries)}개 질문")

    # 검증 실행
    print("\n🧪 검증 시작...\n")
    for i, query_data in enumerate(queries, 1):
        validator.validate_query(query_data, i)
        # 질문 간 간격
        if i < len(queries):
            time.sleep(1)

    # 리포트 생성
    print("\n\n" + "=" * 80)
    print("📊 리포트 생성 중...")
    print("=" * 80)

    report = validator.generate_report()

    # 출력
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = f"reports/askable_queries_validation_{timestamp}.json"
    md_path = f"reports/askable_queries_validation_{timestamp}.md"

    validator.export_json_report(report, json_path)
    validator.export_markdown_report(report, md_path)

    # 요약 출력
    print("\n" + "=" * 80)
    print("📊 검증 결과 요약")
    print("=" * 80)
    print(f"\n총 {report['total']}개 질문:")
    print(f"  ✅ PASS: {report['passed']}")
    print(f"  ❌ FAIL: {report['failed']}")
    print(f"  🔥 ERROR: {report['errors']}")
    print(f"\n성공률: {report['success_rate']}")
    print(f"평균 응답 시간: {report['avg_latency']}")
    print(f"평균 검색 점수: {report['avg_score']}")

    # 실패 질문 목록
    if report['failed'] > 0 or report['errors'] > 0:
        print("\n❌ 실패/에러 질문:")
        for r in report['results']:
            if r['status'] != 'PASS':
                print(f"  [{r['index']}] {r['query'][:50]}... ({r['status']})")

    print("\n" + "=" * 80)
    print("✅ 검증 완료!")
    print("=" * 80)
    print(f"\n상세 리포트:")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")

    # 종료 코드 반환
    return 0 if report['failed'] == 0 and report['errors'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
