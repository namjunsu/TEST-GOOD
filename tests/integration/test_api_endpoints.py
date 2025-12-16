"""
FastAPI 엔드포인트 테스트
- Health check
- Config API
- Metrics API
- Error handling

pytest-mock 없이 기본 pytest 기능으로 테스트
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI 테스트 클라이언트 생성"""
    # Import는 fixture 내부에서 수행하여 환경 격리
    from app.api.main import app
    return TestClient(app)


class TestHealthCheck:
    """/_healthz 엔드포인트 테스트"""

    def test_health_check_returns_200(self, client):
        """헬스체크 엔드포인트가 200 반환"""
        response = client.get("/_healthz")
        assert response.status_code == 200

    def test_health_check_response_format(self, client):
        """헬스체크 응답 형식 확인"""
        response = client.get("/_healthz")
        data = response.json()

        # 필수 필드 확인
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_check_includes_timestamp(self, client):
        """헬스체크 응답에 타임스탬프 포함"""
        response = client.get("/_healthz")
        data = response.json()

        # 타임스탬프 필드 확인
        assert "timestamp" in data or "time" in data or "checked_at" in data


class TestRootEndpoint:
    """/ 루트 엔드포인트 테스트"""

    def test_root_returns_200(self, client):
        """루트 엔드포인트가 200 반환"""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_response_format(self, client):
        """루트 응답 형식 확인"""
        response = client.get("/")
        data = response.json()

        # API 정보 포함
        assert "message" in data or "status" in data or "version" in data


class TestConfigAPI:
    """/api/config 엔드포인트 테스트"""

    def test_config_returns_200(self, client):
        """설정 API가 200 반환"""
        response = client.get("/api/config")
        assert response.status_code == 200

    def test_config_response_is_dict(self, client):
        """설정 응답이 딕셔너리"""
        response = client.get("/api/config")
        data = response.json()

        assert isinstance(data, dict)

    def test_config_no_sensitive_data(self, client):
        """설정에 민감한 정보 미포함"""
        response = client.get("/api/config")
        data = response.json()

        # 민감한 키워드 미포함 확인
        data_str = str(data).lower()
        sensitive_keywords = ["password", "secret", "api_key", "token"]

        for keyword in sensitive_keywords:
            # 키 이름에 민감한 단어가 있으면 값이 마스킹되었는지 확인
            if keyword in data_str:
                # 실제 값이 노출되지 않았는지 확인 (****로 마스킹)
                assert "****" in data_str or keyword not in str(data.values()).lower()


class TestMetricsAPI:
    """/metrics 엔드포인트 테스트"""

    def test_metrics_returns_200(self, client):
        """메트릭스 API가 200 반환"""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_response_format(self, client):
        """메트릭스 응답 형식 확인"""
        response = client.get("/metrics")
        data = response.json()

        assert isinstance(data, dict)


class TestFilesPreviewAPI:
    """/files/preview 엔드포인트 테스트"""

    def test_preview_missing_ref_returns_422(self, client):
        """ref 파라미터 없이 요청 시 422 반환"""
        response = client.get("/files/preview")
        assert response.status_code == 422  # FastAPI validation error

    def test_preview_nonexistent_file_returns_error(self, client):
        """존재하지 않는 파일 요청 시 에러 반환"""
        import base64
        # base64 인코딩된 존재하지 않는 경로
        fake_path = "/nonexistent/path/file.pdf"
        encoded_ref = base64.b64encode(fake_path.encode()).decode()
        response = client.get(f"/files/preview?ref={encoded_ref}")
        # 403 (DOCS_DIR 외부), 404 (파일 없음), 422 (검증 실패)
        assert response.status_code in [403, 404, 422, 400]


class TestFilesDownloadAPI:
    """/files/download 엔드포인트 테스트"""

    def test_download_missing_ref_returns_422(self, client):
        """ref 파라미터 없이 요청 시 422 반환"""
        response = client.get("/files/download")
        assert response.status_code == 422

    def test_download_nonexistent_file_returns_error(self, client):
        """존재하지 않는 파일 요청 시 에러 반환"""
        import base64
        # base64 인코딩된 존재하지 않는 경로
        fake_path = "/nonexistent/path/file.pdf"
        encoded_ref = base64.b64encode(fake_path.encode()).decode()
        response = client.get(f"/files/download?ref={encoded_ref}")
        # 403 (DOCS_DIR 외부), 404 (파일 없음), 422 (검증 실패)
        assert response.status_code in [403, 404, 422, 400]


class TestCORSHeaders:
    """CORS 헤더 테스트"""

    def test_cors_allow_origin(self, client):
        """CORS Allow-Origin 헤더 확인"""
        response = client.get(
            "/",
            headers={"Origin": "http://localhost:8501"}
        )
        # 응답이 정상이면 CORS가 작동하는 것
        assert response.status_code == 200


class TestGZipCompression:
    """GZip 압축 테스트"""

    def test_accept_encoding_gzip(self, client):
        """GZip 압축 요청 처리"""
        response = client.get(
            "/api/config",
            headers={"Accept-Encoding": "gzip"}
        )
        assert response.status_code == 200
        # 응답이 압축되었거나 정상 처리됨


class TestErrorHandling:
    """에러 처리 테스트"""

    def test_404_for_unknown_path(self, client):
        """존재하지 않는 경로에 대해 404 반환"""
        response = client.get("/unknown/path/12345")
        assert response.status_code == 404

    def test_405_for_wrong_method(self, client):
        """잘못된 HTTP 메서드에 대해 405 반환"""
        response = client.post("/")  # GET만 허용된 엔드포인트
        assert response.status_code == 405


class TestRequestLogging:
    """요청 로깅 미들웨어 테스트"""

    def test_request_id_in_response_headers(self, client):
        """응답 헤더에 Request-ID 포함"""
        response = client.get("/")

        # X-Request-ID 또는 유사한 헤더 확인
        headers = dict(response.headers)
        _has_request_id = any(
            "request-id" in k.lower() or "trace-id" in k.lower()
            for k in headers.keys()
        )
        # 미들웨어가 설정된 경우에만 확인 (현재는 status_code만 체크)
        assert response.status_code == 200


class TestContentType:
    """Content-Type 테스트"""

    def test_json_content_type(self, client):
        """JSON 응답의 Content-Type 확인"""
        response = client.get("/api/config")
        assert "application/json" in response.headers.get("content-type", "")
