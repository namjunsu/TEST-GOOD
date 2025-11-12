#!/usr/bin/env python3
"""
Context Hydrator 성능 벤치마크

측정 항목:
- extraction_time: p50, p95, p99
- total_length: 평균, 최소, 최대
- compression_applied: 비율
- pdf_tail_status: 성공/실패 비율

케이스:
- (i) 청크만
- (ii) 청크 + PDF 테일
- (iii) 텍스트 레이어 없는 PDF (실패 케이스)
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.utils.context_hydrator import hydrate_context


def load_sample_chunks(data_dir: Path) -> List[Dict[str, Any]]:
    """
    샘플 청크 데이터 로드

    Args:
        data_dir: 데이터 디렉토리

    Returns:
        청크 리스트
    """
    chunks = []

    # 패턴 1: 청크만 (JSON 파일)
    chunks_file = data_dir / "sample_chunks.json"
    if chunks_file.exists():
        with open(chunks_file, encoding="utf-8") as f:
            chunks.extend(json.load(f))

    # 패턴 2: PDF 파일에서 청크 생성
    pdf_files = list(data_dir.glob("**/*.pdf"))
    for pdf_path in pdf_files[:10]:  # 최대 10개
        chunks.append({"file_path": str(pdf_path), "text": f"샘플 청크 from {pdf_path.name}"})

    return chunks


def benchmark_case(
    chunks: List[Dict[str, Any]], mode: str, case_name: str, repeat: int = 10
) -> Dict[str, Any]:
    """
    케이스별 벤치마크

    Args:
        chunks: 청크 리스트
        mode: 생성 모드 (rag/summarize)
        case_name: 케이스 이름
        repeat: 반복 횟수

    Returns:
        벤치마크 결과
    """
    times = []
    lengths = []
    token_estimates = []
    compression_count = 0
    pdf_success_count = 0
    pdf_fail_count = 0
    truncate_counts = {"none": 0, "compact": 0, "hardcut": 0}

    for _ in range(repeat):
        start = time.perf_counter()
        text, metrics = hydrate_context(chunks, max_len=10000, mode=mode)
        elapsed = time.perf_counter() - start

        times.append(elapsed)
        lengths.append(metrics["total_length"])
        token_estimates.append(metrics["token_estimate"])

        if metrics["compression_applied"]:
            compression_count += 1

        if metrics["pdf_tail_status"] == "success":
            pdf_success_count += 1
        elif metrics["pdf_tail_status"] == "fail":
            pdf_fail_count += 1

        truncate_counts[metrics["truncate_reason"]] += 1

    return {
        "case": case_name,
        "mode": mode,
        "repeat": repeat,
        "time_p50": statistics.median(times),
        "time_p95": statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times),
        "time_p99": statistics.quantiles(times, n=100)[98] if len(times) >= 100 else max(times),
        "time_avg": statistics.mean(times),
        "length_avg": statistics.mean(lengths),
        "length_min": min(lengths),
        "length_max": max(lengths),
        "token_estimate_avg": statistics.mean(token_estimates),
        "compression_ratio": compression_count / repeat,
        "pdf_success_ratio": pdf_success_count / repeat if (pdf_success_count + pdf_fail_count) > 0 else 0,
        "pdf_fail_ratio": pdf_fail_count / repeat if (pdf_success_count + pdf_fail_count) > 0 else 0,
        "truncate_distribution": truncate_counts,
    }


def main():
    """메인 벤치마크 실행"""
    print("=" * 80)
    print("Context Hydrator 성능 벤치마크")
    print("=" * 80)

    # 데이터 디렉토리
    data_dir = Path(os.getenv("DOCS_DIR", "docs"))
    if not data_dir.exists():
        print(f"⚠️ 데이터 디렉토리 없음: {data_dir}")
        return

    # 샘플 청크 로드
    print(f"\n📂 데이터 로드: {data_dir}")
    all_chunks = load_sample_chunks(data_dir)

    if not all_chunks:
        print("⚠️ 샘플 청크 없음. docs/ 폴더에 PDF 파일을 추가하세요.")
        return

    print(f"✅ 청크 로드 완료: {len(all_chunks)}개")

    # 케이스별 벤치마크
    cases = [
        ("chunks_only", all_chunks[:3], "rag"),  # 청크만
        ("chunks_pdf_tail", all_chunks[:5], "rag"),  # 청크 + PDF 테일
        ("summarize_mode", all_chunks[:3], "summarize"),  # Summarize 모드
    ]

    results = []
    for case_name, chunks, mode in cases:
        print(f"\n🔍 케이스: {case_name} (mode={mode}, chunks={len(chunks)})")
        result = benchmark_case(chunks, mode, case_name, repeat=10)
        results.append(result)

        # 결과 출력
        print(f"  ⏱️  Time: p50={result['time_p50']:.3f}s, p95={result['time_p95']:.3f}s")
        print(f"  📏 Length: avg={result['length_avg']:.0f}, min={result['length_min']}, max={result['length_max']}")
        print(f"  🔢 Token Estimate: avg={result['token_estimate_avg']:.0f}")
        print(f"  🗜️  Compression Ratio: {result['compression_ratio']:.1%}")
        print(f"  📄 PDF Success Ratio: {result['pdf_success_ratio']:.1%}")
        print(f"  ✂️  Truncate: {result['truncate_distribution']}")

    # 임계값 체크
    print("\n" + "=" * 80)
    print("📊 임계값 검증")
    print("=" * 80)

    thresholds = {
        "time_p95": 0.400,  # 400ms (pdfplumber 포함)
        "compression_ratio_max": 0.80,  # 80% 이상이면 튜닝 필요
    }

    for result in results:
        print(f"\n케이스: {result['case']}")

        # Time p95 체크
        if result["time_p95"] > thresholds["time_p95"]:
            print(f"  ⚠️  Time p95 초과: {result['time_p95']:.3f}s > {thresholds['time_p95']:.3f}s")
        else:
            print(f"  ✅ Time p95 OK: {result['time_p95']:.3f}s")

        # Compression Ratio 체크
        if result["compression_ratio"] > thresholds["compression_ratio_max"]:
            print(
                f"  ⚠️  Compression Ratio 높음: {result['compression_ratio']:.1%} "
                f"(CONTEXT_MAX_TOKENS 또는 TOKENS_PER_CHAR 튜닝 필요)"
            )
        else:
            print(f"  ✅ Compression Ratio OK: {result['compression_ratio']:.1%}")

    # JSON 저장
    output_file = Path("reports") / f"benchmark_context_hydrator_{int(time.time())}.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 결과 저장: {output_file}")
    print("\n✅ 벤치마크 완료")


if __name__ == "__main__":
    main()
