"""Guard moduli — con Supervisor attivo: verifica online e attiva i login."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence

from utils.logger import get_logger

logger = get_logger("jarvis.module_guard")


@dataclass
class ModuleStatus:
    module_id: str
    label: str
    online: bool
    message: str = ""
    required: bool = True


class ModuleProvider(Protocol):
    module_id: str
    label: str
    required: bool

    def probe_online(self) -> bool:
        """Check leggero: sessione già attiva senza forzare login."""

    def ensure_online(self) -> bool:
        """Se offline, attiva login/connessione. True se online a fine operazione."""


class EniSpaceModuleProvider:
    """eniSpace: area privata autenticata (SSO se necessario)."""

    module_id = "enispace"
    label = "eniSpace"
    required = True

    def __init__(self, enispace_service: Any) -> None:
        self._svc = enispace_service

    def probe_online(self) -> bool:
        svc = self._svc
        if svc is None:
            return False
        try:
            if hasattr(svc, "_enispace_private_online"):
                return bool(svc._enispace_private_online())
            if hasattr(svc, "is_logged_in"):
                return bool(svc.is_logged_in())
        except Exception as exc:
            logger.debug("eniSpace probe: %s", exc)
        return False

    def ensure_online(self) -> bool:
        svc = self._svc
        if svc is None:
            return False
        try:
            if hasattr(svc, "ensure_enispace_online"):
                return bool(svc.ensure_enispace_online())
            if hasattr(svc, "login"):
                return bool(svc.login(allow_manual=True))
        except Exception as exc:
            logger.warning("eniSpace ensure/login: %s", exc)
            return False
        return self.probe_online()


class MailModuleProvider:
    """Mailbox IMAP: configurata + connessione OK."""

    module_id = "mail"
    label = "Mail IMAP"
    required = True

    def __init__(
        self,
        imap_config_factory: Callable[[], Any],
        *,
        test_connection: Optional[Callable[[Any], tuple[bool, str]]] = None,
    ) -> None:
        self._factory = imap_config_factory
        self._test_connection = test_connection

    def probe_online(self) -> bool:
        cfg = None
        try:
            cfg = self._factory()
        except Exception:
            return False
        if cfg is None:
            return False
        # Credenziali presenti = configurato; ensure farà il ping reale
        user = getattr(cfg, "username", None) or getattr(cfg, "user", None)
        host = getattr(cfg, "host", None) or getattr(cfg, "server", None)
        return bool(user and host)

    def ensure_online(self) -> bool:
        cfg = None
        try:
            cfg = self._factory()
        except Exception as exc:
            logger.debug("Mail config: %s", exc)
            return False
        if cfg is None:
            return False
        if self._test_connection is None:
            return self.probe_online()
        try:
            ok, msg = self._test_connection(cfg)
            if not ok:
                logger.warning("Mail IMAP offline: %s", msg)
            return bool(ok)
        except Exception as exc:
            logger.warning("Mail IMAP ensure: %s", exc)
            return False


class PrintModuleProvider:
    """Coda stampa: online se stampante configurata (non blocca il Supervisor)."""

    module_id = "print"
    label = "Stampa"
    required = False

    def __init__(self, printer_factory: Callable[[], str]) -> None:
        self._printer_factory = printer_factory

    def probe_online(self) -> bool:
        try:
            return bool((self._printer_factory() or "").strip())
        except Exception:
            return False

    def ensure_online(self) -> bool:
        # Nessun login stampante: solo configurazione
        return self.probe_online()


class ModuleOnlineGuard:
    """
    Con Supervisor attivo: per ogni modulo richiesto
    verifica online; se offline attiva login/ensure.
    """

    def __init__(self, providers: Sequence[ModuleProvider]) -> None:
        self.providers = list(providers)
        self._last: dict[str, ModuleStatus] = {}

    def last_statuses(self) -> list[ModuleStatus]:
        if self._last:
            return [self._last[p.module_id] for p in self.providers if p.module_id in self._last]
        return []

    def all_required_online(self) -> bool:
        statuses = self.last_statuses()
        if not statuses:
            return False
        return all(s.online for s in statuses if s.required)

    def check_and_ensure(
        self,
        *,
        ensure: bool = True,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> list[ModuleStatus]:
        results: list[ModuleStatus] = []
        for provider in self.providers:
            online = False
            message = ""
            try:
                online = bool(provider.probe_online())
                if online:
                    message = "già online"
                elif ensure:
                    logger.info(
                        "Modulo %s offline → attiva login/connessione",
                        provider.label,
                    )
                    if on_progress:
                        try:
                            on_progress(f"Attivazione modulo {provider.label}")
                        except Exception:
                            pass
                    online = bool(provider.ensure_online())
                    message = (
                        "login completato" if online else "login fallito o incompleto"
                    )
                else:
                    message = "offline"
            except Exception as exc:
                online = False
                message = str(exc)[:160]
                logger.warning("Modulo %s: %s", provider.label, exc)

            status = ModuleStatus(
                module_id=provider.module_id,
                label=provider.label,
                online=online,
                message=message,
                required=bool(getattr(provider, "required", True)),
            )
            self._last[provider.module_id] = status
            results.append(status)
            logger.info(
                "Modulo %s: %s — %s",
                status.label,
                "ONLINE" if status.online else "OFFLINE",
                status.message,
            )
        return results
