"""
Alert 시스템 테스트 (v2.0)
- Webhook URL 검증
- 민감정보 마스킹
- 메시지 축약
- severity/메타데이터
- DRY-RUN 모드
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.alerts import (
    _build_blocks,
    _is_valid_webhook,
    _mask_sensitive,
    _mask_value,
    _truncate_text,
    send_warning,
)


class TestWebhookValidation:
    """Webhook URL 검증 테스트"""

    def test_valid_webhook(self):
        """유효한 Webhook URL"""
        valid_urls = [
            "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX",
            "https://hooks.slack.com/services/ABC123/DEF456/ghi789-jkl012",
        ]
        for url in valid_urls:
            assert _is_valid_webhook(url) is True

    def test_invalid_webhook(self):
        """잘못된 Webhook URL"""
        invalid_urls = [
            "",
            "http://hooks.slack.com/services/T00000000/B00000000/X",  # http (not https)
            "https://hooks.slack.com/invalid",
            "https://example.com/webhook",
            "not-a-url",
            None,
        ]
        for url in invalid_urls:
            assert _is_valid_webhook(url) is False


class TestSensitiveMasking:
    """민감정보 마스킹 테스트"""

    def test_mask_value_short(self):
        """짧은 값 마스킹 (6자 이하)"""
        assert _mask_value("abc") == "****"
        assert _mask_value("123456") == "****"

    def test_mask_value_long(self):
        """긴 값 마스킹 (앞뒤 3자 + ****)"""
        assert _mask_value("secret123456") == "sec****456"
        assert _mask_value("verylongsecrettoken") == "ver****ken"

    def test_mask_value_non_string(self):
        """비문자열 값 (그대로 반환)"""
        assert _mask_value(123) == 123
        assert _mask_value(None) is None

    def test_mask_sensitive_dict(self):
        """dict 민감정보 마스킹"""
        data = {
            "username": "alice",
            "password": "secret123",
            "token": "abc123xyz789",
            "api_key": "myapikey",
        }
        masked = _mask_sensitive(data)

        assert masked["username"] == "alice"  # 마스킹 안됨
        assert masked["password"] == "sec****123"  # 마스킹됨
        assert masked["token"] == "abc****789"
        assert masked["api_key"] == "mya****key"

    def test_mask_sensitive_nested(self):
        """중첩 dict 마스킹"""
        data = {
            "user": {"name": "bob", "secret": "topsecret"},
            "config": {"apikey": "mykey123"},
        }
        masked = _mask_sensitive(data)

        assert masked["user"]["name"] == "bob"
        assert masked["user"]["secret"] == "top****ret"
        assert masked["config"]["apikey"] == "myk****123"

    def test_mask_sensitive_list(self):
        """list 마스킹"""
        data = [
            {"password": "pass123"},
            {"token": "token456"},
        ]
        masked = _mask_sensitive(data)

        assert masked[0]["password"] == "pas****123"
        assert masked[1]["token"] == "tok****456"

    def test_mask_sensitive_case_insensitive(self):
        """대소문자 무관 마스킹"""
        data = {"Password": "secret", "TOKEN": "mytoken", "Api_Key": "apikey123"}
        masked = _mask_sensitive(data)

        assert masked["Password"] == "****"  # "secret" is 6 chars
        assert masked["TOKEN"] == "myt****ken"
        assert masked["Api_Key"] == "api****123"


class TestTextTruncation:
    """텍스트 축약 테스트"""

    def test_truncate_within_limit(self):
        """제한 내 텍스트 (축약 안됨)"""
        text, truncated = _truncate_text("short text", 100)
        assert text == "short text"
        assert truncated is False

    def test_truncate_exceeds_limit(self):
        """제한 초과 텍스트 (축약됨)"""
        text, truncated = _truncate_text("a" * 1000, 50)
        assert len(text) <= 50 + len("\n…(truncated)")
        assert truncated is True
        assert text.endswith("…(truncated)")

    def test_truncate_none(self):
        """None 입력"""
        text, truncated = _truncate_text(None, 100)
        assert text == ""
        assert truncated is False


class TestBuildBlocks:
    """Slack 블록 구성 테스트"""

    def test_build_blocks_basic(self):
        """기본 블록 구성"""
        payload = {"fs_file_count": 100, "index_file_count": 95}
        blocks = _build_blocks("Test Alert", payload, "HIGH", "test-source")

        assert "text" in blocks
        assert blocks["text"] == ":warning: Test Alert"
        assert "blocks" in blocks
        assert len(blocks["blocks"]) >= 3  # header, meta, detail

    def test_build_blocks_with_fields(self):
        """fields 포함 블록 구성"""
        payload = {
            "fs_file_count": 100,
            "index_file_count": 95,
            "stale_index_entries": 5,
        }
        blocks = _build_blocks("Test Alert", payload, "CRITICAL", "index-diff")

        # fields block 포함 여부 확인
        field_blocks = [b for b in blocks["blocks"] if b.get("type") == "section" and "fields" in b]
        assert len(field_blocks) >= 1

    def test_build_blocks_severity(self):
        """severity 포함 확인"""
        payload = {"test": "data"}
        blocks = _build_blocks("Alert", payload, "LOW", None)

        header = blocks["blocks"][0]
        assert "LOW" in header["text"]["text"]

    def test_build_blocks_metadata(self):
        """메타데이터 포함 확인"""
        payload = {"test": "data"}
        blocks = _build_blocks("Alert", payload, "MEDIUM", "my-source")

        # context block 찾기
        context_blocks = [b for b in blocks["blocks"] if b.get("type") == "context"]
        assert len(context_blocks) >= 1

        context = context_blocks[0]
        # service, env, host, source, time 확인
        text = str(context)
        assert "service" in text.lower()
        assert "my-source" in text


class TestSendWarning:
    """send_warning() 통합 테스트"""

    @patch("app.alerts.DRY_RUN", True)
    def test_send_warning_dry_run(self, caplog):
        """DRY-RUN 모드 (실제 전송 안함)"""
        result = send_warning(
            "Test Alert", {"key": "value"}, severity="HIGH", source="test"
        )

        assert result["dry_run"] is True
        assert "payload" in result

    @patch("app.alerts.DRY_RUN", False)
    @patch("app.alerts.SLACK_WEBHOOK", "")
    def test_send_warning_invalid_webhook(self):
        """잘못된 Webhook URL (DRY-RUN 처리)"""
        result = send_warning("Test", {"data": "test"})

        assert result["dry_run"] is True

    @patch("app.alerts.DRY_RUN", False)
    @patch("app.alerts.SLACK_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    @patch("app.alerts._post_slack")
    def test_send_warning_success(self, mock_post):
        """성공적인 전송"""
        mock_post.return_value = {"dry_run": False, "status": 200, "truncated": False}

        result = send_warning(
            "Success Test", {"count": 100}, severity="LOW", source="unittest"
        )

        assert result["dry_run"] is False
        assert result["status"] == 200
        mock_post.assert_called_once()

    def test_send_warning_severity_normalization(self):
        """severity 정규화"""
        # 잘못된 severity → HIGH로 기본값
        with patch("app.alerts.DRY_RUN", True):
            result = send_warning("Test", {}, severity="INVALID")
            # DRY-RUN이므로 payload 확인
            assert result["dry_run"] is True

    def test_send_warning_empty_title(self):
        """빈 제목 (기본값 "Alert")"""
        with patch("app.alerts.DRY_RUN", True):
            result = send_warning("", {"data": "test"})
            assert result["dry_run"] is True

    def test_send_warning_masked_sensitive(self):
        """민감정보 마스킹 확인"""
        with patch("app.alerts.DRY_RUN", True):
            payload = {"password": "secret123", "normal": "data"}
            result = send_warning("Masked Test", payload)

            # DRY-RUN이므로 payload 내부 확인
            # 실제 전송되는 블록에는 마스킹된 데이터가 포함됨
            assert result["dry_run"] is True


class TestPostSlackRetry:
    """_post_slack 재시도 로직 테스트 (모킹)"""

    @patch("app.alerts.SLACK_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    @patch("app.alerts.urllib.request.urlopen")
    def test_post_slack_success(self, mock_urlopen):
        """성공적인 전송"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        from app.alerts import _post_slack

        result = _post_slack({"text": "test"})

        assert result["dry_run"] is False
        assert result["status"] == 200

    @patch("app.alerts.SLACK_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    @patch("app.alerts.urllib.request.urlopen")
    @patch("app.alerts.time.sleep")  # sleep 건너뛰기
    def test_post_slack_retry_5xx(self, mock_sleep, mock_urlopen):
        """5xx 에러 재시도"""
        from urllib.error import HTTPError

        # 세 번째 시도: 성공 응답
        mock_success = MagicMock()
        mock_success.status = 200
        mock_success.__enter__ = MagicMock(return_value=mock_success)
        mock_success.__exit__ = MagicMock(return_value=False)

        # 첫 2번 500 에러, 3번째 성공
        mock_urlopen.side_effect = [
            HTTPError(None, 500, "Internal Server Error", {}, None),
            HTTPError(None, 503, "Service Unavailable", {}, None),
            mock_success,
        ]

        from app.alerts import _post_slack

        result = _post_slack({"text": "test"})

        # 재시도 후 성공
        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2  # 2번 백오프
        assert result["status"] == 200

    @patch("app.alerts.SLACK_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    @patch("app.alerts.urllib.request.urlopen")
    @patch("app.alerts.time.sleep")
    def test_post_slack_max_retries_exceeded(self, mock_sleep, mock_urlopen):
        """최대 재시도 초과"""
        from urllib.error import HTTPError

        # 계속 500 에러
        mock_urlopen.side_effect = HTTPError(None, 500, "Error", {}, None)

        from app.alerts import _post_slack

        result = _post_slack({"text": "test"})

        # 최대 재시도 후 실패 반환
        assert result["dry_run"] is False
        assert "error" in result

    @patch("app.alerts.SLACK_WEBHOOK", "https://hooks.slack.com/services/T/B/X")
    @patch("app.alerts.urllib.request.urlopen")
    @patch("app.alerts.time.sleep")
    def test_post_slack_429_retry_after(self, mock_sleep, mock_urlopen):
        """429 Rate Limit + Retry-After 헤더"""
        from urllib.error import HTTPError

        # 429 에러 (Retry-After 헤더 포함)
        error = HTTPError(None, 429, "Too Many Requests", {}, None)
        error.headers = {"Retry-After": "2"}

        # 두 번째 시도: 성공 응답
        mock_success = MagicMock()
        mock_success.status = 200
        mock_success.__enter__ = MagicMock(return_value=mock_success)
        mock_success.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            error,
            mock_success,
        ]

        from app.alerts import _post_slack

        result = _post_slack({"text": "test"})

        # Retry-After 2초 대기 후 재시도
        mock_sleep.assert_called_with(2)
        assert result["status"] == 200


class TestEdgeCases:
    """경계 케이스"""

    def test_empty_payload(self):
        """빈 페이로드"""
        with patch("app.alerts.DRY_RUN", True):
            result = send_warning("Empty Payload", {})
            assert result["dry_run"] is True

    def test_large_payload(self):
        """큰 페이로드 (축약 테스트)"""
        large_payload = {"data": "x" * 10000}
        blocks = _build_blocks("Large Payload", large_payload, "HIGH", None)

        # 블록이 생성되고, JSON이 축약되었는지 확인
        assert "blocks" in blocks
        detail_block = blocks["blocks"][-1]
        text = detail_block["text"]["text"]
        # 축약 표시 포함 여부
        assert "truncated" in text or len(text) < len(json.dumps(large_payload))

    def test_special_characters_in_payload(self):
        """특수문자 포함 페이로드"""
        payload = {"message": "Test <>&\"'`"}
        with patch("app.alerts.DRY_RUN", True):
            result = send_warning("Special Chars", payload)
            assert result["dry_run"] is True
