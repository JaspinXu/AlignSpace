from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from alignspace.auth.service import AuthError, user_view

COOKIE = "alignspace_refresh"
COOKIE_PATH = "/v1/auth"
router = APIRouter(prefix=COOKIE_PATH, tags=["accounts"])


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterInput(LoginInput):
    password: str = Field(min_length=15, max_length=128)


def require_origin(request: Request):
    if request.headers.get("origin") not in request.app.state.container.auth.config.origins:
        raise AuthError("ORIGIN_NOT_ALLOWED", "请求来源不被允许。", 403)


def current_user(request: Request):
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError()
    return request.app.state.container.auth.authenticate(token)


CurrentUser = Annotated[object, Depends(current_user)]


def _auth_response(request, response, result):
    payload, refresh, max_age = result
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        COOKIE, refresh, max_age=max_age, httponly=True,
        secure=request.app.state.container.auth.config.secure_cookie,
        samesite="strict", path=COOKIE_PATH,
    )
    return payload


@router.post("/register", status_code=201, dependencies=[Depends(require_origin)])
def register(body: RegisterInput, request: Request, response: Response):
    service = request.app.state.container.auth
    service.throttle("register-ip", request.client.host, limit=10, window=60)
    return _auth_response(request, response, service.register(str(body.email), body.password))


@router.post("/login", dependencies=[Depends(require_origin)])
def login(body: LoginInput, request: Request, response: Response):
    service = request.app.state.container.auth
    service.throttle("login-ip", request.client.host, limit=30)
    service.throttle("login-email", str(body.email), limit=10)
    return _auth_response(request, response, service.login(str(body.email), body.password))


@router.post("/refresh", dependencies=[Depends(require_origin)])
def refresh(request: Request, response: Response):
    return _auth_response(
        request, response, request.app.state.container.auth.refresh(request.cookies.get(COOKIE))
    )


@router.post("/logout", status_code=204, dependencies=[Depends(require_origin)])
def logout(request: Request):
    service = request.app.state.container.auth
    service.logout(request.cookies.get(COOKIE))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE, path=COOKIE_PATH, httponly=True,
        secure=service.config.secure_cookie, samesite="strict",
    )
    return response


@router.get("/me")
def me(user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return user_view(user)
