"""Logging dual-level: GLOBAL + MODULE."""

from __future__ import annotations

from datetime import date
from logging import FileHandler, Formatter, Logger

from utils.logger import get_logger
from utils.paths import logs_dir, module_logs_dir


def global_logger() -> Logger:
    return get_logger("vision.global")


def module_logger(module_id: str) -> Logger:
    log = get_logger(f"modules.{module_id}")
    marker = f"_module_file_{module_id}"
    if getattr(log, marker, False):
        return log
    path = module_logs_dir(module_id) / f"{module_id}-{date.today().isoformat()}.log"
    handler = FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    log.addHandler(handler)
    setattr(log, marker, True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    return log
