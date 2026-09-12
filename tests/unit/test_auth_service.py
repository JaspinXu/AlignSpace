import time

import jwt
import pytest

from alignspace.auth.config import AuthConfig
from alignspace.auth.service import AuthError, AuthService
from alignspace.persistence.database import create_engine_and_session

SECRET = "unit-test-auth-secret-that-is-long-enough-to-avoid-hmac-key-length-warnings"
PASSWORD = "a sufficiently long password"


class FakeClock:
    def __init__(self, start: float | None = None) -> None:
        self._now = time.time() if start is None else start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def auth(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'unit-auth.db'}")
    clock = FakeClock()
    service = AuthService(
        session_factory,
        AuthConfig(secret=SECRET, secure_cookie=False),
        clock=clock,
    )
    try:
        yield service, clock
    finally:
        engine.dispose()


def _register(service: AuthService) -> dict:
    payload, _, _ = service.register("owner@example.com", PASSWORD)
    return payload


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _sign(service: AuthService, claims: dict, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, service.config.secret, algorithm=algorithm)


def test_expired_access_token_is_rejected(auth):
    service, _ = auth
    token = _register(service)["accessToken"]
    claims = _claims(token)
    claims["exp"] = int(time.time()) - 10
    with pytest.raises(AuthError):
        service.authenticate(_sign(service, claims))


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "attacker"},
        {"aud": "some-other-api"},
        {"exp": int(time.time()) + 900, "nbf": int(time.time()) + 900},
    ],
)
def test_tokens_with_wrong_issuer_audience_or_not_before_are_rejected(auth, override):
    service, _ = auth
    token = _register(service)["accessToken"]
    claims = _claims(token) | override
    with pytest.raises(AuthError):
        service.authenticate(_sign(service, claims))


def test_token_signed_with_a_non_allowed_algorithm_is_rejected(auth):
    service, _ = auth
    token = _register(service)["accessToken"]
    wrong = _sign(service, _claims(token), algorithm="HS512")
    with pytest.raises(AuthError):
        service.authenticate(wrong)


def test_access_token_dies_with_the_absolute_session_lifetime(auth):
    service, clock = auth
    token = _register(service)["accessToken"]
    assert service.authenticate(token).email == "owner@example.com"
    clock.advance(service.config.session_seconds + 1)
    with pytest.raises(AuthError):
        service.authenticate(token)


def test_missing_or_weak_secret_refuses_to_start():
    with pytest.raises(RuntimeError):
        AuthConfig(secret="x" * 31).validate()
    assert AuthConfig(secret="x" * 32).validate() is None
    with pytest.raises(RuntimeError):
        AuthConfig(secret="x" * 40, origins=()).validate()
