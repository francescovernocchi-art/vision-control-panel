"""Worker thread per operazioni lunghe senza bloccare la GUI."""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Optional

from utils.logger import get_logger

logger = get_logger("worker")


class BackgroundWorker:
    """Esegue una callable in un thread daemon e notifica successo/errore."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run(
        self,
        target: Callable[[], Any],
        *,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        name: str = "eni-worker",
    ) -> bool:
        with self._lock:
            if self.is_running:
                logger.warning("Operazione già in corso — richiesta ignorata.")
                return False

            def _wrap() -> None:
                try:
                    result = target()
                    if on_success:
                        on_success(result)
                except Exception as exc:
                    logger.error("Worker error: %s", exc)
                    logger.debug(traceback.format_exc())
                    if on_error:
                        on_error(exc)

            self._thread = threading.Thread(target=_wrap, name=name, daemon=True)
            self._thread.start()
            return True
