from fastapi.testclient import TestClient


def register_customer(client: TestClient, email: str = "khach@example.com"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "MatKhau-AnToan-123",
            "full_name": "Khách Hàng Demo",
            "phone": "0900000000",
        },
    )


def test_register_customer_returns_safe_user(auth_client: TestClient) -> None:
    response = register_customer(auth_client, "KHACH@example.com")

    assert response.status_code == 201
    data = response.json()["data"]
    assert data == {
        "id": data["id"],
        "email": "khach@example.com",
        "full_name": "Khách Hàng Demo",
        "phone": "0900000000",
        "role": "customer",
        "is_active": True,
    }
    assert "password" not in response.text.lower()


def test_register_rejects_duplicate_email(auth_client: TestClient) -> None:
    assert register_customer(auth_client).status_code == 201

    response = register_customer(auth_client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_rejects_blank_full_name(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "blank-name@example.com",
            "password": "MatKhau-AnToan-123",
            "full_name": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_me_and_logout_session_flow(auth_client: TestClient) -> None:
    assert register_customer(auth_client).status_code == 201

    login = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "KHACH@example.com", "password": "MatKhau-AnToan-123"},
    )

    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    assert login.json()["data"]["role"] == "customer"

    current_user = auth_client.get("/api/v1/auth/me")
    assert current_user.status_code == 200
    assert current_user.json()["data"]["email"] == "khach@example.com"
    assert "password" not in current_user.text.lower()

    logout = auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_wrong_password_without_disclosing_account(
    auth_client: TestClient,
) -> None:
    assert register_customer(auth_client).status_code == 201

    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "khach@example.com", "password": "MatKhau-Sai-123"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    unknown_account = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "khong-ton-tai@example.com", "password": "MatKhau-Sai-123"},
    )
    assert unknown_account.status_code == 401
    assert unknown_account.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_authentication(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_is_idempotent_and_clears_stale_cookie(auth_client: TestClient) -> None:
    auth_client.cookies.set("shop_session", "stale-session-token")

    response = auth_client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "logged_out"
    assert "shop_session=" in response.headers["set-cookie"]


def test_customer_is_forbidden_from_admin_route(auth_client: TestClient) -> None:
    assert register_customer(auth_client).status_code == 201
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": "khach@example.com", "password": "MatKhau-AnToan-123"},
    ).status_code == 200

    response = auth_client.get("/api/v1/admin/auth-check")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_admin_is_allowed_on_admin_route(
    auth_client: TestClient, create_auth_user
) -> None:
    create_auth_user("admin@example.com", role="admin")
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "MatKhau-AnToan-123"},
    ).status_code == 200

    response = auth_client.get("/api/v1/admin/auth-check")

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"
    assert "password" not in response.text.lower()


def test_forgot_password_does_not_disclose_account_existence(
    auth_client: TestClient,
) -> None:
    missing = auth_client.post(
        "/api/v1/auth/forgot-password", json={"email": "missing@example.com"}
    )
    assert register_customer(auth_client).status_code == 201
    existing = auth_client.post(
        "/api/v1/auth/forgot-password", json={"email": "khach@example.com"}
    )

    assert missing.status_code == existing.status_code == 200
    assert missing.json()["data"] == existing.json()["data"]
    assert "token" not in existing.text.lower()
    assert "set-cookie" not in existing.headers


def test_reset_password_demo_is_single_use_and_revokes_old_password(
    auth_client: TestClient, get_demo_reset_token
) -> None:
    assert register_customer(auth_client).status_code == 201
    forgot = auth_client.post(
        "/api/v1/auth/forgot-password", json={"email": "khach@example.com"}
    )
    assert forgot.status_code == 200
    reset_token = get_demo_reset_token("khach@example.com")
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": "khach@example.com", "password": "MatKhau-AnToan-123"},
    ).status_code == 200
    old_session_token = auth_client.cookies.get("shop_session")
    auth_client.cookies.clear()

    reset = auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "MatKhau-Moi-AnToan-456",
        },
    )

    assert reset.status_code == 200
    auth_client.cookies.set("shop_session", old_session_token)
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    auth_client.cookies.clear()
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": "khach@example.com", "password": "MatKhau-AnToan-123"},
    ).status_code == 401
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "khach@example.com",
            "password": "MatKhau-Moi-AnToan-456",
        },
    ).status_code == 200

    repeated_reset = auth_client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "MatKhau-Khac-789"},
    )
    assert repeated_reset.status_code == 401
    assert repeated_reset.json()["error"]["code"] == "INVALID_RESET_TOKEN"