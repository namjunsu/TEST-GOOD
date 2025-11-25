#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
DB 기반 질문 프리셋 자동 생성기

현재 metadata.db에 존재하는 실제 문서만을 기준으로
검증 가능한 질문 프리셋을 자동 생성합니다.

출력:
- docs/ASKABLE_QUERIES.md
- reports/askable_queries_verified.csv
- ui/presets.json
"""

import sqlite3
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict


class QueryGenerator:
    """실제 문서 기반 질문 생성기"""

    def __init__(self, db_path: str = "metadata.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        # 환경변수에서 설정 로드
        self.rag_min_score = float(os.getenv("RAG_MIN_SCORE", "0.35"))
        self.require_citations = os.getenv("REQUIRE_CITATIONS", "true").lower() == "true"

    def extract_equipment_keywords(self) -> Dict[str, int]:
        """문서에서 실제 장비 키워드 추출"""
        self.cursor.execute("""
            SELECT keywords FROM documents
            WHERE keywords IS NOT NULL AND keywords != '[]'
        """)

        equipment = defaultdict(int)
        for row in self.cursor.fetchall():
            try:
                kw_list = json.loads(row['keywords'])
                for kw in kw_list:
                    # 장비명으로 보이는 키워드만 (한글+영문 혼합, 최소 2자)
                    if len(kw) >= 2 and not kw.isdigit():
                        equipment[kw] += 1
            except:
                pass

        # 빈도순 정렬
        return dict(sorted(equipment.items(), key=lambda x: x[1], reverse=True))

    def get_document_summaries(self) -> List[Dict[str, Any]]:
        """문서 요약 정보 추출"""
        self.cursor.execute("""
            SELECT
                filename,
                title,
                drafter,
                date,
                year,
                category,
                doctype,
                keywords,
                text_preview
            FROM documents
            WHERE filename IS NOT NULL
            ORDER BY date DESC
            LIMIT 100
        """)

        summaries = []
        for row in self.cursor.fetchall():
            doc = dict(row)
            # 키워드 파싱
            try:
                doc['keywords'] = json.loads(doc['keywords'] or '[]')
            except:
                doc['keywords'] = []
            summaries.append(doc)

        return summaries

    def generate_query_templates(self, summaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """실제 문서 기반 질문 템플릿 생성"""
        queries = []

        # 1. 일반 대화 (문서 불필요)
        queries.extend([
            {
                "query": "안녕하세요",
                "category": "일반 대화",
                "expected_mode": "chat",
                "expected_citations": False,
                "difficulty": "easy"
            },
            {
                "query": "1 + 1은?",
                "category": "일반 대화",
                "expected_mode": "chat",
                "expected_citations": False,
                "difficulty": "easy"
            }
        ])

        # 2. 작성자별 문서 검색 (실제 작성자만)
        drafters = {}
        for doc in summaries:
            if doc['drafter'] and doc['drafter'].strip():
                drafters[doc['drafter']] = drafters.get(doc['drafter'], 0) + 1

        top_drafters = sorted(drafters.items(), key=lambda x: x[1], reverse=True)[:3]
        for drafter, count in top_drafters:
            queries.append({
                "query": f"{drafter} 작성 문서 요약해줘",
                "category": "작성자 검색",
                "expected_mode": "rag",
                "expected_citations": True,
                "difficulty": "medium",
                "metadata": {"drafter": drafter, "expected_count": count}
            })

        # 3. 연도별 문서 검색
        years = {}
        for doc in summaries:
            if doc['year']:
                years[doc['year']] = years.get(doc['year'], 0) + 1

        top_years = sorted(years.items(), key=lambda x: x[0], reverse=True)[:3]
        for year, count in top_years:
            queries.append({
                "query": f"{year}년 작성된 문서 리스트",
                "category": "연도별 검색",
                "expected_mode": "rag",
                "expected_citations": True,
                "difficulty": "medium",
                "metadata": {"year": year, "expected_count": count}
            })

        # 4. 특정 문서 요약 (파일명 기반)
        for doc in summaries[:10]:  # 상위 10개
            filename = doc['filename']
            # 파일명에서 핵심 키워드 추출
            match = re.search(r'\d{4}-\d{2}-\d{2}_(.+)\.pdf', filename)
            if match:
                core_name = match.group(1).replace('_', ' ')
                queries.append({
                    "query": f"{core_name} 관련 문서 요약해줘",
                    "category": "문서 요약",
                    "expected_mode": "rag",
                    "expected_citations": True,
                    "difficulty": "medium",
                    "metadata": {"filename": filename}
                })

        # 5. 장비별 문서 검색 (실제 키워드 기반)
        equipment_keywords = self.extract_equipment_keywords()
        top_equipment = list(equipment_keywords.items())[:10]

        for equipment, count in top_equipment:
            if count >= 3:  # 최소 3개 이상 문서에 등장
                queries.append({
                    "query": f"{equipment} 관련 구매/수리 내역은?",
                    "category": "장비 검색",
                    "expected_mode": "rag",
                    "expected_citations": True,
                    "difficulty": "hard",
                    "metadata": {"equipment": equipment, "expected_count": count}
                })

        # 6. 카테고리별 검색
        categories = {}
        for doc in summaries:
            if doc['category'] and doc['category'].strip() and doc['category'] != ':':
                categories[doc['category']] = categories.get(doc['category'], 0) + 1

        for category, count in categories.items():
            if count >= 5:  # 최소 5개 이상
                queries.append({
                    "query": f"{category} 카테고리 문서 요약",
                    "category": "카테고리 검색",
                    "expected_mode": "rag",
                    "expected_citations": True,
                    "difficulty": "medium",
                    "metadata": {"category": category, "expected_count": count}
                })

        # 7. 무근거 질문 (DB에 없는 내용)
        queries.extend([
            {
                "query": "APEX 중계 동시통역 라우팅 정확한 연결 도면?",
                "category": "무근거 방지",
                "expected_mode": "chat",
                "expected_citations": False,
                "difficulty": "hard"
            },
            {
                "query": "존재하지_않는_장비_12345의 구매 이력은?",
                "category": "무근거 방지",
                "expected_mode": "chat",
                "expected_citations": False,
                "difficulty": "hard"
            }
        ])

        return queries

    def export_markdown(self, queries: List[Dict[str, Any]], output_path: str):
        """Markdown 포맷 출력"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# AI-CHAT 질문 가능 목록 (Askable Queries)\n\n")
            f.write(f"**생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**DB 기준**: metadata.db (483개 문서)\n")
            f.write(f"**RAG_MIN_SCORE**: {self.rag_min_score}\n")
            f.write(f"**REQUIRE_CITATIONS**: {self.require_citations}\n\n")
            f.write("---\n\n")

            f.write("## 사용 방법\n\n")
            f.write("이 문서는 현재 DB에 존재하는 실제 문서만을 기준으로 생성된 **검증 가능한 질문 목록**입니다.\n\n")
            f.write("- ✅ **RAG 모드**: 문서 검색 + 출처 인용 응답\n")
            f.write("- 💬 **Chat 모드**: 일반 대화 (문서 불필요)\n\n")
            f.write("---\n\n")

            # 카테고리별 그룹화
            by_category = defaultdict(list)
            for q in queries:
                by_category[q['category']].append(q)

            for category, items in sorted(by_category.items()):
                f.write(f"## {category}\n\n")
                for i, q in enumerate(items, 1):
                    mode_icon = "✅" if q['expected_mode'] == "rag" else "💬"
                    f.write(f"### {mode_icon} {i}. {q['query']}\n\n")
                    f.write(f"- **예상 모드**: {q['expected_mode']}\n")
                    f.write(f"- **출처 인용**: {'예' if q['expected_citations'] else '아니오'}\n")
                    f.write(f"- **난이도**: {q['difficulty']}\n")

                    if 'metadata' in q:
                        f.write(f"- **메타데이터**: {json.dumps(q['metadata'], ensure_ascii=False)}\n")

                    f.write("\n")

        print(f"✅ Markdown 저장: {output_path}")

    def export_csv(self, queries: List[Dict[str, Any]], output_path: str):
        """CSV 포맷 출력"""
        import csv
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "query",
                "category",
                "expected_mode",
                "expected_citations",
                "difficulty",
                "metadata"
            ])

            for q in queries:
                writer.writerow([
                    q['query'],
                    q['category'],
                    q['expected_mode'],
                    q['expected_citations'],
                    q['difficulty'],
                    json.dumps(q.get('metadata', {}), ensure_ascii=False)
                ])

        print(f"✅ CSV 저장: {output_path}")

    def export_json(self, queries: List[Dict[str, Any]], output_path: str):
        """JSON 포맷 출력 (UI 프리셋용)"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # UI용으로 간소화
        presets = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "total_queries": len(queries),
            "presets": []
        }

        for q in queries:
            preset = {
                "id": f"q_{len(presets['presets']) + 1}",
                "text": q['query'],
                "category": q['category'],
                "mode": q['expected_mode'],
                "difficulty": q['difficulty']
            }

            if 'metadata' in q:
                preset['metadata'] = q['metadata']

            presets['presets'].append(preset)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2, ensure_ascii=False)

        print(f"✅ JSON 저장: {output_path}")

    def close(self):
        """DB 연결 종료"""
        self.conn.close()


def main():
    print("=" * 80)
    print("🤖 AI-CHAT 질문 프리셋 자동 생성기")
    print("=" * 80)
    print()

    # 생성기 초기화
    generator = QueryGenerator()

    # 문서 요약 추출
    print("📚 문서 메타데이터 추출 중...")
    summaries = generator.get_document_summaries()
    print(f"   추출 완료: {len(summaries)}개 문서")

    # 질문 생성
    print("\n🔍 질문 프리셋 생성 중...")
    queries = generator.generate_query_templates(summaries)
    print(f"   생성 완료: {len(queries)}개 질문")

    # 카테고리별 통계
    by_category = defaultdict(int)
    by_mode = defaultdict(int)
    for q in queries:
        by_category[q['category']] += 1
        by_mode[q['expected_mode']] += 1

    print("\n📊 생성 통계:")
    print(f"   카테고리별:")
    for cat, cnt in sorted(by_category.items()):
        print(f"     - {cat}: {cnt}개")
    print(f"   모드별:")
    for mode, cnt in sorted(by_mode.items()):
        print(f"     - {mode}: {cnt}개")

    # 출력
    print("\n💾 파일 저장 중...")
    generator.export_markdown(queries, "docs/ASKABLE_QUERIES.md")
    generator.export_csv(queries, "reports/askable_queries_verified.csv")
    generator.export_json(queries, "ui/presets.json")

    generator.close()

    print("\n" + "=" * 80)
    print("✅ 질문 프리셋 생성 완료!")
    print("=" * 80)
    print()
    print("다음 단계:")
    print("  1. 생성된 질문 검토: docs/ASKABLE_QUERIES.md")
    print("  2. 검증 실행: python scripts/scenario_validation.py")
    print("  3. UI 프리셋 적용: ui/presets.json")


if __name__ == "__main__":
    main()
