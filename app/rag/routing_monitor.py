"""
쿼리 라우팅 모니터링 시스템
- 모든 라우팅 결정 기록
- 잘못된 라우팅 감지
- 신뢰도 점수 계산
"""

import json
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    """라우팅 결정 기록"""
    timestamp: str
    query: str
    mode: str
    reason: str
    confidence: float  # 0.0 ~ 1.0
    user_feedback: Optional[str] = None  # 사용자 피드백 (나중에 추가)


class RoutingMonitor:
    """라우팅 모니터링"""

    def __init__(self, log_dir: str = "logs/routing"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 일일 로그 파일
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"routing_{today}.jsonl"

        logger.info(f"📊 라우팅 모니터 초기화: {self.log_file}")

    def log_decision(
        self,
        query: str,
        mode: str,
        reason: str,
        confidence: float = 1.0
    ) -> None:
        """라우팅 결정 기록

        Args:
            query: 사용자 질의
            mode: 선택된 모드 (cost, search, document, qa)
            reason: 선택 이유 (패턴명 등)
            confidence: 신뢰도 (0.0~1.0)
        """
        decision = RoutingDecision(
            timestamp=datetime.now().isoformat(),
            query=query[:200],  # 길이 제한
            mode=mode,
            reason=reason,
            confidence=confidence
        )

        # JSONL 형식으로 저장 (한 줄에 하나씩)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"라우팅 로그 기록 실패: {e}")

        # 낮은 신뢰도 경고
        if confidence < 0.5:
            logger.warning(
                f"⚠️ 낮은 신뢰도 라우팅: confidence={confidence:.2f}, "
                f"mode={mode}, query='{query[:50]}...'"
            )

    def get_daily_stats(self) -> dict[str, Any]:
        """일일 통계 조회"""
        if not self.log_file.exists():
            return {"error": "No routing logs found"}

        try:
            decisions = []
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    decisions.append(json.loads(line))

            if not decisions:
                return {"total": 0}

            # 모드별 분포
            mode_counts = Counter(d["mode"] for d in decisions)

            # 평균 신뢰도
            avg_confidence = sum(d["confidence"] for d in decisions) / len(decisions)

            # 낮은 신뢰도 질의
            low_conf_queries = [
                {
                    "query": d["query"],
                    "mode": d["mode"],
                    "confidence": d["confidence"]
                }
                for d in decisions
                if d["confidence"] < 0.7
            ]

            return {
                "total": len(decisions),
                "mode_distribution": dict(mode_counts),
                "avg_confidence": round(avg_confidence, 3),
                "low_confidence_count": len(low_conf_queries),
                "low_confidence_queries": low_conf_queries[:10]  # 최대 10개
            }

        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {"error": str(e)}

    def suggest_patterns(self, min_occurrences: int = 5) -> list[dict[str, Any]]:
        """반복되는 질의에서 패턴 제안

        Args:
            min_occurrences: 최소 발생 횟수

        Returns:
            제안 패턴 리스트
        """
        # 일주일치 로그 분석
        suggestions = []

        try:
            # 최근 7일 로그 수집
            all_queries = []
            for i in range(7):
                date = datetime.now().date() - __import__("datetime").timedelta(days=i)
                log_file = self.log_dir / f"routing_{date}.jsonl"

                if log_file.exists():
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            all_queries.append(json.loads(line))

            if not all_queries:
                return []

            # QA 모드로 간 질의 중 반복되는 것 찾기
            qa_queries = [q["query"] for q in all_queries if q["mode"] == "qa"]
            query_counts = Counter(qa_queries)

            # 자주 나오는 질의 제안
            for query, count in query_counts.most_common(20):
                if count >= min_occurrences:
                    suggestions.append({
                        "query": query,
                        "count": count,
                        "current_mode": "qa",
                        "suggestion": "검색 패턴에 추가 검토 필요"
                    })

            return suggestions

        except Exception as e:
            logger.error(f"패턴 제안 실패: {e}")
            return []


# 전역 인스턴스
_monitor = None
_monitor_lock = threading.Lock()


def get_monitor() -> RoutingMonitor:
    """싱글톤 모니터 인스턴스 반환 (thread-safe)"""
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:  # Double-check locking
                _monitor = RoutingMonitor()
    return _monitor
