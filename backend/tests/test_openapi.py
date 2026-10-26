from fastapi.testclient import TestClient


def _schema_option(parameter: dict, expected_type: str) -> dict:
    parameter_schema = parameter["schema"]
    if parameter_schema.get("type") == expected_type:
        return parameter_schema
    return next(
        option
        for option in parameter_schema["anyOf"]
        if option.get("type") == expected_type
    )


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
    assert product_list_responses["200"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ProductListEnvelope"
    assert product_list_responses["422"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ErrorEnvelope"
    assert product_detail_responses["200"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ProductDetailEnvelope"
    assert product_detail_responses["404"]["content"]["application/json"][
        "schema"
    ]["$ref"] == "#/components/schemas/ErrorEnvelope"
    assert product_detail_responses["422"]["content"]["application/json"][
        "schema"
    ]["$ref"] == "#/components/schemas/ErrorEnvelope"

    list_operation = paths["/api/v1/products"]["get"]
    parameters = {
        parameter["name"]: parameter for parameter in list_operation["parameters"]
    }
    assert set(parameters) == {
        "page",
        "page_size",
        "q",
        "category",
        "min_price",
        "max_price",
        "color",
        "size",
    }
    assert all(
        parameter["in"] == "query" and parameter.get("required") is not True
        for parameter in parameters.values()
    )
    page_schema = _schema_option(parameters["page"], "integer")
    assert page_schema["minimum"] == 1
    assert page_schema["maximum"] == 1_000_000
    assert page_schema["default"] == 1
    page_size_schema = _schema_option(parameters["page_size"], "integer")
    assert page_size_schema["minimum"] == 1
    assert page_size_schema["maximum"] == 100
    assert page_size_schema["default"] == 20
    for name, maximum_length in {
        "q": 200,
        "category": 140,
        "color": 120,
        "size": 20,
    }.items():
        assert _schema_option(parameters[name], "string")["maxLength"] == maximum_length
    for name in ("min_price", "max_price"):
        price_schema = _schema_option(parameters[name], "integer")
        assert price_schema["minimum"] == 0
        assert price_schema["maximum"] == 9_223_372_036_854_775_807
    assert parameters["category"]["schema"]["examples"] == ["ao-thun"]
    assert parameters["color"]["schema"]["examples"] == ["den"]
    assert parameters["size"]["schema"]["examples"] == ["M"]

    card_schema = schema["components"]["schemas"]["ProductCardResponse"]
    assert {"category", "in_stock"} <= set(card_schema["required"])
    page_response_schema = schema["components"]["schemas"]["ProductPageData"]
    assert {"items", "page", "page_size", "total"} == set(
        page_response_schema["required"]
    )
    detail_schema = schema["components"]["schemas"]["ProductDetailResponse"]
    assert {"description", "images", "variants"} <= set(detail_schema["required"])
    error_schema = schema["components"]["schemas"]["ErrorEnvelope"]
    assert {"error", "meta"} == set(error_schema["required"])
    assert {"code", "message", "fields", "details"} == set(
        schema["components"]["schemas"]["ErrorBody"]["required"]
    )


def test_openapi_contains_admin_knowledge_and_index_status_contract(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    expected = {
        "/api/v1/admin/knowledge-documents": {"get", "post"},
        "/api/v1/admin/knowledge-documents/{document_id}": {
            "get",
            "patch",
            "delete",
        },
        "/api/v1/admin/knowledge-documents/{document_id}/reindex": {"post"},
        "/api/v1/admin/rag-index-jobs": {"get"},
        "/api/v1/admin/rag-index-jobs/{job_id}": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths
        assert methods <= set(paths[path])
        for method in methods:
            operation = paths[path][method]
            assert operation["security"]
            assert {"401", "403"} <= set(operation["responses"])
            assert operation["responses"]["422"]["content"]["application/json"][
                "schema"
            ]["$ref"] == "#/components/schemas/ErrorEnvelope"

    for path, method in (
        ("/api/v1/admin/knowledge-documents/{document_id}", "get"),
        ("/api/v1/admin/knowledge-documents/{document_id}", "patch"),
        ("/api/v1/admin/knowledge-documents/{document_id}", "delete"),
        ("/api/v1/admin/knowledge-documents/{document_id}/reindex", "post"),
        ("/api/v1/admin/rag-index-jobs/{job_id}", "get"),
    ):
        assert paths[path][method]["responses"]["404"]["content"][
            "application/json"
        ]["schema"]["$ref"] == "#/components/schemas/ErrorEnvelope"

    for method in ("get", "patch", "delete"):
        assert "409" in paths[
            "/api/v1/admin/knowledge-documents/{document_id}"
        ][method]["responses"]
    assert "409" in paths[
        "/api/v1/admin/knowledge-documents/{document_id}/reindex"
    ]["post"]["responses"]