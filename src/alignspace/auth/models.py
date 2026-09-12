from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from alignspace.persistence.tables import Base


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class SessionRow(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RefreshTokenRow(Base):
    __tablename__ = "refresh_tokens"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RateLimitRow(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class JoinCodeRow(Base):
    __tablename__ = "project_join_codes"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class MigrationRow(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
