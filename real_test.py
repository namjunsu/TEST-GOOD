#!/usr/bin/env python3
"""
실제 답변 테스트 - 간단한 질문들로 테스트
"""

import sys
import os
import time
from datetime import datetime

# 경고 메시지 숨기기
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import warnings
warnings.filterwarnings('ignore')

from perfect_rag import PerfectRAG

def test_query(rag, query, mode, num):
    """단일 질문 테스트"""
    print(f"\n{'='*80}")
    print(f"테스트 #{num}: {query}")
    print(f"모드: {mode}")
    print('-'*80)

    start_time = time.time()

    try:
        # 실제 답변 생성
        answer = rag.answer(query, mode=mode)
        elapsed = time.time() - start_time

        # 결과 출력
        print(f"⏱️ 응답 시간: {elapsed:.2f}초")
        print(f"📝 답변 길이: {len(answer)}자")

        # 답변 미리보기 (최대 800자)
        print(f"\n📌 답변:")
        if len(answer) > 800:
            print(answer[:800] + "\n...[생략]...")
        else:
            print(answer)

        # 품질 체크
        is_error = "❌" in answer or "찾을 수 없" in answer
        has_content = len(answer) > 50

        if is_error:
            print("\n⚠️ 오류 응답 감지")
        elif has_content:
            print("\n✅ 정상 응답")
        else:
            print("\n⚠️ 응답이 너무 짧음")

        return {
            'success': not is_error and has_content,
            'time': elapsed,
            'length': len(answer)
        }

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def main():
    print("🚀 실제 답변 테스트 시작")
    print(f"시작 시간: {datetime.now()}")

    # RAG 초기화
    print("\n📚 시스템 로딩 중...")
    rag = PerfectRAG()
    print(f"✅ 로딩 완료 - PDF: {len(rag.pdf_files)}개, TXT: {len(rag.txt_files)}개")

    # 테스트 질문들 (간단한 것부터)
    test_cases = [
        ("2020년 문서 보여줘", "document"),
        ("구매 문서 목록", "document"),
        ("중계차 장비 현황", "asset"),
        ("카메라 구매 문서", "document"),
        ("2019년 수리 내역", "document"),
        ("광화문 스튜디오 장비", "asset"),
        ("최근 구매한 장비", "document"),
        ("자산 목록 보여줘", "asset"),
        ("UPS 관련 문서", "document"),
        ("영상취재팀 장비", "document"),
    ]

    results = []

    # 각 테스트 실행
    for i, (query, mode) in enumerate(test_cases, 1):
        result = test_query(rag, query, mode, i)
        results.append(result)

        # 테스트 사이에 잠시 대기
        if i < len(test_cases):
            print("\n💤 다음 테스트를 위해 2초 대기...")
            time.sleep(2)

    # 결과 요약
    print("\n" + "="*80)
    print("📊 테스트 결과 요약")
    print("="*80)

    success_count = sum(1 for r in results if r.get('success', False))
    fail_count = len(results) - success_count

    print(f"✅ 성공: {success_count}/{len(results)}")
    print(f"❌ 실패: {fail_count}/{len(results)}")

    # 시간 통계
    times = [r.get('time', 0) for r in results if 'time' in r]
    if times:
        avg_time = sum(times) / len(times)
        print(f"\n⏱️ 평균 응답 시간: {avg_time:.2f}초")
        print(f"  최소: {min(times):.2f}초")
        print(f"  최대: {max(times):.2f}초")

    print(f"\n종료 시간: {datetime.now()}")

    # 상세 결과 저장
    with open('real_test_results.txt', 'w', encoding='utf-8') as f:
        f.write(f"테스트 실행 시간: {datetime.now()}\n")
        f.write(f"성공: {success_count}/{len(results)}\n")
        f.write(f"실패: {fail_count}/{len(results)}\n")
        f.write(f"평균 응답 시간: {avg_time:.2f}초\n" if times else "")
        f.write("\n상세 결과:\n")
        for i, (query, mode) in enumerate(test_cases, 1):
            r = results[i-1]
            f.write(f"\n테스트 #{i}: {query} ({mode})\n")
            f.write(f"  결과: {'성공' if r.get('success') else '실패'}\n")
            if 'time' in r:
                f.write(f"  시간: {r['time']:.2f}초\n")
            if 'error' in r:
                f.write(f"  오류: {r['error']}\n")

    print("\n💾 결과를 real_test_results.txt에 저장했습니다.")

if __name__ == "__main__":
    main()