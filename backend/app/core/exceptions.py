from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class APIErrorResponse(BaseModel):
    detail: str | list[Any]
    status_code: int
    error_type: str


from app.services.persistence.exceptions import PersistenceError


def _http_error_type(status_code: int) -> str:
    if status_code == 415:
        return "unsupported_media_type"
    return "http_error"


def _sanitize_validation_errors(errors: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    for error in errors:
        item = dict(error)
        raw_input = item.get("input")
        if isinstance(raw_input, bytes):
            item["input"] = raw_input.decode("utf-8", errors="replace")
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: str(value) if isinstance(value, BaseException) else value
                for key, value in ctx.items()
            }
        sanitized.append(item)
    return sanitized


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PersistenceError)
    async def persistence_exception_handler(
        _request: Request,
        exc: PersistenceError,
    ) -> JSONResponse:
        payload = APIErrorResponse(
            detail=exc.message,
            status_code=exc.status_code,
            error_type=exc.error_type,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, (str, list)) else str(exc.detail)
        payload = APIErrorResponse(
            detail=detail,
            status_code=exc.status_code,
            error_type=_http_error_type(exc.status_code),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        payload = APIErrorResponse(
            detail=_sanitize_validation_errors(exc.errors()),
            status_code=422,
            error_type="validation_error",
        )
        return JSONResponse(
            status_code=422,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        payload = APIErrorResponse(
            detail="Internal server error",
            status_code=500,
            error_type="internal_error",
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(),
        )
