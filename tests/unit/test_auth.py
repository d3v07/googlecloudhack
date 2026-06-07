import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import ROLE_DBRE, ROLE_USER, UserRecord, require_role
from api.server import create_app
from controller.auth import (
    Identity,
    TokenError,
    _b64e,
    decode_jwt,
    encode_jwt,
    hash_password,
    make_session_token,
    read_session_token,
    verify_password,
)

SECRET = "test-session-secret-please-rotate"


# ---------------------------------------------------------------- password hashing


def test_hash_verify_roundtrip() -> None:
    stored = hash_password("correct horse battery staple")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery staple", stored) is True


def test_verify_rejects_wrong_password() -> None:
    stored = hash_password("s3cret-pw")
    assert verify_password("not-it", stored) is False


def test_hash_is_salted_unique() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a) and verify_password("same", b)


def test_hash_rejects_empty_password() -> None:
    with pytest.raises(ValueError):
        hash_password("")


@pytest.mark.parametrize("bad", ["", "not-a-hash", "scrypt$bad", "bcrypt$1$2$3$4$5"])
def test_verify_handles_malformed_stored(bad: str) -> None:
    assert verify_password("whatever", bad) is False


# ---------------------------------------------------------------- HS256 token


def test_jwt_roundtrip() -> None:
    token = encode_jwt({"sub": "x", "role": "user"}, SECRET)
    assert decode_jwt(token, SECRET) == {"sub": "x", "role": "user"}


def test_jwt_rejects_tampered_signature() -> None:
    head, payload, sig = encode_jwt({"sub": "x"}, SECRET).split(".")
    with pytest.raises(TokenError):
        decode_jwt(f"{head}.{payload}.{sig[:-2]}xx", SECRET)


def test_jwt_rejects_wrong_secret() -> None:
    token = encode_jwt({"sub": "x"}, SECRET)
    with pytest.raises(TokenError):
        decode_jwt(token, "other-secret")


def test_jwt_rejects_tampered_payload() -> None:
    head, _payload, sig = encode_jwt({"role": "user"}, SECRET).split(".")
    forged = _b64e(b'{"role":"dbre"}')
    with pytest.raises(TokenError):
        decode_jwt(f"{head}.{forged}.{sig}", SECRET)


def test_jwt_rejects_expired() -> None:
    token = make_session_token(Identity("u", "U", "user"), SECRET, ttl_seconds=-1)
    with pytest.raises(TokenError):
        read_session_token(token, SECRET)


def test_jwt_rejects_malformed() -> None:
    with pytest.raises(TokenError):
        decode_jwt("not.a.jwt.token", SECRET)
    with pytest.raises(TokenError):
        decode_jwt("only-one-segment", SECRET)


def test_session_token_roundtrip() -> None:
    ident = Identity("dev.trivedi", "Dev Trivedi", ROLE_USER)
    assert read_session_token(make_session_token(ident, SECRET), SECRET) == ident


def test_read_session_token_missing_claim() -> None:
    token = encode_jwt({"sub": "x"}, SECRET)  # no role claim
    with pytest.raises(TokenError):
        read_session_token(token, SECRET)


def _signed(header_json: bytes, payload_b64: str) -> str:
    import hashlib
    import hmac

    head = _b64e(header_json)
    sig = _b64e(
        hmac.new(SECRET.encode(), f"{head}.{payload_b64}".encode(), hashlib.sha256).digest()
    )
    return f"{head}.{payload_b64}.{sig}"


def test_jwt_rejects_unsupported_alg() -> None:
    token = _signed(b'{"alg":"none","typ":"JWT"}', _b64e(b'{"sub":"x","role":"user"}'))
    with pytest.raises(TokenError):
        decode_jwt(token, SECRET)


def test_jwt_rejects_bad_signature_encoding() -> None:
    head = _b64e(b'{"alg":"HS256","typ":"JWT"}')
    with pytest.raises(TokenError):
        decode_jwt(f"{head}.{_b64e(b'{}')}.x", SECRET)


def test_jwt_rejects_bad_payload_json() -> None:
    # valid signature over a non-JSON payload -> reaches the payload-decode failure branch
    with pytest.raises(TokenError):
        decode_jwt(_signed(b'{"alg":"HS256","typ":"JWT"}', _b64e(b"not-json")), SECRET)


class _FakeUserCol:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        return next((d for d in self._docs if d["username"] == query["username"]), None)


def test_mongo_user_store_get_and_missing() -> None:
    from api.auth import MongoUserStore

    store = MongoUserStore(
        _FakeUserCol(
            [{"username": "dbre", "display_name": "DBRE", "role": "dbre", "password_hash": "h"}]
        )
    )
    user = store.get_user("dbre")
    assert user is not None and user.username == "dbre" and user.role == "dbre"
    assert store.get_user("missing") is None


# ---------------------------------------------------------------- login route


class FakeAuthStore:
    def __init__(self, users: list[UserRecord]) -> None:
        self._users = {u.username: u for u in users}

    def get_user(self, username: str) -> UserRecord | None:
        return self._users.get(username)


def _user(username: str, role: str, password: str) -> UserRecord:
    return UserRecord(
        username=username,
        display_name=username.replace(".", " ").title(),
        role=role,
        password_hash=hash_password(password),
    )


def _login_client(monkeypatch, users: list[UserRecord]) -> TestClient:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_auth_test_xyz")
    return TestClient(create_app(auth_store=FakeAuthStore(users)))


def test_login_success_returns_token_and_role(monkeypatch) -> None:
    client = _login_client(monkeypatch, [_user("dbre", ROLE_DBRE, "pw-dbre")])
    resp = client.post("/auth/login", json={"username": "dbre", "password": "pw-dbre"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == ROLE_DBRE
    assert data["username"] == "dbre"
    assert read_session_token(data["token"], SECRET).role == ROLE_DBRE


def test_login_wrong_password_401(monkeypatch) -> None:
    client = _login_client(monkeypatch, [_user("dev.trivedi", ROLE_USER, "right")])
    resp = client.post("/auth/login", json={"username": "dev.trivedi", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user_401(monkeypatch) -> None:
    client = _login_client(monkeypatch, [_user("dev.trivedi", ROLE_USER, "x")])
    resp = client.post("/auth/login", json={"username": "ghost", "password": "x"})
    assert resp.status_code == 401


def test_login_503_when_session_secret_missing(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_auth_test_xyz")
    client = TestClient(create_app(auth_store=FakeAuthStore([_user("dbre", ROLE_DBRE, "pw")])))
    assert (
        client.post("/auth/login", json={"username": "dbre", "password": "pw"}).status_code == 503
    )


def test_login_503_when_auth_store_not_configured(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_auth_test_xyz")
    client = TestClient(create_app())
    assert (
        client.post("/auth/login", json={"username": "dbre", "password": "pw"}).status_code == 503
    )


# ---------------------------------------------------------------- role guard


def _guarded_app(*roles: str) -> FastAPI:
    app = FastAPI()

    @app.get("/guarded")
    def guarded(identity=Depends(require_role(*roles))) -> dict:
        return {"username": identity.username, "role": identity.role}

    return app


def test_require_role_allows_matching(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    client = TestClient(_guarded_app(ROLE_DBRE))
    token = make_session_token(Identity("dbre", "DBRE", ROLE_DBRE), SECRET)
    resp = client.get("/guarded", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == ROLE_DBRE


def test_require_role_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    assert TestClient(_guarded_app(ROLE_DBRE)).get("/guarded").status_code == 401


def test_require_role_rejects_wrong_role(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    client = TestClient(_guarded_app(ROLE_DBRE))
    token = make_session_token(Identity("dev", "Dev", ROLE_USER), SECRET)
    resp = client.get("/guarded", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_require_role_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    client = TestClient(_guarded_app())
    resp = client.get("/guarded", headers={"Authorization": "Bearer garbage.token.here"})
    assert resp.status_code == 401
