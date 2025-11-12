"""
성능 설정 하위호환 레이어 v1.0
================================

v0 → v1 자동 매핑:
- parallel.max_workers → pools.*.max_workers
- parallel.use_multiprocessing → pools.cpu.executor
- ocr.enabled → ocr.mode
- memory.max_memory_mb → memory.hard_limit_mb
"""

import os
from typing import Dict, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


def normalize_performance_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    성능 설정 v0 → v1 정규화

    Args:
        cfg: 원본 설정 (v0 or v1)

    Returns:
        정규화된 v1 설정
    """
    cfg = cfg.copy()  # 원본 보존

    # 1. 병렬 처리 설정
    _normalize_parallel(cfg)

    # 2. OCR 설정
    _normalize_ocr(cfg)

    # 3. 캐시 설정
    _normalize_cache(cfg)

    # 4. 메모리 설정
    _normalize_memory(cfg)

    # 5. 문서 처리 설정
    _normalize_documents(cfg)

    # 6. 로깅 설정
    _normalize_logging(cfg)

    # 스키마 버전 설정
    cfg.setdefault("schema_version", 1)

    logger.info(f"성능 설정 정규화 완료: v{cfg.get('schema_version', 0)}")
    return cfg


def _normalize_parallel(cfg: Dict[str, Any]) -> None:
    """병렬 처리 설정 정규화"""
    parallel = cfg.get("parallel", {})

    # pools가 없으면 v0 → v1 변환
    if "pools" not in parallel:
        max_workers = parallel.get("max_workers", 4)
        chunk_size = parallel.get("chunk_size", 10)
        use_mp = parallel.get("use_multiprocessing", False)

        # CPU 코어 수 기반 auto 계산
        cpu_count = os.cpu_count() or 4

        # auto 워커 계산
        io_workers = max_workers if not use_mp else min(8, 2 * cpu_count)
        cpu_workers = max_workers if use_mp else max(1, cpu_count - 1)

        parallel["pools"] = {
            "io": {
                "executor": "thread",
                "max_workers": io_workers,
                "chunk_size": chunk_size * 2,  # IO는 더 큰 chunk
                "queue_size": 128,
            },
            "cpu": {
                "executor": "process" if use_mp else "thread",
                "max_workers": cpu_workers,
                "chunk_size": chunk_size,
                "queue_size": 32,
            },
        }

        logger.info(
            f"병렬 풀 변환: io={io_workers}, cpu={cpu_workers} "
            f"(use_mp={use_mp}, cpu_count={cpu_count})"
        )


def _normalize_ocr(cfg: Dict[str, Any]) -> None:
    """OCR 설정 정규화"""
    ocr = cfg.get("ocr", {})

    # mode가 없으면 v0 → v1 변환
    if "mode" not in ocr:
        enabled = ocr.get("enabled", True)

        # v0 로직: enabled=True → fallback
        if enabled:
            ocr["mode"] = "fallback"
        else:
            ocr["mode"] = "off"

        logger.info(f"OCR 모드 변환: enabled={enabled} → mode={ocr['mode']}")

    # 타임아웃 정규화
    if "page_timeout_sec" not in ocr:
        timeout = ocr.get("timeout", 30)
        ocr["page_timeout_sec"] = min(timeout // 6, 5)  # 페이지당 ~5초
        ocr["doc_timeout_sec"] = timeout

    # 품질 설정 기본값
    ocr.setdefault("dpi", 300)
    ocr.setdefault("lang", "kor+eng")
    ocr.setdefault("concurrent_pages", 2)
    ocr.setdefault("max_pages", 30)


def _normalize_cache(cfg: Dict[str, Any]) -> None:
    """캐시 설정 정규화"""
    cache = cfg.get("cache", {})

    # v1 필드 기본값
    cache.setdefault("policy", "LRU")
    cache.setdefault("version_salt", "v1")

    # preload 정규화
    if "preload" in cache:
        preload = cache["preload"]
        # v0: preload: true → v1: preload: {enabled: true, limit: 200}
        if isinstance(preload, bool):
            cache["preload"] = {
                "enabled": preload,
                "limit": 200,
                "types": ["metadata", "frequent_docs"],
            }
        elif isinstance(preload, dict):
            preload.setdefault("limit", 200)
            preload.setdefault("types", ["metadata", "frequent_docs"])

    # ttl_overrides 기본값
    cache.setdefault(
        "ttl_overrides",
        {"ocr_results": 72, "embeddings": 168, "metadata": 24},
    )


def _normalize_memory(cfg: Dict[str, Any]) -> None:
    """메모리 설정 정규화"""
    memory = cfg.get("memory", {})

    # v0: max_memory_mb → v1: hard_limit_mb
    if "hard_limit_mb" not in memory:
        max_mem = memory.get("max_memory_mb", 2000)
        memory["soft_limit_mb"] = int(max_mem * 0.85)  # 85%를 소프트 임계값
        memory["hard_limit_mb"] = max_mem

        logger.info(
            f"메모리 임계값 설정: soft={memory['soft_limit_mb']}MB, "
            f"hard={memory['hard_limit_mb']}MB"
        )

    # queue_backpressure 기본값
    if "queue_backpressure" not in memory:
        memory["queue_backpressure"] = {
            "enabled": True,
            "max_inflight_tasks": 64,
            "drop_policy": "oldest",
        }

    # monitor 기본값
    if "monitor" not in memory:
        memory["monitor"] = {
            "enabled": True,
            "check_interval_sec": 10,
            "alert_threshold_pct": 85,
        }


def _normalize_documents(cfg: Dict[str, Any]) -> None:
    """문서 처리 설정 정규화"""
    docs = cfg.get("documents", {})

    # warmup 기본값
    if "warmup" not in docs:
        docs["warmup"] = {
            "enabled": True,
            "top_k": 100,
            "delay_sec": 5,
            "types": ["metadata", "index"],
        }

    docs.setdefault("max_file_size_mb", 50)


def _normalize_logging(cfg: Dict[str, Any]) -> None:
    """로깅 설정 정규화"""
    logging = cfg.get("logging", {})

    # v1 필드 기본값
    logging.setdefault("structured", False)  # 기본은 일반 로그
    logging.setdefault("sample_debug_rate", 0.05)

    # file 설정 기본값
    if "file" not in logging:
        logging["file"] = {
            "enabled": True,
            "max_mb": 10,
            "backup_count": 5,
        }


def resolve_auto_workers(
    pool_type: str, cpu_count: Optional[int] = None
) -> int:
    """
    'auto' 워커 수 계산

    Args:
        pool_type: "io" or "cpu"
        cpu_count: CPU 코어 수 (None이면 자동 감지)

    Returns:
        워커 수
    """
    if cpu_count is None:
        cpu_count = os.cpu_count() or 4

    if pool_type == "io":
        return min(8, 2 * cpu_count)
    elif pool_type == "cpu":
        return max(1, cpu_count - 1)
    else:
        return 4  # fallback
