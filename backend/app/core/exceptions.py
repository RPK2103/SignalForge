from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class APIErrorResponse(BaseModel):
    detail: str | list[Any]
    status_code: int
    error_type: str


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, (str, list)) else str(exc.detail)
        payload = APIErrorResponse(
            detail=detail,
            status_code=exc.status_code,
            error_type="http_error",
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
            detail=exc.errors(),
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
