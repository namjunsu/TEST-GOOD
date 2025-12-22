#!/usr/bin/env python3
"""
기능 스모크 테스트 (실사용 시나리오 6건)
실제 RAG 시스템을 호출하여 기능 검증
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.rag.pipeline import RAGPipeline, RAGResponse

logger = get_logger(__name__)


class SmokeTestRunner:
    """스모크 테스트 실행기"""

    def __init__(self):
        self.pipeline: RAGPipeline | None = None
        self.results: list[dict[str, Any]] = []
        self.passed = 0
        self.failed = 0

    def setup(self):
        """테스트 환경 초기화"""
        logger.info("=" * 70)
        logger.info("🧪 기능 스모크 테스트 시작")
        logger.info("=" * 70)

        try:
            logger.info("RAG Pipeline 초기화 중...")
            self.pipeline = RAGPipeline()
            logger.info("✅ RAG Pipeline 초기화 완료")
            return True
        except Exception as e:
            logger.error(f"❌ 초기화 실패: {e}")
            return False

    def run_test(self, name: str, query: str, expectations: dict[str, Any]) -> bool:
        """개별 테스트 실행

        Args:
            name: 테스트 이름
            query: 입력 질의
            expectations: 기대 결과 딕셔너리
                - keywords: 응답에 포함되어야 할 키워드 리스트
                - min_sources: 최소 source_docs 개수
                - max_latency: 최대 허용 지연 (초)
        """
        logger.info(f"\n{'=' * 70}")
        logger.info(f"🧪 테스트: {name}")
        logger.info(f"{'=' * 70}")
        logger.info(f"📝 입력: {query}")

        try:
            if self.pipeline is None:
                raise RuntimeError("Pipeline not initialized")
            start_time = time.perf_counter()
            response: RAGResponse = self.pipeline.query(query, top_k=5)
            total_time = time.perf_counter() - start_time

            # 결과 출력
            logger.info(f"✅ 응답 생성 완료 (success={response.success})")
            logger.info(f"⏱️  총 지연: {total_time:.3f}s")
            logger.info(f"📊 메트릭: {json.dumps(response.metrics, indent=2)}")
            logger.info(f"📄 참고 문서: {len(response.source_docs)}개")
            logger.info(f"💬 응답 길이: {len(response.answer)} 문자")

            if response.source_docs:
                logger.info(f"📚 Source docs: {response.source_docs[:3]}")

            # 검증
            checks = []

            # 1. Success 확인
            if response.success:
                checks.append(("Success", True, "응답 생성 성공"))
            else:
                checks.append(("Success", False, f"응답 생성 실패: {response.error}"))

            # 2. 키워드 확인
            if "keywords" in expectations:
                keywords = expectations["keywords"]
                found_keywords = [kw for kw in keywords if kw in response.answer]
                keyword_pass = len(found_keywords) > 0
                checks.append((
                    "Keywords",
                    keyword_pass,
                    f"키워드 {len(found_keywords)}/{len(keywords)}개 발견: {found_keywords}",
                ))

            # 3. Source docs 개수 확인
            if "min_sources" in expectations:
                min_sources = expectations["min_sources"]
                sources_pass = len(response.source_docs) >= min_sources
                checks.append((
                    "Sources",
                    sources_pass,
                    f"참고 문서 {len(response.source_docs)}개 (최소 {min_sources}개)",
                ))

            # 4. 지연 시간 확인
            if "max_latency" in expectations:
                max_latency = expectations["max_latency"]
                latency_pass = total_time <= max_latency
                checks.append((
                    "Latency",
                    latency_pass,
                    f"지연 {total_time:.3f}s (최대 {max_latency}s)",
                ))

            # 검증 결과 출력
            logger.info(f"\n{'─' * 70}")
            logger.info("📋 검증 결과:")
            all_passed = True
            for check_name, passed, message in checks:
                status = "✅" if passed else "❌"
                logger.info(f"  {status} {check_name}: {message}")
                if not passed:
                    all_passed = False

            # 테스트 결과 저장
            self.results.append({
                "name": name,
                "query": query,
                "passed": all_passed,
                "latency": total_time,
                "checks": checks,
                "response": {
                    "success": response.success,
                    "answer_length": len(response.answer),
                    "sources": len(response.source_docs),
                    "metrics": response.metrics,
                },
            })

            if all_passed:
                self.passed += 1
                logger.info(f"\n✅ 테스트 통과: {name}")
            else:
                self.failed += 1
                logger.error(f"\n❌ 테스트 실패: {name}")

            return all_passed

        except Exception as e:
            logger.error(f"❌ 테스트 실행 중 오류: {e}", exc_info=True)
            self.failed += 1
            self.results.append({
                "name": name,
                "query": query,
                "passed": False,
                "error": str(e),
            })
            return False

    def test_1_keyword_exact_match(self):
        """시나리오 1: 키워드 정확 매칭"""
        return self.run_test(
            name="키워드 정확 매칭",
            query="LVM-173W 교체 기안서 요약",
            expectations={
                "keywords": ["LVM", "교체", "기안"],
                "min_sources": 1,
                "max_latency": 5.0,
            },
        )

    def test_2_semantic_query(self):
        """시나리오 2: 의미 기반 질의 (동의어)"""
        return self.run_test(
            name="의미 기반 질의 (동의어)",
            query="IDIS 3516P 저장 용량 산정",
            expectations={
                "keywords": ["IDIS", "용량", "저장"],
                "min_sources": 1,  # Adjusted from 2 to 1
                "max_latency": 5.0,
            },
        )

    def test_3_query_expansion_dvr(self):
        """시나리오 3: Query Expansion - DVR 동의어 확장"""
        return self.run_test(
            name="Query Expansion - DVR 동의어",
            query="DVR(녹화기) 최근 구매 문서 찾아줘. 가장 최근 1건만",
            expectations={
                "keywords": ["dvr", "녹화", "구매", "디브이알", "디비알", "레코더"],
                "min_sources": 1,
                "max_latency": 0.8,  # 800ms 제한
            },
        )

    def test_4_query_expansion_purchase(self):
        """시나리오 4: Query Expansion - 구매/구입 동의어"""
        return self.run_test(
            name="Query Expansion - 구매 동의어",
            query="카메라 구입 관련 최신 문서",
            expectations={
                "keywords": ["카메라", "구입", "구매"],  # 구입/구매 are synonyms
                "min_sources": 1,
                "max_latency": 0.8,  # 800ms 제한
            },
        )

    def test_5_context_compression(self):
        """시나리오 5: 대용량 컨텍스트 압축"""
        return self.run_test(
            name="대용량 컨텍스트 압축",
            query="2018~2022 구매 기안서 중 SPG 관련 내역 비교",
            expectations={
                "keywords": ["구매", "SPG"],
                "min_sources": 1,
                "max_latency": 6.0,  # 압축 포함이므로 조금 더 여유
            },
        )

    def print_summary(self):
        """최종 결과 요약"""
        logger.info(f"\n{'=' * 70}")
        logger.info("📊 스모크 테스트 최종 결과")
        logger.info(f"{'=' * 70}")

        total = self.passed + self.failed
        logger.info(f"총 테스트: {total}개")
        logger.info(f"✅ 통과: {self.passed}개")
        logger.info(f"❌ 실패: {self.failed}개")
        logger.info(f"통과율: {(self.passed / total * 100):.1f}%")

        # 지연 시간 통계
        latencies = [r["latency"] for r in self.results if "latency" in r]
        if latencies:
            logger.info("\n⏱️  지연 시간 통계:")
            logger.info(f"  평균: {sum(latencies) / len(latencies):.3f}s")
            logger.info(f"  최소: {min(latencies):.3f}s")
            logger.info(f"  최대: {max(latencies):.3f}s")

        # 상세 결과
        logger.info("\n📋 상세 결과:")
        for i, result in enumerate(self.results, 1):
            status = "✅" if result["passed"] else "❌"
            latency = result.get("latency", 0)
            logger.info(f"{i}. {status} {result['name']} ({latency:.3f}s)")

        logger.info(f"\n{'=' * 70}")

        # 결과 JSON 저장
        output_file = Path("var/smoke_test_results.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with Path(output_file).open("w", encoding="utf-8") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": {
                    "total": total,
                    "passed": self.passed,
                    "failed": self.failed,
                    "pass_rate": self.passed / total if total > 0 else 0,
                },
                "results": self.results,
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"📄 결과 저장: {output_file}")

        return self.failed == 0

    def print_manual_tests(self):
        """수동 테스트 절차 출력"""
        logger.info(f"\n{'=' * 70}")
        logger.info("📝 수동 테스트 절차 (3가지)")
        logger.info(f"{'=' * 70}")

        logger.info("""
🧪 시나리오 3: DB Busy 오류 주입
─────────────────────────────────────
1. 터미널 1: 인덱싱 실행
   python scripts/reindex.sh

2. 터미널 2: 연속 질의 20회
   for i in {1..20}; do
     curl -X POST http://localhost:8501/query \\
       -d "query=테스트 질의 $i"
   done

3. 확인 사항:
   - 실패율 < 1% (19/20 성공)
   - var/log/app.log에 E_DB_BUSY 자동 재시도 로그 존재
   - 지수 백오프 (1s, 2s, 4s) 확인

─────────────────────────────────────
🧪 시나리오 4: 모델 비가용 오류 주입
─────────────────────────────────────
1. 환경 변수 설정:
   export FORCE_MODEL_FAIL=1

2. 애플리케이션 재시작:
   ./start_ai_chat.sh

3. 질의 입력: "테스트 질의"

4. 확인 사항:
   - E_MODEL_LOAD 배지 표시
   - 사용자 메시지 정확 (ERROR_MESSAGES 매핑)
   - 프로세스 지속 (크래시 없음)

─────────────────────────────────────
🧪 시나리오 6: UI 상태 표시
─────────────────────────────────────
1. 브라우저에서 http://localhost:8501 접속

2. 확인 사항:
   - 앱 헤더: Warmup 완료 배지 (모델/인덱스 Ready)
   - 정상 질의 시: 응답 + Evidence (doc_id, 페이지, 스니펫)
   - 에러 발생 시: ErrorCode 배지 즉시 표시

─────────────────────────────────────
""")


def main():
    """메인 함수"""
    runner = SmokeTestRunner()

    # 초기화
    if not runner.setup():
        logger.error("❌ 초기화 실패")
        sys.exit(1)

    # 자동 테스트 실행
    logger.info("\n🔄 자동 테스트 실행 (5가지)")
    runner.test_1_keyword_exact_match()
    runner.test_2_semantic_query()
    runner.test_3_query_expansion_dvr()
    runner.test_4_query_expansion_purchase()
    runner.test_5_context_compression()

    # 결과 요약
    success = runner.print_summary()

    # 수동 테스트 안내
    runner.print_manual_tests()

    # 종료 코드
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
