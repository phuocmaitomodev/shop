from app.core.security import hash_password, verify_password


def test_password_is_stored_as_argon2_hash() -> None:
    password = "MatKhau-AnToan-123"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2")
    assert verify_password(password, password_hash) is True
    assert verify_password("MatKhau-Sai-123", password_hash) is False