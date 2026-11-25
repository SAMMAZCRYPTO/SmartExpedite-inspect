import base64
import hashlib
import hmac
import secrets
from typing import Optional

PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 310_000


def is_password_hashed(stored: Optional[str]) -> bool:
    return bool(stored and stored.startswith(f"{PBKDF2_PREFIX}$"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    hash_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


MIN_PBKDF2_ITERATIONS = 100_000
MAX_PBKDF2_ITERATIONS = 2_000_000


def verify_password(plain_password: str, stored_password: str) -> bool:
    if not plain_password or not stored_password:
        return False
    if not is_password_hashed(stored_password):
        return False
    try:
        _, iter_str, salt_b64, expected_b64 = stored_password.split("$", 3)
        iterations = int(iter_str)
        if not (MIN_PBKDF2_ITERATIONS <= iterations <= MAX_PBKDF2_ITERATIONS):
            return False
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(expected_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False
