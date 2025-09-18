#!/usr/bin/env python3
"""
답변 품질 상세 테스트 스크립트
RAG 시스템의 답변 정확도, 관련성, 완성도를 평가
"""

import time
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime
import re
import hashlib

# 색상 코드
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"


class QualityTester:
    """답변 품질 테스터"""

    def __init__(self):
        self.rag = None
        self.test_results = []
        self.issues_found = []

    def initialize_rag(self):
        """RAG 시스템 초기화"""
        print(f"{CYAN}RAG 시스템 초기화 중...{RESET}")
        try:
            from perfect_rag import PerfectRAG
            self.rag = PerfectRAG(preload_llm=True)
            print(f"{GREEN}✅ RAG 시스템 초기화 완료{RESET}")
            return True
        except Exception as e:
            print(f"{RED}❌ RAG 초기화 실패: {e}{RESET}")
            return False

    def test_document_search(self):
        """문서 검색 품질 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}1. 문서 검색 품질 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        test_cases = [
            {
                "query": "2024년 중계차 보수 비용은 얼마인가요?",
                "expected_keywords": ["중계차", "보수", "비용", "2024"],
                "expected_info": ["금액", "업체", "내용"],
                "category": "specific_amount"
            },
            {
                "query": "DVR 구매 건 상세 내용 알려줘",
                "expected_keywords": ["DVR", "구매", "수량", "모델"],
                "expected_info": ["구매수량", "모델명", "업체"],
                "category": "purchase_details"
            },
            {
                "query": "광화문 방송시설에서 구매한 소모품 목록",
                "expected_keywords": ["광화문", "소모품", "방송"],
                "expected_info": ["품목", "수량", "금액"],
                "category": "location_items"
            },
            {
                "query": "2019년에 구매한 카메라 정보",
                "expected_keywords": ["2019", "카메라", "구매"],
                "expected_info": ["모델", "수량", "금액"],
                "category": "year_filter"
            },
            {
                "query": "삼각대 구입 관련 문서 찾아줘",
                "expected_keywords": ["삼각대", "구입"],
                "expected_info": ["모델", "수량", "업체"],
                "category": "equipment"
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{CYAN}테스트 {i}: {test_case['query']}{RESET}")

            # 응답 시간 측정
            start_time = time.time()
            try:
                response = self.rag.answer(test_case['query'])
                response_time = time.time() - start_time
            except Exception as e:
                print(f"{RED}❌ 검색 실패: {e}{RESET}")
                self.issues_found.append({
                    "test": f"문서검색_{i}",
                    "query": test_case['query'],
                    "issue": f"검색 실행 실패: {str(e)}",
                    "severity": "HIGH"
                })
                continue

            # 품질 평가
            quality_score = self._evaluate_response_quality(
                response,
                test_case['expected_keywords'],
                test_case['expected_info']
            )

            # 결과 저장
            result = {
                "test_id": f"doc_search_{i}",
                "query": test_case['query'],
                "category": test_case['category'],
                "response_time": response_time,
                "response_length": len(response) if response else 0,
                "quality_score": quality_score,
                "response": response[:500] if response else None  # 처음 500자만 저장
            }
            self.test_results.append(result)

            # 출력
            self._print_test_result(result)

    def test_asset_search(self):
        """자산 검색 품질 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}2. 자산/장비 검색 품질 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        test_cases = [
            {
                "query": "중계차에 있는 장비 목록",
                "expected_keywords": ["중계차", "장비", "목록"],
                "expected_format": "list",
                "min_items": 5
            },
            {
                "query": "신승만 차장이 관리하는 장비",
                "expected_keywords": ["신승만", "차장", "장비"],
                "expected_format": "list",
                "min_items": 10
            },
            {
                "query": "2020년 이전에 구입한 장비 수",
                "expected_keywords": ["2020", "이전", "구입"],
                "expected_format": "count",
                "min_items": 100
            },
            {
                "query": "천만원 이상 장비 목록",
                "expected_keywords": ["천만원", "이상", "장비"],
                "expected_format": "list",
                "min_items": 5
            },
            {
                "query": "SONY 제품 검색",
                "expected_keywords": ["SONY", "제품"],
                "expected_format": "list",
                "min_items": 1
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{CYAN}테스트 {i}: {test_case['query']}{RESET}")

            start_time = time.time()
            try:
                # Asset 모드로 전환
                self.rag.search_mode = 'asset'
                response = self.rag.answer(test_case['query'])
                response_time = time.time() - start_time
            except Exception as e:
                print(f"{RED}❌ 자산 검색 실패: {e}{RESET}")
                self.issues_found.append({
                    "test": f"asset_search_{i}",
                    "query": test_case['query'],
                    "issue": f"자산 검색 실패: {str(e)}",
                    "severity": "HIGH"
                })
                continue

            # 자산 검색 품질 평가
            quality_score = self._evaluate_asset_response(
                response,
                test_case['expected_keywords'],
                test_case['expected_format'],
                test_case.get('min_items', 0)
            )

            result = {
                "test_id": f"asset_search_{i}",
                "query": test_case['query'],
                "response_time": response_time,
                "quality_score": quality_score,
                "response_preview": response[:300] if response else None
            }
            self.test_results.append(result)
            self._print_test_result(result)

    def test_response_consistency(self):
        """응답 일관성 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}3. 응답 일관성 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        # 같은 질문을 여러 번 해서 일관성 확인
        test_query = "2024년 중계차 보수 관련 정보를 알려주세요"
        responses = []

        print(f"\n{CYAN}동일 질문 5회 반복 테스트: {test_query}{RESET}")

        for i in range(5):
            try:
                response = self.rag.answer(test_query)
                responses.append(response)
                print(f"  시도 {i+1}: {len(response)}자 응답")
            except Exception as e:
                print(f"  시도 {i+1}: {RED}실패 - {e}{RESET}")

        # 일관성 분석
        if len(responses) >= 2:
            consistency_score = self._analyze_consistency(responses)
            print(f"\n일관성 점수: {self._get_score_color(consistency_score)}{consistency_score:.1f}%{RESET}")

            if consistency_score < 80:
                self.issues_found.append({
                    "test": "consistency",
                    "query": test_query,
                    "issue": f"응답 일관성 부족 (점수: {consistency_score:.1f}%)",
                    "severity": "MEDIUM"
                })

    def test_edge_cases(self):
        """엣지 케이스 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}4. 엣지 케이스 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        edge_cases = [
            {
                "query": "",
                "name": "빈 쿼리",
                "expected_behavior": "에러 또는 안내 메시지"
            },
            {
                "query": "asdfghjkl",
                "name": "무의미한 텍스트",
                "expected_behavior": "관련 문서 없음 안내"
            },
            {
                "query": "2099년 문서",
                "name": "미래 날짜",
                "expected_behavior": "문서 없음 안내"
            },
            {
                "query": "?" * 100,
                "name": "특수문자만",
                "expected_behavior": "유효하지 않은 쿼리 안내"
            },
            {
                "query": "SELECT * FROM documents",
                "name": "SQL 인젝션 시도",
                "expected_behavior": "정상 처리 또는 무시"
            },
            {
                "query": "a" * 1000,
                "name": "초장문 쿼리",
                "expected_behavior": "정상 처리 또는 길이 제한"
            }
        ]

        for i, test_case in enumerate(edge_cases, 1):
            print(f"\n{CYAN}테스트 {i}: {test_case['name']}{RESET}")
            print(f"  쿼리: {test_case['query'][:50]}...")

            try:
                start_time = time.time()
                response = self.rag.answer(test_case['query'])
                response_time = time.time() - start_time

                print(f"  {GREEN}✅ 처리 성공{RESET} ({response_time:.2f}초)")
                print(f"  응답 길이: {len(response)}자")

                # 비정상적인 응답 체크
                if not response or len(response) < 10:
                    print(f"  {YELLOW}⚠️ 응답이 너무 짧음{RESET}")
                elif len(response) > 10000:
                    print(f"  {YELLOW}⚠️ 응답이 너무 김{RESET}")

            except Exception as e:
                print(f"  {RED}❌ 예외 발생: {e}{RESET}")
                self.issues_found.append({
                    "test": f"edge_case_{i}",
                    "case": test_case['name'],
                    "issue": f"예외 처리 실패: {str(e)}",
                    "severity": "LOW"
                })

    def test_performance(self):
        """성능 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}5. 성능 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        queries = [
            "중계차 보수 비용",
            "DVR 구매",
            "광화문 소모품",
            "2019년 카메라",
            "삼각대 구입"
        ]

        # 콜드 스타트 테스트
        print(f"\n{CYAN}콜드 스타트 테스트:{RESET}")
        cold_times = []
        for query in queries:
            # 캐시 초기화
            if hasattr(self.rag, 'answer_cache'):
                self.rag.answer_cache.clear()

            start_time = time.time()
            try:
                response = self.rag.answer(query)
                elapsed = time.time() - start_time
                cold_times.append(elapsed)
                print(f"  '{query}': {elapsed:.2f}초")
            except:
                print(f"  '{query}': {RED}실패{RESET}")

        # 캐시된 응답 테스트
        print(f"\n{CYAN}캐시 히트 테스트:{RESET}")
        cached_times = []
        for query in queries:
            start_time = time.time()
            try:
                response = self.rag.answer(query)
                elapsed = time.time() - start_time
                cached_times.append(elapsed)
                print(f"  '{query}': {elapsed:.4f}초")
            except:
                print(f"  '{query}': {RED}실패{RESET}")

        # 성능 분석
        if cold_times and cached_times:
            avg_cold = sum(cold_times) / len(cold_times)
            avg_cached = sum(cached_times) / len(cached_times)
            speedup = avg_cold / avg_cached if avg_cached > 0 else 0

            print(f"\n{BOLD}성능 요약:{RESET}")
            print(f"  평균 콜드 스타트: {avg_cold:.2f}초")
            print(f"  평균 캐시 히트: {avg_cached:.4f}초")
            print(f"  속도 향상: {speedup:.1f}배")

            if avg_cold > 5:
                self.issues_found.append({
                    "test": "performance",
                    "issue": f"콜드 스타트 시간이 너무 김: {avg_cold:.2f}초",
                    "severity": "MEDIUM"
                })

    def test_multilingual(self):
        """다국어 처리 테스트"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}6. 다국어 처리 테스트{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        test_cases = [
            ("DVR purchase", "영어"),
            ("カメラ購入", "일본어"),
            ("摄像机采购", "중국어"),
            ("Caméra achat", "프랑스어")
        ]

        for query, language in test_cases:
            print(f"\n{CYAN}{language} 테스트: {query}{RESET}")
            try:
                response = self.rag.answer(query)
                if response and len(response) > 50:
                    print(f"  {GREEN}✅ 처리 성공{RESET}")
                else:
                    print(f"  {YELLOW}⚠️ 응답 부족{RESET}")
            except Exception as e:
                print(f"  {RED}❌ 실패: {e}{RESET}")

    def _evaluate_response_quality(self, response: str,
                                  expected_keywords: List[str],
                                  expected_info: List[str]) -> float:
        """응답 품질 평가"""
        if not response:
            return 0.0

        score = 0
        max_score = len(expected_keywords) + len(expected_info)

        response_lower = response.lower()

        # 키워드 체크
        for keyword in expected_keywords:
            if keyword.lower() in response_lower:
                score += 1

        # 정보 포함 여부 체크
        for info in expected_info:
            # 간단한 패턴 매칭
            if info == "금액" and re.search(r'\d+[,\d]*\s*원', response):
                score += 1
            elif info == "수량" and re.search(r'\d+\s*[개대]', response):
                score += 1
            elif info.lower() in response_lower:
                score += 1

        return (score / max_score) * 100 if max_score > 0 else 0

    def _evaluate_asset_response(self, response: str,
                                expected_keywords: List[str],
                                expected_format: str,
                                min_items: int) -> float:
        """자산 검색 응답 평가"""
        if not response:
            return 0.0

        score = 0
        max_score = 100

        response_lower = response.lower()

        # 키워드 체크 (30점)
        keyword_score = 0
        for keyword in expected_keywords:
            if keyword.lower() in response_lower:
                keyword_score += 30 / len(expected_keywords)
        score += keyword_score

        # 형식 체크 (30점)
        if expected_format == "list":
            # 리스트 형식 체크 (번호, 불릿 등)
            if re.search(r'[\d•\-]\s+', response):
                score += 30
        elif expected_format == "count":
            # 숫자 포함 체크
            if re.search(r'\d+[개대]|\d+\s*개', response):
                score += 30

        # 최소 아이템 수 체크 (40점)
        if min_items > 0:
            # 간단히 줄 수로 체크
            lines = response.split('\n')
            item_lines = [l for l in lines if l.strip() and not l.startswith('총')]
            if len(item_lines) >= min_items:
                score += 40
            else:
                score += (len(item_lines) / min_items) * 40

        return min(score, 100)

    def _analyze_consistency(self, responses: List[str]) -> float:
        """응답 일관성 분석"""
        if len(responses) < 2:
            return 0.0

        # 간단한 일관성 체크: 응답 길이와 주요 숫자/날짜 비교
        lengths = [len(r) for r in responses]
        avg_length = sum(lengths) / len(lengths)

        # 길이 편차 계산
        length_variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)
        length_consistency = max(0, 100 - (length_variance ** 0.5) / avg_length * 100)

        # 숫자 일관성 체크
        numbers_per_response = []
        for response in responses:
            numbers = re.findall(r'\d{1,3}(?:,\d{3})*', response)
            numbers_per_response.append(set(numbers))

        # 공통 숫자 비율
        if numbers_per_response:
            common_numbers = set.intersection(*numbers_per_response)
            all_numbers = set.union(*numbers_per_response)
            number_consistency = len(common_numbers) / len(all_numbers) * 100 if all_numbers else 100
        else:
            number_consistency = 100

        return (length_consistency + number_consistency) / 2

    def _print_test_result(self, result: Dict):
        """테스트 결과 출력"""
        score = result.get('quality_score', 0)
        time_taken = result.get('response_time', 0)

        # 점수에 따른 색상
        score_color = self._get_score_color(score)

        print(f"  응답 시간: {time_taken:.2f}초")
        print(f"  품질 점수: {score_color}{score:.1f}%{RESET}")

        if score < 60:
            self.issues_found.append({
                "test": result['test_id'],
                "query": result.get('query', ''),
                "issue": f"품질 점수 낮음: {score:.1f}%",
                "severity": "MEDIUM"
            })

    def _get_score_color(self, score: float) -> str:
        """점수에 따른 색상 반환"""
        if score >= 80:
            return GREEN
        elif score >= 60:
            return YELLOW
        else:
            return RED

    def generate_report(self):
        """최종 보고서 생성"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}{BOLD}답변 품질 테스트 최종 보고서{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

        # 전체 요약
        total_tests = len(self.test_results)
        avg_score = sum(r.get('quality_score', 0) for r in self.test_results) / total_tests if total_tests > 0 else 0
        avg_time = sum(r.get('response_time', 0) for r in self.test_results) / total_tests if total_tests > 0 else 0

        print(f"\n{BOLD}📊 전체 요약:{RESET}")
        print(f"  총 테스트 수: {total_tests}")
        print(f"  평균 품질 점수: {self._get_score_color(avg_score)}{avg_score:.1f}%{RESET}")
        print(f"  평균 응답 시간: {avg_time:.2f}초")
        print(f"  발견된 이슈: {len(self.issues_found)}개")

        # 이슈 분류
        if self.issues_found:
            print(f"\n{BOLD}🔍 발견된 주요 문제점:{RESET}")

            # 심각도별 분류
            high_issues = [i for i in self.issues_found if i.get('severity') == 'HIGH']
            medium_issues = [i for i in self.issues_found if i.get('severity') == 'MEDIUM']
            low_issues = [i for i in self.issues_found if i.get('severity') == 'LOW']

            if high_issues:
                print(f"\n{RED}🔴 심각한 문제 ({len(high_issues)}개):{RESET}")
                for issue in high_issues[:5]:  # 최대 5개만 표시
                    print(f"  • {issue['test']}: {issue['issue']}")

            if medium_issues:
                print(f"\n{YELLOW}🟡 중간 문제 ({len(medium_issues)}개):{RESET}")
                for issue in medium_issues[:5]:
                    print(f"  • {issue['test']}: {issue['issue']}")

            if low_issues:
                print(f"\n{CYAN}🔵 경미한 문제 ({len(low_issues)}개):{RESET}")
                for issue in low_issues[:3]:
                    print(f"  • {issue['test']}: {issue['issue']}")

        # 카테고리별 성능
        print(f"\n{BOLD}📈 카테고리별 성능:{RESET}")
        categories = {}
        for result in self.test_results:
            cat = result.get('category', 'unknown')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(result.get('quality_score', 0))

        for cat, scores in categories.items():
            if scores:
                avg = sum(scores) / len(scores)
                print(f"  {cat}: {self._get_score_color(avg)}{avg:.1f}%{RESET}")

        # 개선 권장사항
        print(f"\n{BOLD}💡 개선 권장사항:{RESET}")
        recommendations = self._generate_recommendations()
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")

        # JSON 보고서 저장
        report_file = f"quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "avg_quality_score": avg_score,
                "avg_response_time": avg_time,
                "total_issues": len(self.issues_found)
            },
            "test_results": self.test_results,
            "issues": self.issues_found,
            "recommendations": recommendations
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"\n📄 상세 보고서 저장: {report_file}")

    def _generate_recommendations(self) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []

        # 이슈 분석
        issue_types = {}
        for issue in self.issues_found:
            issue_text = issue['issue']
            if '품질 점수 낮음' in issue_text:
                issue_types['low_quality'] = issue_types.get('low_quality', 0) + 1
            elif '일관성' in issue_text:
                issue_types['consistency'] = issue_types.get('consistency', 0) + 1
            elif '시간' in issue_text or '성능' in issue_text:
                issue_types['performance'] = issue_types.get('performance', 0) + 1
            elif '검색 실패' in issue_text:
                issue_types['search_failure'] = issue_types.get('search_failure', 0) + 1

        # 권장사항 생성
        if issue_types.get('low_quality', 0) > 3:
            recommendations.append("답변 품질 개선: 프롬프트 엔지니어링 및 컨텍스트 확장 필요")

        if issue_types.get('consistency', 0) > 0:
            recommendations.append("응답 일관성 개선: 캐싱 로직 검토 및 시드 고정 고려")

        if issue_types.get('performance', 0) > 0:
            recommendations.append("성능 최적화: 인덱싱 개선 및 병렬 처리 확대")

        if issue_types.get('search_failure', 0) > 0:
            recommendations.append("검색 안정성: 에러 핸들링 강화 및 폴백 메커니즘 추가")

        # 일반 권장사항
        avg_score = sum(r.get('quality_score', 0) for r in self.test_results) / len(self.test_results) if self.test_results else 0

        if avg_score < 70:
            recommendations.append("전반적인 답변 품질 향상을 위한 모델 파인튜닝 고려")

        if not recommendations:
            recommendations.append("시스템이 전반적으로 양호하나, 지속적인 모니터링 권장")

        return recommendations


def main():
    """메인 실행 함수"""
    print(f"{MAGENTA}{BOLD}")
    print("="*60)
    print("   AI-CHAT RAG 시스템 답변 품질 상세 테스트")
    print("="*60)
    print(f"{RESET}")

    tester = QualityTester()

    # RAG 초기화
    if not tester.initialize_rag():
        print(f"{RED}테스트를 중단합니다.{RESET}")
        return False

    # 각 테스트 실행
    try:
        tester.test_document_search()
        tester.test_asset_search()
        tester.test_response_consistency()
        tester.test_edge_cases()
        tester.test_performance()
        tester.test_multilingual()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}테스트가 중단되었습니다.{RESET}")
    except Exception as e:
        print(f"\n{RED}테스트 중 오류 발생: {e}{RESET}")
        import traceback
        traceback.print_exc()

    # 최종 보고서
    tester.generate_report()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)