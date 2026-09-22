import pytest
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNSPACE_AUTH_SECRET", "test-secret-for-authentication-with-enough-entropy")
    monkeypatch.setenv("ALIGNSPACE_DEV", "1")
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
    )
    with TestClient(app, headers=ORIGIN) as client:
        yield client


def register(client, email="Owner@example.com"):
    response = client.post(
        "/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(result):
    return {"Authorization": f"Bearer {result['accessToken']}"}


@pytest.mark.parametrize("length,expected", [(7, 422), (8, 201), (128, 201), (129, 422)])
def test_registration_password_length_boundaries(auth_client, length, expected):
    credentials = {"email": "boundary@example.com", "password": "x" * length}
    assert auth_client.post("/v1/auth/register", json=credentials).status_code == expected
    if expected == 201:
        assert auth_client.post("/v1/auth/login", json=credentials).status_code == 200


def test_register_normalizes_email_and_creates_real_session(auth_client):
    result = register(auth_client)
    assert result["user"]["email"] == "owner@example.com"
    assert result["user"]["emailVerified"] is False
    assert auth_client.get("/v1/auth/me", headers=bearer(result)).json() == result["user"]
    assert auth_client.get("/v1/projects", headers=bearer(result)).json() == []
    assert "HttpOnly" in auth_client.post("/v1/auth/refresh").headers["set-cookie"]


def test_duplicate_email_wrong_password_and_password_validation(auth_client):
    register(auth_client)
    duplicate = auth_client.post(
        "/v1/auth/register", json={"email": "OWNER@example.com", "password": PASSWORD}
    )
    assert duplicate.status_code == 409
    bad = auth_client.post(
        "/v1/auth/login", json={"email": "owner@example.com", "password": "wrong password"}
    )
    unknown = auth_client.post(
        "/v1/auth/login", json={"email": "unknown@example.com", "password": "wrong password"}
    )
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert PASSWORD not in duplicate.text
    for email, password in [("invalid", PASSWORD), ("short@example.com", "short")]:
        assert auth_client.post(
            "/v1/auth/register", json={"email": email, "password": password}
        ).status_code == 422


def test_refresh_rotates_and_reuse_revokes_session(auth_client):
    first = register(auth_client)
    old_cookie = auth_client.cookies.get("alignspace_refresh")
    refreshed = auth_client.post("/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert auth_client.cookies.get("alignspace_refresh") != old_cookie
    auth_client.cookies.clear()
    replay = auth_client.post(
        "/v1/auth/refresh", headers={"Cookie": f"alignspace_refresh={old_cookie}"}
    )
    assert replay.status_code == 401
    assert auth_client.get("/v1/auth/me", headers=bearer(first)).status_code == 401
    assert auth_client.get("/v1/auth/me", headers=bearer(refreshed.json())).status_code == 401


def test_logout_invalidates_access_and_refresh_and_can_log_in_again(auth_client):
    first = register(auth_client)
    assert auth_client.post("/v1/auth/logout").status_code == 204
    assert auth_client.get("/v1/auth/me", headers=bearer(first)).status_code == 401
    assert auth_client.post("/v1/auth/refresh").status_code == 401
    login = auth_client.post(
        "/v1/auth/login", json={"email": "OWNER@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    assert auth_client.get("/v1/auth/me", headers=bearer(login.json())).status_code == 200


def test_origins_and_forged_headers_are_rejected(auth_client):
    assert auth_client.post(
        "/v1/auth/register",
        headers={"Origin": "https://attacker.example"},
        json={"email": "owner@example.com", "password": PASSWORD},
    ).status_code == 403
    assert auth_client.get(
        "/v1/projects/anything",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
    ).status_code == 401
    assert auth_client.get(
        "/v1/projects", headers={"Authorization": "Bearer forged"}
    ).status_code == 401


def test_registration_and_login_are_throttled(auth_client):
    for _ in range(10):
        result = auth_client.post(
            "/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD}
        )
        assert result.status_code == 401
    limited = auth_client.post(
        "/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD}
    )
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_register_ip_limit_is_configurable(monkeypatch):
    from alignspace.auth.config import AuthConfig

    monkeypatch.delenv("ALIGNSPACE_REGISTER_IP_LIMIT", raising=False)
    assert AuthConfig.from_env().register_ip_limit == 10
    monkeypatch.setenv("ALIGNSPACE_REGISTER_IP_LIMIT", "100")
    assert AuthConfig.from_env().register_ip_limit == 100
