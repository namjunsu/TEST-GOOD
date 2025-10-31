#!/usr/bin/env python3
"""
Alert System for Index Hygiene Monitoring
인덱스 위생 모니터링 알림 시스템
"""
import os
import json
import urllib.request


DRY_RUN = os.getenv("ALERTS_DRY_RUN", "true").lower() == "true"
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")


def send_warning(title: str, payload: dict) -> dict:
    """
    Slack으로 경고 알림 전송

    Args:
        title: 알림 제목
        payload: 전송할 데이터 (dict)

    Returns:
        전송 결과 (dry_run, status 등)

    Example:
        send_warning("인덱스 정합성 경고", {
            "fs_file_count": 488,
            "index_file_count": 474,
            "stale_index_entries": 3
        })
    """
    body = {
        "text": f":warning: {title}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "```" + json.dumps(payload, ensure_ascii=False, indent=2) + "```"
                }
            }
        ]
    }

    if DRY_RUN or not SLACK_WEBHOOK:
        print(f"[ALERTS DRY-RUN] {title}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return {"dry_run": True, "payload": body}

    try:
        req = urllib.request.Request(
            SLACK_WEBHOOK,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"dry_run": False, "status": r.status}
    except Exception as e:
        print(f"[ALERTS ERROR] Failed to send: {e}")
        return {"dry_run": False, "error": str(e)}
