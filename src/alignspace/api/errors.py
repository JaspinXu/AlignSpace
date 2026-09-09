from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from alignspace.application.resources import AssetLimitError, ConsentRequiredError
from alignspace.application.service import AuthorizationError
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.repository import IdempotencyConflictError


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    recoverable: bool,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlationId": correlation_id,
                "recoverable": recoverable,
                "details": details or {},
            }
        },
        headers={"X-Correlation-Id": correlation_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthorizationError)
    async def authorization_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
        return _response(
            request,
            status_code=403,
            code="FORBIDDEN",
            message=str(exc),
            recoverable=False,
        )

    @app.exception_handler(ConsentRequiredError)
    async def consent_handler(request: Request, exc: ConsentRequiredError) -> JSONResponse:
        return _response(
            request,
            status_code=409,
            code="CONSENT_REQUIRED",
            message=str(exc),
            recoverable=True,
        )

    @app.exception_handler(AssetLimitError)
    async def asset_limit_handler(request: Request, exc: AssetLimitError) -> JSONResponse:
        return _response(
            request,
            status_code=409,
            code="ASSET_LIMIT_REACHED",
            message=str(exc),
            recoverable=True,
        )

    @app.exception_handler(StaleStateError)
    async def stale_state_handler(request: Request, exc: StaleStateError) -> JSONResponse:
        return _response(
            request,
            status_code=409,
            code="STATE_VERSION_STALE",
            message=str(exc),
            recoverable=True,
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_handler(
        request: Request,
        exc: IdempotencyConflictError,
    ) -> JSONResponse:
        return _response(
            request,
            status_code=409,
            code="IDEMPOTENCY_KEY_CONFLICT",
            message=str(exc),
            recoverable=True,
        )

    @app.exception_handler(KeyError)
    async def not_found_handler(request: Request, exc: KeyError) -> JSONResponse:
        message = str(exc.args[0]) if exc.args else "resource not found"
        code = "PROJECT_NOT_FOUND" if message.startswith("project ") else "RESOURCE_NOT_FOUND"
        return _response(
            request,
            status_code=404,
            code=code,
            message=message,
            recoverable=False,
        )

    @app.exception_handler(ValueError)
    async def value_handler(request: Request, exc: ValueError) -> JSONResponse:
        return _response(
            request,
            status_code=400,
            code="INVALID_REQUEST",
            message=str(exc),
            recoverable=True,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        safe_details = {
            "issues": [
                {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
                for item in exc.errors()
            ]
        }
        return _response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="The request did not match the API contract.",
            recoverable=True,
            details=safe_details,
        )
