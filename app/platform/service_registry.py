"""ServiceRegistry — catalogo servizi esistenti (nessuna istanza duplicata)."""

from __future__ import annotations

import threading
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger("platform.services")


class ServiceRegistry:
    """Registra riferimenti a servizi già creati dal Core/app — non ne istanzia di nuovi."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, Any] = {}

    def register(self, service_id: str, service: Any) -> None:
        if not service_id:
            raise ValueError("service_id obbligatorio")
        with self._lock:
            # Non sovrascrivere silenziosamente con un'altra istanza
            existing = self._services.get(service_id)
            if existing is not None and existing is not service:
                logger.warning(
                    "Service %s già registrato — mantengo istanza esistente (no duplicate)",
                    service_id,
                )
                return
            self._services[service_id] = service
        logger.info("Service registered id=%s type=%s", service_id, type(service).__name__)

    def get(self, service_id: str) -> Optional[Any]:
        with self._lock:
            return self._services.get(service_id)

    def require(self, service_id: str) -> Any:
        svc = self.get(service_id)
        if svc is None:
            raise KeyError(f"Service non registrato: {service_id}")
        return svc

    def has(self, service_id: str) -> bool:
        return self.get(service_id) is not None

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._services.keys())
