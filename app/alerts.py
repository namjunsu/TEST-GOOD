#!/usr/bin/env python3
"""
Alert System for Index Hygiene Monitoring v2.0
인덱스 위생 모니터링 알림 시스템 (강화판)

개선사항:
1. 재시도/백오프 로직 (429 Retry-After, 5xx)
2. 민감정보 마스킹 (password, secret, token 등)
3. severity/메타데이터 추가 (service/env/host/source)
4. 메시지 축약 (Slack 40k chars 제한 대응)
5. Webhook URL 검증
6. logging 모듈 통합
7. 타임스탬프 추가
"""
import datetime
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv("ALERTS_DRY_RUN", "true").lower() == "true"
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
ALERT_TIMEOUT_SEC = float(os.getenv("ALERT_TIMEOUT_SEC", "5"))
MAX_BODY_CHARS = int(os.getenv("ALERT_MAX_BODY_CHARS", "12000"))  # Slack 제한 대비 여유
MAX_JSON_SNIPPET = int(os.getenv("ALERT_MAX_JSON_SNIPPET", "4000"))
MAX_RETRIES = int(os.getenv("ALERT_MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.getenv("ALERT_BACKOFF_BASE", "0.6"))  # 지수 백오프 시작
SERVICE_NAME = os.getenv("SERVICE_NAME", "ai-chat-rag")
ENV = os.getenv("ENV", "dev")

_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "session",
}


def _is_valid_webhook(url: str) -> bool:
    """Webhook URL 포맷 검증

    Args:
        url: Slack Webhook URL

    Returns:
        유효 여부
    """
    return bool(re.match(r"^https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+$", url or ""))


def _mask_value(val: str) -> str:
    """민감 값 마스킹

    Args:
        val: 원본 값

    Returns:
        마스킹된 값 (앞뒤 3자 + ****)
    """
    if not isinstance(val, str):
        return val
    if len(val) <= 6:
        return "****"
    return val[:3] + "****" + val[-3:]


def _mask_sensitive(obj: Any) -> Any:
    """민감정보 재귀 마스킹

    Args:
        obj: 원본 객체 (dict/list/기타)

    Returns:
        마스킹된 객체
    """
    if isinstance(obj, dict):
        return {
            k: (_mask_value(v) if k.lower() in _SENSITIVE_KEYS else _mask_sensitive(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_sensitive(v) for v in obj]
    return obj


def _truncate_text(s: str, limit: int) -> Tuple[str, bool]:
    """텍스트 축약

    Args:
        s: 원본 텍스트
        limit: 최대 길이

    Returns:
        (축약된 텍스트, 축약 여부)
    """
    if s is None:
        return "", False
    if len(s) <= limit:
        return s, False
    return s[:limit] + "\n…(truncated)", True


def _json_block(payload: dict) -> str:
    """JSON 페이로드를 마스킹/축약된 코드 블록으로 변환

    Args:
        payload: 원본 페이로드

    Returns:
        마크다운 코드 블록
    """
    masked = _mask_sensitive(payload)
    text = json.dumps(masked, ensure_ascii=False, indent=2)
    text, _ = _truncate_text(text, MAX_JSON_SNIPPET)
    return "```" + text + "```"


def _build_blocks(
    title: str, payload: dict, severity: str, source: Optional[str]
) -> Dict[str, Any]:
    """Slack 메시지 블록 구성

    Args:
        title: 알림 제목
        payload: 페이로드
        severity: 심각도 (LOW/MEDIUM/HIGH/CRITICAL)
        source: 이벤트 소스

    Returns:
        Slack 메시지 body
    """
    host = socket.gethostname()
    timestamp = datetime.datetime.now().isoformat()

    header = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*{title}*  ·  `{severity}`"},
    }

    meta = {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"*service*: `{SERVICE_NAME}` · *env*: `{ENV}` · *host*: `{host}`",
            },
            {
                "type": "mrkdwn",
                "text": f"*source*: `{source or 'index-hygiene'}` · *time*: `{timestamp}`",
            },
        ],
    }

    # 중요한 키들은 fields로 요약
    fields = []
    for k in (
        "fs_file_count",
        "index_file_count",
        "stale_index_entries",
        "orphan_files",
        "missing_text_ratio",
    ):
        if k in payload:
            fields.append({"type": "mrkdwn", "text": f"*{k}*\n{payload[k]}"})

    fields_block = {"type": "section", "fields": fields} if fields else None

    detail_block = {"type": "section", "text": {"type": "mrkdwn", "text": _json_block(payload)}}

    blocks = [header, meta]
    if fields_block:
        blocks.append(fields_block)
    blocks.append(detail_block)

    return {"text": f":warning: {title}", "blocks": blocks}


def _post_slack(body: dict) -> Dict[str, Any]:
    """Slack Webhook POST (재시도/백오프 포함)

    Args:
        body: Slack 메시지 body

    Returns:
        전송 결과 (status, error, truncated)
    """
    raw = json.dumps(body, ensure_ascii=False)
    raw, truncated = _truncate_text(raw, MAX_BODY_CHARS)
    data = raw.encode("utf-8")

    req = urllib.request.Request(
        SLACK_WEBHOOK,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"{SERVICE_NAME}-alerts/2.0",
        },
        method="POST",
    )

    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=ALERT_TIMEOUT_SEC) as r:
                status = getattr(r, "status", 200)
                logger.info(f"Alert sent successfully: status={status}")
                return {"dry_run": False, "status": status, "truncated": truncated}
        except urllib.error.HTTPError as e:
            status = e.code
            # 429: Slack이 Retry-After 제공하는 경우 준수
            if status == 429:
                retry_after = int(e.headers.get("Retry-After", "1"))
                logger.warning(f"Rate limited (429), retrying after {retry_after}s")
                time.sleep(retry_after)
            elif 500 <= status < 600 and attempt < MAX_RETRIES:
                delay = BACKOFF_BASE * (2**attempt)
                logger.warning(
                    f"Server error ({status}), retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(delay)
                attempt += 1
            else:
                logger.error(f"Failed to send alert: HTTP {status}")
                return {"dry_run": False, "error": f"HTTP {status}", "truncated": truncated}
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE * (2**attempt)
                logger.warning(
                    f"Network error, retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                time.sleep(delay)
                attempt += 1
            else:
                logger.error(f"Failed to send alert after {MAX_RETRIES} retries: {e}")
                return {"dry_run": False, "error": str(e), "truncated": truncated}


def send_warning(
    title: str, payload: dict, *, severity: str = "HIGH", source: Optional[str] = None
) -> dict:
    """
    Slack으로 경고 알림 전송 (강화판)

    Args:
        title: 알림 제목
        payload: 전송할 데이터 (dict)
        severity: 심각도 (LOW|MEDIUM|HIGH|CRITICAL, 기본: HIGH)
        source: 이벤트 소스 태그 (예: 'index-diff', 'consistency-check')

    Returns:
        전송 결과 (dry_run, status|error, truncated)

    Example:
        send_warning("인덱스 정합성 경고", {
            "fs_file_count": 488,
            "index_file_count": 474,
            "stale_index_entries": 3
        }, severity="CRITICAL", source="index-diff")

    환경변수:
        ALERTS_DRY_RUN: "true"이면 실제 전송하지 않음 (기본: true)
        SLACK_WEBHOOK_URL: Slack Webhook URL
        ALERT_TIMEOUT_SEC: 타임아웃 (초, 기본: 5)
        ALERT_MAX_RETRIES: 최대 재시도 횟수 (기본: 3)
        ALERT_BACKOFF_BASE: 백오프 시작 시간 (초, 기본: 0.6)
        SERVICE_NAME: 서비스 이름 (기본: ai-chat-rag)
        ENV: 환경 (dev/prod, 기본: dev)
    """
    if not title:
        title = "Alert"

    severity = severity.upper()
    if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        severity = "HIGH"

    body = _build_blocks(title, payload, severity, source)

    if DRY_RUN or not _is_valid_webhook(SLACK_WEBHOOK):
        # DRY-RUN 또는 잘못된 Webhook → 콘솔로 안전 출력
        safe = _mask_sensitive(payload)
        logger.warning(
            f"[ALERTS DRY-RUN] {title} [{severity}] service={SERVICE_NAME} env={ENV} source={source or 'index-hygiene'}"
        )
        logger.info(json.dumps(safe, ensure_ascii=False, indent=2))
        return {"dry_run": True, "payload": body}

    return _post_slack(body)
