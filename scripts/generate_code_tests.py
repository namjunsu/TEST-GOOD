#!/usr/bin/env python3
"""실제 DB 기반 코드 검색 테스트 자동 생성

model_codes 테이블에서 상위 N개 코드를 추출하여
변형 쿼리(하이픈/무공백/소문자)를 자동 생성
"""

import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_test_cases(db_path: str = "metadata.db", top_n: int = 20) -> List[Dict[str, Any]]:
    """실제 DB에서 상위 코드 추출 및 테스트 케이스 생성

    Args:
        db_path: 데이터베이스 경로
        top_n: 상위 N개 코드 선택

    Returns:
        테스트 케이스 리스트
    """
    conn = sqlite3.connect(db_path)

    # 상위 N개 코드 추출 (문서 수 기준)
    cursor = conn.execute("""
        SELECT norm_code, code, COUNT(*) as doc_count
        FROM model_codes
        GROUP BY norm_code
        ORDER BY doc_count DESC
        LIMIT ?
    """, (top_n,))

    rows = cursor.fetchall()
    logger.info(f"상위 {len(rows)}개 코드 추출 완료")

    test_cases = []
    test_id_counter = 1

    for norm_code, sample_code, doc_count in rows:
        # 파일명에 코드가 포함된 문서 확인
        cursor_filename = conn.execute("""
            SELECT d.filename
            FROM model_codes m
            JOIN documents d ON m.doc_id = d.id
            WHERE m.norm_code = ?
            LIMIT 1
        """, (norm_code,))

        filename_row = cursor_filename.fetchone()
        sample_filename = filename_row[0] if filename_row else ""

        # 변형 1: 기본 (원본 + 수식어 "관련 문서")
        test_cases.append({
            "id": f"auto_{test_id_counter:03d}",
            "query": f"{sample_code} 관련 문서",
            "expect_norm_code": norm_code,
            "expect_contains": norm_code,  # norm_code 기준
            "min_hits_at_3": 1,
            "description": f"{norm_code} 기본 검색 ({doc_count}개 문서)"
        })
        test_id_counter += 1

        # 변형 2: 수식어 1 (정규형 + "정보")
        test_cases.append({
            "id": f"auto_{test_id_counter:03d}",
            "query": f"{sample_code} 정보",
            "expect_norm_code": norm_code,
            "expect_contains": norm_code,
            "min_hits_at_3": 1,
            "description": f"{norm_code} 수식어 검색 (정보)"
        })
        test_id_counter += 1

        # 변형 3: 수식어 2 (소문자 + "사양") - Patch D
        test_cases.append({
            "id": f"auto_{test_id_counter:03d}",
            "query": f"{sample_code.lower()} 사양",
            "expect_norm_code": norm_code,
            "expect_contains": norm_code,
            "min_hits_at_3": 1,
            "description": f"{norm_code} 소문자+수식어 검색 (사양)"
        })
        test_id_counter += 1

    conn.close()

    logger.info(f"총 {len(test_cases)}개 테스트 케이스 생성")
    return test_cases


def main():
    """메인 실행"""
    print("=" * 80)
    print("실제 DB 기반 코드 검색 테스트 자동 생성")
    print("=" * 80)

    # 테스트 케이스 생성 (Patch D: top 15개로 증가 → 45개 케이스)
    test_cases = generate_test_cases(top_n=15)  # 상위 15개 코드

    # 기존 YAML 구조 로드 (성능 기준 등)
    suite_path = Path("suites/model_codes.yaml")

    if suite_path.exists():
        with open(suite_path, "r", encoding="utf-8") as f:
            existing_suite = yaml.safe_load(f)

        performance_criteria = existing_suite.get("performance_criteria", {})
        validation_options = existing_suite.get("validation_options", {})
    else:
        performance_criteria = {
            "hit_at_3_min": 0.90,
            "mrr_at_10_min": 0.80,
            "citation_rate_min": 1.0,
            "p95_latency_max_ms": 5000
        }
        validation_options = {
            "top_k": 10,
            "check_citations": True,
            "measure_latency": True
        }

    # 새 YAML 구조 생성
    new_suite = {
        "test_cases": test_cases,
        "performance_criteria": performance_criteria,
        "validation_options": validation_options
    }

    # YAML 파일로 저장
    with open(suite_path, "w", encoding="utf-8") as f:
        yaml.dump(new_suite, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n✅ 테스트 스위트 생성 완료: {suite_path}")
    print(f"   테스트 케이스: {len(test_cases)}개")
    print(f"   성능 기준: Hit@3 ≥ {performance_criteria['hit_at_3_min']}, "
          f"MRR@10 ≥ {performance_criteria['mrr_at_10_min']}")
    print()

    # 샘플 출력
    print("샘플 테스트 케이스 (처음 5개):")
    for tc in test_cases[:5]:
        print(f"  - {tc['id']}: {tc['query']}")
        print(f"    기대 코드: {tc['expect_norm_code']}, 최소 히트: {tc['min_hits_at_3']}")

    print("\n" + "=" * 80)
    print("다음 명령으로 검증 실행:")
    print("  python3 scripts/validate_codes.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
