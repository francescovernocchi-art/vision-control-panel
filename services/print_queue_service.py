"""Coda di stampa locale: elenco PDF e stampa a cascata su Windows."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from database.db import Database
from database.models import PrintQueueItem
from utils.logger import get_logger

logger = get_logger("print_queue")


@dataclass
class PrintJobResult:
    item: PrintQueueItem
    success: bool
    message: str = ""


class PrintQueueService:
    """Gestisce coda PDF e stampa silenziosa sulla stampante predefinita."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        path: Path | str,
        *,
        order_number: str = "",
        acquisition_module: str = "",
        eml_name: str = "",
    ) -> PrintQueueItem:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"File non trovato: {p}")
        item = self.db.add_print_queue_item(
            local_path=str(p.resolve()),
            order_number=order_number,
            acquisition_module=acquisition_module,
            eml_name=eml_name,
            filename=p.name,
        )
        logger.info(
            "In coda stampa: %s (ordine=%s modulo=%s)",
            p.name,
            order_number or "—",
            acquisition_module or "—",
        )
        return item

    def list(self, *, pending_only: bool = False) -> list[PrintQueueItem]:
        return self.db.list_print_queue(pending_only=pending_only)

    def remove(self, item_id: int) -> None:
        self.db.remove_print_queue_item(item_id)

    def clear(self, *, pending_only: bool = False) -> int:
        n = self.db.clear_print_queue(pending_only=pending_only)
        logger.info("Coda stampa svuotata (%s elementi)", n)
        return n

    def count_pending(self) -> int:
        return len(self.list(pending_only=True))

    def print_file(self, path: Path | str) -> None:
        """Invia un PDF alla stampante predefinita Windows."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"File non trovato: {p}")
        if os.name != "nt":
            raise RuntimeError("La stampa a cascata è supportata solo su Windows.")
        # Verb «print» → stampante di sistema predefinita
        os.startfile(str(p.resolve()), "print")  # type: ignore[attr-defined]
        logger.info("Inviato alla stampante: %s", p.name)

    def print_all(
        self,
        *,
        pending_only: bool = True,
        delay_seconds: float = 2.5,
    ) -> list[PrintJobResult]:
        """
        Stampa a cascata tutti gli elementi in coda.
        Gli errori su un file non interrompono il resto.
        """
        items = self.list(pending_only=pending_only)
        results: list[PrintJobResult] = []
        for i, item in enumerate(items):
            path = Path(item.local_path)
            try:
                if not path.is_file():
                    raise FileNotFoundError(f"File mancante: {path}")
                self.print_file(path)
                if item.id is not None:
                    self.db.mark_print_queue_printed(item.id, status="printed")
                results.append(
                    PrintJobResult(item=item, success=True, message="Inviato in stampa")
                )
            except Exception as exc:
                logger.exception("Stampa fallita per %s: %s", path, exc)
                if item.id is not None:
                    self.db.mark_print_queue_printed(item.id, status="error")
                results.append(
                    PrintJobResult(item=item, success=False, message=str(exc))
                )
            if i < len(items) - 1:
                time.sleep(delay_seconds)
        ok = sum(1 for r in results if r.success)
        logger.info("Stampa coda completata: %s/%s ok", ok, len(results))
        return results
