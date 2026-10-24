"""Password hashing and encryption for account-scoped Gmail credentials."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken

PASSWORD_ITERATIONS = 600_000
EMAIL_PATTERN = re.compile(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def valid_email(email: str) -> bool:
    return len(email) <= 254 and EMAIL_PATTERN.fullmatch(email) is not None


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Password must contain 12 to 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode("ascii"), expected)
    except (ValueError, TypeError, UnicodeEncodeError):
        return False


def _fernet() -> Fernet:
    key = os.environ.get("CERTIFY_CREDENTIAL_KEY")
    if not key:
        raise RuntimeError("User credential encryption is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("User credential encryption key is invalid") from exc


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Saved Gmail credentials could not be decrypted") from exc