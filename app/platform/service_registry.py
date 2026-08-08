"""ServiceRegistry — catalogo servizi esistenti + descriptor (soft DI)."""

from __future__ import annotations

import threading
from typing import Any, Optional

from app.platform.descriptors import ServiceDescriptor
from utils.logger import get_logger

logger = get_logger("platform.services")


class ServiceRegistry:
    """Registra riferimenti a servizi già creati — non ne istanzia di nuovi."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, Any] = {}
        self._descriptors: dict[str, ServiceDescriptor] = {}

    def register(
        self,
        service_id: str,
        service: Any,
        *,
        descriptor: Optional[ServiceDescriptor] = None,
    ) -> None:
        if not service_id:
            raise ValueError("service_id obbligatorio")
        with self._lock:
            existing = self._services.get(service_id)
            if existing is not None and existing is not service:
                logger.warning(
                    "Service %s già registrato — mantengo istanza esistente (no duplicate)",
                    service_id,
                )
                return
            self._services[service_id] = service
            desc = descriptor or ServiceDescriptor(
                service_id=service_id,
                display_name=service_id,
                lifetime="external",
                available=True,
            )
            desc.available = True
            self._descriptors[service_id] = desc
        logger.info("Service registered id=%s type=%s", service_id, type(service).__name__)

    def register_unavailable(
        self,
        service_id: str,
        *,
        descriptor: Optional[ServiceDescriptor] = None,
        reason: str = "unavailable",
    ) -> None:
        """Descriptor only — nessuna implementazione inventata."""
        desc = descriptor or ServiceDescriptor(
            service_id=service_id,
            display_name=service_id,
            lifetime="external",
            available=False,
            metadata={"reason": reason},
        )
        desc.available = False
        desc.metadata = dict(desc.metadata or {})
        desc.metadata["reason"] = reason
        with self._lock:
            self._descriptors[service_id] = desc
            # non toccare istanza se già presente
        logger.warning("Service unavailable id=%s reason=%s", service_id, reason)

    def get(self, service_id: str) -> Optional[Any]:
        with self._lock:
            return self._services.get(service_id)

    def get_descriptor(self, service_id: str) -> Optional[ServiceDescriptor]:
        with self._lock:
            return self._descriptors.get(service_id)

    def list_descriptors(self) -> list[ServiceDescriptor]:
        with self._lock:
            return list(self._descriptors.values())

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

    def list_all_ids(self) -> list[str]:
        with self._lock:
            return sorted(set(self._services) | set(self._descriptors))
