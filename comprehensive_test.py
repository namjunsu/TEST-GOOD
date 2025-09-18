#!/usr/bin/env python3
"""
종합 테스트 스크립트
다양한 질문으로 시스템 테스트
"""

import sys
import time
import json
from datetime import datetime
from perfect_rag import PerfectRAG

def test_queries():
    """다양한 테스트 질문들"""
    return [
        # 연도별 검색
        ("2020년 구매 문서 목록 보여줘", "document"),
        ("2019년에 구매한 장비들 정리해줘", "document"),
        ("2017년 수리 문서 찾아줘", "document"),

        # 카테고리별 검색
        ("구매 관련 문서 최근 5개 보여줘", "document"),
        ("수리 보수 관련 문서 요약해줘", "document"),
        ("폐기 관련 문서 있나?", "document"),

        # 특정 장비 검색
        ("카메라 관련 구매 문서 찾아줘", "document"),
        ("중계차 관련 문서 모두 보여줘", "document"),
        ("UPS 교체 관련 문서 있어?", "document"),

        # 금액 관련
        ("2020년 총 구매 금액 얼마야?", "document"),
        ("가장 비싼 구매 건은 뭐야?", "document"),

        # 자산 검색 (Asset 모드)
        ("중계차에 있는 장비 목록 보여줘", "asset"),
        ("광화문 스튜디오 장비 현황", "asset"),
        ("신승만 차장이 관리하는 장비", "asset"),
        ("2020년 이전 구입한 장비들", "asset"),

        # 복합 질문
        ("2019년부터 2021년까지 카메라 구매 내역", "document"),
        ("스튜디오 조명 관련 모든 문서", "document"),
        ("영상취재팀 관련 구매 및 수리 문서", "document"),

        # 내용 분석 질문
        ("중계차 노후 보수 관련 내용 정리해줘", "document"),
        ("방송장비 구매 절차가 어떻게 되는지 설명해줘", "document"),
    ]

def run_test(rag, query, mode, test_num):
    """단일 테스트 실행"""
    print(f"\n{'='*80}")
    print(f"테스트 #{test_num}: {query}")
    print(f"모드: {mode}")
    print('-'*80)

    start_time = time.time()

    try:
        # 실제 질문 처리
        result = rag.answer(query, mode=mode)

        elapsed = time.time() - start_time

        # 결과 분석
        result_lines = result.split('\n')

        print(f"⏱️ 응답 시간: {elapsed:.2f}초")
        print(f"📝 응답 길이: {len(result)}자")
        print(f"📄 응답 라인 수: {len(result_lines)}")

        # 응답 내용 출력 (처음 500자)
        print("\n📌 응답 내용:")
        if len(result) > 500:
            print(result[:500] + "...[생략]...")
        else:
            print(result)

        # 응답 품질 체크
        quality_check = {
            "has_content": len(result) > 50,
            "not_error": "❌" not in result and "찾을 수 없" not in result,
            "has_structure": any(marker in result for marker in ["📌", "•", "-", "1.", "##"]),
            "response_time": elapsed < 10,
        }

        print(f"\n✅ 품질 체크:")
        for check, passed in quality_check.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}: {passed}")

        return {
            "query": query,
            "mode": mode,
            "elapsed": elapsed,
            "result_length": len(result),
            "quality_checks": quality_check,
            "success": all(quality_check.values()),
            "sample": result[:200]
        }

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return {
            "query": query,
            "mode": mode,
            "error": str(e),
            "success": False
        }

def main():
    print("🚀 종합 테스트 시작...")
    print(f"시작 시간: {datetime.now()}")

    # RAG 시스템 초기화
    print("\n📚 RAG 시스템 로딩 중...")
    rag = PerfectRAG()
    print(f"✅ 시스템 준비 완료")
    print(f"  - PDF 파일: {len(rag.pdf_files)}개")
    print(f"  - TXT 파일: {len(rag.txt_files)}개")
    print(f"  - 캐시 엔트리: {len(rag.metadata_cache)}개")

    # 테스트 실행
    test_cases = test_queries()
    results = []

    for i, (query, mode) in enumerate(test_cases, 1):
        result = run_test(rag, query, mode, i)
        results.append(result)

        # 잠시 대기 (서버 부하 방지)
        if i < len(test_cases):
            time.sleep(1)

    # 결과 요약
    print("\n" + "="*80)
    print("📊 테스트 결과 요약")
    print("="*80)

    successful = sum(1 for r in results if r.get("success", False))
    failed = len(results) - successful

    print(f"✅ 성공: {successful}/{len(results)}")
    print(f"❌ 실패: {failed}/{len(results)}")

    # 실패한 케이스 상세
    if failed > 0:
        print("\n❌ 실패한 테스트:")
        for r in results:
            if not r.get("success", False):
                print(f"  - {r['query']}")
                if "error" in r:
                    print(f"    오류: {r['error']}")

    # 평균 응답 시간
    response_times = [r.get("elapsed", 0) for r in results if "elapsed" in r]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        print(f"\n⏱️ 평균 응답 시간: {avg_time:.2f}초")
        print(f"  최소: {min(response_times):.2f}초")
        print(f"  최대: {max(response_times):.2f}초")

    # 결과 저장
    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 상세 결과를 test_results.json에 저장했습니다.")

    print(f"\n종료 시간: {datetime.now()}")

    return results

if __name__ == "__main__":
    results = main()