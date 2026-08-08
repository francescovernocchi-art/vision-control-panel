"""Logging dedicato Remote Agent — niente secret."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.remote.security import redact_secrets
from utils.paths import logs_dir

_configured = False


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_secrets(str(record.msg))
            if record.args:
                record.args = tuple(
                    redact_secrets(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        except Exception:
            pass
        return True


def get_remote_logger() -> logging.Logger:
    global _configured
    logger = logging.getLogger("vision.remote")
    if _configured:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        logs_dir().mkdir(parents=True, exist_ok=True)
        path: Path = logs_dir() / "vision_remote.log"
        handler = RotatingFileHandler(
            path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
        )
        handler.addFilter(_RedactFilter())
        logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(
            logging.Formatter("%(asctime)s | REMOTE | %(message)s", "%H:%M:%S")
        )
        console.addFilter(_RedactFilter())
        logger.addHandler(console)
    _configured = True
    return logger


class remote_log:  # noqa: N801 — API stile modulo
    @staticmethod
    def info(msg: str, *args: object) -> None:
        get_remote_logger().info(msg, *args)

    @staticmethod
    def warning(msg: str, *args: object) -> None:
        get_remote_logger().warning(msg, *args)

    @staticmethod
    def error(msg: str, *args: object) -> None:
        get_remote_logger().error(msg, *args)

    @staticmethod
    def debug(msg: str, *args: object) -> None:
        get_remote_logger().debug(msg, *args)
