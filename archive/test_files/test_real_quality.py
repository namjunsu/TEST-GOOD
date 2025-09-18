#!/usr/bin/env python3
"""
실제 답변 품질 테스트
모델이 로드된 상태에서 실제 답변 품질 확인
"""

import time
from pathlib import Path
import sys

# 색상 코드
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def test_real_answers():
    """실제 답변 테스트"""
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}실제 답변 품질 테스트{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

    # RAG 초기화
    print("RAG 시스템 초기화 중...")
    from perfect_rag import PerfectRAG
    rag = PerfectRAG(preload_llm=True)

    # 테스트 질문들
    test_questions = [
        {
            "query": "2024년 중계차 보수 비용 총액은?",
            "expected": ["비용", "금액", "원", "중계차"]
        },
        {
            "query": "DVR 구매 수량과 모델명을 알려주세요",
            "expected": ["DVR", "수량", "모델", "대"]
        },
        {
            "query": "광화문 사옥에 구매한 방송 소모품 목록",
            "expected": ["광화문", "소모품", "구매"]
        },
        {
            "query": "2019년에 구매한 카메라 관련 정보",
            "expected": ["2019", "카메라"]
        },
        {
            "query": "삼각대 구입 건의 상세 내용",
            "expected": ["삼각대", "구입"]
        }
    ]

    results = []

    for i, test in enumerate(test_questions, 1):
        print(f"\n{BOLD}테스트 {i}: {test['query']}{RESET}")
        print("-" * 50)

        # 캐시 초기화 (정확한 테스트를 위해)
        if hasattr(rag, 'answer_cache'):
            rag.answer_cache.clear()

        # 답변 생성
        start_time = time.time()
        try:
            answer = rag.answer(test['query'])
            elapsed_time = time.time() - start_time

            # 답변 분석
            if answer:
                print(f"⏱️ 응답 시간: {elapsed_time:.2f}초")
                print(f"📝 답변 길이: {len(answer)}자")

                # 키워드 체크
                found_keywords = []
                missing_keywords = []
                for keyword in test['expected']:
                    if keyword in answer:
                        found_keywords.append(keyword)
                    else:
                        missing_keywords.append(keyword)

                if found_keywords:
                    print(f"{GREEN}✅ 포함된 키워드: {', '.join(found_keywords)}{RESET}")
                if missing_keywords:
                    print(f"{YELLOW}⚠️ 누락된 키워드: {', '.join(missing_keywords)}{RESET}")

                # 답변 미리보기
                preview = answer[:300] if len(answer) > 300 else answer
                print(f"\n📄 답변 미리보기:")
                print(f"{preview}...")

                # 품질 점수 계산
                score = (len(found_keywords) / len(test['expected'])) * 100
                color = GREEN if score >= 70 else YELLOW if score >= 40 else RED
                print(f"\n품질 점수: {color}{score:.0f}%{RESET}")

                results.append({
                    "query": test['query'],
                    "score": score,
                    "time": elapsed_time,
                    "length": len(answer),
                    "answer_preview": preview
                })

            else:
                print(f"{RED}❌ 답변 생성 실패{RESET}")
                results.append({
                    "query": test['query'],
                    "score": 0,
                    "time": elapsed_time,
                    "length": 0,
                    "answer_preview": None
                })

        except Exception as e:
            print(f"{RED}❌ 오류 발생: {e}{RESET}")
            results.append({
                "query": test['query'],
                "score": 0,
                "time": 0,
                "length": 0,
                "error": str(e)
            })

    # 최종 요약
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}테스트 결과 요약{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

    total_score = sum(r['score'] for r in results) / len(results) if results else 0
    avg_time = sum(r['time'] for r in results) / len(results) if results else 0
    avg_length = sum(r['length'] for r in results) / len(results) if results else 0

    print(f"평균 품질 점수: {total_score:.1f}%")
    print(f"평균 응답 시간: {avg_time:.2f}초")
    print(f"평균 답변 길이: {avg_length:.0f}자")

    # 문제점 분석
    print(f"\n{BOLD}발견된 문제점:{RESET}")
    problems = []

    if total_score < 50:
        problems.append("• 전반적인 답변 품질이 낮음")
    if avg_time > 10:
        problems.append("• 응답 시간이 너무 길음")
    if avg_length < 100:
        problems.append("• 답변이 너무 짧음")
    elif avg_length > 2000:
        problems.append("• 답변이 너무 장황함")

    # LLM 관련 문제 체크
    for result in results:
        if 'error' in result and 'model' in result['error'].lower():
            problems.append("• LLM 모델 로딩 문제 있음")
            break

    if problems:
        for problem in problems:
            print(f"{YELLOW}{problem}{RESET}")
    else:
        print(f"{GREEN}✅ 특별한 문제점 없음{RESET}")

    return results


def suggest_improvements(results):
    """개선 제안"""
    print(f"\n{BOLD}개선 제안:{RESET}")

    suggestions = []

    # 결과 분석
    avg_score = sum(r['score'] for r in results) / len(results) if results else 0

    if avg_score < 30:
        suggestions.append({
            "priority": "HIGH",
            "area": "프롬프트 엔지니어링",
            "action": "시스템 프롬프트 개선 및 few-shot 예제 추가"
        })

    if any(r['time'] > 15 for r in results):
        suggestions.append({
            "priority": "HIGH",
            "area": "성능 최적화",
            "action": "컨텍스트 크기 조정 및 배치 처리 개선"
        })

    if any(r['length'] < 50 for r in results):
        suggestions.append({
            "priority": "MEDIUM",
            "area": "답변 생성",
            "action": "최소 답변 길이 설정 및 폴백 메커니즘 강화"
        })

    # 개선 제안 출력
    for i, suggestion in enumerate(suggestions, 1):
        color = RED if suggestion['priority'] == 'HIGH' else YELLOW
        print(f"\n{i}. {color}[{suggestion['priority']}]{RESET} {suggestion['area']}")
        print(f"   → {suggestion['action']}")

    return suggestions


if __name__ == "__main__":
    print(f"{BOLD}AI-CHAT RAG 시스템 실제 품질 테스트{RESET}\n")

    try:
        results = test_real_answers()
        suggestions = suggest_improvements(results)

        # 보고서 저장
        import json
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": results,
            "suggestions": suggestions
        }

        report_file = f"real_quality_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n📄 보고서 저장: {report_file}")

    except KeyboardInterrupt:
        print(f"\n{YELLOW}테스트 중단됨{RESET}")
    except Exception as e:
        print(f"{RED}테스트 실패: {e}{RESET}")
        import traceback
        traceback.print_exc()