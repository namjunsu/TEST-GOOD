"""티비로직 문서 미인식 문제 진단 스크립트

검사 항목:
1. BM25 인덱스에 TVLogic 문서 청크 존재 여부
2. 청크 내용에 "TVLogic" / "티비로직" 키워드 포함 여부
3. 메타데이터 DB text_preview 품질 확인
4. 검색 결과 컨텍스트 추출 시뮬레이션

사용법:
    python scripts/diagnose_tvlogic_issue.py
"""

import sqlite3
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.rag.retrievers.hybrid import HybridRetriever
from app.data.metadata_db import MetadataDB
from app.rag.utils.context_hydrator import hydrate_context


def check_bm25_index():
    """하이브리드 검색 인덱스 확인"""
    print("=" * 60)
    print("1. 하이브리드 검색 인덱스 확인")
    print("=" * 60)

    try:
        retriever = HybridRetriever()
    except Exception as e:
        print(f"\n❌ HybridRetriever 초기화 실패: {e}")
        return

    # 검색어: "티비로직", "TVLogic", "남준수"
    for keyword in ["티비로직", "TVLogic", "남준수"]:
        try:
            results = retriever.search(keyword, top_k=10)
        except Exception as e:
            print(f"\n❌ 검색 실패 ('{keyword}'): {e}")
            continue

        print(f"\n🔍 검색어: '{keyword}' (결과: {len(results)}건)")

        found_tvlogic = False
        for i, r in enumerate(results, 1):
            filename = r.get("filename", "N/A")
            if "TVLogic" in filename or "티비로직" in filename:
                found_tvlogic = True
                # 여러 필드 시도 (content, snippet, text)
                text_preview = (r.get("content") or r.get("snippet") or r.get("text") or "")[:200]
                score = r.get("score", 0)

                print(f"\n  #{i} [HIT] {filename}")
                print(f"     Score: {score:.2f}")
                print(f"     Text: {text_preview}")

                # 키워드 포함 여부 확인
                has_tvlogic = "tvlogic" in text_preview.lower() or "티비로직" in text_preview or "모니터" in text_preview
                print(f"     키워드 포함: {'✅ YES' if has_tvlogic else '❌ NO'}")

        if not found_tvlogic:
            print(f"   ⚠️  TVLogic 파일명을 가진 결과 없음")


def check_metadata_db():
    """메타데이터 DB text_preview 확인"""
    print("\n" + "=" * 60)
    print("2. 메타데이터 DB text_preview 확인")
    print("=" * 60)

    try:
        db = MetadataDB()
        conn = db._get_conn()
    except Exception as e:
        print(f"\n❌ MetadataDB 연결 실패: {e}")
        return

    try:
        cursor = conn.execute("""
            SELECT filename, text_preview, drafter, date
            FROM documents
            WHERE filename LIKE '%TVLogic%' OR filename LIKE '%티비로직%'
            ORDER BY date DESC
        """)

        rows = cursor.fetchall()
        print(f"\n📊 TVLogic 관련 문서: {len(rows)}건")

        if len(rows) == 0:
            print("   ⚠️  메타데이터 DB에 TVLogic 문서가 없습니다!")
            return

        for i, row in enumerate(rows, 1):
            filename = row["filename"]
            preview = row["text_preview"] or ""
            drafter = row["drafter"]
            date = row["date"]

            print(f"\n  #{i} {filename}")
            print(f"     기안자: {drafter} | 날짜: {date}")
            print(f"     Preview (100자): {preview[:100]}")

            # 키워드 포함 여부
            has_keyword = "tvlogic" in preview.lower() or "티비로직" in preview or "모니터" in preview
            print(f"     핵심 내용 포함: {'✅ YES' if has_keyword else '❌ NO (양식만!)'}")

    except Exception as e:
        print(f"\n❌ 쿼리 실행 실패: {e}")


def simulate_context_extraction():
    """실제 컨텍스트 추출 과정 시뮬레이션"""
    print("\n" + "=" * 60)
    print("3. 컨텍스트 추출 시뮬레이션")
    print("=" * 60)

    try:
        retriever = HybridRetriever()
        results = retriever.search("2025년 남준수 티비로직", top_k=5)
    except Exception as e:
        print(f"\n❌ 검색 실패: {e}")
        return

    print(f"\n검색 결과: {len(results)}건")

    if len(results) == 0:
        print("   ⚠️  검색 결과가 없습니다!")
        return

    # 검색 결과 상세
    print("\n검색 결과 상세:")
    for i, r in enumerate(results, 1):
        filename = r.get("filename", "N/A")
        score = r.get("score", 0)
        print(f"  #{i} {filename} (score={score:.2f})")

    try:
        # hydrate_context로 실제 컨텍스트 생성
        context, metrics = hydrate_context(results, max_len=3000, mode="qa")
    except Exception as e:
        print(f"\n❌ 컨텍스트 추출 실패: {e}")
        return

    print(f"\n📝 생성된 컨텍스트 (길이: {len(context)}자)")
    print(f"   사용된 청크: {metrics.get('chunks_used', 0)}/{metrics.get('chunks_received', 0)}")
    print(f"   폴백 체인: {metrics.get('fallback_chain', [])}")
    print(f"\n   컨텍스트 내용 (앞 500자):")
    print("   " + "-" * 58)
    for line in context[:500].split("\n"):
        print(f"   {line}")
    print("   " + "-" * 58)

    # 티비로직 키워드 포함 여부
    has_tvlogic = "tvlogic" in context.lower() or "티비로직" in context
    print(f"\n   컨텍스트에 '티비로직' 포함: {'✅ YES' if has_tvlogic else '❌ NO'}")


def print_diagnosis_summary():
    """진단 요약 및 권장 조치"""
    print("\n" + "=" * 60)
    print("📋 진단 요약 및 권장 조치")
    print("=" * 60)
    print("""
진단 결과를 바탕으로 다음 중 해당하는 시나리오를 확인하세요:

[시나리오 A] BM25 인덱스에 TVLogic 청크 없음
  증상: BM25 검색 결과에 TVLogic 파일명이 없거나, 있어도 text가 비어있음
  원인: 인덱싱 실패 또는 OCR 품질 문제
  해결: BM25 인덱스 재구축
    → python scripts/build_index.py --force-rebuild

[시나리오 B] text_preview가 양식만 포함
  증상: 메타데이터 DB의 text_preview에 "기안서(미디어텍양식)..." 같은 양식만 있음
  원인: PDF 첫 페이지 파싱 시 양식 텍스트만 추출됨
  해결: clean_text_preview() 함수 개선
    → app/rag/handlers/response.py 수정

[시나리오 C] BM25 청크는 있지만 컨텍스트에 포함 안 됨
  증상: BM25 검색 결과에는 TVLogic 있는데, 최종 컨텍스트에는 없음
  원인: 폴백 체인에서 text_preview가 먼저 선택됨
  해결: 폴백 체인 순서 조정
    → app/rag/utils/context_hydrator.py 수정

[시나리오 D] 복합 원인
  증상: 여러 문제가 동시에 발생
  해결: 시나리오 B + C 동시 적용
""")


def main():
    """메인 진단 프로세스"""
    print("\n" + "🔍 티비로직 문서 미인식 문제 진단 시작 " + "\n")

    check_bm25_index()
    check_metadata_db()
    simulate_context_extraction()

    print("\n" + "=" * 60)
    print("✅ 진단 완료")
    print("=" * 60)

    print_diagnosis_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  진단이 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
