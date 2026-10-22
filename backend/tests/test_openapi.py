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


def test_openapi_contains_be05_public_catalog_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert {
        "/api/v1/categories",
        "/api/v1/products",
        "/api/v1/products/{slug}",
    } <= set(paths)
    assert paths["/api/v1/categories"]["get"].get("security") is None
    assert paths["/api/v1/products"]["get"].get("security") is None

    product_list_responses = paths["/api/v1/products"]["get"]["responses"]
    product_detail_responses = paths["/api/v1/products/{slug}"]["get"][
        "responses"
    ]
    assert product_list_responses["422"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ErrorEnvelope"
    assert product_detail_responses["404"]["content"]["application/json"][
        "schema"
    ]["$ref"] == "#/components/schemas/ErrorEnvelope"
    assert product_detail_responses["422"]["content"]["application/json"][
        "schema"
    ]["$ref"] == "#/components/schemas/ErrorEnvelope"