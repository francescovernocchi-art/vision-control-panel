"""Gestione credenziali tramite Windows Credential Manager (keyring).

La password NON viene mai salvata in chiaro in file, JSON, .env o SQLite.
Nel database può essere memorizzato al massimo lo username.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import keyring
from keyring.errors import KeyringError

from utils.logger import get_logger
from utils.paths import KEYRING_SERVICE

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

    def __init__(self, service_name: str = KEYRING_SERVICE) -> None:
        self.service_name = service_name

    def save(self, username: str, password: str) -> None:
        username = username.strip()
        if not username:
            raise ValueError("Username obbligatorio.")
        if not password:
            raise ValueError("Password obbligatoria.")
        try:
            # Rimuove eventuali account precedenti con username diverso
            previous = self.get_username()
            if previous and previous != username:
                try:
                    keyring.delete_password(self.service_name, previous)
                except KeyringError:
                    pass
            keyring.set_password(self.service_name, username, password)
            # Memorizza anche il nome utente "corrente" con chiave dedicata
            keyring.set_password(self.service_name, "__current_username__", username)
            logger.info("Credenziali salvate in Windows Credential Manager.")
        except KeyringError as exc:
            logger.error("Errore salvataggio credenziali: %s", exc)
            raise RuntimeError(
                "Impossibile salvare le credenziali nel Credential Manager di Windows."
            ) from exc

    def get_username(self) -> Optional[str]:
        try:
            return keyring.get_password(self.service_name, "__current_username__")
        except KeyringError as exc:
            logger.warning("Impossibile leggere username da keyring: %s", exc)
            return None

    def get_password(self, username: Optional[str] = None) -> Optional[str]:
        user = username or self.get_username()
        if not user:
            return None
        try:
            return keyring.get_password(self.service_name, user)
        except KeyringError as exc:
            logger.warning("Impossibile leggere password da keyring: %s", exc)
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
        username = self.get_username()
        try:
            if username:
                keyring.delete_password(self.service_name, username)
            keyring.delete_password(self.service_name, "__current_username__")
            logger.info("Credenziali rimosse dal Credential Manager.")
        except KeyringError as exc:
            logger.warning("Rimozione credenziali: %s", exc)
