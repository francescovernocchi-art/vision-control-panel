"""Mail handler eniSpace — delega a MailWatcher / parser legacy."""

from __future__ import annotations

from typing import Any, Optional


class EniSpaceMailHandler:
    def __init__(self, watcher: Any = None) -> None:
        self.watcher = watcher

    def bind(self, watcher: Any) -> None:
        self.watcher = watcher
