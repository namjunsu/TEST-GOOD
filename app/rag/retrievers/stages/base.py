"""검색 Stage 기본 클래스 및 공통 타입

모든 검색 Stage는 이 모듈의 BaseSearchStage를 상속받아 구현합니다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StageResult:
    """Stage 실행 결과

    Attributes:
        results: 검색 결과 리스트
        should_continue: 다음 Stage 실행 여부 (False면 조기 종료)
        stage_name: 실행된 Stage 이름
        hit_count: 매칭된 문서 수
        metadata: 추가 메타데이터 (디버깅용)
    """

    results: list[dict[str, Any]]
    should_continue: bool = True
    stage_name: str = ""
    hit_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.hit_count == 0:
            self.hit_count = len(self.results)


@dataclass
class SearchContext:
    """검색 컨텍스트 (Stage 간 공유 데이터)

    Attributes:
        query: 원본 검색 질의
        top_k: 상위 K개 결과
        mode: 검색 모드 ("chat", "doc_anchored" 등)
        selected_filename: 우선 검색할 문서명
        strict_content: 정밀 내용 검색 모드
        seen_filenames: 이미 검색된 파일명 (중복 제거용)
        accumulated_results: 누적된 검색 결과
    """

    query: str
    top_k: int
    mode: str = "chat"
    selected_filename: Optional[str] = None
    strict_content: bool = False
    seen_filenames: set[str] = field(default_factory=set)
    accumulated_results: list[dict[str, Any]] = field(default_factory=list)

    def add_results(self, results: list[dict[str, Any]]) -> int:
        """결과 추가 (중복 제거)

        Args:
            results: 추가할 결과 리스트

        Returns:
            실제 추가된 결과 수
        """
        added = 0
        for result in results:
            filename = result.get("filename")
            if filename and filename not in self.seen_filenames:
                self.seen_filenames.add(filename)
                self.accumulated_results.append(result)
                added += 1
        return added


class BaseSearchStage(ABC):
    """검색 Stage 기본 클래스

    모든 검색 Stage는 이 클래스를 상속받아 execute() 메서드를 구현합니다.

    Attributes:
        name: Stage 이름 (로깅/디버깅용)
        priority: 실행 우선순위 (낮을수록 먼저 실행)
    """

    name: str = "BaseStage"
    priority: int = 100

    @abstractmethod
    def execute(self, context: SearchContext) -> StageResult:
        """Stage 실행

        Args:
            context: 검색 컨텍스트

        Returns:
            StageResult: 검색 결과 및 메타데이터
        """
        pass

    def should_skip(self, context: SearchContext) -> bool:
        """Stage 스킵 여부 결정

        서브클래스에서 오버라이드하여 조건부 실행 구현

        Args:
            context: 검색 컨텍스트

        Returns:
            True면 스킵, False면 실행
        """
        return False

    def _make_empty_result(self, reason: str = "") -> StageResult:
        """빈 결과 생성

        Args:
            reason: 빈 결과 이유

        Returns:
            빈 StageResult
        """
        return StageResult(
            results=[],
            should_continue=True,
            stage_name=self.name,
            metadata={"reason": reason} if reason else {},
        )

    def _log_execution(self, context: SearchContext, result: StageResult) -> None:
        """실행 결과 로깅

        Args:
            context: 검색 컨텍스트
            result: 실행 결과
        """
        if result.hit_count > 0:
            logger.info(
                f"🎯 {self.name}: {result.hit_count}건 반환 "
                f"(continue={result.should_continue})"
            )
        else:
            logger.debug(f"⏭️ {self.name}: 결과 없음")
