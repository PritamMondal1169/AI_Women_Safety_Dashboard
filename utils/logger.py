"""
utils/logger.py — Centralised Loguru logger for the Women Safety Product.

Usage (anywhere in the project):

    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Camera initialised on source {src}", src=0)

Features:
- Colourised console output with level filtering.
- Rotating file sink (size-based) with configurable retention.
- Separate ERROR-only sink for fast post-mortem triage.
- Thread-safe by default (loguru uses an internal lock).
- Call setup_logging() once in main.py; all other modules just call get_logger().
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# Internal flag to prevent double-initialisation
_initialised: bool = False


def setup_logging(
    log_dir: Path,
    level: str = "DEBUG",
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """
    Configure loguru sinks.  Call this ONCE from main.py before anything else.

    Args:
        log_dir:   Directory where log files are written (created if absent).
        level:     Minimum log level for console and main file sinks.
        rotation:  Loguru rotation trigger, e.g. "10 MB" or "1 day".
        retention: How long to keep old log files, e.g. "7 days".
    """
    global _initialised
    if _initialised:
        return

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove the default loguru handler (prints everything to stderr without format)
    logger.remove()

    # ── Console sink ──────────────────────────────────────────────────────────
    console_fmt = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )
    logger.add(
        sys.stderr,
        format=console_fmt,
        level=level,
        colorize=True,
        backtrace=True,    # full traceback on exceptions
        diagnose=True,     # variable values in tracebacks (disable in prod if privacy needed)
        enqueue=False,     # synchronous; use True for async / multiprocess apps
    )

    # ── Main rotating file sink ───────────────────────────────────────────────
    main_log = log_dir / "safety_{time:YYYY-MM-DD}.log"
    file_fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} — {message}"
    )
    logger.add(
        str(main_log),
        format=file_fmt,
        level=level,
        rotation=rotation,
        retention=retention,
        compression="gz",   # compress rotated logs to save disk space
        backtrace=True,
        diagnose=False,     # keep diagnose off in files (verbose / sensitive)
        enqueue=True,       # non-blocking file writes
        encoding="utf-8",
    )

    # ── Error-only sink for quick triage ─────────────────────────────────────
    error_log = log_dir / "errors_{time:YYYY-MM-DD}.log"
    logger.add(
        str(error_log),
        format=file_fmt,
        level="ERROR",
        rotation=rotation,
        retention=retention,
        compression="gz",
        backtrace=True,
        diagnose=False,
        enqueue=True,
        encoding="utf-8",
    )

    _initialised = True
    logger.info(
        "Logging initialised | level={lvl} | dir={d} | rotation={r} | retention={ret}",
        lvl=level,
        d=str(log_dir),
        r=rotation,
        ret=retention,
    )


def get_logger(name: Optional[str] = None):
    """
    Return a loguru logger bound to the given name.

    Because loguru is a singleton, this simply returns the module-level
    `logger` with an optional contextual binding for structured output.

    Args:
        name: Usually __name__ of the calling module.

    Returns:
        A loguru Logger instance.
    """
    if name:
        return logger.bind(name=name)
    return logger


# ---------------------------------------------------------------------------
# Convenience: allow `from utils.logger import log` as a module-level shortcut
# ---------------------------------------------------------------------------
log = logger
