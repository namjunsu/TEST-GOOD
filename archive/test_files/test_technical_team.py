#!/usr/bin/env python3
"""
기술관리팀 관점에서 RAG 시스템 답변 품질 상세 테스트
실제 업무에서 필요한 질문들로 테스트
"""

from perfect_rag import PerfectRAG
import time
import json

def test_technical_team_queries():
    """기술관리팀 실무 질문 테스트"""
    print("🔧 기술관리팀 실무 질문 테스트")
    print("="*80)
    print("📌 테스트 목적: 실제 기술관리팀이 업무에서 필요로 하는 정보를 정확히 제공하는지 확인")
    print("="*80)
    
    # RAG 시스템 초기화
    print("\n시스템 초기화 중...")
    rag = PerfectRAG()
    
    # 기술관리팀 실무 질문들
    test_queries = [
        # === 장비 자산 관련 상세 질문 ===
        {
            "category": "📊 장비 현황 파악",
            "query": "HD 카메라 중 Sony 제품만 보여줘. 구입연도와 위치도 같이 알려줘",
            "mode": "asset",
            "expected": "Sony HD 카메라 목록, 구입일, 위치 정보"
        },
        {
            "category": "💰 예산 관리",
            "query": "2023년에 구매한 장비 중 1억원 이상인 고가 장비 목록",
            "mode": "asset",
            "expected": "2023년 고가 장비 목록과 금액"
        },
        {
            "category": "📍 위치별 자산",
            "query": "광화문 스튜디오에 있는 모든 조명 장비 목록과 구입일",
            "mode": "asset",
            "expected": "광화문 스튜디오 조명 장비 상세 목록"
        },
        {
            "category": "👤 담당자별 관리",
            "query": "신승만 차장이 관리하는 장비 전체 목록과 총 금액",
            "mode": "asset",
            "expected": "담당자별 장비 목록과 금액 합계"
        },
        {
            "category": "🔄 교체 주기 파악",
            "query": "2020년 이전에 구입한 카메라 장비 중 아직 사용 중인 것들",
            "mode": "asset",
            "expected": "오래된 카메라 장비 목록 (교체 검토 대상)"
        },
        {
            "category": "🏢 부서별 자산",
            "query": "뉴스제작팀에서 사용하는 모든 편집 장비 현황",
            "mode": "asset",
            "expected": "부서별 편집 장비 상세 현황"
        },
        {
            "category": "🔧 유지보수 계획",
            "query": "중계차에 설치된 장비 중 5년 이상 된 장비들",
            "mode": "asset",
            "expected": "중계차 노후 장비 목록"
        },
        {
            "category": "📈 구매 분석",
            "query": "최근 3년간 가장 많이 구매한 장비 종류는?",
            "mode": "asset",
            "expected": "장비 종류별 구매 통계"
        },
        
        # === 문서 기반 정책/절차 질문 ===
        {
            "category": "📋 구매 절차",
            "query": "1천만원 이상 장비 구매시 필요한 결재 절차와 서류는?",
            "mode": "document",
            "expected": "고가 장비 구매 절차 상세"
        },
        {
            "category": "🔍 기술 검토",
            "query": "장비 구매전 기술검토는 누가하고 어떤 내용을 검토하나요?",
            "mode": "document",
            "expected": "기술검토 담당자와 검토 항목"
        },
        {
            "category": "📝 기안서 작성",
            "query": "장비 수리 기안서에 꼭 포함되어야 하는 내용은?",
            "mode": "document",
            "expected": "수리 기안서 필수 항목"
        },
        {
            "category": "💼 업체 선정",
            "query": "장비 구매 업체 선정 기준과 견적 비교 방법은?",
            "mode": "document",
            "expected": "업체 선정 기준과 절차"
        }
    ]
    
    # 결과 저장
    results = []
    success_count = 0
    
    # 각 질문 테스트
    for i, test in enumerate(test_queries, 1):
        print(f"\n{'='*80}")
        print(f"테스트 {i}/{len(test_queries)}: {test['category']}")
        print(f"질문: {test['query']}")
        print(f"모드: {test['mode']}")
        print(f"기대 답변: {test['expected']}")
        print("-"*80)
        
        try:
            start_time = time.time()
            
            # RAG 시스템 호출
            response = rag.answer(
                test['query'], 
                mode=test['mode']
            )
            
            elapsed = time.time() - start_time
            
            # 응답 분석
            print("\n📝 응답:")
            if isinstance(response, str):
                # 응답 길이 확인
                response_length = len(response)
                
                # 처음 800자 출력
                if response_length > 800:
                    print(response[:800] + f"\n\n... [전체 {response_length}자, 일부 생략] ...")
                else:
                    print(response)
                
                # 답변 품질 평가
                quality_score = evaluate_answer_quality(response, test)
                print(f"\n📊 답변 평가:")
                print(f"  - 응답 길이: {response_length}자")
                print(f"  - 응답 시간: {elapsed:.2f}초")
                print(f"  - 품질 점수: {quality_score}/10")
                
                result = {
                    "question": test['query'],
                    "category": test['category'],
                    "response_length": response_length,
                    "response_time": elapsed,
                    "quality_score": quality_score,
                    "success": quality_score >= 6
                }
                
                if quality_score >= 6:
                    print("  ✅ 답변 품질 양호")
                    success_count += 1
                else:
                    print("  ⚠️ 답변 품질 개선 필요")
                    
            else:
                print(str(response)[:500])
                result = {
                    "question": test['query'],
                    "category": test['category'],
                    "response_length": 0,
                    "response_time": elapsed,
                    "quality_score": 0,
                    "success": False
                }
                print("  ❌ 비정상 응답 형식")
            
            results.append(result)
            
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            results.append({
                "question": test['query'],
                "category": test['category'],
                "error": str(e),
                "success": False
            })
    
    # 최종 결과 요약
    print(f"\n{'='*80}")
    print("📊 테스트 결과 요약")
    print("="*80)
    
    # 카테고리별 성공률
    category_stats = {}
    for result in results:
        cat = result.get('category', 'Unknown')
        if cat not in category_stats:
            category_stats[cat] = {'total': 0, 'success': 0}
        category_stats[cat]['total'] += 1
        if result.get('success', False):
            category_stats[cat]['success'] += 1
    
    print("\n📈 카테고리별 성공률:")
    for cat, stats in category_stats.items():
        success_rate = (stats['success'] / stats['total']) * 100
        print(f"  {cat}: {stats['success']}/{stats['total']} ({success_rate:.0f}%)")
    
    # 전체 통계
    total_tests = len(test_queries)
    avg_response_time = sum(r.get('response_time', 0) for r in results) / total_tests
    avg_quality = sum(r.get('quality_score', 0) for r in results) / total_tests
    
    print(f"\n📊 전체 통계:")
    print(f"  - 전체 성공률: {success_count}/{total_tests} ({(success_count/total_tests)*100:.0f}%)")
    print(f"  - 평균 응답 시간: {avg_response_time:.2f}초")
    print(f"  - 평균 품질 점수: {avg_quality:.1f}/10")
    
    # 개선 필요 항목
    failed = [r for r in results if not r.get('success', False)]
    if failed:
        print(f"\n⚠️ 개선 필요 항목 ({len(failed)}개):")
        for f in failed[:5]:  # 최대 5개만 표시
            print(f"  - {f['question'][:50]}...")
            if 'error' in f:
                print(f"    오류: {f['error'][:50]}")
    
    # 결과 저장
    with open('technical_team_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 상세 결과가 'technical_team_test_results.json'에 저장되었습니다.")

def evaluate_answer_quality(response: str, test_case: dict) -> int:
    """답변 품질을 10점 만점으로 평가"""
    score = 0
    
    # 1. 응답 길이 (2점)
    if len(response) > 100:
        score += 1
    if len(response) > 300:
        score += 1
    
    # 2. 구조화된 답변 (2점)
    if any(marker in response for marker in ['•', '📌', '📋', '###', '**']):
        score += 1
    if response.count('\n') > 3:  # 여러 줄로 구성
        score += 1
    
    # 3. 구체적 정보 포함 (3점)
    # 숫자 정보
    import re
    numbers = re.findall(r'\d+', response)
    if len(numbers) > 2:
        score += 1
    
    # 날짜 정보
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', response):
        score += 1
    
    # 금액 정보
    if '원' in response and any(char.isdigit() for char in response):
        score += 1
    
    # 4. 질문 키워드 포함 (2점)
    query_keywords = test_case['query'].lower().split()
    matching_keywords = sum(1 for kw in query_keywords if kw in response.lower())
    if matching_keywords >= len(query_keywords) * 0.3:
        score += 1
    if matching_keywords >= len(query_keywords) * 0.6:
        score += 1
    
    # 5. 답변 완성도 (1점)
    if not any(phrase in response for phrase in ['찾을 수 없', '오류', '실패', '없습니다']):
        score += 1
    
    return min(score, 10)

if __name__ == "__main__":
    test_technical_team_queries()