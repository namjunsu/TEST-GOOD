"""애플리케이션 예외 정의

계층적 예외 구조:
- AppError (기본)
  - ConfigError (설정)
  - DatabaseError (데이터베이스)
  - ModelError (AI 모델)
  - SearchError (검색)
"""


class AppError(Exception):
    """애플리케이션 기본 예외"""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (상세: {self.details})"
        return self.message


class ConfigError(AppError):
    """설정 관련 예외

    Example:
        raise ConfigError("설정 파일 로드 실패", details="/path/to/config.json")
    """
    pass


class DatabaseError(AppError):
    """데이터베이스 관련 예외

    Example:
        raise DatabaseError("DB 연결 실패", details="timeout after 5s")
    """
    pass


class ModelError(AppError):
    """AI 모델 관련 예외

    Example:
        raise ModelError("모델 로드 실패", details="CUDA out of memory")
    """
    pass


class SearchError(AppError):
    """검색 관련 예외

    Example:
        raise SearchError("인덱스 로드 실패", details="index file not found")
    """
    pass


class ValidationError(AppError):
    """입력 검증 실패

    Example:
        raise ValidationError("빈 질문", details="query cannot be empty")
    """
    pass


# ============================================================================
# 에러 코드 상수
# ============================================================================

class ErrorCode:
    """RAG 파이프라인 에러 코드

    UI에서 에러 코드 기반 메시지 매핑에 사용.
    """
    # 검색 단계
    E_RETRIEVE = "E_RETRIEVE"  # 검색 실패
    E_INDEX_LOAD = "E_INDEX_LOAD"  # 인덱스 로드 실패
    E_INDEX_LOCK = "E_INDEX_LOCK"  # 인덱스 파일락 충돌

    # 재랭킹 단계
    E_RERANK = "E_RERANK"  # 재랭킹 실패

    # 압축 단계
    E_COMPRESS = "E_COMPRESS"  # 압축 실패

    # 생성 단계
    E_GENERATE = "E_GENERATE"  # LLM 생성 실패
    E_MODEL_LOAD = "E_MODEL_LOAD"  # 모델 로드 실패

    # 데이터베이스
    E_DB_BUSY = "E_DB_BUSY"  # DB 동시 접근 충돌
    E_DB_LOCK = "E_DB_LOCK"  # DB 락 타임아웃
    E_DB_CORRUPT = "E_DB_CORRUPT"  # DB 손상

    # 시스템
    E_TIMEOUT = "E_TIMEOUT"  # 타임아웃
    E_MEMORY = "E_MEMORY"  # 메모리 부족
    E_NETWORK = "E_NETWORK"  # 네트워크 오류


# UI 메시지 매핑 (참조용)
ERROR_MESSAGES = {
    ErrorCode.E_RETRIEVE: "🔍 검색 중 오류가 발생했습니다.",
    ErrorCode.E_INDEX_LOAD: "📚 인덱스를 불러올 수 없습니다. 재인덱싱이 필요합니다.",
    ErrorCode.E_INDEX_LOCK: "🔒 인덱스가 사용 중입니다. 잠시 후 다시 시도해주세요.",
    ErrorCode.E_RERANK: "🎯 결과 정렬 중 오류가 발생했습니다.",
    ErrorCode.E_COMPRESS: "📦 문서 압축 중 오류가 발생했습니다.",
    ErrorCode.E_GENERATE: "🤖 답변 생성 중 오류가 발생했습니다.",
    ErrorCode.E_MODEL_LOAD: "⚙️ AI 모델을 불러올 수 없습니다.",
    ErrorCode.E_DB_BUSY: "💾 데이터베이스가 사용 중입니다. 잠시 후 다시 시도해주세요.",
    ErrorCode.E_DB_LOCK: "🔒 데이터베이스 접근 시간 초과입니다.",
    ErrorCode.E_DB_CORRUPT: "⚠️ 데이터베이스 손상이 의심됩니다. 관리자에게 문의하세요.",
    ErrorCode.E_TIMEOUT: "⏱️ 응답 시간이 초과되었습니다. 다시 시도해주세요.",
    ErrorCode.E_MEMORY: "💾 메모리가 부족합니다. 대화 내역을 정리해주세요.",
    ErrorCode.E_NETWORK: "🌐 네트워크 오류가 발생했습니다.",
}
