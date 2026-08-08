"""Logging strutturato: file giornaliero + coda thread-safe per la GUI.

IMPORTANTE (freeze Windows «App non risponde»):
Mai chiamare Tk/CustomTkinter da un logging.Handler.emit().
emit() tiene il lock del Handler; tk.call/after da un worker thread
su Windows è sincrono e aspetta il mainloop → deadlock se il main
thread sta a sua volta facendo logger.info (es. append_activity).
La GUI drena la coda con after() sul thread UI.
"""

from __future__ import annotations

import logging
import queue
import sys
from datetime import date
from logging.handlers import MemoryHandler
from typing import Callable

from utils.paths import logs_dir

_configured = False
_gui_callbacks: list[Callable[[str], None]] = []
# Coda lock-free verso la GUI (nessuna chiamata Tk qui)
_gui_log_queue: queue.SimpleQueue[str] = queue.SimpleQueue()


class GuiLogHandler(logging.Handler):
    """Inoltra INFO+ alla coda GUI — mai tocchi Tk da emit()."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            try:
                _gui_log_queue.put_nowait(msg)
            except Exception:
                pass
            # Callback opzionali: devono essere non-bloccanti (no Tk sync)
            for callback in list(_gui_callbacks):
                try:
                    callback(msg)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


def drain_gui_log_queue(max_items: int = 200) -> list[str]:
    """Svuota la coda log per il pump UI (chiamare solo dal thread Tk)."""
    out: list[str] = []
    for _ in range(max(1, max_items)):
        try:
            out.append(_gui_log_queue.get_nowait())
        except queue.Empty:
            break
    return out


class DebugFilter(logging.Filter):
    """Permette record DEBUG solo se la modalità debug è attiva."""

    def __init__(self) -> None:
        super().__init__()
        self.debug_enabled = False

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.INFO:
            return True
        return self.debug_enabled


_debug_filter = DebugFilter()


def set_debug_mode(enabled: bool) -> None:
    _debug_filter.debug_enabled = enabled
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if enabled else logging.INFO)


def register_gui_callback(callback: Callable[[str], None]) -> None:
    if callback not in _gui_callbacks:
        _gui_callbacks.append(callback)


def unregister_gui_callback(callback: Callable[[str], None]) -> None:
    if callback in _gui_callbacks:
        _gui_callbacks.remove(callback)


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configura logging su file giornaliero e console."""
    global _configured
    logger = logging.getLogger("enispace")
    if _configured:
        set_debug_mode(debug)
        return logger

    logs_dir().mkdir(parents=True, exist_ok=True)
    log_file = logs_dir() / f"enispace-{date.today().isoformat()}.log"

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    gui_formatter = logging.Formatter(fmt="%(asctime)s %(message)s", datefmt="%H:%M")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_debug_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    gui_handler = GuiLogHandler()
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(gui_formatter)

    # Buffer iniziale per non perdere messaggi prima della GUI
    memory = MemoryHandler(capacity=200, flushLevel=logging.ERROR, target=gui_handler)
    memory.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(gui_handler)
    logger.addHandler(memory)

    set_debug_mode(debug)
    _configured = True
    logger.info("Logging inizializzato -> %s", log_file)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"enispace.{name}")
    return logging.getLogger("enispace")
