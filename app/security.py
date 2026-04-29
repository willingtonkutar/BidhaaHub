from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


SECRET_KEY = os.getenv("BIDHAAHUB_SECRET_KEY", "bidhaahub-development-secret-key")
TOKEN_TTL_SECONDS = int(os.getenv("BIDHAAHUB_TOKEN_TTL_SECONDS", str(60 * 60 * 12)))


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 120_000)
    return f"{salt_value}${_base64url_encode(digest)}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt_value, digest_value = hashed_password.split("$", 1)
    except ValueError:
        return False
    expected = hash_password(password, salt_value)
    return hmac.compare_digest(expected, hashed_password)


def create_access_token(subject: str, role: str, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, object]:
    header_text, payload_text, signature_text = token.split(".")
    signing_input = f"{header_text}.{payload_text}"
    expected_signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(_base64url_encode(expected_signature), signature_text):
        raise ValueError("Invalid token signature")

    payload = json.loads(_base64url_decode(payload_text))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return payload