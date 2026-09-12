import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class AuthConfig:
    secret: str
    origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    secure_cookie: bool = True
    access_seconds: int = 15 * 60
    session_seconds: int = 7 * 24 * 60 * 60
    issuer: str = "alignspace"
    audience: str = "alignspace-api"

    @classmethod
    def from_env(cls):
        return cls(
            secret=os.getenv("ALIGNSPACE_AUTH_SECRET", ""),
            origins=tuple(
                item.strip() for item in os.getenv(
                    "ALIGNSPACE_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
                ).split(",") if item.strip()
            ),
            secure_cookie=os.getenv("ALIGNSPACE_DEV") != "1",
        )

    def validate(self):
        if len(self.secret.encode()) < 32:
            raise RuntimeError("ALIGNSPACE_AUTH_SECRET must contain at least 32 bytes.")
        if not self.origins:
            raise RuntimeError("Configure at least one explicit ALIGNSPACE_ORIGINS origin.")
        for origin in self.origins:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"} or not url.netloc
                or url.path or url.query or url.fragment or url.username
                or "*" in origin
            ):
                raise RuntimeError("ALIGNSPACE_ORIGINS must contain exact HTTP(S) origins.")
            if not self.secure_cookie and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError("Insecure development cookies are limited to loopback origins.")
