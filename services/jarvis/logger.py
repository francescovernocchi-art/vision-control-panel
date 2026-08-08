"""Console / log eventi JARVIS (in-memory + callback UI)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Deque, Optional

from services.jarvis.states import LogLevel
from utils.logger import get_logger

logger = get_logger("jarvis")

ConsoleCallback = Callable[["JarvisLogEntry"], None]


@dataclass
class JarvisLogEntry:
    timestamp: str
    level: str
    message: str
    state: str = ""

    def format_line(self) -> str:
        return f"{self.timestamp} — [{self.level}] {self.message}"


class JarvisLogger:
    """Log visivo JARVIS: non cancella lo storico persistente (solo buffer UI)."""

    def __init__(self, *, maxlen: int = 500) -> None:
        self._entries: Deque[JarvisLogEntry] = deque(maxlen=maxlen)
        self._listeners: list[ConsoleCallback] = []

    def add_listener(self, cb: ConsoleCallback) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: ConsoleCallback) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def clear_visual(self) -> None:
        """Svuota solo il buffer console UI."""
        self._entries.clear()

    def entries(self) -> list[JarvisLogEntry]:
        return list(self._entries)

    def log(
        self,
        message: str,
        *,
        level: str = LogLevel.INFO,
        state: str = "",
    ) -> JarvisLogEntry:
        ts = datetime.now().strftime("%H:%M:%S")
        entry = JarvisLogEntry(
            timestamp=ts, level=str(level), message=message, state=state or ""
        )
        self._entries.append(entry)
        # File log tecnico
        low = str(level).upper()
        line = f"JARVIS [{low}] {message}"
        if low == LogLevel.ERROR:
            logger.error("%s", line)
        elif low == LogLevel.WARNING:
            logger.warning("%s", line)
        else:
            logger.info("%s", line)
        for cb in list(self._listeners):
            try:
                cb(entry)
            except Exception:
                pass
        return entry
