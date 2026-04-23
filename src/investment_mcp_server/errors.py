"""Domain errors and stable error payloads for investment market data tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload


class InvestmentMCPError(Exception):
    """Base exception for project-specific errors."""

    code = "INTERNAL_ERROR"
    retryable = False

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InputError(InvestmentMCPError):
    code = "INVALID_INPUT"


class InvalidTickerError(InvestmentMCPError):
    code = "INVALID_TICKER"


class InvalidIntervalError(InvestmentMCPError):
    code = "INVALID_INTERVAL"


class InvalidTimeRangeError(InvestmentMCPError):
    code = "INVALID_TIME_RANGE"


class RateLimitedError(InvestmentMCPError):
    code = "RATE_LIMITED"
    retryable = True


class TickerNotFoundError(InvestmentMCPError):
    code = "TICKER_NOT_FOUND"


class NoDataError(InvestmentMCPError):
    code = "NO_DATA"


class DataAlignmentError(InvestmentMCPError):
    code = "DATA_ALIGNMENT_ERROR"


class UpstreamHTTPStatusError(InvestmentMCPError):
    """Represents a non-2xx upstream response with status code details."""

    def __init__(self, status_code: int, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details=details)
        self.status_code = status_code


class UpstreamUnavailableError(InvestmentMCPError):
    code = "UPSTREAM_UNAVAILABLE"
    retryable = True


def map_exception_to_error_payload(exc: Exception) -> ErrorPayload:
    """Convert known exceptions into a stable MCP tool error payload."""
    if isinstance(exc, RateLimitedError):
        return ErrorPayload(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )

    if isinstance(exc, UpstreamHTTPStatusError):
        if exc.status_code == 429:
            return ErrorPayload(
                code="RATE_LIMITED",
                message=exc.message,
                retryable=True,
                details={"status_code": exc.status_code, **(exc.details or {})},
            )
        if exc.status_code in {500, 502, 503, 504}:
            return ErrorPayload(
                code="UPSTREAM_UNAVAILABLE",
                message=exc.message,
                retryable=True,
                details={"status_code": exc.status_code, **(exc.details or {})},
            )
        return ErrorPayload(
            code="UPSTREAM_BAD_RESPONSE",
            message=exc.message,
            retryable=False,
            details={"status_code": exc.status_code, **(exc.details or {})},
        )

    if isinstance(exc, httpx.TimeoutException):
        return ErrorPayload(
            code="UPSTREAM_UNAVAILABLE",
            message=str(exc) or "Upstream request timed out",
            retryable=True,
        )

    if isinstance(exc, httpx.RequestError):
        return ErrorPayload(
            code="UPSTREAM_UNAVAILABLE",
            message=str(exc) or "Upstream request failed",
            retryable=True,
        )

    if isinstance(exc, InvestmentMCPError):
        return ErrorPayload(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )

    return ErrorPayload(
        code="INTERNAL_ERROR",
        message="Unexpected internal error",
        retryable=False,
    )
