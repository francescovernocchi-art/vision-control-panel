"""Connector eniSpace — punta ai servizi legacy già funzionanti."""

from __future__ import annotations

from typing import Any, Optional


class EniSpaceConnector:
    """Facade sottile sui servizi esistenti (Browser/EniSpace/Batch)."""

    def __init__(
        self,
        *,
        enispace_service: Any = None,
        batch_service: Any = None,
        browser_service: Any = None,
    ) -> None:
        self.enispace = enispace_service
        self.batch = batch_service
        self.browser = browser_service

    def is_ready(self) -> bool:
        return self.enispace is not None

    def session_active(self) -> bool:
        try:
            if self.enispace is None:
                return False
            if hasattr(self.enispace, "_enispace_private_online"):
                return bool(self.enispace._enispace_private_online())
            if hasattr(self.enispace, "is_logged_in"):
                return bool(self.enispace.is_logged_in())
        except Exception:
            return False
        return False

    def ensure_online(self) -> bool:
        """Attiva login se la sessione privata non è online."""
        try:
            if self.enispace is None:
                return False
            if hasattr(self.enispace, "ensure_enispace_online"):
                return bool(self.enispace.ensure_enispace_online())
            if hasattr(self.enispace, "login"):
                return bool(self.enispace.login(allow_manual=True))
        except Exception:
            return False
        return self.session_active()
