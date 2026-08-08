"""Gestione credenziali tramite Windows Credential Manager (keyring).

La password NON viene mai salvata in chiaro in file, JSON, .env o SQLite.
Nel database può essere memorizzato al massimo lo username.

VIS•ION usa service name dedicati; in lettura può fare fallback al legacy
VIS eniSpace Utility per non richiedere re-inserimento password in fase di clone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import keyring
from keyring.errors import KeyringError

from utils.logger import get_logger
from utils.paths import (
    KEYRING_MAIL_SERVICE,
    KEYRING_MAIL_SERVICE_LEGACY,
    KEYRING_SERVICE,
    KEYRING_SERVICE_LEGACY,
)

logger = get_logger("credentials")


@dataclass
class Credentials:
    username: str
    password: str

    @property
    def is_complete(self) -> bool:
        return bool(self.username.strip()) and bool(self.password)


class CredentialService:
    """Wrapper sicuro su keyring / Windows Credential Manager."""

    def __init__(
        self,
        service_name: str = KEYRING_SERVICE,
        *,
        legacy_service_name: Optional[str] = None,
    ) -> None:
        self.service_name = service_name
        # Fallback automatico per i due service name standard
        if legacy_service_name is not None:
            self.legacy_service_name = legacy_service_name
        elif service_name == KEYRING_SERVICE:
            self.legacy_service_name = KEYRING_SERVICE_LEGACY
        elif service_name == KEYRING_MAIL_SERVICE:
            self.legacy_service_name = KEYRING_MAIL_SERVICE_LEGACY
        else:
            self.legacy_service_name = None

    def save(self, username: str, password: str) -> None:
        username = username.strip()
        if not username:
            raise ValueError("Username obbligatorio.")
        if not password:
            raise ValueError("Password obbligatoria.")
        try:
            previous = self.get_username(prefer_legacy=False)
            if previous and previous != username:
                try:
                    keyring.delete_password(self.service_name, previous)
                except KeyringError:
                    pass
            keyring.set_password(self.service_name, username, password)
            keyring.set_password(self.service_name, "__current_username__", username)
            logger.info("Credenziali salvate in Windows Credential Manager (%s).", self.service_name)
        except KeyringError as exc:
            logger.error("Errore salvataggio credenziali: %s", exc)
            raise RuntimeError(
                "Impossibile salvare le credenziali nel Credential Manager di Windows."
            ) from exc

    def get_username(self, *, prefer_legacy: bool = True) -> Optional[str]:
        try:
            user = keyring.get_password(self.service_name, "__current_username__")
            if user:
                return user
        except KeyringError as exc:
            logger.warning("Impossibile leggere username da keyring: %s", exc)
        if prefer_legacy and self.legacy_service_name:
            try:
                return keyring.get_password(
                    self.legacy_service_name, "__current_username__"
                )
            except KeyringError:
                return None
        return None

    def get_password(
        self, username: Optional[str] = None, *, prefer_legacy: bool = True
    ) -> Optional[str]:
        user = username or self.get_username(prefer_legacy=prefer_legacy)
        if not user:
            return None
        try:
            pwd = keyring.get_password(self.service_name, user)
            if pwd:
                return pwd
        except KeyringError as exc:
            logger.warning("Impossibile leggere password da keyring: %s", exc)
        if prefer_legacy and self.legacy_service_name:
            try:
                return keyring.get_password(self.legacy_service_name, user)
            except KeyringError:
                return None
        return None

    def load(self) -> Optional[Credentials]:
        username = self.get_username()
        if not username:
            return None
        password = self.get_password(username)
        if password is None:
            return Credentials(username=username, password="")
        return Credentials(username=username, password=password)

    def has_credentials(self) -> bool:
        creds = self.load()
        return bool(creds and creds.is_complete)

    def delete(self) -> None:
        username = self.get_username(prefer_legacy=False)
        try:
            if username:
                keyring.delete_password(self.service_name, username)
            keyring.delete_password(self.service_name, "__current_username__")
            logger.info("Credenziali rimosse dal Credential Manager (%s).", self.service_name)
        except KeyringError as exc:
            logger.warning("Rimozione credenziali: %s", exc)
