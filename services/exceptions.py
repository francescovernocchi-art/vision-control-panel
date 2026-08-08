"""Eccezioni tipizzate per messaggi utente in italiano."""

from __future__ import annotations


class EniSpaceError(Exception):
    """Errore base eniSpace — message già in italiano per la GUI."""

    def __init__(self, message: str, *, technical: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


class NetworkError(EniSpaceError):
    pass


class PortalUnreachableError(EniSpaceError):
    pass


class SessionExpiredError(EniSpaceError):
    pass


class ContractNotFoundError(EniSpaceError):
    pass


class TimeoutErrorEni(EniSpaceError):
    pass


class BrowserError(EniSpaceError):
    pass


class DownloadFailedError(EniSpaceError):
    pass


class CredentialsMissingError(EniSpaceError):
    pass


class LoginFailedError(EniSpaceError):
    pass


class PageStructureChangedError(EniSpaceError):
    pass


class SelectorsNotConfiguredError(EniSpaceError):
    """Sollevata quando i selettori del portale non sono ancora mappati."""

    def __init__(
        self,
        step: str,
        *,
        message: str | None = None,
    ) -> None:
        msg = message or (
            f"Il passaggio «{step}» non è ancora collegato al portale reale.\n"
            "Utilizzare «Registra navigazione» nelle Impostazioni per mappare "
            "i selettori, oppure accompagnare lo sviluppatore nella navigazione."
        )
        super().__init__(msg, technical=f"SELECTOR_PENDING:{step}")
        self.step = step
