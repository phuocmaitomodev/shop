import pytest
from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str = "khach@example.com") -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "MatKhau-AnToan-123",
            "full_name": "Khách Hàng Demo",
            "phone": "0900000000",
        },
    )
    assert register.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "MatKhau-AnToan-123"},
    )
    assert login.status_code == 200


def test_customer_can_read_own_safe_profile(auth_client: TestClient) -> None:
    _register_and_login(auth_client)

    response = auth_client.get("/api/v1/account/profile")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "id": data["id"],
        "email": "khach@example.com",
        "full_name": "Khách Hàng Demo",
        "phone": "0900000000",
        "role": "customer",
        "is_active": True,
    }
    assert not {"password", "password_hash", "session", "token"} & set(data)


def test_profile_requires_authentication(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/account/profile")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_admin_is_forbidden_from_customer_profile(
    auth_client: TestClient, create_auth_user
) -> None:
    create_auth_user("admin@example.com", role="admin")
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "MatKhau-AnToan-123"},
    )
    assert login.status_code == 200

    response = auth_client.get("/api/v1/account/profile")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CUSTOMER_REQUIRED"


def test_customer_can_update_normalized_profile_and_changes_persist(
    auth_client: TestClient,
) -> None:
    _register_and_login(auth_client)

    response = auth_client.patch(
        "/api/v1/account/profile",
        json={"full_name": "  Nguyễn Văn An  ", "phone": "   "},
    )

    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Nguyễn Văn An"
    assert response.json()["data"]["phone"] is None
    persisted = auth_client.get("/api/v1/account/profile")
    assert persisted.status_code == 200
    assert persisted.json()["data"] == response.json()["data"]


def test_profile_patch_requires_at_least_one_editable_field(
    auth_client: TestClient,
) -> None:
    _register_and_login(auth_client)

    response = auth_client.patch("/api/v1/account/profile", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_patch_rejects_immutable_and_sensitive_fields(
    auth_client: TestClient,
) -> None:
    _register_and_login(auth_client)

    response = auth_client.patch(
        "/api/v1/account/profile",
        json={
            "full_name": "Tên Bị Từ Chối",
            "email": "attacker@example.com",
            "role": "admin",
            "is_active": False,
            "password_hash": "not-a-real-hash",
            "session": "not-a-session",
            "token": "not-a-token",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    current = auth_client.get("/api/v1/account/profile")
    assert current.json()["data"]["email"] == "khach@example.com"
    assert current.json()["data"]["full_name"] == "Khách Hàng Demo"
    assert current.json()["data"]["role"] == "customer"
    assert current.json()["data"]["is_active"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "   "},
        {"full_name": "a" * 201},
        {"full_name": None},
        {"phone": "1" * 33},
    ],
)
def test_profile_patch_returns_stable_validation_error(
    auth_client: TestClient, payload: dict
) -> None:
    _register_and_login(auth_client)

    response = auth_client.patch("/api/v1/account/profile", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_update_is_isolated_to_authenticated_customer(
    auth_client: TestClient,
) -> None:
    _register_and_login(auth_client, "customer-a@example.com")
    auth_client.cookies.clear()
    _register_and_login(auth_client, "customer-b@example.com")
    auth_client.cookies.clear()
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "customer-a@example.com",
            "password": "MatKhau-AnToan-123",
        },
    ).status_code == 200

    updated = auth_client.patch(
        "/api/v1/account/profile",
        json={"full_name": "Khách Hàng A", "phone": " 0911222333 "},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["phone"] == "0911222333"
    auth_client.cookies.clear()
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "customer-b@example.com",
            "password": "MatKhau-AnToan-123",
        },
    ).status_code == 200

    other_profile = auth_client.get("/api/v1/account/profile")

    assert other_profile.status_code == 200
    assert other_profile.json()["data"]["email"] == "customer-b@example.com"
    assert other_profile.json()["data"]["full_name"] == "Khách Hàng Demo"
    assert other_profile.json()["data"]["phone"] == "0900000000"


def test_profile_patch_requires_customer_authentication(
    auth_client: TestClient, create_auth_user
) -> None:
    unauthenticated = auth_client.patch(
        "/api/v1/account/profile", json={"full_name": "Không Được Sửa"}
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"

    create_auth_user("admin@example.com", role="admin")
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "MatKhau-AnToan-123"},
    ).status_code == 200
    admin = auth_client.patch(
        "/api/v1/account/profile", json={"full_name": "Không Được Sửa"}
    )
    assert admin.status_code == 403
    assert admin.json()["error"]["code"] == "CUSTOMER_REQUIRED"
