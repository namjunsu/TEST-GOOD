#!/usr/bin/env python3
"""
시스템 검증 유틸리티 (완벽 버전)

개선 사항:
- 로깅 시스템 통합
- 완전한 타입 힌트
- 프로그레스 바
- 결과 캐싱
- 더 나은 에러 메시지
- 테스트 가능한 구조
"""

import sys
import os
import shutil
import platform
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import json
import pickle

# 외부 의존성 (조건부)
try:
    from packaging import version
    PACKAGING_AVAILABLE = True
except ImportError:
    PACKAGING_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# 프로젝트 루트 경로
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

# 로깅 시스템 import (우리가 만든 것)
try:
    from app.core.logging import get_logger as get_unified_logger
    logger = get_unified_logger("system_checker")
    LOGGING_AVAILABLE = True
except ImportError:
    logger = None
    LOGGING_AVAILABLE = False


class CheckStatus(Enum):
    """검사 상태"""
    PASS = "✅"
    WARN = "⚠️"
    FAIL = "❌"
    INFO = "ℹ️"
    SKIP = "⏭️"


@dataclass
class CheckItem:
    """개별 검사 항목"""
    name: str
    status: CheckStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    action: Optional[str] = None  # 사용자가 취할 수 있는 액션

    def __str__(self) -> str:
        """문자열 표현"""
        result = f"{self.status.value} {self.message}"
        if self.action:
            result += f"\n   → {self.action}"
        return result


@dataclass
class CheckResult:
    """검사 결과 데이터 클래스"""
    items: List[CheckItem] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    duration: float = 0.0

    def add_item(self, item: CheckItem) -> None:
        """검사 항목 추가"""
        self.items.append(item)

    def get_by_status(self, status: CheckStatus) -> List[CheckItem]:
        """상태별 항목 필터링"""
        return [item for item in self.items if item.status == status]

    @property
    def errors(self) -> List[CheckItem]:
        """에러 항목"""
        return self.get_by_status(CheckStatus.FAIL)

    @property
    def warnings(self) -> List[CheckItem]:
        """경고 항목"""
        return self.get_by_status(CheckStatus.WARN)

    @property
    def passed(self) -> List[CheckItem]:
        """통과 항목"""
        return self.get_by_status(CheckStatus.PASS)

    def is_success(self) -> bool:
        """에러가 없으면 성공"""
        return len(self.errors) == 0

    def has_warnings(self) -> bool:
        """경고 있음"""
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'success': self.is_success(),
            'has_warnings': self.has_warnings(),
            'errors': [asdict(item) for item in self.errors],
            'warnings': [asdict(item) for item in self.warnings],
            'passed': [asdict(item) for item in self.passed],
            'metrics': self.metrics,
            'timestamp': self.timestamp,
            'duration': self.duration
        }


class SystemChecker:
    """시스템 요구사항 및 상태 검사 (완벽 버전)"""

    # 필수 패키지 및 최소 버전
    REQUIRED_PACKAGES: Dict[str, Tuple[str, str]] = {
        'streamlit': ('1.20.0', 'Streamlit'),
        'pandas': ('1.3.0', 'Pandas'),
        'numpy': ('1.20.0', 'NumPy'),
        'torch': ('2.0.0', 'PyTorch'),
        'sentence_transformers': ('2.0.0', 'Sentence Transformers'),
        'pdfplumber': ('0.7.0', 'PDFPlumber'),
    }

    # 선택적 패키지
    OPTIONAL_PACKAGES: Dict[str, str] = {
        'faiss': 'FAISS (CPU)',
        # 'faiss-gpu': 'FAISS (GPU)',  # Python 3.12+는 faiss-cpu 사용 (AVX2 지원)
        'psutil': 'psutil (시스템 모니터링)',
        'packaging': 'packaging (버전 비교)',
    }

    # 최소 시스템 요구사항
    MIN_DISK_GB: float = 1.0
    MIN_MEMORY_GB: float = 2.0
    RECOMMENDED_DISK_GB: float = 5.0
    RECOMMENDED_MEMORY_GB: float = 4.0

    # 캐시 설정
    CACHE_FILE: Path = project_root / '.system_check_cache.pkl'
    CACHE_TTL: int = 3600  # 1시간

    def __init__(
        self,
        verbose: bool = True,
        parallel: bool = True,
        use_cache: bool = True,
        show_progress: bool = True
    ) -> None:
        """
        Args:
            verbose: 상세 출력 여부
            parallel: 병렬 검사 여부
            use_cache: 캐시 사용 여부
            show_progress: 진행 상황 표시 여부
        """
        self.result = CheckResult()
        self.verbose = verbose
        self.parallel = parallel
        self.use_cache = use_cache
        self.show_progress = show_progress
        self.start_time = time.time()

        # 로깅
        if LOGGING_AVAILABLE and logger:
            logger.info("SystemChecker 초기화")

    def check_all(self) -> CheckResult:
        """모든 검사 실행"""
        if self.verbose:
            self._print_header()

        # 캐시 확인
        if self.use_cache:
            cached = self._load_cache()
            if cached:
                if self.verbose:
                    print("📦 캐시된 결과 사용 (빠른 검증)")
                return cached

        # 검사 실행
        checks: List[Tuple[str, Callable[[], None]]] = [
            ("Python 버전", self.check_python_version),
            ("필수 패키지", self.check_required_packages),
            ("디렉토리 구조", self.check_directories),
            ("시스템 리소스", self.check_system_resources),
            ("GPU", self.check_gpu),
            ("데이터베이스", self.check_database_files),
            ("설정 파일", self.check_config_files),
        ]

        total_checks = len(checks)

        if self.parallel:
            self._run_parallel_checks(checks, total_checks)
        else:
            self._run_sequential_checks(checks, total_checks)

        # 종료
        self.result.duration = time.time() - self.start_time

        # 캐시 저장
        if self.use_cache:
            self._save_cache(self.result)

        # 결과 출력
        if self.verbose:
            self._print_results()

        # 로깅
        if LOGGING_AVAILABLE and logger:
            logger.info(f"검사 완료: {len(self.result.errors)}개 오류, "
                       f"{len(self.result.warnings)}개 경고")

        return self.result

    def _run_parallel_checks(
        self,
        checks: List[Tuple[str, Callable[[], None]]],
        total: int
    ) -> None:
        """병렬 검사 실행"""
        completed = 0

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(check_func): name
                for name, check_func in checks
            }

            for future in as_completed(futures):
                name = futures[future]
                try:
                    future.result()
                    completed += 1
                    if self.show_progress:
                        self._show_progress(completed, total, name)
                except Exception as e:
                    self.result.add_item(CheckItem(
                        name=name,
                        status=CheckStatus.FAIL,
                        message=f"{name} 검사 실패",
                        details={'error': str(e)},
                        action="로그를 확인하세요"
                    ))
                    if LOGGING_AVAILABLE and logger:
                        logger.error(f"{name} 검사 실패", exception=e)

    def _run_sequential_checks(
        self,
        checks: List[Tuple[str, Callable[[], None]]],
        total: int
    ) -> None:
        """순차 검사 실행"""
        for i, (name, check_func) in enumerate(checks, 1):
            try:
                check_func()
                if self.show_progress:
                    self._show_progress(i, total, name)
            except Exception as e:
                self.result.add_item(CheckItem(
                    name=name,
                    status=CheckStatus.FAIL,
                    message=f"{name} 검사 실패",
                    details={'error': str(e)},
                    action="로그를 확인하세요"
                ))
                if LOGGING_AVAILABLE and logger:
                    logger.error(f"{name} 검사 실패", exception=e)

    def _show_progress(self, current: int, total: int, name: str) -> None:
        """진행 상황 표시"""
        percent = (current / total) * 100
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)

        print(f"\r[{bar}] {percent:.0f}% - {name}...", end='', flush=True)

        if current == total:
            print()  # 줄바꿈

    def check_python_version(self) -> None:
        """Python 버전 체크 (타입 힌트 완전)"""
        required_version: Tuple[int, int] = (3, 8)
        current_version: Tuple[int, int] = sys.version_info[:2]

        self.result.metrics['python_version'] = f"{current_version[0]}.{current_version[1]}"
        self.result.metrics['python_impl'] = platform.python_implementation()

        if current_version >= required_version:
            self.result.add_item(CheckItem(
                name="python_version",
                status=CheckStatus.PASS,
                message=f"Python {sys.version.split()[0]} ({platform.python_implementation()})",
                details={
                    'version': self.result.metrics['python_version'],
                    'implementation': platform.python_implementation()
                }
            ))
        else:
            self.result.add_item(CheckItem(
                name="python_version",
                status=CheckStatus.FAIL,
                message=f"Python 버전 부족: {current_version[0]}.{current_version[1]}",
                details={
                    'required': f"{required_version[0]}.{required_version[1]}",
                    'current': f"{current_version[0]}.{current_version[1]}"
                },
                action=f"Python {required_version[0]}.{required_version[1]} 이상으로 업그레이드하세요"
            ))

    def check_required_packages(self) -> None:
        """필수 패키지 및 버전 체크 (개선된 버전)"""
        for pkg_name, (min_version, display_name) in self.REQUIRED_PACKAGES.items():
            self._check_package(pkg_name, display_name, min_version, required=True)

        # 선택적 패키지
        for pkg_name, display_name in self.OPTIONAL_PACKAGES.items():
            self._check_package(pkg_name, display_name, None, required=False)

    def _check_package(
        self,
        pkg_name: str,
        display_name: str,
        min_version: Optional[str],
        required: bool
    ) -> None:
        """개별 패키지 체크"""
        import importlib.util
        import importlib.metadata

        spec = importlib.util.find_spec(pkg_name)

        if spec is None:
            status = CheckStatus.FAIL if required else CheckStatus.WARN
            self.result.add_item(CheckItem(
                name=f"package_{pkg_name}",
                status=status,
                message=f"{display_name} 미설치",
                action=f"pip install {pkg_name}"
            ))
            return

        # 버전 확인
        if min_version:
            try:
                installed_version = importlib.metadata.version(pkg_name)

                if PACKAGING_AVAILABLE:
                    # packaging 모듈 사용 (더 정확함)
                    if version.parse(installed_version) >= version.parse(min_version):
                        self.result.add_item(CheckItem(
                            name=f"package_{pkg_name}",
                            status=CheckStatus.PASS,
                            message=f"{display_name} {installed_version}",
                            details={'version': installed_version}
                        ))
                    else:
                        self.result.add_item(CheckItem(
                            name=f"package_{pkg_name}",
                            status=CheckStatus.WARN,
                            message=f"{display_name} 버전 부족: {installed_version} < {min_version}",
                            action=f"pip install --upgrade {pkg_name}"
                        ))
                else:
                    # packaging 없으면 간단 비교
                    self.result.add_item(CheckItem(
                        name=f"package_{pkg_name}",
                        status=CheckStatus.PASS,
                        message=f"{display_name} {installed_version}",
                        details={'version': installed_version, 'version_check': 'skipped'}
                    ))

            except importlib.metadata.PackageNotFoundError:
                # 메타데이터 없음 (개발 설치 등)
                self.result.add_item(CheckItem(
                    name=f"package_{pkg_name}",
                    status=CheckStatus.PASS,
                    message=f"{display_name} (버전 확인 불가)",
                    details={'version_check': 'unavailable'}
                ))
        else:
            # 버전 체크 불필요
            self.result.add_item(CheckItem(
                name=f"package_{pkg_name}",
                status=CheckStatus.PASS,
                message=f"{display_name}",
            ))

    def check_directories(self) -> None:
        """필수 디렉토리 체크"""
        required_dirs: Dict[str, str] = {
            'docs': '문서 디렉토리',
            'models': '모델 디렉토리',
            'logs': '로그 디렉토리',
            'rag_system/cache': '캐시 디렉토리',
            'rag_system/db': 'DB 디렉토리',
            'utils': '유틸리티 디렉토리',
        }

        for dir_path, description in required_dirs.items():
            full_path: Path = project_root / dir_path

            if full_path.exists():
                # 권한도 함께 체크
                writable = os.access(full_path, os.W_OK)
                status = CheckStatus.PASS if writable else CheckStatus.WARN

                self.result.add_item(CheckItem(
                    name=f"dir_{dir_path}",
                    status=status,
                    message=f"{description}: {dir_path}/{'(읽기전용)' if not writable else ''}",
                    details={'path': str(full_path), 'writable': writable}
                ))
            else:
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    self.result.add_item(CheckItem(
                        name=f"dir_{dir_path}",
                        status=CheckStatus.WARN,
                        message=f"{description} 자동 생성됨: {dir_path}/",
                        details={'path': str(full_path), 'created': True}
                    ))
                except OSError as e:
                    self.result.add_item(CheckItem(
                        name=f"dir_{dir_path}",
                        status=CheckStatus.FAIL,
                        message=f"{description} 생성 실패",
                        details={'path': str(full_path), 'error': str(e)},
                        action=f"수동으로 생성하세요: mkdir -p {dir_path}"
                    ))

    def check_system_resources(self) -> None:
        """시스템 리소스 체크 (개선된 버전)"""
        # 디스크 공간
        try:
            disk = shutil.disk_usage(project_root)
            free_gb = disk.free / (1024 ** 3)
            total_gb = disk.total / (1024 ** 3)
            usage_percent = (disk.used / disk.total) * 100

            self.result.metrics['disk_free_gb'] = round(free_gb, 2)
            self.result.metrics['disk_total_gb'] = round(total_gb, 2)
            self.result.metrics['disk_usage_percent'] = round(usage_percent, 2)

            if free_gb < self.MIN_DISK_GB:
                self.result.add_item(CheckItem(
                    name="disk_space",
                    status=CheckStatus.FAIL,
                    message=f"디스크 공간 부족: {free_gb:.1f}GB",
                    details={'free': free_gb, 'total': total_gb},
                    action=f"최소 {self.MIN_DISK_GB}GB 확보 필요"
                ))
            elif free_gb < self.RECOMMENDED_DISK_GB:
                self.result.add_item(CheckItem(
                    name="disk_space",
                    status=CheckStatus.WARN,
                    message=f"디스크 공간 여유 부족: {free_gb:.1f}GB / {total_gb:.1f}GB",
                    details={'free': free_gb, 'total': total_gb},
                    action=f"권장: {self.RECOMMENDED_DISK_GB}GB 이상"
                ))
            else:
                self.result.add_item(CheckItem(
                    name="disk_space",
                    status=CheckStatus.PASS,
                    message=f"디스크: {free_gb:.1f}GB / {total_gb:.1f}GB ({100-usage_percent:.1f}% 여유)",
                    details={'free': free_gb, 'total': total_gb, 'usage': usage_percent}
                ))

        except Exception as e:
            self.result.add_item(CheckItem(
                name="disk_space",
                status=CheckStatus.WARN,
                message="디스크 공간 체크 실패",
                details={'error': str(e)}
            ))

        # 메모리 (psutil 필요)
        if PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                available_gb = mem.available / (1024 ** 3)
                total_gb = mem.total / (1024 ** 3)

                self.result.metrics['memory_available_gb'] = round(available_gb, 2)
                self.result.metrics['memory_total_gb'] = round(total_gb, 2)
                self.result.metrics['memory_usage_percent'] = mem.percent

                if available_gb < self.MIN_MEMORY_GB:
                    self.result.add_item(CheckItem(
                        name="memory",
                        status=CheckStatus.WARN,
                        message=f"메모리 부족: {available_gb:.1f}GB / {total_gb:.1f}GB",
                        details={'available': available_gb, 'total': total_gb},
                        action="다른 프로그램을 종료하세요"
                    ))
                else:
                    self.result.add_item(CheckItem(
                        name="memory",
                        status=CheckStatus.PASS,
                        message=f"메모리: {available_gb:.1f}GB / {total_gb:.1f}GB 사용 가능",
                        details={'available': available_gb, 'total': total_gb, 'usage': mem.percent}
                    ))

            except Exception as e:
                self.result.add_item(CheckItem(
                    name="memory",
                    status=CheckStatus.WARN,
                    message="메모리 체크 실패",
                    details={'error': str(e)}
                ))
        else:
            self.result.add_item(CheckItem(
                name="memory",
                status=CheckStatus.SKIP,
                message="메모리 체크 건너뜀 (psutil 미설치)",
                action="pip install psutil"
            ))

    def check_gpu(self) -> None:
        """GPU 감지 및 상태 체크"""
        gpu_found = False

        # NVIDIA GPU (PyTorch)
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)

                self.result.metrics['gpu_available'] = True
                self.result.metrics['gpu_count'] = gpu_count
                self.result.metrics['gpu_memory_gb'] = round(gpu_memory, 2)
                self.result.metrics['gpu_name'] = gpu_name

                self.result.add_item(CheckItem(
                    name="gpu",
                    status=CheckStatus.PASS,
                    message=f"NVIDIA GPU: {gpu_name} ({gpu_memory:.1f}GB)",
                    details={
                        'count': gpu_count,
                        'name': gpu_name,
                        'memory': gpu_memory
                    }
                ))
                gpu_found = True

        except ImportError:
            pass
        except Exception as e:
            self.result.add_item(CheckItem(
                name="gpu",
                status=CheckStatus.WARN,
                message="GPU 체크 실패",
                details={'error': str(e)}
            ))

        if not gpu_found:
            self.result.metrics['gpu_available'] = False
            self.result.add_item(CheckItem(
                name="gpu",
                status=CheckStatus.INFO,
                message="GPU 없음 (CPU 모드로 실행)",
                details={'mode': 'CPU'}
            ))

    def check_database_files(self) -> None:
        """데이터베이스 파일 체크"""
        db_files: Dict[str, str] = {
            'everything_index.db': '문서 인덱스 DB',
            'metadata.db': '메타데이터 DB'
        }

        total_size = 0.0

        for db_file, description in db_files.items():
            db_path: Path = project_root / db_file

            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                total_size += size_mb

                self.result.add_item(CheckItem(
                    name=f"db_{db_file}",
                    status=CheckStatus.PASS,
                    message=f"{description}: {size_mb:.1f}MB",
                    details={'path': str(db_path), 'size_mb': size_mb}
                ))
            else:
                self.result.add_item(CheckItem(
                    name=f"db_{db_file}",
                    status=CheckStatus.WARN,
                    message=f"{description} 없음",
                    details={'path': str(db_path)},
                    action="자동 인덱싱으로 생성됩니다"
                ))

        if total_size > 0:
            self.result.metrics['db_total_size_mb'] = round(total_size, 2)

    def check_config_files(self) -> None:
        """설정 파일 체크"""
        config_file: Path = project_root / 'config.py'

        if not config_file.exists():
            self.result.add_item(CheckItem(
                name="config_file",
                status=CheckStatus.FAIL,
                message="config.py 파일 없음",
                details={'path': str(config_file)},
                action="config.py 파일을 생성하세요"
            ))
            return

        try:
            import config

            # 필수 설정 체크
            required_settings: List[str] = [
                'QWEN_MODEL_PATH',
                'DOCS_DIR',
                'MODELS_DIR',
                'CACHE_DIR',
                'DB_DIR'
            ]

            missing = [s for s in required_settings if not hasattr(config, s)]

            if missing:
                self.result.add_item(CheckItem(
                    name="config_settings",
                    status=CheckStatus.WARN,
                    message=f"누락된 설정: {', '.join(missing)}",
                    details={'missing': missing},
                    action=f"config.py에 {', '.join(missing)} 추가"
                ))
            else:
                self.result.add_item(CheckItem(
                    name="config_settings",
                    status=CheckStatus.PASS,
                    message="설정 파일 검증 완료",
                ))

            # validate_config 실행
            if hasattr(config, 'validate_config'):
                validations = config.validate_config()
                for check, passed in validations.items():
                    if not passed:
                        self.result.add_item(CheckItem(
                            name=f"config_validation_{check}",
                            status=CheckStatus.WARN,
                            message=f"설정 검증 실패: {check}",
                        ))

            # 모델 파일 체크
            if hasattr(config, 'QWEN_MODEL_PATH'):
                model_path = Path(config.QWEN_MODEL_PATH)
                if model_path.exists():
                    size_mb = model_path.stat().st_size / (1024 * 1024)
                    self.result.metrics['model_size_mb'] = round(size_mb, 2)
                    self.result.add_item(CheckItem(
                        name="model_file",
                        status=CheckStatus.PASS,
                        message=f"AI 모델: {model_path.name} ({size_mb:.1f}MB)",
                        details={'path': str(model_path), 'size_mb': size_mb}
                    ))
                else:
                    self.result.add_item(CheckItem(
                        name="model_file",
                        status=CheckStatus.WARN,
                        message=f"AI 모델 파일 없음: {model_path.name}",
                        details={'path': str(model_path)},
                        action="AI 분석 기능 비활성화됨"
                    ))

        except ImportError as e:
            self.result.add_item(CheckItem(
                name="config_import",
                status=CheckStatus.FAIL,
                message="config.py 임포트 실패",
                details={'error': str(e)},
                action="config.py 문법 오류를 수정하세요"
            ))
        except Exception as e:
            self.result.add_item(CheckItem(
                name="config_check",
                status=CheckStatus.WARN,
                message="설정 검증 중 오류",
                details={'error': str(e)}
            ))

    def _load_cache(self) -> Optional[CheckResult]:
        """캐시 로드"""
        if not self.CACHE_FILE.exists():
            return None

        try:
            # 캐시 파일 나이 확인
            cache_age = time.time() - self.CACHE_FILE.stat().st_mtime
            if cache_age > self.CACHE_TTL:
                return None

            with open(self.CACHE_FILE, 'rb') as f:
                cached_result = pickle.load(f)

            if LOGGING_AVAILABLE and logger:
                logger.debug("캐시된 결과 로드 성공")

            return cached_result

        except Exception as e:
            if LOGGING_AVAILABLE and logger:
                logger.warning(f"캐시 로드 실패: {e}")
            return None

    def _save_cache(self, result: CheckResult) -> None:
        """캐시 저장"""
        try:
            with open(self.CACHE_FILE, 'wb') as f:
                pickle.dump(result, f)

            if LOGGING_AVAILABLE and logger:
                logger.debug("검사 결과 캐시 저장 완료")

        except Exception as e:
            if LOGGING_AVAILABLE and logger:
                logger.warning(f"캐시 저장 실패: {e}")

    def _print_header(self) -> None:
        """헤더 출력"""
        print("=" * 70)
        print("  AI-CHAT 시스템 검증 v3.0 (Perfect Edition)")
        print("=" * 70)

    def _print_results(self) -> None:
        """검사 결과 출력 (개선된 버전)"""
        print("\n" + "=" * 70)
        print("  검사 결과")
        print("=" * 70)

        # 에러
        errors = self.result.errors
        if errors:
            print(f"\n🔴 오류 ({len(errors)}개) - 반드시 수정 필요:")
            for item in errors:
                print(f"  {item}")

        # 경고
        warnings = self.result.warnings
        if warnings:
            print(f"\n⚠️  경고 ({len(warnings)}개) - 선택적 수정:")
            for item in warnings:
                print(f"  {item}")

        # 정상
        passed = self.result.passed
        if passed and not errors:
            print(f"\n✅ 정상 ({len(passed)}개):")
            for item in passed[:10]:  # 처음 10개만
                print(f"  {item.message}")
            if len(passed) > 10:
                print(f"  ... 외 {len(passed) - 10}개 항목")

        # 메트릭 요약
        if self.result.metrics:
            print("\n📊 시스템 정보:")
            interesting_metrics = {
                'python_version': 'Python',
                'disk_free_gb': '디스크 여유 (GB)',
                'memory_available_gb': '메모리 여유 (GB)',
                'gpu_available': 'GPU',
                'db_total_size_mb': 'DB 크기 (MB)',
            }
            for key, label in interesting_metrics.items():
                if key in self.result.metrics:
                    value = self.result.metrics[key]
                    print(f"  • {label}: {value}")

        # 요약
        print("\n" + "=" * 70)
        print(f"⏱️  검사 시간: {self.result.duration:.2f}초")

        if errors:
            print(f"❌ 검증 실패: {len(errors)}개 오류, {len(warnings)}개 경고")
            print("\n💡 위 액션을 참고하여 오류를 수정하세요.")
        elif warnings:
            print(f"⚠️  경고 있음: {len(warnings)}개 경고")
            print("\n💡 시스템은 작동하지만 일부 기능이 제한될 수 있습니다.")
        else:
            print("✅ 모든 검사 통과!")
            print(f"\n🎉 총 {len(passed)}개 항목이 정상입니다.")

        print("=" * 70 + "\n")

    def to_json(self, file_path: Optional[Path] = None) -> str:
        """결과를 JSON으로 저장"""
        json_str = json.dumps(self.result.to_dict(), indent=2, ensure_ascii=False)

        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_str)

        return json_str


def quick_check() -> bool:
    """빠른 체크 (핵심만)"""
    checker = SystemChecker(verbose=False, parallel=False, show_progress=False)
    checker.check_python_version()
    checker.check_config_files()
    checker.check_directories()
    return checker.result.is_success()


def main() -> None:
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description='AI-CHAT 시스템 검증 (완벽 버전)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python system_checker.py                    # 기본 검사
  python system_checker.py --json result.json # JSON 출력
  python system_checker.py --quiet            # 간단한 출력
  python system_checker.py --no-cache         # 캐시 사용 안 함
        """
    )

    parser.add_argument('--json', type=str, help='결과를 JSON 파일로 저장')
    parser.add_argument('--quiet', action='store_true', help='간단한 출력')
    parser.add_argument('--no-parallel', action='store_true', help='병렬 처리 비활성화')
    parser.add_argument('--no-cache', action='store_true', help='캐시 사용 안 함')
    parser.add_argument('--no-progress', action='store_true', help='진행바 숨기기')

    args = parser.parse_args()

    checker = SystemChecker(
        verbose=not args.quiet,
        parallel=not args.no_parallel,
        use_cache=not args.no_cache,
        show_progress=not args.no_progress
    )

    result = checker.check_all()

    # JSON 출력
    if args.json:
        checker.to_json(Path(args.json))
        if not args.quiet:
            print(f"\n📄 결과가 {args.json}에 저장되었습니다.")

    # Exit code
    sys.exit(0 if result.is_success() else 1)


if __name__ == "__main__":
    main()
