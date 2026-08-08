"""Download file locali con versioning e verifica hash SHA-256."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.logger import get_logger
from utils.paths import contract_download_dir, mda_day_download_dir

logger = get_logger("download")


@dataclass
class DownloadResult:
    success: bool
    path: Optional[Path] = None
    sha256: Optional[str] = None
    size: Optional[int] = None
    skipped: bool = False
    message: str = ""
    is_revision: bool = False


class DownloadService:
    """Gestisce salvataggio file, anti-sovrascrittura e versioning."""

    def __init__(self, base_folder: Path | str) -> None:
        self.base_folder = Path(base_folder)
        self.base_folder.mkdir(parents=True, exist_ok=True)

    def set_base_folder(self, folder: Path | str) -> None:
        self.base_folder = Path(folder)
        self.base_folder.mkdir(parents=True, exist_ok=True)

    def contract_folder(self, contract_number: str) -> Path:
        return contract_download_dir(self.base_folder, contract_number)

    def mda_day_folder(
        self, acquisition_module: str, day: str | None = None
    ) -> Path:
        """Cartella MdA_{modulo}_{YYYY-MM-DD} sotto la root download."""
        return mda_day_download_dir(self.base_folder, acquisition_module, day)

    def resolve_folder(
        self,
        *,
        contract_number: str = "",
        acquisition_module: str = "",
        day: str | None = None,
    ) -> Path:
        """Preferisce cartella MdA_giorno se il modulo è noto, altrimenti ordine."""
        module = (acquisition_module or "").strip()
        if module:
            return self.mda_day_folder(module, day)
        return self.contract_folder(contract_number)

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def format_size(size: Optional[int]) -> str:
        if size is None:
            return "—"
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}".replace(".", ",")
            value /= 1024
        return f"{size} B"

    def find_identical(
        self,
        contract_number: str,
        *,
        filename: Optional[str] = None,
        size: Optional[int] = None,
        sha256: Optional[str] = None,
        acquisition_module: str = "",
        day: str | None = None,
    ) -> Optional[Path]:
        """Cerca un file già presente uguale (hash, o nome+dimensione)."""
        folder = self.resolve_folder(
            contract_number=contract_number,
            acquisition_module=acquisition_module,
            day=day,
        )
        if not folder.is_dir():
            return None

        if sha256:
            for path in folder.iterdir():
                if path.is_file():
                    try:
                        if self.sha256_file(path) == sha256:
                            return path
                    except OSError:
                        continue

        if filename and size is not None:
            candidate = folder / filename
            if candidate.is_file() and candidate.stat().st_size == size:
                return candidate

        if filename:
            candidate = folder / filename
            if candidate.is_file():
                return candidate

        return None

    def next_version_path(self, folder: Path, filename: str) -> Path:
        """
        Se il file esiste, genera Specifica Tecnica_rev2.pdf, _rev3, ...
        Non elimina mai le versioni precedenti.
        """
        target = folder / filename
        if not target.exists():
            return target

        stem = Path(filename).stem
        suffix = Path(filename).suffix
        # Se già _revN, incrementa
        match = re.match(r"^(.*)_rev(\d+)$", stem, flags=re.IGNORECASE)
        if match:
            base = match.group(1)
            start = int(match.group(2)) + 1
        else:
            base = stem
            start = 2

        rev = start
        while True:
            candidate = folder / f"{base}_rev{rev}{suffix}"
            if not candidate.exists():
                return candidate
            rev += 1

    def prepare_destination(
        self,
        contract_number: str,
        filename: str,
        *,
        expected_sha256: Optional[str] = None,
        expected_size: Optional[int] = None,
        acquisition_module: str = "",
        day: str | None = None,
    ) -> DownloadResult:
        """
        Determina il percorso di destinazione senza sovrascrivere.
        Se il file esistente è identico → skip.
        Se diverso → nuova revisione.
        """
        folder = self.resolve_folder(
            contract_number=contract_number,
            acquisition_module=acquisition_module,
            day=day,
        )
        safe_name = self._sanitize_filename(filename)
        existing = folder / safe_name

        if existing.is_file():
            try:
                existing_hash = self.sha256_file(existing)
                same_hash = expected_sha256 and existing_hash == expected_sha256
                same_size = (
                    expected_size is not None
                    and existing.stat().st_size == expected_size
                    and not expected_sha256
                )
                if same_hash or same_size:
                    return DownloadResult(
                        success=True,
                        path=existing,
                        sha256=existing_hash,
                        size=existing.stat().st_size,
                        skipped=True,
                        message="Documento già presente (identico).",
                    )
            except OSError as exc:
                logger.warning("Lettura file esistente fallita: %s", exc)

            dest = self.next_version_path(folder, safe_name)
            return DownloadResult(
                success=True,
                path=dest,
                skipped=False,
                is_revision=True,
                message=f"Nuova versione → {dest.name}",
            )

        return DownloadResult(
            success=True,
            path=existing,
            skipped=False,
            message="Pronto al download.",
        )

    def finalize_from_temp(
        self,
        temp_path: Path,
        destination: Path,
    ) -> DownloadResult:
        """Sposta un file temporaneo nella destinazione definitiva e calcola hash."""
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                # Sicurezza aggiuntiva: non sovrascrivere
                destination = self.next_version_path(
                    destination.parent, destination.name
                )
            shutil.move(str(temp_path), str(destination))
            digest = self.sha256_file(destination)
            size = destination.stat().st_size
            logger.info("File salvato: %s (%s)", destination, self.format_size(size))
            return DownloadResult(
                success=True,
                path=destination,
                sha256=digest,
                size=size,
                message="Download completato.",
            )
        except PermissionError as exc:
            logger.error("Permessi insufficienti: %s", exc)
            return DownloadResult(
                success=False,
                message="Permessi cartella insufficienti o file bloccato.",
            )
        except OSError as exc:
            logger.error("Errore salvataggio file: %s", exc)
            return DownloadResult(
                success=False,
                message=f"Download fallito: {exc}",
            )

    def open_folder(self, contract_number: Optional[str] = None) -> Path:
        folder = (
            self.contract_folder(contract_number)
            if contract_number
            else self.base_folder
        )
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except OSError as exc:
            logger.error("Impossibile aprire cartella: %s", exc)
            raise RuntimeError(
                "Impossibile aprire la cartella download. Verificare i permessi."
            ) from exc
        return folder

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        name = name.strip().replace("\x00", "")
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        name = name.rstrip(". ")
        return name or "documento"
