"""
Centralized logging configuration.

Usage in business code:
    from app.core.logger import get_logger
    logger = get_logger(__name__)
    logger.debug("...")
    logger.info("...")
    logger.error("...", exc_info=True)
"""

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# ── ANSI color codes ──────────────────────────────────────────────
_RESET = "\033[0m"
_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[41m\033[37m",  # red bg, white fg
}


class ColoredFormatter(logging.Formatter):
    """Formatter that injects ANSI color codes for console output."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s  %(levelname_color)s  %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        color = _COLORS.get(levelname, "")
        record.levelname_color = f"{color}{levelname}{_RESET}" if color else levelname
        return super().format(record)


class PlainFormatter(logging.Formatter):
    """Formatter for file output (no color codes)."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name.

    Convenience wrapper around logging.getLogger.  All loggers inherit
    the root configuration applied by setup_logging().
    """
    return logging.getLogger(name)


def setup_logging(settings) -> None:
    """Configure the root logger and quiet noisy third-party loggers.

    Must be called once at startup, before any requests are served.
    Works for both the FastAPI process and the Celery worker.
    """

    root = logging.getLogger()
    root.setLevel(_to_level(settings.LOG_LEVEL))

    # Remove any pre-existing handlers (idempotent)
    for h in list(root.handlers):
        root.removeHandler(h)

    # ── Console handler (colored) ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(_to_level(settings.LOG_LEVEL))
    console.setFormatter(ColoredFormatter())
    root.addHandler(console)

    # ── File handler (rotating, plain text) ──
    log_dir = settings.LOG_DIR
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, settings.LOG_FILE)
        fh = RotatingFileHandler(
            file_path,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(_to_level(settings.LOG_LEVEL))
        fh.setFormatter(PlainFormatter())
        root.addHandler(fh)

    # ── Uvicorn loggers: inherit our root config ──
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True

    # ── SQLAlchemy engine: independent level ──
    sa = logging.getLogger("sqlalchemy.engine")
    sa.handlers.clear()
    sa.propagate = True
    sa.setLevel(_to_level(settings.LOG_MYSQL_LEVEL))

    # ── Quiet noisy connection-pool logs ──
    logging.getLogger("sqlalchemy.pool.QueuePool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)

    # ── Quiet httpcore / httpx ──
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# ── Request logging middleware ────────────────────────────────────

_request_logger = logging.getLogger("api.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request: method, path, status, duration."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _request_logger.exception(
                "Unhandled exception %s %s", request.method, request.url.path
            )
            raise
        duration = time.perf_counter() - start
        _request_logger.info(
            "%s %s %s %.4fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response


# ── Helpers ────────────────────────────────────────────────────────

def _to_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.DEBUG)
