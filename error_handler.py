"""
Error Handler - 체계적인 에러 처리 및 복구 시스템
GPU OOM, 파일 읽기 실패, 네트워크 오류 등을 우아하게 처리
"""

import time
import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Optional, List, Dict
from functools import wraps
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class DetailedError(Exception):
    """상세 정보를 포함한 커스텀 에러 클래스"""

    def __init__(self, message: str, details: Dict = None,
                 error_code: str = None, suggestions: List[str] = None):
        """
        Args:
            message: 에러 메시지
            details: 상세 정보 딕셔너리
            error_code: 에러 코드
            suggestions: 해결 제안 리스트
        """
        super().__init__(message)
        self.details = details or {}
        self.error_code = error_code
        self.suggestions = suggestions or []
        self.timestamp = datetime.now().isoformat()
        self.traceback = traceback.format_exc()

    def to_dict(self) -> Dict:
        """에러 정보를 딕셔너리로 변환"""
        return {
            "message": str(self),
            "error_code": self.error_code,
            "details": self.details,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp,
            "traceback": self.traceback
        }

    def to_json(self) -> str:
        """에러 정보를 JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class RAGErrorHandler:
    """RAG 시스템 전용 에러 처리 클래스"""

    @staticmethod
    def handle_gpu_oom(func: Callable) -> Callable:
        """
        GPU 메모리 부족 처리 데코레이터
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RuntimeError as e:
                error_msg = str(e).lower()
                if "out of memory" in error_msg or "cuda" in error_msg:
                    logger.warning(f"⚠️ GPU 메모리 부족 감지: {func.__name__}")

                    # GPU 메모리 정리 시도
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            logger.info("🧹 GPU 캐시 정리 완료")
                    except ImportError:
                        pass

                    # 배치 크기 줄여서 재시도
                    if 'batch_size' in kwargs and kwargs['batch_size'] > 1:
                        new_batch_size = max(1, kwargs['batch_size'] // 2)
                        logger.info(f"🔄 배치 크기를 {new_batch_size}로 줄여서 재시도")
                        kwargs['batch_size'] = new_batch_size
                        return func(*args, **kwargs)

                    # CPU 모드로 폴백
                    if 'device' in kwargs:
                        logger.info("💻 CPU 모드로 전환하여 재시도")
                        kwargs['device'] = 'cpu'
                        return func(*args, **kwargs)

                    # n_gpu_layers 줄이기
                    if 'n_gpu_layers' in kwargs:
                        new_layers = max(0, kwargs['n_gpu_layers'] - 10)
                        logger.info(f"🔄 GPU 레이어를 {new_layers}로 줄여서 재시도")
                        kwargs['n_gpu_layers'] = new_layers
                        return func(*args, **kwargs)

                raise DetailedError(
                    "GPU 메모리 부족으로 처리 실패",
                    details={"original_error": str(e)},
                    error_code="GPU_OOM",
                    suggestions=[
                        "배치 크기를 줄여보세요",
                        "GPU 메모리를 정리하세요",
                        "CPU 모드를 사용하세요"
                    ]
                )
        return wrapper

    @staticmethod
    def safe_file_read(file_path: Path,
                      encodings: List[str] = None,
                      return_bytes: bool = False) -> Optional[str]:
        """
        여러 인코딩으로 파일 읽기 시도

        Args:
            file_path: 파일 경로
            encodings: 시도할 인코딩 리스트
            return_bytes: 바이트로 반환할지 여부

        Returns:
            파일 내용 또는 None
        """
        if encodings is None:
            encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']

        file_path = Path(file_path)

        # 파일 존재 확인
        if not file_path.exists():
            logger.error(f"❌ 파일을 찾을 수 없음: {file_path}")
            return None

        # 파일 권한 확인
        if not file_path.is_file():
            logger.error(f"❌ 파일이 아님: {file_path}")
            return None

        # 바이트 모드로 읽기
        if return_bytes:
            try:
                with open(file_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"❌ 바이트 읽기 실패: {file_path} - {e}")
                return None

        # 텍스트 모드로 읽기 (여러 인코딩 시도)
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                    logger.debug(f"✅ {encoding} 인코딩으로 파일 읽기 성공: {file_path.name}")
                    return content
            except UnicodeDecodeError:
                continue
            except PermissionError:
                logger.error(f"❌ 파일 접근 권한 없음: {file_path}")
                return None
            except Exception as e:
                logger.error(f"❌ 파일 읽기 오류: {file_path} - {e}")
                continue

        # 모든 인코딩 실패시 에러 무시하고 읽기
        try:
            with open(file_path, 'rb') as f:
                content = f.read().decode('utf-8', errors='ignore')
                logger.warning(f"⚠️ 에러 무시 모드로 파일 읽기: {file_path.name}")
                return content
        except Exception as e:
            logger.error(f"❌ 파일 읽기 완전 실패: {file_path} - {e}")
            return None

    @staticmethod
    def retry_with_backoff(max_retries: int = 3,
                          backoff_factor: float = 2.0,
                          max_wait: float = 30.0,
                          exceptions: tuple = (Exception,)) -> Callable:
        """
        지수 백오프로 재시도하는 데코레이터

        Args:
            max_retries: 최대 재시도 횟수
            backoff_factor: 백오프 배수
            max_wait: 최대 대기 시간
            exceptions: 재시도할 예외 타입들
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e

                        if attempt == max_retries - 1:
                            # 마지막 시도 실패
                            logger.error(f"❌ {func.__name__} 최종 실패 ({max_retries}회 시도)")
                            raise

                        # 대기 시간 계산
                        wait_time = min(backoff_factor ** attempt, max_wait)
                        logger.warning(f"⏳ 시도 {attempt + 1}/{max_retries} 실패, "
                                     f"{wait_time:.1f}초 대기 후 재시도")
                        time.sleep(wait_time)

                # 여기에 도달하면 안됨
                if last_exception:
                    raise last_exception

            return wrapper
        return decorator

    @staticmethod
    def handle_pdf_extraction_error(func: Callable) -> Callable:
        """
        PDF 추출 에러 처리 데코레이터
        """
        @wraps(func)
        def wrapper(self, pdf_path: Path, *args, **kwargs):
            extraction_methods = [
                ('pdfplumber', func),
                ('pypdf2', getattr(self, '_extract_with_pypdf2', None)),
                ('ocr', getattr(self, '_try_ocr_extraction', None))
            ]

            last_error = None
            for method_name, method in extraction_methods:
                if method is None:
                    continue

                try:
                    logger.debug(f"🔍 {method_name}로 PDF 추출 시도: {pdf_path.name}")
                    result = method(self, pdf_path, *args, **kwargs) if method != func else func(self, pdf_path, *args, **kwargs)

                    # 결과 검증
                    if result and len(str(result)) > 100:
                        logger.info(f"✅ {method_name}로 추출 성공: {pdf_path.name}")
                        return result
                    else:
                        logger.warning(f"⚠️ {method_name} 추출 결과가 너무 짧음")

                except Exception as e:
                    last_error = e
                    logger.warning(f"⚠️ {method_name} 실패: {pdf_path.name} - {e}")
                    continue

            # 모든 방법 실패
            error_msg = f"모든 추출 방법 실패: {pdf_path.name}"
            raise DetailedError(
                error_msg,
                details={
                    "file": str(pdf_path),
                    "last_error": str(last_error)
                },
                error_code="PDF_EXTRACTION_FAILED",
                suggestions=[
                    "PDF 파일이 손상되지 않았는지 확인하세요",
                    "OCR이 필요한 스캔 문서일 수 있습니다",
                    "다른 PDF 뷰어로 열어보세요"
                ]
            )
        return wrapper

    @staticmethod
    def log_and_continue(default_value: Any = None) -> Callable:
        """
        에러 발생시 로그만 남기고 계속 진행하는 데코레이터
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"⚠️ {func.__name__} 실행 중 에러 (계속 진행): {e}")
                    return default_value
            return wrapper
        return decorator

    @staticmethod
    def validate_input(validation_func: Callable) -> Callable:
        """
        입력 검증 데코레이터
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 검증 실행
                is_valid, error_msg = validation_func(*args, **kwargs)
                if not is_valid:
                    raise ValueError(f"입력 검증 실패: {error_msg}")
                return func(*args, **kwargs)
            return wrapper
        return decorator


class ErrorRecovery:
    """에러 복구 전략 클래스"""

    @staticmethod
    def with_fallback(primary_func: Callable,
                     fallback_func: Callable,
                     *args, **kwargs) -> Any:
        """
        Primary 함수 실패시 Fallback 함수 실행

        Args:
            primary_func: 주 함수
            fallback_func: 대체 함수
            *args, **kwargs: 함수 인자

        Returns:
            함수 실행 결과
        """
        try:
            return primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary 함수 실패, Fallback 실행: {e}")
            return fallback_func(*args, **kwargs)

    @staticmethod
    def progressive_degradation(funcs: List[Callable],
                              *args, **kwargs) -> Any:
        """
        점진적 기능 저하 - 여러 함수를 순차적으로 시도

        Args:
            funcs: 시도할 함수 리스트 (우선순위 순)
            *args, **kwargs: 함수 인자

        Returns:
            첫 번째 성공한 함수의 결과
        """
        errors = []
        for i, func in enumerate(funcs):
            try:
                logger.debug(f"시도 {i + 1}/{len(funcs)}: {func.__name__}")
                return func(*args, **kwargs)
            except Exception as e:
                errors.append((func.__name__, str(e)))
                continue

        # 모든 시도 실패
        raise DetailedError(
            "모든 복구 시도 실패",
            details={"attempts": errors},
            error_code="ALL_RECOVERY_FAILED"
        )


# 전역 에러 핸들러 인스턴스
error_handler = RAGErrorHandler()
error_recovery = ErrorRecovery()


# 유틸리티 함수
def safe_execute(func: Callable, *args,
                default_return=None,
                log_errors=True, **kwargs) -> Any:
    """
    안전하게 함수 실행

    Args:
        func: 실행할 함수
        default_return: 에러 발생시 반환할 기본값
        log_errors: 에러 로깅 여부

    Returns:
        함수 실행 결과 또는 기본값
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"함수 실행 실패: {func.__name__} - {e}")
        return default_return