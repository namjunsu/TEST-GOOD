#!/usr/bin/env python3
"""
8가지 시나리오 기능 점검 스크립트

운영 준비 완료 확인용 - 일반 대화 vs 문서근거 RAG 자동 전환 테스트

사용법:
    python test_8_scenarios.py

    또는 특정 시나리오만:
    python test_8_scenarios.py --scenario 1
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from app.core.logging import get_logger
from app.rag.pipeline import RAGPipeline

logger = get_logger(__name__)


class ScenarioTest:
    """시나리오 테스트 러너"""

    def __init__(self):
        self.pipeline = RAGPipeline()
        self.results = []

    def run_scenario(self,
                    scenario_num: int,
                    title: str,
                    query: str,
                    expected_mode: str,
                    expected_has_citations: bool) -> dict[str, Any]:
        """단일 시나리오 실행

        Args:
            scenario_num: 시나리오 번호
            title: 시나리오 제목
            query: 테스트 질의
            expected_mode: 예상 모드 (chat|rag)
            expected_has_citations: 출처 인용 예상 여부

        Returns:
            결과 딕셔너리
        """
        print("\n" + "=" * 80)
        print(f"🧪 시나리오 {scenario_num}: {title}")
        print("=" * 80)
        print(f"질의: {query}")
        print("-" * 80)

        start_time = time.time()

        try:
            # RAG 파이프라인 호출
            response = self.pipeline.query(query)

            elapsed = time.time() - start_time

            # 결과 분석
            actual_mode = response.metrics.get("mode", "unknown")
            has_citations = len(response.source_docs) > 0 or len(response.evidence_chunks) > 0
            top_score = response.metrics.get("top_score", 0.0)

            # 답변 미리보기 (최대 200자)
            answer_preview = response.answer[:200] + "..." if len(response.answer) > 200 else response.answer

            print("\n📊 결과:")
            print(f"  모드: {actual_mode}")
            print(f"  최고 점수: {top_score:.3f}")
            print(f"  출처 개수: {len(response.source_docs)}")
            print(f"  응답 시간: {elapsed:.2f}초")
            print("\n💬 답변 미리보기:")
            print(f"  {answer_preview}")

            if response.source_docs:
                print("\n📚 출처:")
                for i, doc in enumerate(response.source_docs[:3], 1):
                    print(f"  {i}. {doc}")

            # 검증
            mode_match = actual_mode == expected_mode
            citation_match = has_citations == expected_has_citations

            status = "✅ PASS" if (mode_match and citation_match) else "❌ FAIL"

            if not mode_match:
                print(f"\n⚠️  모드 불일치: 예상={expected_mode}, 실제={actual_mode}")
            if not citation_match:
                print(f"\n⚠️  출처 인용 불일치: 예상={expected_has_citations}, 실제={has_citations}")

            print(f"\n{status}")

            result = {
                "scenario": scenario_num,
                "title": title,
                "query": query,
                "status": "PASS" if (mode_match and citation_match) else "FAIL",
                "actual_mode": actual_mode,
                "expected_mode": expected_mode,
                "has_citations": has_citations,
                "expected_has_citations": expected_has_citations,
                "top_score": top_score,
                "latency": elapsed,
                "answer_length": len(response.answer),
            }

            self.results.append(result)
            return result

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

            result = {
                "scenario": scenario_num,
                "title": title,
                "query": query,
                "status": "ERROR",
                "error": str(e),
            }
            self.results.append(result)
            return result

    def print_summary(self):
        """전체 결과 요약 출력"""
        print("\n\n" + "=" * 80)
        print("📊 전체 시나리오 테스트 결과 요약")
        print("=" * 80)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")
        total = len(self.results)

        print(f"\n총 {total}개 시나리오:")
        print(f"  ✅ PASS: {passed}")
        print(f"  ❌ FAIL: {failed}")
        print(f"  🔥 ERROR: {errors}")
        print(f"\n성공률: {passed / total * 100:.1f}%")

        # 실패한 시나리오 상세
        if failed > 0 or errors > 0:
            print("\n❌ 실패/에러 시나리오:")
            for r in self.results:
                if r["status"] != "PASS":
                    print(f"  [{r['scenario']}] {r['title']}: {r['status']}")
                    if "error" in r:
                        print(f"      Error: {r['error']}")

        # 로그 파일 저장
        log_file = f"reports/scenario_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        Path("reports").mkdir(exist_ok=True, parents=True)

        import json
        with Path(log_file).open("w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                },
                "results": self.results,
            }, f, indent=2, ensure_ascii=False)

        print(f"\n📝 상세 결과 저장: {log_file}")


def main():
    """메인 실행 함수"""

    print("=" * 80)
    print("🚀 AI-CHAT 운영 준비 8가지 시나리오 테스트")
    print("=" * 80)
    print(f"시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"MODE: {os.getenv('MODE', 'AUTO')}")
    print(f"RAG_MIN_SCORE: {os.getenv('RAG_MIN_SCORE', '0.35')}")
    print(f"ALLOW_UNGROUNDED_CHAT: {os.getenv('ALLOW_UNGROUNDED_CHAT', 'true')}")

    runner = ScenarioTest()

    # ========================================================================
    # 시나리오 정의
    # ========================================================================

    scenarios = [
        # 1. 일반 대화: 문서 인용 없이 답변
        {
            "num": 1,
            "title": "일반 대화 (문서 인용 없음)",
            "query": "1+1은?",
            "expected_mode": "chat",
            "expected_has_citations": False,
        },

        # 2. 회사 문서 검색: 문서 인용 포함
        {
            "num": 2,
            "title": "회사 문서 검색 (문서 인용 포함)",
            "query": "2024-08-14 기술관리팀 방송시스템 소모품 구매 검토서 요약해줘",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },

        # 3. 정책 질의: 관련 문서 인용
        {
            "num": 3,
            "title": "정책 질의 (관련 문서 인용)",
            "query": "NVR 저장용량 산정 기준과 HDD 교체 주기는?",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },

        # 4. 인프라 구성: 다이어그램 섹션 인용
        {
            "num": 4,
            "title": "인프라 구성 (다이어그램 섹션 인용)",
            "query": "Tri-Level Sync/Black Burst 신호 분배 구성 요약",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },

        # 5. 사례 비교: 해당 보고서 인용
        {
            "num": 5,
            "title": "사례 비교 (해당 보고서 인용)",
            "query": "뉴스 스튜디오 지미집 Control Box 수리 건 핵심 원인/조치",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },

        # 6. 필터 검색: 메타필터 동작
        {
            "num": 6,
            "title": "필터 검색 (메타필터 동작)",
            "query": "기안자=남준수, 2024년 문서만 요약 리스트",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },

        # 7. 무근거 방지: 근거 없으면 '근거 없음'
        {
            "num": 7,
            "title": "무근거 방지 (근거 없음 처리)",
            "query": "APEX 중계 동시통역 라우팅 정확한 연결 도면?",
            "expected_mode": "chat",  # 근거 없으면 chat 모드로 폴백
            "expected_has_citations": False,
        },

        # 8. 긴 문서 요약: TL;DR
        {
            "num": 8,
            "title": "긴 문서 요약 (TL;DR)",
            "query": "방송시스템 소모품 구매 검토서 3문장 TL;DR",
            "expected_mode": "rag",
            "expected_has_citations": True,
        },
    ]

    # 특정 시나리오만 실행할지 확인
    if "--scenario" in sys.argv:
        idx = sys.argv.index("--scenario")
        if idx + 1 < len(sys.argv):
            scenario_num = int(sys.argv[idx + 1])
            scenarios = [s for s in scenarios if s["num"] == scenario_num]
            if not scenarios:
                print(f"❌ 시나리오 {scenario_num}을 찾을 수 없습니다.")
                return 1

    # 시나리오 실행
    for scenario in scenarios:
        runner.run_scenario(
            scenario["num"],
            scenario["title"],
            scenario["query"],
            scenario["expected_mode"],
            scenario["expected_has_citations"],
        )

        # 시나리오 간 간격
        if scenario != scenarios[-1]:
            time.sleep(1)

    # 결과 요약
    runner.print_summary()

    # 종료 코드 반환
    failed_count = sum(1 for r in runner.results if r["status"] != "PASS")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
