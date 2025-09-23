#!/usr/bin/env python3
"""
시스템 전체 진단 및 개선점 도출
최고의 개발자가 되기 위한 첫 걸음
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple
import json

class SystemAuditor:
    """시스템 품질 진단"""

    def __init__(self):
        self.issues = []
        self.metrics = {}
        self.recommendations = []

    def analyze_code_quality(self, filepath: Path) -> Dict:
        """코드 품질 분석"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        issues = {
            'bare_except': content.count('except:'),
            'print_statements': content.count('print('),
            'todo_comments': content.count('TODO'),
            'hardcoded_values': self._find_hardcoded_values(content),
            'long_functions': self._find_long_functions(content),
            'no_docstrings': self._check_docstrings(content),
            'complexity': self._calculate_complexity(content)
        }

        return issues

    def _find_hardcoded_values(self, content: str) -> int:
        """하드코딩된 값 찾기"""
        hardcoded = 0
        patterns = ['= 4', '= 10', '= 60', 'localhost', '8501']
        for pattern in patterns:
            hardcoded += content.count(pattern)
        return hardcoded

    def _find_long_functions(self, content: str) -> List[str]:
        """50줄 이상 함수 찾기"""
        long_funcs = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
                        length = node.end_lineno - node.lineno
                        if length > 50:
                            long_funcs.append(f"{node.name}({length} lines)")
        except:
            pass
        return long_funcs

    def _check_docstrings(self, content: str) -> int:
        """docstring 없는 함수 수"""
        no_docs = 0
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not ast.get_docstring(node):
                        no_docs += 1
        except:
            pass
        return no_docs

    def _calculate_complexity(self, content: str) -> int:
        """순환 복잡도 계산 (간단 버전)"""
        complexity = 1
        complexity += content.count('if ')
        complexity += content.count('elif ')
        complexity += content.count('for ')
        complexity += content.count('while ')
        complexity += content.count('except ')
        return complexity

    def audit_system(self) -> Dict:
        """전체 시스템 진단"""
        print("🔍 시스템 전체 진단 시작...")
        print("=" * 60)

        # 핵심 파일들 분석
        core_files = [
            'perfect_rag.py',
            'web_interface.py',
            'auto_indexer.py',
            'config.py'
        ]

        total_issues = {
            'critical': 0,
            'major': 0,
            'minor': 0,
            'info': 0
        }

        file_reports = {}

        for filename in core_files:
            filepath = Path(filename)
            if filepath.exists():
                print(f"\n📄 {filename} 분석 중...")
                issues = self.analyze_code_quality(filepath)
                file_reports[filename] = issues

                # 심각도 분류
                if issues['bare_except'] > 0:
                    total_issues['critical'] += issues['bare_except']
                    print(f"  ❌ Critical: {issues['bare_except']}개 bare except")

                if issues['long_functions']:
                    total_issues['major'] += len(issues['long_functions'])
                    print(f"  ⚠️  Major: {len(issues['long_functions'])}개 긴 함수")
                    for func in issues['long_functions'][:3]:
                        print(f"     - {func}")

                if issues['hardcoded_values'] > 5:
                    total_issues['major'] += 1
                    print(f"  ⚠️  Major: {issues['hardcoded_values']}개 하드코딩")

                if issues['no_docstrings'] > 10:
                    total_issues['minor'] += 1
                    print(f"  ⚡ Minor: {issues['no_docstrings']}개 문서화 없음")

        # 테스트 커버리지 확인
        test_files = list(Path('.').glob('test_*.py'))
        print(f"\n📊 테스트 현황:")
        print(f"  테스트 파일: {len(test_files)}개")
        print(f"  커버리지: 측정 안됨 ❌")

        # 최종 점수 계산
        score = 100
        score -= total_issues['critical'] * 10
        score -= total_issues['major'] * 5
        score -= total_issues['minor'] * 2
        score = max(0, score)

        print("\n" + "=" * 60)
        print(f"🎯 시스템 품질 점수: {score}/100")

        if score >= 90:
            grade = "A - Excellent"
        elif score >= 80:
            grade = "B - Good"
        elif score >= 70:
            grade = "C - Average"
        elif score >= 60:
            grade = "D - Below Average"
        else:
            grade = "F - Poor"

        print(f"📈 등급: {grade}")

        # 개선 권장사항
        print("\n💡 개선 권장사항:")
        recommendations = []

        if total_issues['critical'] > 0:
            recommendations.append("1. 🚨 모든 bare except를 구체적 예외로 변경")
        if total_issues['major'] > 5:
            recommendations.append("2. ⚠️  50줄 이상 함수들을 작은 단위로 분할")
        if len(test_files) < 5:
            recommendations.append("3. 🧪 단위 테스트 작성 (pytest 사용)")
        recommendations.append("4. 📊 성능 모니터링 도구 추가")
        recommendations.append("5. 📝 API 문서화 및 타입 힌트 추가")

        for rec in recommendations:
            print(f"  {rec}")

        # 결과 저장
        report = {
            'score': score,
            'grade': grade,
            'issues': total_issues,
            'files': file_reports,
            'recommendations': recommendations
        }

        with open('system_audit_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n✅ 상세 리포트: system_audit_report.json")

        return report

def main():
    """메인 실행"""
    auditor = SystemAuditor()
    report = auditor.audit_system()

    # 개선 로드맵 생성
    print("\n" + "=" * 60)
    print("🗺️ 개선 로드맵")
    print("=" * 60)

    if report['score'] < 70:
        print("""
Phase 1: 긴급 수정 (1-2일)
  - Bare except 제거
  - 에러 핸들링 개선
  - 하드코딩 제거

Phase 2: 구조 개선 (3-5일)
  - 함수 분할 및 리팩토링
  - 테스트 코드 작성
  - 비동기 처리 도입

Phase 3: 최적화 (1주)
  - 성능 프로파일링
  - 캐시 시스템 개선
  - 모니터링 도구 구축

Phase 4: 프로덕션 준비 (2주)
  - Docker 컨테이너화
  - CI/CD 파이프라인
  - 문서화 완성
        """)
    else:
        print("시스템이 양호한 상태입니다. 점진적 개선을 진행하세요.")

if __name__ == "__main__":
    main()