"""Password hashing (scrypt) and HS256 session tokens — pure stdlib, no third-party
dependencies, no I/O. Shared by the seed script (hashing), the login route (verify + issue),
and the role guards (verify). The dashboard verifies the same HS256 token with `jose`, so the
token format here is standards-compliant JWT."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

# scrypt (RFC 7914) interactive-login profile. memory ≈ 128 * N * r ≈ 16 MiB.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 2**26  # 64 MiB — headroom over the working set across OpenSSL builds
_SALT_BYTES = 16

_DEFAULT_TTL_SECONDS = 12 * 3600


class TokenError(Exception):
    """Raised when a session token is malformed, unsigned, tampered, or expired."""


@dataclass(frozen=True)
class Identity:
    username: str
    display_name: str
    role: str


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "$".join(
        ["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), _b64e(salt), _b64e(derived)]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n_s, r_s, p_s, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(dk_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


def encode_jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64e(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64e(signature))
    return ".".join(segments)


def decode_jwt(token: str, secret: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("malformed token")
    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64d(header_b64))
    except (ValueError, TypeError) as exc:
        raise TokenError("bad header") from exc
    if header.get("alg") != "HS256":
        raise TokenError("unsupported algorithm")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64d(signature_b64)
    except (ValueError, TypeError) as exc:
        raise TokenError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, provided):
        raise TokenError("bad signature")
    try:
        payload = json.loads(_b64d(payload_b64))
    except (ValueError, TypeError) as exc:
        raise TokenError("bad payload") from exc
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        raise TokenError("token expired")
    return payload


def make_session_token(
    identity: Identity,
    secret: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    issued = time.time() if now is None else now
    payload = {
        "sub": identity.username,
        "name": identity.display_name,
        "role": identity.role,
        "iat": int(issued),
        "exp": int(issued + ttl_seconds),
    }
    return encode_jwt(payload, secret)


def read_session_token(token: str, secret: str) -> Identity:
    payload = decode_jwt(token, secret)
    try:
        return Identity(
            username=payload["sub"],
            display_name=payload.get("name", payload["sub"]),
            role=payload["role"],
        )
    except KeyError as exc:
        raise TokenError(f"missing claim: {exc}") from exc
