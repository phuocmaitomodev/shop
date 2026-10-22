import base64
import hashlib
import hmac
import secrets
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = _password_hasher.hash("dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def derive_demo_reset_token(app_secret: str, token_id: UUID) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"),
        str(token_id).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")