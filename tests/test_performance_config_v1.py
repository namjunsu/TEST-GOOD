"""
테스트: 성능 설정 v1.0
======================

v0 → v1 하위호환 + 병렬 풀 + OCR 모드 통합 테스트
"""

import pytest
from app.config.performance_compat import (
    normalize_performance_config,
    resolve_auto_workers,
)


class TestPerformanceCompat:
    """성능 설정 하위호환 테스트"""

    def test_v0_to_v1_parallel(self):
        """v0 병렬 설정 → v1 풀 구조 변환"""
        v0_config = {
            "parallel": {
                "max_workers": 4,
                "chunk_size": 10,
                "use_multiprocessing": False,
            }
        }

        v1_config = normalize_performance_config(v0_config)

        assert "pools" in v1_config["parallel"]
        assert "io" in v1_config["parallel"]["pools"]
        assert "cpu" in v1_config["parallel"]["pools"]
        assert v1_config["parallel"]["pools"]["io"]["executor"] == "thread"

    def test_v0_to_v1_ocr_enabled(self):
        """v0 OCR enabled=True → v1 mode=fallback"""
        v0_config = {"ocr": {"enabled": True}}

        v1_config = normalize_performance_config(v0_config)

        assert v1_config["ocr"]["mode"] == "fallback"

    def test_v0_to_v1_ocr_disabled(self):
        """v0 OCR enabled=False → v1 mode=off"""
        v0_config = {"ocr": {"enabled": False}}

        v1_config = normalize_performance_config(v0_config)

        assert v1_config["ocr"]["mode"] == "off"

    def test_v0_to_v1_memory(self):
        """v0 메모리 max_memory_mb → v1 soft/hard 임계값"""
        v0_config = {"memory": {"max_memory_mb": 2000}}

        v1_config = normalize_performance_config(v0_config)

        assert v1_config["memory"]["soft_limit_mb"] == 1700  # 85%
        assert v1_config["memory"]["hard_limit_mb"] == 2000

    def test_v0_to_v1_cache_preload(self):
        """v0 캐시 preload bool → v1 preload dict"""
        v0_config = {"cache": {"preload": True}}

        v1_config = normalize_performance_config(v0_config)

        assert isinstance(v1_config["cache"]["preload"], dict)
        assert v1_config["cache"]["preload"]["enabled"] is True
        assert v1_config["cache"]["preload"]["limit"] == 200

    def test_v1_config_unchanged(self):
        """v1 설정은 변경되지 않음"""
        v1_config = {
            "schema_version": 1,
            "parallel": {
                "pools": {
                    "io": {"executor": "thread", "max_workers": 8},
                    "cpu": {"executor": "process", "max_workers": 3},
                }
            },
            "ocr": {"mode": "fallback"},
        }

        normalized = normalize_performance_config(v1_config)

        assert normalized["parallel"]["pools"]["io"]["executor"] == "thread"
        assert normalized["ocr"]["mode"] == "fallback"


class TestAutoWorkers:
    """auto 워커 계산 테스트"""

    def test_io_workers(self):
        """IO 워커 = min(8, 2*CPU)"""
        # 4코어
        workers = resolve_auto_workers("io", cpu_count=4)
        assert workers == 8

        # 6코어
        workers = resolve_auto_workers("io", cpu_count=6)
        assert workers == 8  # max 8

    def test_cpu_workers(self):
        """CPU 워커 = max(1, CPU-1)"""
        # 4코어
        workers = resolve_auto_workers("cpu", cpu_count=4)
        assert workers == 3

        # 1코어
        workers = resolve_auto_workers("cpu", cpu_count=1)
        assert workers == 1  # min 1

    def test_fallback_workers(self):
        """알 수 없는 타입은 4"""
        workers = resolve_auto_workers("unknown", cpu_count=4)
        assert workers == 4


class TestOCRMode:
    """OCR 모드 테스트"""

    def test_ocr_mode_off(self):
        """OCR 모드: off"""
        config = {"ocr": {"mode": "off"}}
        normalized = normalize_performance_config(config)

        assert normalized["ocr"]["mode"] == "off"

    def test_ocr_mode_fallback(self):
        """OCR 모드: fallback"""
        config = {"ocr": {"mode": "fallback"}}
        normalized = normalize_performance_config(config)

        assert normalized["ocr"]["mode"] == "fallback"

    def test_ocr_mode_force(self):
        """OCR 모드: force"""
        config = {"ocr": {"mode": "force"}}
        normalized = normalize_performance_config(config)

        assert normalized["ocr"]["mode"] == "force"

    def test_ocr_timeout_conversion(self):
        """OCR 타임아웃 변환 (v0 → v1)"""
        config = {"ocr": {"timeout": 30}}
        normalized = normalize_performance_config(config)

        assert "page_timeout_sec" in normalized["ocr"]
        assert "doc_timeout_sec" in normalized["ocr"]
        assert normalized["ocr"]["doc_timeout_sec"] == 30


class TestMemoryLimits:
    """메모리 임계값 테스트"""

    def test_soft_hard_limits(self):
        """소프트/하드 임계값 설정"""
        config = {"memory": {"max_memory_mb": 3000}}
        normalized = normalize_performance_config(config)

        assert normalized["memory"]["soft_limit_mb"] == 2550  # 85%
        assert normalized["memory"]["hard_limit_mb"] == 3000

    def test_queue_backpressure(self):
        """큐 백프레셔 기본값"""
        config = {"memory": {}}
        normalized = normalize_performance_config(config)

        backpressure = normalized["memory"]["queue_backpressure"]
        assert backpressure["enabled"] is True
        assert backpressure["max_inflight_tasks"] == 64
        assert backpressure["drop_policy"] == "oldest"

    def test_memory_monitor(self):
        """메모리 모니터 기본값"""
        config = {"memory": {}}
        normalized = normalize_performance_config(config)

        monitor = normalized["memory"]["monitor"]
        assert monitor["enabled"] is True
        assert monitor["check_interval_sec"] == 10
        assert monitor["alert_threshold_pct"] == 85


class TestCachePolicy:
    """캐시 정책 테스트"""

    def test_cache_policy_default(self):
        """캐시 정책 기본값: LRU"""
        config = {"cache": {}}
        normalized = normalize_performance_config(config)

        assert normalized["cache"]["policy"] == "LRU"
        assert normalized["cache"]["version_salt"] == "v1"

    def test_cache_ttl_overrides(self):
        """캐시 TTL 오버라이드"""
        config = {"cache": {}}
        normalized = normalize_performance_config(config)

        ttl = normalized["cache"]["ttl_overrides"]
        assert ttl["ocr_results"] == 72
        assert ttl["embeddings"] == 168
        assert ttl["metadata"] == 24


class TestDocumentsWarmup:
    """문서 워밍업 테스트"""

    def test_warmup_default(self):
        """워밍업 기본값"""
        config = {"documents": {}}
        normalized = normalize_performance_config(config)

        warmup = normalized["documents"]["warmup"]
        assert warmup["enabled"] is True
        assert warmup["top_k"] == 100
        assert warmup["delay_sec"] == 5
        assert "metadata" in warmup["types"]


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    def test_scenario_v0_full_config(self):
        """시나리오 1: v0 전체 설정 변환"""
        v0_config = {
            "parallel": {
                "enabled": True,
                "max_workers": 4,
                "chunk_size": 10,
                "use_multiprocessing": False,
            },
            "cache": {"enabled": True, "max_size": 1000, "preload": True},
            "ocr": {"enabled": True, "timeout": 30, "max_file_size_mb": 10},
            "memory": {"max_memory_mb": 2000},
        }

        v1_config = normalize_performance_config(v0_config)

        # 병렬
        assert "pools" in v1_config["parallel"]
        # OCR
        assert v1_config["ocr"]["mode"] == "fallback"
        # 메모리
        assert v1_config["memory"]["soft_limit_mb"] == 1700
        # 캐시
        assert v1_config["cache"]["policy"] == "LRU"

    def test_scenario_multiprocessing_enabled(self):
        """시나리오 2: multiprocessing 활성화"""
        config = {
            "parallel": {
                "max_workers": 4,
                "use_multiprocessing": True,
            }
        }

        normalized = normalize_performance_config(config)

        # CPU 풀은 process executor
        assert normalized["parallel"]["pools"]["cpu"]["executor"] == "process"

    def test_scenario_ocr_force_mode(self):
        """시나리오 3: OCR force 모드 (스캔본 대량 처리)"""
        config = {"ocr": {"mode": "force", "max_pages": 50, "concurrent_pages": 4}}

        normalized = normalize_performance_config(config)

        assert normalized["ocr"]["mode"] == "force"
        assert normalized["ocr"]["max_pages"] == 50
        assert normalized["ocr"]["concurrent_pages"] == 4
