import hashlib
import secrets
import time
from contextlib import contextmanager
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from alignspace.auth.config import AuthConfig
from alignspace.auth.models import RateLimitRow, RefreshTokenRow, SessionRow, UserRow


class AuthError(Exception):
    def __init__(self, code="UNAUTHENTICATED", message="请重新登录。", status=401):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def write_transaction(session_factory):
    # SQLite has no row-level SELECT FOR UPDATE. Acquire the writer lock before
    # reading tokens/codes so competing requests cannot both consume one value.
    with session_factory() as session:
        session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


def user_view(user: UserRow) -> dict:
    return {"id": user.id, "email": user.email, "emailVerified": False}


class AuthService:
    def __init__(self, session_factory, config: AuthConfig, clock=time.time):
        self.sessions = session_factory
        self.config = config
        self.clock = clock
        self.hasher = PasswordHasher()
        self._dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))

    def throttle(self, action: str, identifier: str, *, limit=10, window=60):
        now = int(self.clock())
        key = digest(f"{action}:{identifier}")
        exceeded = False
        with write_transaction(self.sessions) as db:
            # Bound retention even when random identities are attempted.
            db.execute(delete(RateLimitRow).where(RateLimitRow.window_start < now - 86400))
            row = db.get(RateLimitRow, key)
            if row is None:
                db.add(RateLimitRow(key=key, window_start=now, attempts=1))
            elif now - row.window_start >= window:
                row.window_start, row.attempts = now, 1
            elif row.attempts >= limit:
                exceeded = True
            else:
                row.attempts += 1
        if exceeded:
            raise AuthError("RATE_LIMITED", "尝试次数过多，请稍后重试。", 429)

    def register(self, email: str, password: str):
        password_hash = self.hasher.hash(password)
        try:
            with write_transaction(self.sessions) as db:
                user = UserRow(
                    id=str(uuid4()), email=email, password_hash=password_hash,
                    created_at=int(self.clock()),
                )
                db.add(user)
                db.flush()
                return self._new_session(db, user)
        except IntegrityError as exc:
            raise AuthError("EMAIL_IN_USE", "该邮箱已注册，请登录。", 409) from exc

    def login(self, email: str, password: str):
        with self.sessions() as db:
            user = db.scalar(select(UserRow).where(UserRow.email == email))
            hashed = user.password_hash if user else self._dummy_hash
        try:
            self.hasher.verify(hashed, password)
        except VerificationError:
            raise AuthError("INVALID_CREDENTIALS", "邮箱或密码不正确。") from None
        if user is None:
            raise AuthError("INVALID_CREDENTIALS", "邮箱或密码不正确。")
        with write_transaction(self.sessions) as db:
            current = db.get(UserRow, user.id)
            if self.hasher.check_needs_rehash(current.password_hash):
                current.password_hash = self.hasher.hash(password)
            return self._new_session(db, current)

    def _new_session(self, db, user):
        now = int(self.clock())
        # Keep token reuse history for the entire live session; expired sessions
        # and their token history can be removed together.
        db.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
        session = SessionRow(
            id=str(uuid4()), user_id=user.id,
            expires_at=now + self.config.session_seconds, revoked=False,
        )
        db.add(session)
        db.flush()
        return self._issue(db, session, user)

    def _issue(self, db, session, user):
        self.config.validate()
        now = int(self.clock())
        refresh = secrets.token_urlsafe(48)
        db.add(RefreshTokenRow(digest=digest(refresh), session_id=session.id, consumed=False))
        access = jwt.encode(
            {
                "sub": user.id, "sid": session.id, "iss": self.config.issuer,
                "aud": self.config.audience, "iat": now, "nbf": now,
                "exp": min(now + self.config.access_seconds, session.expires_at),
                "jti": str(uuid4()),
            },
            self.config.secret, algorithm="HS256",
        )
        return {"accessToken": access, "user": user_view(user)}, refresh, session.expires_at - now

    def refresh(self, raw: str | None):
        if not raw or len(raw) > 256:
            raise AuthError()
        result = None
        with write_transaction(self.sessions) as db:
            token = db.get(RefreshTokenRow, digest(raw))
            session = db.get(SessionRow, token.session_id) if token else None
            if session and token.consumed:
                # Commit revocation before reporting the replay error.
                session.revoked = True
            elif session and not session.revoked and session.expires_at > self.clock():
                token.consumed = True
                result = self._issue(db, session, db.get(UserRow, session.user_id))
        if result is None:
            raise AuthError()
        return result

    def authenticate(self, token: str):
        self.config.validate()
        try:
            claims = jwt.decode(
                token, self.config.secret, algorithms=["HS256"],
                issuer=self.config.issuer, audience=self.config.audience,
                options={"require": ["sub", "sid", "exp", "iat", "nbf", "iss", "aud"]},
            )
            if not isinstance(claims["sid"], str):
                raise AuthError()
        except jwt.PyJWTError:
            raise AuthError() from None
        with self.sessions() as db:
            session = db.get(SessionRow, claims["sid"])
            if (
                session is None or session.revoked or session.expires_at <= self.clock()
                or session.user_id != claims["sub"]
            ):
                raise AuthError()
            user = db.get(UserRow, session.user_id)
            if user is None:
                raise AuthError()
            return user

    def logout(self, raw: str | None):
        if not raw or len(raw) > 256:
            return
        with write_transaction(self.sessions) as db:
            token = db.get(RefreshTokenRow, digest(raw))
            if token:
                session = db.get(SessionRow, token.session_id)
                if session:
                    session.revoked = True
