from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import create_app


def test_liveness_returns_success_envelope_with_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "healthy"}
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_unknown_route_returns_standard_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == {
        "code": "NOT_FOUND",
        "message": "Không tìm thấy tài nguyên.",
        "fields": {},
        "details": {},
    }
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_readiness_returns_service_unavailable_when_database_connection_fails(
    client: TestClient,
) -> None:
    class UnavailableSession:
        async def execute(self, statement) -> None:
            raise ConnectionRefusedError("database is unavailable")

    async def unavailable_session():
        yield UnavailableSession()

    client.app.dependency_overrides[get_db_session] = unavailable_session
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_error_keeps_standard_envelope_and_request_id() -> None:
    application = create_app()

    @application.get("/test-only/unhandled-error")
    async def unhandled_error() -> None:
        raise RuntimeError("test failure")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(
            "/test-only/unhandled-error",
            headers={"X-Request-ID": "test-request-id"},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Đã xảy ra lỗi không mong muốn.",
            "fields": {},
            "details": {},
        },
        "meta": {"request_id": "test-request-id"},
    }
