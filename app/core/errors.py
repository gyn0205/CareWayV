"""Shared API error responses and validation input redaction."""

from collections.abc import Callable
from http import HTTPStatus
from typing import Literal, TypeVar

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings

Endpoint = TypeVar("Endpoint", bound=Callable[..., object])


class WayfindingError(Exception):
    def __init__(
        self,
        code: Literal[
            "kiosk_not_found", "kiosk_conflict", "invalid_audio", "voice_not_configured", "transcription_failed",
            "speech_failed",
        ],
        message: str,
    ):
        super().__init__(message)
        self.code = code


def redact_validation_input(endpoint: Endpoint) -> Endpoint:
    """Hide submitted values in validation errors for this endpoint."""
    setattr(endpoint, "_redact_validation_input", True)
    return endpoint


async def handle_wayfinding_error(_request: Request, error: WayfindingError) -> JSONResponse:
    return JSONResponse(
        status_code=settings.WAYFINDING_ERROR_STATUS[error.code],
        content={"detail": str(error)},
    )


async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    if getattr(request.scope.get("endpoint"), "_redact_validation_input", False):
        # FastAPI's default validation response includes the submitted audio.
        details = [
            {key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()
        ]
        return JSONResponse(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(details)},
        )
    return await request_validation_exception_handler(request, error)


api_exception_handlers = {
    RequestValidationError: handle_validation_error,
    WayfindingError: handle_wayfinding_error,
}
