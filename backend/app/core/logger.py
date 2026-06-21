"""
Centralized logging configuration.

日志文件:
  logs/debug.log   — 仅 DEBUG 级别，按大小轮转（20 MB × 20 个文件）
  logs/info.log    — INFO  及以上，按日轮转（保留 10 天）
  logs/error.log   — ERROR 及以上，按日轮转（保留 10 天）
  logs/mysql.log   — SQLAlchemy 引擎，按大小轮转（20 MB × 20 个文件）

Usage:
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
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# ── ANSI color codes ──────────────────────────────────────────────
_RESET = "\033[0m"
_COLORS = {
    "DEBUG": "\033[36m",       # cyan
    "INFO": "\033[32m",        # green
    "WARNING": "\033[33m",     # yellow
    "ERROR": "\033[31m",       # red
    "CRITICAL": "\033[41m\033[37m",  # red bg, white fg
}

_CONSOLE_FMT = "%(asctime)s  %(levelname_color)s  %(name)s - %(message)s"
_FILE_FMT = "%(asctime)s  %(levelname)-8s  %(name)s - %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class LevelFilter(logging.Filter):
    """Only allow records whose level exactly matches *level*."""

    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


class ColoredFormatter(logging.Formatter):
    """Inject ANSI color into levelname for console output."""

    def __init__(self):
        super().__init__(fmt=_CONSOLE_FMT, datefmt=_DATE_FMT)

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        record.levelname_color = f"{color}{record.levelname}{_RESET}" if color else record.levelname
        return super().format(record)


# ── Core API ──────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Return a logger for the calling module."""
    return logging.getLogger(name)


def setup_logging(settings) -> None:
    """Initialise root logger with console + level-based file handlers.

    Call once at process startup (FastAPI lifespan / Celery worker init).
    """

    root = logging.getLogger()
    root.setLevel(_to_level(settings.LOG_LEVEL))
    _clear_handlers(root)

    # ── Console (colored, all levels) ──
    root.addHandler(_console_handler(settings))

    # ── File handlers ──
    log_dir = settings.LOG_DIR
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

        # debug  — only DEBUG level, size-based (20 MB × 20)
        dh = _rotating_handler(
            "debug.log", log_dir, settings.LOG_MAX_BYTES,
            settings.LOG_BACKUP_COUNT, logging.DEBUG,
        )
        dh.addFilter(LevelFilter(logging.DEBUG))
        root.addHandler(dh)

        # info   — daily rotation (10 days)
        root.addHandler(_timed_handler(
            "info.log", log_dir, settings.LOG_BACKUP_DAYS, logging.INFO,
        ))

        # error  — daily rotation (10 days)
        root.addHandler(_timed_handler(
            "error.log", log_dir, settings.LOG_BACKUP_DAYS, logging.ERROR,
        ))

    # ── Uvicorn: inherit root config ──
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _reparent(name)

    # ── SQLAlchemy: mysql.log (size-based, independent level) ──
    _configure_sqlalchemy(settings, log_dir)

    # ── Quiet noisy libs ──
    _quiet("sqlalchemy.pool.QueuePool", logging.WARNING)
    _quiet("sqlalchemy.dialects", logging.WARNING)
    _quiet("httpx", logging.WARNING)
    _quiet("httpcore", logging.WARNING)


# ── Handlers ──────────────────────────────────────────────────────

def _console_handler(settings) -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(_to_level(settings.LOG_LEVEL))
    h.setFormatter(ColoredFormatter())
    return h


def _timed_handler(filename: str, log_dir: str, backup_days: int,
                   level: int) -> logging.Handler:
    """TimedRotatingFileHandler — rotate at midnight, keep N days."""
    h = TimedRotatingFileHandler(
        os.path.join(log_dir, filename),
        when="midnight",
        interval=1,
        backupCount=backup_days,
        encoding="utf-8",
    )
    h.setLevel(level)
    h.setFormatter(logging.Formatter(fmt=_FILE_FMT, datefmt=_DATE_FMT))
    return h


def _rotating_handler(filename: str, log_dir: str, max_bytes: int,
                      backup_count: int, level: int) -> logging.Handler:
    """RotatingFileHandler — roll over by size, keep N files."""
    h = RotatingFileHandler(
        os.path.join(log_dir, filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    h.setLevel(level)
    h.setFormatter(logging.Formatter(fmt=_FILE_FMT, datefmt=_DATE_FMT))
    return h


# ── SQLAlchemy ────────────────────────────────────────────────────

def _configure_sqlalchemy(settings, log_dir: str) -> None:
    sa = logging.getLogger("sqlalchemy.engine")
    _clear_handlers(sa)
    sa.setLevel(_to_level(settings.LOG_MYSQL_LEVEL))
    sa.propagate = False  # MySQL logs stay in mysql.log only

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        h = _rotating_handler(
            "mysql.log", log_dir, settings.LOG_MAX_BYTES,
            settings.LOG_BACKUP_COUNT, _to_level(settings.LOG_MYSQL_LEVEL),
        )
        sa.addHandler(h)

    # Console mirror for MySQL when level is permissive enough
    if _to_level(settings.LOG_MYSQL_LEVEL) <= logging.WARNING:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(_to_level(settings.LOG_MYSQL_LEVEL))
        ch.setFormatter(ColoredFormatter())
        sa.addHandler(ch)


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


# ── Helpers ───────────────────────────────────────────────────────

def _to_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.DEBUG)


def _clear_handlers(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        logger.removeHandler(h)


def _reparent(logger_name: str) -> None:
    lg = logging.getLogger(logger_name)
    _clear_handlers(lg)
    lg.propagate = True


def _quiet(logger_name: str, level: int) -> None:
    logging.getLogger(logger_name).setLevel(level)
