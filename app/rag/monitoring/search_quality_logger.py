"""검색 품질 로깅 시스템

모든 검색 쿼리, 결과, 점수를 로깅하여 품질 분석 가능

사용법:
    from app.rag.monitoring.search_quality_logger import SearchQualityLogger

    logger = SearchQualityLogger()
    logger.log_search(query, results, score_stats)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class SearchQualityLogger:
    """검색 품질 로깅"""

    def __init__(self, log_dir: str = "logs"):
        """초기화

        Args:
            log_dir: 로그 디렉토리 경로
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # JSONL 파일 (추가 모드)
        self.log_file = self.log_dir / "search_quality.jsonl"

    def log_search(self, query: str, results: List[Dict[str, Any]],
                   score_stats: Dict[str, Any], metadata: Dict[str, Any] = None):
        """검색 로깅

        Args:
            query: 검색 쿼리
            results: 검색 결과 리스트
            score_stats: 점수 통계 (top1, top2, delta12 등)
            metadata: 추가 메타데이터 (mode, latency 등)
        """
        # 품질 평가
        quality = self._assess_quality(score_stats, results)

        # 로그 엔트리 생성
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "hits": len(results),
            "quality": quality,
            "score_stats": score_stats,
        }

        # 메타데이터 추가
        if metadata:
            log_entry.update(metadata)

        # 상위 3개 결과 요약
        if results:
            log_entry["top3"] = [
                {
                    "filename": r.get("filename", "Unknown")[:50],
                    "score": round(r.get("score", 0.0), 2)
                }
                for r in results[:3]
            ]

        # JSONL 파일에 추가
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _assess_quality(self, score_stats: Dict[str, Any],
                       results: List[Dict[str, Any]]) -> str:
        """검색 품질 평가

        Args:
            score_stats: 점수 통계
            results: 검색 결과

        Returns:
            품질 등급 (HIGH_CONFIDENCE, MEDIUM_CONFIDENCE, LOW_CONFIDENCE)
        """
        top1 = score_stats.get("top1", 0.0)
        delta12 = score_stats.get("delta12", 0.0)
        hits = len(results)

        # 결과 없음
        if hits == 0:
            return "NO_RESULTS"

        # 고신뢰도: top1 > 5.0 and delta12 > 1.0
        if top1 > 5.0 and delta12 > 1.0:
            return "HIGH_CONFIDENCE"

        # 중신뢰도: top1 > 2.0
        elif top1 > 2.0:
            return "MEDIUM_CONFIDENCE"

        # 저신뢰도: 나머지
        else:
            return "LOW_CONFIDENCE"

    def get_recent_logs(self, n: int = 100) -> List[Dict[str, Any]]:
        """최근 로그 조회

        Args:
            n: 조회할 로그 수

        Returns:
            로그 엔트리 리스트
        """
        if not self.log_file.exists():
            return []

        logs = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 최근 n개 반환
        return logs[-n:]

    def get_quality_stats(self, n: int = 1000) -> Dict[str, Any]:
        """품질 통계 분석

        Args:
            n: 분석할 최근 로그 수

        Returns:
            통계 딕셔너리
        """
        logs = self.get_recent_logs(n)

        if not logs:
            return {"total": 0}

        # 품질별 카운트
        quality_counts = {}
        for log in logs:
            quality = log.get("quality", "UNKNOWN")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

        # 평균 히트 수
        avg_hits = sum(log.get("hits", 0) for log in logs) / len(logs)

        # 평균 top1 점수
        avg_top1 = sum(log.get("score_stats", {}).get("top1", 0.0) for log in logs) / len(logs)

        return {
            "total": len(logs),
            "quality_distribution": quality_counts,
            "avg_hits": round(avg_hits, 2),
            "avg_top1_score": round(avg_top1, 2),
            "low_confidence_ratio": quality_counts.get("LOW_CONFIDENCE", 0) / len(logs)
        }
