"""Finestra Impostazioni + wizard primo avvio."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from database.models import AppSettings
from ui.icons import apply_app_icon
from ui.theme import COLORS, font_family
from utils.paths import APP_NAME, default_download_dir

if TYPE_CHECKING:
    from database.db import Database
    from services.credential_service import CredentialService
    from services.enispace_service import EniSpaceService


class SettingsWindow(ctk.CTkToplevel):
    """Impostazioni: credenziali, download, browser, debug."""

    def __init__(
        self,
        master: ctk.CTk,
        db: "Database",
        credentials: "CredentialService",
        enispace: "EniSpaceService",
        *,
        on_saved: Optional[Callable[[], None]] = None,
        on_test_access: Optional[Callable[[], None]] = None,
        on_record_navigation: Optional[Callable[[], None]] = None,
        on_open_marketplace: Optional[Callable[[], None]] = None,
        on_open_ordini: Optional[Callable[[], None]] = None,
        on_open_document_flow: Optional[Callable[[], None]] = None,
        on_activity: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master)
        self.db = db
        self.credentials = credentials
        self.enispace = enispace
        self.on_saved = on_saved
        self.on_test_access = on_test_access
        self.on_record_navigation = on_record_navigation
        self.on_open_marketplace = on_open_marketplace
        self.on_open_ordini = on_open_ordini
        self.on_open_document_flow = on_open_document_flow
        self.on_activity = on_activity

        self.title(f"Impostazioni — {APP_NAME}")
        self.geometry("640x780")
        self.minsize(520, 680)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        self.grab_set()
        apply_app_icon(self)

        self._show_password = tk.BooleanVar(value=False)
        self._build()
        self._load()
        self.after(50, self.focus)

    def _build(self) -> None:
        pad = {"padx": 20, "pady": 6}
        root = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg"])
        root.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            root,
            text="Impostazioni",
            font=ctk.CTkFont(family=font_family(), size=22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", **pad)
        ctk.CTkLabel(
            root,
            text="GENERALE · MAIL · ENISPACE · STAMPA · JARVIS · LOG",
            font=ctk.CTkFont(family=font_family(), size=11),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        # --- Account ---
        self._section(root, "GENERALE — Account eniSpace")
        ctk.CTkLabel(root, text="Username eniSpace", text_color=COLORS["muted"]).pack(
            anchor="w", padx=20
        )
        self.username_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.username_entry.pack(fill="x", **pad)

        ctk.CTkLabel(root, text="Password", text_color=COLORS["muted"]).pack(
            anchor="w", padx=20
        )
        pass_row = ctk.CTkFrame(root, fg_color="transparent")
        pass_row.pack(fill="x", **pad)
        self.password_entry = ctk.CTkEntry(
            pass_row,
            height=36,
            show="•",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.password_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkCheckBox(
            pass_row,
            text="Mostra",
            variable=self._show_password,
            command=self._toggle_password,
            text_color=COLORS["muted"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            root,
            text="SALVA CREDENZIALI",
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._save_credentials,
        ).pack(fill="x", **pad)

        # --- Download ---
        self._section(root, "STAMPA / DOWNLOAD — Cartelle")
        ctk.CTkLabel(root, text="Cartella download", text_color=COLORS["muted"]).pack(
            anchor="w", padx=20
        )
        dl_row = ctk.CTkFrame(root, fg_color="transparent")
        dl_row.pack(fill="x", **pad)
        self.download_entry = ctk.CTkEntry(
            dl_row, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.download_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            dl_row,
            text="Sfoglia",
            width=90,
            height=36,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self._browse_folder,
        ).pack(side="left", padx=(8, 0))

        self.open_folder_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Apri cartella dopo download",
            variable=self.open_folder_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        # --- Casella IMAP (stile VIS Protocollo) ---
        self._section(root, "MAIL — Casella IMAP / SMTP (MdA_Eni)")
        ctk.CTkLabel(
            root,
            text="Host IMAP (es. pop.securemail.pro)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.imap_host_entry = ctk.CTkEntry(
            root,
            height=36,
            placeholder_text="pop.securemail.pro",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.imap_host_entry.pack(fill="x", **pad)

        row_imap = ctk.CTkFrame(root, fg_color="transparent")
        row_imap.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_imap, text="Porta", text_color=COLORS["muted"]).pack(
            side="left"
        )
        self.imap_port_entry = ctk.CTkEntry(
            row_imap,
            width=80,
            height=36,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.imap_port_entry.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_imap, text="Sicurezza", text_color=COLORS["muted"]).pack(
            side="left"
        )
        self.imap_security_var = tk.StringVar(value="SSL")
        self.imap_security_menu = ctk.CTkOptionMenu(
            row_imap,
            values=["SSL", "STARTTLS", "NONE"],
            variable=self.imap_security_var,
            width=120,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.imap_security_menu.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            root,
            text="Utente casella (email completa)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.imap_user_entry = ctk.CTkEntry(
            root,
            height=36,
            placeholder_text="nome@dominio.it",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.imap_user_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root,
            text="Password casella (Credential Manager)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.imap_pass_entry = ctk.CTkEntry(
            root,
            height=36,
            show="•",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.imap_pass_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root,
            text="Cartella IMAP (scegli dall'elenco o digita)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        row_folder = ctk.CTkFrame(root, fg_color="transparent")
        row_folder.pack(fill="x", padx=20, pady=4)
        self.imap_folder_var = tk.StringVar(value="INBOX.MdA_Eni")
        self.imap_folder_combo = ctk.CTkComboBox(
            row_folder,
            height=36,
            values=["INBOX.MdA_Eni", "INBOX", "MdA_Eni"],
            variable=self.imap_folder_var,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["panel"],
            dropdown_hover_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.imap_folder_combo.pack(side="left", fill="x", expand=True)
        # Combo editabile: consente digita/manuale
        try:
            self.imap_folder_combo._entry.configure(state="normal")  # noqa: SLF001
        except Exception:
            pass
        ctk.CTkButton(
            row_folder,
            text="CARICA CARTELLE",
            height=36,
            width=140,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._load_imap_folders,
        ).pack(side="left", padx=(8, 0))
        # Alias legacy per codice che leggeva l'entry
        self.imap_folder_entry = self.imap_folder_combo

        self.imap_unread_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            root,
            text="Solo mail non lette",
            variable=self.imap_unread_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        # Autosync IMAP
        autosync_row = ctk.CTkFrame(root, fg_color="transparent")
        autosync_row.pack(fill="x", padx=20, pady=(4, 4))
        self.autosync_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            autosync_row,
            text="Autosync casella",
            variable=self.autosync_enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="left")
        ctk.CTkLabel(
            autosync_row,
            text="ogni",
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(16, 6))
        self.autosync_interval_entry = ctk.CTkEntry(
            autosync_row,
            width=64,
            height=32,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.autosync_interval_entry.pack(side="left")
        self.autosync_interval_entry.insert(0, "15")
        ctk.CTkLabel(
            autosync_row,
            text="minuti",
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(
            root,
            text=(
                "Con autosync attivo l'app interroga IMAP in background "
                "(senza bloccare la UI), scarica i MdA e aggiorna il Registro."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            root,
            text="Host SMTP (opzionale, es. authsmtp.securemail.pro)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.smtp_host_entry = ctk.CTkEntry(
            root,
            height=36,
            placeholder_text="authsmtp.securemail.pro",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.smtp_host_entry.pack(fill="x", **pad)

        row_smtp = ctk.CTkFrame(root, fg_color="transparent")
        row_smtp.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_smtp, text="Porta SMTP", text_color=COLORS["muted"]).pack(
            side="left"
        )
        self.smtp_port_entry = ctk.CTkEntry(
            row_smtp,
            width=80,
            height=36,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.smtp_port_entry.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_smtp, text="Sicurezza", text_color=COLORS["muted"]).pack(
            side="left"
        )
        self.smtp_security_var = tk.StringVar(value="SSL")
        self.smtp_security_menu = ctk.CTkOptionMenu(
            row_smtp,
            values=["SSL", "STARTTLS", "NONE"],
            variable=self.smtp_security_var,
            width=120,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.smtp_security_menu.pack(side="left", padx=(8, 0))

        row_mail_btns = ctk.CTkFrame(root, fg_color="transparent")
        row_mail_btns.pack(fill="x", padx=20, pady=(4, 8))
        ctk.CTkButton(
            row_mail_btns,
            text="SALVA CRED. CASELLA",
            height=36,
            width=170,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._save_mail_credentials,
        ).pack(side="left")
        ctk.CTkButton(
            row_mail_btns,
            text="TEST IMAP",
            height=36,
            width=110,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._test_imap,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            row_mail_btns,
            text="TEST SMTP",
            height=36,
            width=110,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._test_smtp,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            root,
            text="IMAP e SMTP usano la stessa password casella. "
            "Dopo TEST IMAP OK (o CARICA CARTELLE) scegli la cartella dall'elenco.",
            text_color=COLORS["muted"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 6))

        # --- Browser ---
        self._section(root, "ENISPACE — Browser / Debug")
        self.hidden_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            root,
            text="Nascondi browser (solo UI app; Chrome headed off-screen)",
            variable=self.hidden_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)
        ctk.CTkLabel(
            root,
            text="Primo login / MFA: se Chrome non compare, disattiva «Nascondi browser», "
            "completa l'accesso, poi riattivalo. La sessione resta nel profilo.",
            text_color=COLORS["muted"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 6))

        self.debug_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Modalità DEBUG (URL, azioni, elementi, errori)",
            variable=self.debug_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        ctk.CTkLabel(
            root, text="Timeout browser (ms)", text_color=COLORS["muted"]
        ).pack(anchor="w", padx=20)
        self.timeout_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.timeout_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root,
            text="URL portale eniSpace",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.url_entry = ctk.CTkEntry(
            root,
            height=36,
            placeholder_text="https://enispace.eni.com/it_IT/home.page",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.url_entry.pack(fill="x", **pad)

        # --- Actions ---
        self._section(root, "LOG / TEST — Acquisizione portale")
        ctk.CTkButton(
            root,
            text="TEST ACCESSO ENISPACE",
            height=40,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._test_access,
        ).pack(fill="x", **pad)

        ctk.CTkButton(
            root,
            text="APRI CHROME (mappa portale)",
            height=40,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            border_width=1,
            border_color="#f59e0b",
            command=self._record_nav,
        ).pack(fill="x", **pad)

        ctk.CTkButton(
            root,
            text="APRI FLUSSO DOCUMENTI (Ordini→Market→Filtri)",
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._open_document_flow,
        ).pack(fill="x", **pad)

        ctk.CTkButton(
            root,
            text="APRI ORDINI E CONSUNTIVI (eniSpace)",
            height=40,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            border_width=1,
            border_color="#4ade80",
            command=self._open_ordini,
        ).pack(fill="x", **pad)

        ctk.CTkButton(
            root,
            text="APRI MARKETPLACE (ultimo URL imparato)",
            height=40,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            border_width=1,
            border_color="#38bdf8",
            command=self._open_marketplace,
        ).pack(fill="x", **pad)

        # --- JARVIS ---
        self._section(root, "JARVIS — Modalità supervisore")
        self.jarvis_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Abilita JARVIS (preferenza; avvio da tab JARVIS o autostart)",
            variable=self.jarvis_enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        self.jarvis_autostart_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Avvio automatico JARVIS all'apertura programma",
            variable=self.jarvis_autostart_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        self.jarvis_simulation_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Modalità simulazione (NO download finale / NO stampa)",
            variable=self.jarvis_simulation_var,
            text_color=COLORS["text"],
            fg_color="#f59e0b",
            hover_color="#d97706",
        ).pack(anchor="w", padx=20, pady=4)
        ctk.CTkLabel(
            root,
            text="Se attiva, in UI compare il banner «JARVIS — SIMULAZIONE».",
            text_color=COLORS["muted"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        ctk.CTkLabel(
            root,
            text="Intervallo controllo mail (secondi, default 60)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.jarvis_interval_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.jarvis_interval_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root, text="Numero massimo retry", text_color=COLORS["muted"]
        ).pack(anchor="w", padx=20)
        self.jarvis_retries_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.jarvis_retries_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root,
            text="Stampante (vuoto = predefinita Windows)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.jarvis_printer_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.jarvis_printer_entry.pack(fill="x", **pad)

        ctk.CTkLabel(
            root,
            text="Cartella download JARVIS (vuoto = cartella globale)",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20)
        self.jarvis_dl_entry = ctk.CTkEntry(
            root, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.jarvis_dl_entry.pack(fill="x", **pad)

        self.jarvis_keep_pdfs_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            root,
            text="Mantieni PDF scaricati",
            variable=self.jarvis_keep_pdfs_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        self.jarvis_debug_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            root,
            text="Debug JARVIS",
            variable=self.jarvis_debug_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", padx=20, pady=4)

        ctk.CTkLabel(
            root,
            text="Animazioni avatar JARVIS",
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=20, pady=(8, 0))
        self.jarvis_avatar_level_var = tk.StringVar(value="Complete")
        self.jarvis_avatar_level_menu = ctk.CTkOptionMenu(
            root,
            values=["Complete", "Ridotte", "Disattivate"],
            variable=self.jarvis_avatar_level_var,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["panel"],
            height=36,
        )
        self.jarvis_avatar_level_menu.pack(fill="x", **pad)
        ctk.CTkLabel(
            root,
            text="Solo interfaccia: non modifica la logica del supervisore.",
            text_color=COLORS["muted"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        ctk.CTkLabel(
            root,
            text=(
                "«Apri Chrome» NON registra un account: apre il browser\n"
                "controllato dal programma. Tu navighi eniSpace (login, ordini,\n"
                "modulo di acquisizione); il log salva le URL visitate.\n\n"
                "Il link Marketplace (UUID.abap-web...) può cambiare: il programma\n"
                "lo impara automaticamente quando lo apri da eniSpace.\n\n"
                "Flusso operativo:\n"
                "  1. Ordini e consuntivi (eniSpace)\n"
                "  2. Marketplace Launchpad\n"
                "  3. Dashboard filtri #ZMP_DSH-DISPLAY&/\n"
                "Usa «Apri flusso documenti» oppure CERCA ORDINE."
            ),
            text_color=COLORS["muted"],
            wraplength=480,
            justify="left",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkButton(
            root,
            text="SALVA IMPOSTAZIONI",
            height=42,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._save_all,
        ).pack(fill="x", padx=20, pady=(12, 20))

    def _section(self, parent: ctk.CTkScrollableFrame, title: str) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
            height=36,
        )
        card.pack(fill="x", padx=12, pady=(14, 2))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=8)
        ctk.CTkFrame(
            head, fg_color=COLORS["accent"], width=3, height=16, corner_radius=1
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            head,
            text=title,
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")

    def _toggle_password(self) -> None:
        self.password_entry.configure(
            show="" if self._show_password.get() else "•"
        )

    def _load(self) -> None:
        settings = self.db.get_settings()
        creds = self.credentials.load()
        username = (creds.username if creds else "") or settings.username
        self.username_entry.delete(0, "end")
        self.username_entry.insert(0, username)
        if creds and creds.password:
            self.password_entry.delete(0, "end")
            self.password_entry.insert(0, creds.password)

        self.download_entry.delete(0, "end")
        self.download_entry.insert(
            0, settings.download_folder or str(default_download_dir())
        )
        self.hidden_var.set(bool(settings.browser_hidden))
        self.debug_var.set(settings.debug_mode)
        self.open_folder_var.set(settings.open_folder_after_download)
        self.timeout_entry.delete(0, "end")
        self.timeout_entry.insert(0, str(settings.browser_timeout_ms))
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, settings.enispace_base_url)
        self.imap_host_entry.delete(0, "end")
        self.imap_host_entry.insert(0, settings.imap_host or "pop.securemail.pro")
        self.imap_port_entry.delete(0, "end")
        self.imap_port_entry.insert(0, str(settings.imap_port or 993))
        self.imap_security_var.set(settings.imap_security or "SSL")
        self.imap_folder_combo.set(settings.imap_folder or "INBOX.MdA_Eni")
        self.imap_unread_var.set(settings.imap_unread_only)
        self.autosync_enabled_var.set(bool(settings.autosync_enabled))
        self.autosync_interval_entry.delete(0, "end")
        self.autosync_interval_entry.insert(
            0, str(max(1, int(settings.autosync_interval_minutes or 15)))
        )
        self.smtp_host_entry.delete(0, "end")
        self.smtp_host_entry.insert(0, settings.smtp_host or "authsmtp.securemail.pro")
        self.smtp_port_entry.delete(0, "end")
        self.smtp_port_entry.insert(0, str(settings.smtp_port or 465))
        self.smtp_security_var.set(settings.smtp_security or "SSL")
        mail_creds = self._mail_credentials().load()
        mail_user = (mail_creds.username if mail_creds else "") or settings.imap_username
        self.imap_user_entry.delete(0, "end")
        self.imap_user_entry.insert(0, mail_user or "")
        self.imap_pass_entry.delete(0, "end")
        if mail_creds and mail_creds.password:
            self.imap_pass_entry.insert(0, mail_creds.password)

        self.jarvis_enabled_var.set(bool(settings.jarvis_enabled))
        self.jarvis_autostart_var.set(bool(settings.jarvis_autostart))
        self.jarvis_simulation_var.set(bool(settings.jarvis_simulation))
        self.jarvis_interval_entry.delete(0, "end")
        self.jarvis_interval_entry.insert(
            0, str(max(15, int(settings.jarvis_interval_seconds or 60)))
        )
        self.jarvis_retries_entry.delete(0, "end")
        self.jarvis_retries_entry.insert(
            0, str(max(1, int(settings.jarvis_max_retries or 3)))
        )
        self.jarvis_printer_entry.delete(0, "end")
        self.jarvis_printer_entry.insert(0, settings.jarvis_printer or "")
        self.jarvis_dl_entry.delete(0, "end")
        self.jarvis_dl_entry.insert(0, settings.jarvis_download_folder or "")
        self.jarvis_keep_pdfs_var.set(bool(settings.jarvis_keep_pdfs))
        self.jarvis_debug_var.set(bool(settings.jarvis_debug))
        level = (settings.jarvis_avatar_level or "full").strip().lower()
        label = {"full": "Complete", "reduced": "Ridotte", "off": "Disattivate"}.get(
            level, "Complete"
        )
        self.jarvis_avatar_level_var.set(label)

    def _browse_folder(self) -> None:
        current = self.download_entry.get().strip() or str(default_download_dir())
        chosen = filedialog.askdirectory(initialdir=current, parent=self)
        if chosen:
            self.download_entry.delete(0, "end")
            self.download_entry.insert(0, chosen)

    def _save_credentials(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showwarning(
                "Credenziali",
                "Inserire username e password.",
                parent=self,
            )
            return
        try:
            self.credentials.save(username, password)
            settings = self.db.get_settings()
            settings.username = username
            self.db.save_settings(settings)
            messagebox.showinfo(
                "Credenziali",
                "Credenziali salvate in Windows Credential Manager.",
                parent=self,
            )
            if self.on_activity:
                self.on_activity("Credenziali salvate.")
        except Exception as exc:
            messagebox.showerror(
                "Errore",
                "Impossibile salvare le credenziali.\nConsultare il log tecnico.",
                parent=self,
            )
            if self.on_activity:
                self.on_activity(f"Errore salvataggio credenziali: {exc}")

    def _collect_settings(self) -> AppSettings:
        settings = self.db.get_settings()
        settings.username = self.username_entry.get().strip()
        settings.download_folder = (
            self.download_entry.get().strip() or str(default_download_dir())
        )
        settings.browser_hidden = bool(self.hidden_var.get())
        settings.browser_visible = not settings.browser_hidden
        settings.debug_mode = bool(self.debug_var.get())
        settings.open_folder_after_download = bool(self.open_folder_var.get())
        settings.enispace_base_url = self.url_entry.get().strip()
        try:
            settings.browser_timeout_ms = max(
                5000, int(self.timeout_entry.get().strip() or "60000")
            )
        except ValueError:
            settings.browser_timeout_ms = 60000
        settings.imap_host = (
            self.imap_host_entry.get().strip() or "pop.securemail.pro"
        )
        try:
            settings.imap_port = max(
                1, int(self.imap_port_entry.get().strip() or "993")
            )
        except ValueError:
            settings.imap_port = 993
        settings.imap_security = self.imap_security_var.get() or "SSL"
        settings.imap_username = self.imap_user_entry.get().strip()
        settings.imap_folder = self._get_imap_folder() or "INBOX.MdA_Eni"
        settings.imap_unread_only = bool(self.imap_unread_var.get())
        settings.autosync_enabled = bool(self.autosync_enabled_var.get())
        try:
            settings.autosync_interval_minutes = max(
                1, int(self.autosync_interval_entry.get().strip() or "15")
            )
        except ValueError:
            settings.autosync_interval_minutes = 15
        settings.smtp_host = (
            self.smtp_host_entry.get().strip() or "authsmtp.securemail.pro"
        )
        try:
            settings.smtp_port = max(
                1, int(self.smtp_port_entry.get().strip() or "465")
            )
        except ValueError:
            settings.smtp_port = 465
        settings.smtp_security = self.smtp_security_var.get() or "SSL"
        settings.jarvis_enabled = bool(self.jarvis_enabled_var.get())
        settings.jarvis_autostart = bool(self.jarvis_autostart_var.get())
        settings.jarvis_simulation = bool(self.jarvis_simulation_var.get())
        try:
            settings.jarvis_interval_seconds = max(
                15, int(self.jarvis_interval_entry.get().strip() or "60")
            )
        except ValueError:
            settings.jarvis_interval_seconds = 60
        try:
            settings.jarvis_max_retries = max(
                1, int(self.jarvis_retries_entry.get().strip() or "3")
            )
        except ValueError:
            settings.jarvis_max_retries = 3
        settings.jarvis_printer = self.jarvis_printer_entry.get().strip()
        settings.jarvis_download_folder = self.jarvis_dl_entry.get().strip()
        settings.jarvis_keep_pdfs = bool(self.jarvis_keep_pdfs_var.get())
        settings.jarvis_debug = bool(self.jarvis_debug_var.get())
        avatar_label = (self.jarvis_avatar_level_var.get() or "Complete").strip()
        settings.jarvis_avatar_level = {
            "Complete": "full",
            "Ridotte": "reduced",
            "Disattivate": "off",
        }.get(avatar_label, "full")
        return settings

    def _get_imap_folder(self) -> str:
        try:
            return (self.imap_folder_combo.get() or "").strip()
        except Exception:
            return (self.imap_folder_var.get() or "").strip()

    def _apply_imap_folders(self, folders: list[str], *, select: str = "") -> None:
        """Aggiorna il combo cartelle dopo LIST IMAP."""
        current = select or self._get_imap_folder() or "INBOX.MdA_Eni"
        values = list(folders) if folders else ["INBOX.MdA_Eni", "INBOX", "MdA_Eni"]
        if current and current not in values:
            values = [current] + values
        self.imap_folder_combo.configure(values=values)
        # Preferisci match MdA se presente e current non valido
        chosen = current
        if folders:
            lower_map = {f.lower(): f for f in folders}
            if current.lower() in lower_map:
                chosen = lower_map[current.lower()]
            elif not any(f.lower() == current.lower() for f in folders):
                for f in folders:
                    if "mda_eni" in f.lower():
                        chosen = f
                        break
        self.imap_folder_combo.set(chosen)
        self.imap_folder_var.set(chosen)

    def _mail_credentials(self):
        from services.credential_service import CredentialService
        from utils.paths import KEYRING_MAIL_SERVICE

        return CredentialService(KEYRING_MAIL_SERVICE)

    def _build_imap_config(self, *, require_password: bool = True):
        from services.imap_mail_service import ImapConfig

        user = self.imap_user_entry.get().strip()
        password = self.imap_pass_entry.get()
        # Una sola credenziale keyring per IMAP + SMTP
        creds = self._mail_credentials().load()
        if not password and creds and creds.password:
            password = creds.password
        if not user and creds:
            user = creds.username or ""
        if require_password and (not user or not password):
            raise ValueError(
                "Inserire utente e password casella (o salvare le credenziali)."
            )
        try:
            imap_port = int(self.imap_port_entry.get().strip() or "993")
        except ValueError:
            imap_port = 993
        try:
            smtp_port = int(self.smtp_port_entry.get().strip() or "465")
        except ValueError:
            smtp_port = 465
        return ImapConfig(
            host=self.imap_host_entry.get().strip() or "pop.securemail.pro",
            port=imap_port,
            security=self.imap_security_var.get() or "SSL",
            username=user,
            password=password or "",
            folder=self._get_imap_folder() or "INBOX.MdA_Eni",
            unread_only=bool(self.imap_unread_var.get()),
            smtp_host=self.smtp_host_entry.get().strip() or "authsmtp.securemail.pro",
            smtp_port=smtp_port,
            smtp_security=self.smtp_security_var.get() or "SSL",
        )

    def _save_mail_credentials(self) -> None:
        username = self.imap_user_entry.get().strip()
        password = self.imap_pass_entry.get()
        if not username or not password:
            messagebox.showwarning(
                "Casella",
                "Inserire utente e password della casella "
                "(stessa password per IMAP e SMTP).",
                parent=self,
            )
            return
        try:
            self._mail_credentials().save(username, password)
            settings = self.db.get_settings()
            settings.imap_username = username
            settings.imap_host = (
                self.imap_host_entry.get().strip() or settings.imap_host
            )
            settings.imap_folder = (
                self._get_imap_folder() or settings.imap_folder
            )
            self.db.save_settings(settings)
            messagebox.showinfo(
                "Casella",
                "Credenziali casella salvate in Windows Credential Manager.\n"
                "(Stessa password usata da TEST IMAP e TEST SMTP.)",
                parent=self,
            )
            if self.on_activity:
                self.on_activity("Credenziali casella IMAP/SMTP salvate.")
        except Exception as exc:
            messagebox.showerror(
                "Errore",
                f"Impossibile salvare le credenziali casella.\n{exc}",
                parent=self,
            )

    def _load_imap_folders(self) -> None:
        if getattr(self, "_imap_folders_busy", False):
            return
        self._imap_folders_busy = True
        if self.on_activity:
            self.on_activity("Caricamento cartelle IMAP…")

        def work() -> tuple[bool, str, list[str]]:
            from services.imap_mail_service import ImapMailService, format_mail_error

            cfg = self._build_imap_config()
            try:
                folders = ImapMailService(cfg).list_folders()
                if not folders:
                    return False, "Nessuna cartella restituita dal server.", []
                return True, f"Trovate {len(folders)} cartelle.", folders
            except Exception as exc:
                return False, format_mail_error(exc, kind="IMAP"), []

        def done(ok: bool, info: str, folders: list[str]) -> None:
            self._imap_folders_busy = False
            if ok and folders:
                self._apply_imap_folders(folders)
                messagebox.showinfo(
                    "Cartelle IMAP",
                    f"{info}\n\nSeleziona la cartella dal menu "
                    "(es. INBOX.MdA_Eni), poi Salva impostazioni.",
                    parent=self,
                )
                if self.on_activity:
                    self.on_activity(f"Cartelle IMAP caricate: {len(folders)}")
            else:
                messagebox.showerror(
                    "Cartelle IMAP",
                    f"Impossibile caricare le cartelle.\n\n{info}",
                    parent=self,
                )

        def runner() -> None:
            try:
                ok, info, folders = work()
            except Exception as exc:
                ok, info, folders = False, str(exc), []
            self.after(0, lambda: done(ok, info, folders))

        threading.Thread(target=runner, daemon=True).start()

    def _test_imap(self) -> None:
        if getattr(self, "_imap_test_busy", False):
            return
        self._imap_test_busy = True
        if self.on_activity:
            self.on_activity("Test IMAP in corso…")

        def work() -> tuple[bool, str, list[str]]:
            from services.imap_mail_service import ImapMailService

            cfg = self._build_imap_config()
            return ImapMailService(cfg).test_connection()

        def done(ok: bool, info: str, folders: list[str]) -> None:
            self._imap_test_busy = False
            if ok:
                if folders:
                    self._apply_imap_folders(folders)
                messagebox.showinfo(
                    "IMAP",
                    f"{info}\n\n"
                    "Seleziona la cartella dal menu a tendina "
                    "(o premi CARICA CARTELLE).",
                    parent=self,
                )
                if self.on_activity:
                    self.on_activity(f"Test IMAP OK: {info}")
            else:
                messagebox.showerror(
                    "IMAP",
                    f"Connessione fallita.\n\n{info}\n\n"
                    "Verificare: email completa, password casella "
                    "(«SALVA CRED. CASELLA» — stessa per SMTP), "
                    "host/porta/SSL.",
                    parent=self,
                )

        def runner() -> None:
            try:
                ok, info, folders = work()
            except Exception as exc:
                ok, info, folders = False, str(exc), []
            self.after(0, lambda: done(ok, info, folders))

        threading.Thread(target=runner, daemon=True).start()

    def _test_smtp(self) -> None:
        if getattr(self, "_smtp_test_busy", False):
            return
        self._smtp_test_busy = True
        if self.on_activity:
            self.on_activity("Test SMTP in corso…")

        def work() -> tuple[bool, str]:
            from services.imap_mail_service import ImapMailService

            cfg = self._build_imap_config()
            return ImapMailService(cfg).test_smtp()

        def done(ok: bool, info: str) -> None:
            self._smtp_test_busy = False
            if ok:
                messagebox.showinfo("SMTP", info, parent=self)
                if self.on_activity:
                    self.on_activity(f"Test SMTP OK: {info}")
            else:
                messagebox.showerror(
                    "SMTP",
                    f"Connessione fallita.\n\n{info}",
                    parent=self,
                )

        def runner() -> None:
            try:
                ok, info = work()
            except Exception as exc:
                ok, info = False, str(exc)
            self.after(0, lambda: done(ok, info))

        threading.Thread(target=runner, daemon=True).start()

    def _save_all(self) -> None:
        settings = self._collect_settings()
        Path(settings.download_folder).mkdir(parents=True, exist_ok=True)
        self.db.save_settings(settings)

        # Aggiorna anche credenziali se compilate
        password = self.password_entry.get()
        if settings.username and password:
            try:
                self.credentials.save(settings.username, password)
            except Exception:
                pass
        mail_user = self.imap_user_entry.get().strip()
        mail_pass = self.imap_pass_entry.get()
        if mail_user and mail_pass:
            try:
                self._mail_credentials().save(mail_user, mail_pass)
            except Exception:
                pass

        self.enispace.base_url = settings.enispace_base_url
        self.enispace.configure_browser(
            hidden=settings.browser_hidden,
            timeout_ms=settings.browser_timeout_ms,
            debug=settings.debug_mode,
        )
        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Impostazioni", "Impostazioni salvate.", parent=self)
        if self.on_activity:
            self.on_activity("Impostazioni aggiornate.")

    def _test_access(self) -> None:
        self._save_all_silent()
        if self.on_test_access:
            self.on_test_access()

    def _record_nav(self) -> None:
        self._save_all_silent()
        if self.on_record_navigation:
            self.on_record_navigation()

    def _open_document_flow(self) -> None:
        self._save_all_silent()
        if self.on_open_document_flow:
            self.on_open_document_flow()

    def _open_ordini(self) -> None:
        self._save_all_silent()
        if self.on_open_ordini:
            self.on_open_ordini()

    def _open_marketplace(self) -> None:
        self._save_all_silent()
        if self.on_open_marketplace:
            self.on_open_marketplace()

    def _save_all_silent(self) -> None:
        settings = self._collect_settings()
        Path(settings.download_folder).mkdir(parents=True, exist_ok=True)
        self.db.save_settings(settings)
        self.enispace.base_url = settings.enispace_base_url
        self.enispace.configure_browser(
            hidden=settings.browser_hidden,
            timeout_ms=settings.browser_timeout_ms,
            debug=settings.debug_mode,
        )
        if self.on_saved:
            self.on_saved()


class SetupWizard(ctk.CTkToplevel):
    """Configurazione guidata al primo avvio."""

    def __init__(
        self,
        master: ctk.CTk,
        db: "Database",
        credentials: "CredentialService",
        *,
        on_complete: Optional[Callable[[], None]] = None,
        on_test_access: Optional[Callable[[Callable[[bool, str], None]], None]] = None,
    ) -> None:
        super().__init__(master)
        self.db = db
        self.credentials = credentials
        self.on_complete = on_complete
        self.on_test_access = on_test_access
        self.step = 0

        self.title(f"Primo avvio — {APP_NAME}")
        self.geometry("520x480")
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        self.grab_set()
        apply_app_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._show_password = tk.BooleanVar(value=False)
        self.container = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.container.pack(fill="both", expand=True, padx=24, pady=24)
        self._render()

    def _clear(self) -> None:
        for w in self.container.winfo_children():
            w.destroy()

    def _render(self) -> None:
        self._clear()
        if self.step == 0:
            self._step_account()
        elif self.step == 1:
            self._step_download()
        elif self.step == 2:
            self._step_test()
        else:
            self._step_done()

    def _step_account(self) -> None:
        ctk.CTkLabel(
            self.container,
            text="1 / 4  —  Account eniSpace",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            self.container,
            text="Inserisci le credenziali aziendali autorizzate.\n"
            "La password sarà salvata in Windows Credential Manager.",
            text_color=COLORS["muted"],
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        ctk.CTkLabel(self.container, text="Username", text_color=COLORS["muted"]).pack(
            anchor="w"
        )
        self.w_user = ctk.CTkEntry(self.container, height=36)
        self.w_user.pack(fill="x", pady=4)
        ctk.CTkLabel(self.container, text="Password", text_color=COLORS["muted"]).pack(
            anchor="w"
        )
        self.w_pass = ctk.CTkEntry(self.container, height=36, show="•")
        self.w_pass.pack(fill="x", pady=4)
        ctk.CTkCheckBox(
            self.container,
            text="Mostra password",
            variable=self._show_password,
            command=lambda: self.w_pass.configure(
                show="" if self._show_password.get() else "•"
            ),
            fg_color=COLORS["accent"],
        ).pack(anchor="w", pady=8)

        settings = self.db.get_settings()
        creds = self.credentials.load()
        self.w_user.insert(0, (creds.username if creds else "") or settings.username)

        self._nav_buttons(back=False, next_label="Avanti", next_cmd=self._save_account)

    def _save_account(self) -> None:
        user = self.w_user.get().strip()
        pwd = self.w_pass.get()
        if not user or not pwd:
            messagebox.showwarning("Account", "Compilare username e password.", parent=self)
            return
        try:
            self.credentials.save(user, pwd)
            s = self.db.get_settings()
            s.username = user
            self.db.save_settings(s)
        except Exception:
            messagebox.showerror(
                "Errore",
                "Impossibile salvare le credenziali nel Credential Manager.",
                parent=self,
            )
            return
        self.step = 1
        self._render()

    def _step_download(self) -> None:
        ctk.CTkLabel(
            self.container,
            text="2 / 4  —  Cartella download",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            self.container,
            text="I documenti verranno salvati in sottocartelle per contratto.",
            text_color=COLORS["muted"],
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        row = ctk.CTkFrame(self.container, fg_color="transparent")
        row.pack(fill="x")
        self.w_folder = ctk.CTkEntry(row, height=36)
        self.w_folder.pack(side="left", fill="x", expand=True)
        self.w_folder.insert(0, self.db.get_settings().download_folder or str(default_download_dir()))
        ctk.CTkButton(
            row,
            text="Sfoglia",
            width=90,
            command=self._browse,
            fg_color=COLORS["panel"],
        ).pack(side="left", padx=(8, 0))

        self._nav_buttons(back=True, next_label="Avanti", next_cmd=self._save_folder)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            initialdir=self.w_folder.get(), parent=self
        )
        if chosen:
            self.w_folder.delete(0, "end")
            self.w_folder.insert(0, chosen)

    def _save_folder(self) -> None:
        folder = self.w_folder.get().strip() or str(default_download_dir())
        Path(folder).mkdir(parents=True, exist_ok=True)
        s = self.db.get_settings()
        s.download_folder = folder
        self.db.save_settings(s)
        self.step = 2
        self._render()

    def _step_test(self) -> None:
        ctk.CTkLabel(
            self.container,
            text="3 / 4  —  Test login",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            self.container,
            text=(
                "Verifica l'accesso a eniSpace.\n"
                "Se compare MFA/OTP, completa il login nel browser visibile.\n\n"
                "Nota: finché l'URL e i selettori non sono mappati, "
                "il test apre il browser per l'acquisizione."
            ),
            text_color=COLORS["muted"],
            justify="left",
            wraplength=450,
        ).pack(anchor="w", pady=(0, 16))

        self.test_status = ctk.CTkLabel(
            self.container, text="", text_color=COLORS["text"], wraplength=450
        )
        self.test_status.pack(anchor="w", pady=8)

        ctk.CTkButton(
            self.container,
            text="TEST ACCESSO ENISPACE",
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._run_test,
        ).pack(fill="x", pady=8)

        self._nav_buttons(
            back=True,
            next_label="Salta e continua",
            next_cmd=lambda: self._goto(3),
        )

    def _run_test(self) -> None:
        self.test_status.configure(text="Test in corso…")
        if not self.on_test_access:
            self.test_status.configure(text="Test non disponibile.")
            return

        def done(ok: bool, message: str) -> None:
            self.after(
                0,
                lambda: self.test_status.configure(
                    text=message,
                    text_color="#4ade80" if ok else "#f87171",
                ),
            )
            if ok:
                self.after(800, lambda: self._goto(3))

        self.on_test_access(done)

    def _step_done(self) -> None:
        ctk.CTkLabel(
            self.container,
            text="4 / 4  —  Completato",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            self.container,
            text=(
                "Configurazione iniziale terminata.\n\n"
                "Puoi cercare un numero contratto dalla schermata principale.\n"
                "La ricerca reale su eniSpace sarà operativa dopo la mappatura "
                "dei selettori (Registra navigazione)."
            ),
            text_color=COLORS["muted"],
            justify="left",
            wraplength=450,
        ).pack(anchor="w", pady=(0, 24))

        ctk.CTkButton(
            self.container,
            text="INIZIA",
            height=44,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self._finish,
        ).pack(fill="x")

    def _nav_buttons(
        self, *, back: bool, next_label: str, next_cmd: Callable[[], None]
    ) -> None:
        row = ctk.CTkFrame(self.container, fg_color="transparent")
        row.pack(side="bottom", fill="x", pady=(24, 0))
        if back:
            ctk.CTkButton(
                row,
                text="Indietro",
                width=120,
                fg_color=COLORS["panel"],
                command=lambda: self._goto(self.step - 1),
            ).pack(side="left")
        ctk.CTkButton(
            row,
            text=next_label,
            width=160,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=next_cmd,
        ).pack(side="right")

    def _goto(self, step: int) -> None:
        self.step = max(0, step)
        self._render()

    def _finish(self) -> None:
        s = self.db.get_settings()
        s.setup_completed = True
        self.db.save_settings(s)
        if self.on_complete:
            self.on_complete()
        self.destroy()

    def _on_close(self) -> None:
        # Consente di chiudere senza completare; il wizard riparte al prossimo avvio
        self.destroy()
