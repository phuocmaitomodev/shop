from fastapi.testclient import TestClient


def test_openapi_contains_be04_auth_and_admin_guard_endpoints(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/admin/auth-check",
    } <= set(paths)
    assert "password_hash" not in str(schema)
    assert paths["/api/v1/auth/me"]["get"]["security"]
    assert paths["/api/v1/admin/auth-check"]["get"]["security"]