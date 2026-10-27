import asyncio
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.v1 import chat as chat_api
from app.core.config import Settings, get_settings
from app.core.middleware import ChatBodyLimitMiddleware
from app.db.session import get_db_session
from app.main import create_app
from app.rag.chat import ChatProduct, ChatResult, ChatSource


PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000003")


def _client(monkeypatch) -> TestClient:
    async def fake_session():
        yield object()

    async def fake_orchestrate(**kwargs):
        assert kwargs["message"] == "Tìm áo thun đen"
        assert kwargs["history"][0].role == "user"
        return ChatResult(
            answer="Áo thun đen: 249.000 ₫; còn hàng.",
            products=[
                ChatProduct(
                    id=PRODUCT_ID,
                    slug="ao-thun-den",
                    name="Áo thun đen",
                    image_url="/media/ao.svg",
                    effective_price=249_000,
                    available_colors=["Đen"],
                    available_sizes=["M"],
                    in_stock=True,
                    url="/san-pham/ao-thun-den",
                )
            ],
            sources=[
                ChatSource(
                    product_id=PRODUCT_ID,
                    rag_document_id=DOCUMENT_ID,
                    chunk_ids=[CHUNK_ID],
                    source_type="product",
                    source_id=PRODUCT_ID,
                    knowledge_type=None,
                    title="Áo thun đen",
                )
            ],
            status="ok",
        )

    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_orchestrate)
    application = create_app()
    application.dependency_overrides[get_db_session] = fake_session
    return TestClient(application)


def test_chat_endpoint_contract_and_hydrated_response(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "Tìm áo thun đen",
                "history": [{"role": "user", "content": "size M"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["products"][0]["id"] == str(PRODUCT_ID)
    assert payload["data"]["products"][0]["url"] == "/san-pham/ao-thun-den"
    assert payload["data"]["sources"][0] == {
        "source_type": "product",
        "source_id": str(PRODUCT_ID),
        "product_id": str(PRODUCT_ID),
        "rag_document_id": str(DOCUMENT_ID),
        "chunk_ids": [str(CHUNK_ID)],
        "knowledge_type": None,
        "title": "Áo thun đen",
    }
    assert payload["meta"]["request_id"]


def test_chat_endpoint_serializes_return_policy_knowledge_source(monkeypatch) -> None:
    async def fake_policy_orchestrate(**_kwargs):
        return ChatResult(
            answer="Bạn có thể đổi hàng trong 07 ngày.",
            products=[],
            sources=[
                ChatSource(
                    source_type="knowledge",
                    source_id=PRODUCT_ID,
                    rag_document_id=DOCUMENT_ID,
                    chunk_ids=[CHUNK_ID],
                    product_id=None,
                    knowledge_type="return_policy",
                    title="Chính sách đổi trả",
                )
            ],
            status="ok",
        )

    client = _client(monkeypatch)
    monkeypatch.setattr(chat_api, "orchestrate_chat", fake_policy_orchestrate)
    with client:
        response = client.post("/api/v1/chat", json={"message": "Đổi hàng thế nào?"})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "answer": "Bạn có thể đổi hàng trong 07 ngày.",
        "products": [],
        "sources": [
            {
                "source_type": "knowledge",
                "source_id": str(PRODUCT_ID),
                "rag_document_id": str(DOCUMENT_ID),
                "chunk_ids": [str(CHUNK_ID)],
                "product_id": None,
                "knowledge_type": "return_policy",
                "title": "Chính sách đổi trả",
            }
        ],
        "status": "ok",
    }


def test_chat_request_bounds_message_and_history(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        too_long = client.post("/api/v1/chat", json={"message": "x" * 1001})
        blank = client.post("/api/v1/chat", json={"message": "   "})
        too_many_turns = client.post(
            "/api/v1/chat",
            json={
                "message": "Tìm áo",
                "history": [
                    {"role": "user", "content": f"lượt {index}"}
                    for index in range(7)
                ],
            },
        )

    assert too_long.status_code == 422
    assert blank.status_code == 422
    assert too_many_turns.status_code == 422
    assert too_long.json()["error"]["code"] == "VALIDATION_ERROR"


def test_openapi_exposes_public_bounded_chat_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/chat"]["post"]

    assert operation.get("security") is None
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ] == "#/components/schemas/ChatEnvelope"
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert request_ref == "#/components/schemas/ChatRequest"
    request_schema = schema["components"]["schemas"]["ChatRequest"]
    assert request_schema["properties"]["message"]["maxLength"] == 1000
    assert request_schema["properties"]["history"]["maxItems"] == 6
    status_schema = schema["components"]["schemas"]["ChatResponse"]["properties"][
        "status"
    ]
    assert set(status_schema["enum"]) == {
        "ok",
        "insufficient_data",
        "out_of_scope",
        "provider_unavailable",
    }
    source_schema = schema["components"]["schemas"]["ChatSourceResponse"]
    assert set(source_schema["required"]) == {
        "source_type",
        "source_id",
        "rag_document_id",
        "chunk_ids",
        "product_id",
        "knowledge_type",
        "title",
    }
    assert set(source_schema["properties"]["source_type"]["enum"]) == {
        "product",
        "knowledge",
    }


def test_chat_endpoint_rate_limits_public_provider_calls(monkeypatch) -> None:
    client = _client(monkeypatch)
    limited_settings = Settings(
        _env_file=None,
        app_env="test",
        app_secret_key="test-only-secret",
        database_url="postgresql+asyncpg://shop:shop@localhost:5432/shop_test",
        chat_rate_limit_requests=1,
    )
    client.app.dependency_overrides[get_settings] = lambda: limited_settings

    payload = {
        "message": "Tìm áo thun đen",
        "history": [{"role": "user", "content": "size M"}],
    }
    with client:
        first = client.post("/api/v1/chat", json=payload)
        second = client.post("/api/v1/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_chat_endpoint_rejects_oversized_body_before_validation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "Tìm áo", "ignored": "x" * 40_000},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_chat_body_limit_counts_streamed_chunks_without_content_length() -> None:
    async def exercise():
        sent = []
        chunks = iter(
            [
                {"type": "http.request", "body": b"123456", "more_body": True},
                {"type": "http.request", "body": b"78901", "more_body": False},
            ]
        )

        async def downstream(_scope, _receive, _send):
            raise AssertionError("oversized request must not reach the application")

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        middleware = ChatBodyLimitMiddleware(downstream, max_body_bytes=10)
        await middleware(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/chat",
                "raw_path": b"/api/v1/chat",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
                "state": {"request_id": "stream-test"},
            },
            receive,
            send,
        )
        return sent

    sent = asyncio.run(exercise())

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
