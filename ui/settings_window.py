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


class SettingsPage(ctk.CTkFrame):
    """Impostazioni modulari — in-app o dialog."""

    def __init__(
        self,
        master,
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
        show_chrome: bool = True,
    ) -> None:
        super().__init__(master, fg_color=COLORS["bg"])
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
        self._show_chrome = show_chrome

        self._show_password = tk.BooleanVar(value=False)
        self._show_mail_password = tk.BooleanVar(value=False)
        self._modules: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_module = "generale"
        self._build()
        self._load()
        self._select_module("generale")

    def reload_active(self) -> None:
        try:
            self._load()
        except Exception:
            pass
        self._select_module(self._active_module)

    # ------------------------------------------------------------------ UI shell
    def _build(self) -> None:
        # Large workspace title (reference IMPOSTAZIONI)
        title_wrap = ctk.CTkFrame(self, fg_color="transparent")
        title_wrap.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            title_wrap,
            text="IMPOSTAZIONI",
            font=ctk.CTkFont(family=font_family(), size=28, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_wrap,
            text="Configura i moduli e le preferenze di VISION",
            font=ctk.CTkFont(family=font_family(), size=14),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(4, 8))

        if self._show_chrome:
            # dialog mode already has window title; keep compact spacer
            pass

        body = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        nav = ctk.CTkScrollableFrame(
            body,
            fg_color=COLORS["sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
            width=280,
        )
        nav.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        ctk.CTkLabel(
            nav,
            text="MODULI",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=16, pady=(16, 10))

        modules = [
            ("generale", "Generale", "Identità e comportamento UI"),
            ("enispace", "EniSpace", "Account e portale"),
            ("mail", "Mail", "Casella e sincronizzazione"),
            ("stampa", "Stampa / Download", "Code e cartelle"),
            ("coin_transport", "Trasporto Monete", "Sala Conta e Protocollo"),
            ("remote", "Remote & Cloud", "Agent e connessione"),
            ("supervisor", "Supervisor", "Automazione operativa"),
            ("diagnostica", "Diagnostica", "Log e controlli"),
        ]
        for key, label, desc in modules:
            card = ctk.CTkFrame(
                nav,
                fg_color="transparent",
                corner_radius=10,
                border_width=1,
                border_color=COLORS["border"],
                height=64,
            )
            card.pack(fill="x", padx=10, pady=4)
            card.pack_propagate(False)
            btn = ctk.CTkButton(
                card,
                text=f"{label}\n{desc}",
                anchor="w",
                height=56,
                corner_radius=10,
                fg_color="transparent",
                hover_color=COLORS["active_nav"],
                text_color=COLORS["text"],
                font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
                command=lambda k=key: self._select_module(k),
            )
            btn.pack(fill="both", expand=True, padx=2, pady=2)
            self._nav_buttons[key] = btn

        self._status_label = ctk.CTkLabel(
            nav,
            text="",
            font=ctk.CTkFont(family=font_family(), size=12),
            text_color=COLORS["muted"],
            wraplength=240,
            justify="left",
        )
        self._status_label.pack(side="bottom", anchor="w", padx=14, pady=14)

        content_host = ctk.CTkFrame(
            body,
            fg_color=COLORS["panel"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        content_host.grid(row=0, column=1, sticky="nsew")
        content_host.grid_rowconfigure(0, weight=1)
        content_host.grid_columnconfigure(0, weight=1)

        self._content = ctk.CTkFrame(content_host, fg_color="transparent")
        self._content.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._modules["generale"] = self._build_generale_panel(self._content)
        self._modules["enispace"] = self._build_enispace_panel(self._content)
        self._modules["mail"] = self._build_mail_panel(self._content)
        self._modules["stampa"] = self._build_stampa_panel(self._content)
        self._modules["coin_transport"] = self._build_coin_transport_panel(self._content)
        self._modules["remote"] = self._build_remote_panel(self._content)
        self._modules["supervisor"] = self._build_supervisor_panel(self._content)
        self._modules["diagnostica"] = self._build_diagnostica_panel(self._content)

        for frame in self._modules.values():
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_remove()

    def _select_module(self, key: str) -> None:
        self._active_module = key
        for k, frame in self._modules.items():
            if k == key:
                frame.grid()
            else:
                frame.grid_remove()
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.configure(
                    fg_color=COLORS["active_nav"],
                    border_width=1,
                    border_color=COLORS["accent"],
                    text_color=COLORS["text"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    border_width=0,
                    text_color=COLORS["muted"],
                )
        if key == "remote":
            self._refresh_remote_panel()
        elif key == "coin_transport":
            panel = self._modules.get("coin_transport")
            coin = getattr(panel, "_coin_panel", None) if panel is not None else None
            if coin is not None:
                try:
                    coin.reload()
                except Exception:
                    pass
            self._set_status("")
        else:
            self._set_status("")

    def _set_status(self, message: str, *, ok: Optional[bool] = None) -> None:
        color = COLORS["muted"]
        if ok is True:
            color = COLORS["success"]
        elif ok is False:
            color = COLORS["danger"]
        self._status_label.configure(text=message, text_color=color)

    def _scroll(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        """Scrollable content host with left padding (avoids CTk canvas clip)."""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        inner = ctk.CTkFrame(scroll, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=(10, 6), pady=4)
        return inner

    def _module_title(self, parent, title: str, subtitle: str) -> None:
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            parent,
            text=subtitle,
            font=ctk.CTkFont(family=font_family(), size=12),
            text_color=COLORS["muted"],
            wraplength=720,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _group(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel_alt"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=8, pady=(0, 12))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=14, pady=(12, 6))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(0, 14))
        return inner

    def _label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(family=font_family(), size=12),
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(6, 2))

    def _entry(self, parent, **kwargs) -> ctk.CTkEntry:
        e = ctk.CTkEntry(
            parent,
            height=36,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
            **kwargs,
        )
        e.pack(fill="x", pady=(0, 4))
        return e

    def _save_bar(self, parent, command, label: str = "Salva modifiche") -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(4, 16))
        ctk.CTkButton(
            bar,
            text=label,
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            command=command,
        ).pack(side="left")

    # ------------------------------------------------------------------ panels
    def _build_generale_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "Generale",
            "Identità applicazione e comportamento interfaccia",
        )
        info = self._group(scroll, "Applicazione")
        ctk.CTkLabel(
            info,
            text=f"Prodotto: {APP_NAME}",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family=font_family(), size=13),
        ).pack(anchor="w")
        try:
            from ui.theme import APP_VERSION
            ver = APP_VERSION
        except Exception:
            ver = "—"
        ctk.CTkLabel(
            info,
            text=f"Versione: {ver}",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family=font_family(), size=12),
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(
            info,
            text="Le credenziali EniSpace, Mail, Stampa e Remote sono nei rispettivi moduli.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family=font_family(), size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        ui = self._group(scroll, "Comportamento UI")
        self._label(ui, "Riduci animazioni (avatar VISION)")
        self.jarvis_avatar_level_var = tk.StringVar(value="Complete")
        self.jarvis_avatar_level_menu = ctk.CTkOptionMenu(
            ui,
            values=["Complete", "Ridotte", "Disattivate"],
            variable=self.jarvis_avatar_level_var,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["panel"],
            height=36,
        )
        self.jarvis_avatar_level_menu.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            ui,
            text=(
                "Ridotte: niente micro-movimento testa, pulse attenuato. "
                "Disattivate: avatar statico. Solo UI — non altera il supervisore."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w")

        self._save_bar(scroll, lambda: self._save_module("Generale"))
        return frame

    def _build_enispace_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "EniSpace",
            "Account, browser e portale eniSpace",
        )

        acc = self._group(scroll, "Account EniSpace")
        self._label(acc, "Username eniSpace")
        self.username_entry = self._entry(acc)
        self._label(acc, "Password")
        pass_row = ctk.CTkFrame(acc, fg_color="transparent")
        pass_row.pack(fill="x", pady=(0, 4))
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
            acc,
            text="Salva credenziali",
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._save_credentials,
        ).pack(anchor="w", pady=(8, 0))

        br = self._group(scroll, "Browser / Portale")
        self.hidden_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            br,
            text="Nascondi browser (solo UI app; Chrome headed off-screen)",
            variable=self.hidden_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        self.chrome_system_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            br,
            text="(Sconsigliato) Profilo Chrome di sistema — non usato (Chrome 151+)",
            variable=self.chrome_system_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        ctk.CTkLabel(
            br,
            text=(
                "Come VIS eniSpace Utility: Chrome di sistema (channel=chrome) "
                "con profilo isolato data/browser-profile. Al primo accesso "
                "completare SSO/MFA; la sessione resta salvata in VISION."
            ),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            br,
            text=(
                "Primo login / MFA: se Chrome non compare, disattiva «Nascondi browser», "
                "completa l'accesso, poi riattivalo. La sessione resta nel profilo."
            ),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 6))
        self._label(br, "Timeout browser (ms)")
        self.timeout_entry = self._entry(br)
        self._label(br, "URL portale eniSpace")
        self.url_entry = self._entry(
            br,
            placeholder_text="https://enispace.eni.com/it_IT/private/myhome.page",
        )

        self._save_bar(scroll, lambda: self._save_module("EniSpace"))
        return frame

    def _build_mail_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        pad = {"padx": 0, "pady": 4}
        self._module_title(scroll, "Mail", "Casella IMAP / SMTP (MdA_Eni)")

        imap = self._group(scroll, "IMAP")
        self._label(imap, "Host IMAP (es. pop.securemail.pro)")
        self.imap_host_entry = self._entry(imap, placeholder_text="pop.securemail.pro")
        row_imap = ctk.CTkFrame(imap, fg_color="transparent")
        row_imap.pack(fill="x", pady=4)
        ctk.CTkLabel(row_imap, text="Porta", text_color=COLORS["muted"]).pack(side="left")
        self.imap_port_entry = ctk.CTkEntry(
            row_imap, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.imap_port_entry.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_imap, text="Sicurezza", text_color=COLORS["muted"]).pack(side="left")
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

        self._label(imap, "Utente casella (email completa)")
        self.imap_user_entry = self._entry(imap, placeholder_text="nome@dominio.it")
        self._label(imap, "Password casella (Credential Manager)")
        mail_pass_row = ctk.CTkFrame(imap, fg_color="transparent")
        mail_pass_row.pack(fill="x", pady=(0, 4))
        self.imap_pass_entry = ctk.CTkEntry(
            mail_pass_row,
            height=36,
            show="•",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.imap_pass_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkCheckBox(
            mail_pass_row,
            text="Mostra",
            variable=self._show_mail_password,
            command=self._toggle_mail_password,
            text_color=COLORS["muted"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(10, 0))

        self._label(imap, "Cartella IMAP (scegli dall'elenco o digita)")
        row_folder = ctk.CTkFrame(imap, fg_color="transparent")
        row_folder.pack(fill="x", pady=4)
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
        try:
            self.imap_folder_combo._entry.configure(state="normal")  # noqa: SLF001
        except Exception:
            pass
        ctk.CTkButton(
            row_folder,
            text="Carica cartelle",
            height=36,
            width=140,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._load_imap_folders,
        ).pack(side="left", padx=(8, 0))
        self.imap_folder_entry = self.imap_folder_combo

        self.imap_unread_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            imap,
            text="Solo mail non lette",
            variable=self.imap_unread_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        autosync_row = ctk.CTkFrame(imap, fg_color="transparent")
        autosync_row.pack(fill="x", pady=4)
        self.autosync_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            autosync_row,
            text="Autosync casella",
            variable=self.autosync_enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="left")
        ctk.CTkLabel(autosync_row, text="ogni", text_color=COLORS["muted"]).pack(
            side="left", padx=(16, 6)
        )
        self.autosync_interval_entry = ctk.CTkEntry(
            autosync_row, width=64, height=32, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.autosync_interval_entry.pack(side="left")
        self.autosync_interval_entry.insert(0, "15")
        ctk.CTkLabel(autosync_row, text="minuti", text_color=COLORS["muted"]).pack(
            side="left", padx=(6, 0)
        )
        ctk.CTkLabel(
            imap,
            text=(
                "Con autosync attivo l'app interroga IMAP in background "
                "(senza bloccare la UI), scarica i MdA e aggiorna il Registro."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        smtp = self._group(scroll, "SMTP")
        self._label(smtp, "Host SMTP (opzionale, es. authsmtp.securemail.pro)")
        self.smtp_host_entry = self._entry(
            smtp, placeholder_text="authsmtp.securemail.pro"
        )
        row_smtp = ctk.CTkFrame(smtp, fg_color="transparent")
        row_smtp.pack(fill="x", pady=4)
        ctk.CTkLabel(row_smtp, text="Porta SMTP", text_color=COLORS["muted"]).pack(side="left")
        self.smtp_port_entry = ctk.CTkEntry(
            row_smtp, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.smtp_port_entry.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_smtp, text="Sicurezza", text_color=COLORS["muted"]).pack(side="left")
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

        row_mail_btns = ctk.CTkFrame(scroll, fg_color="transparent")
        row_mail_btns.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            row_mail_btns,
            text="Salva cred. casella",
            height=36,
            width=170,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._save_mail_credentials,
        ).pack(side="left")
        ctk.CTkButton(
            row_mail_btns,
            text="Test IMAP",
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
            text="Test SMTP",
            height=36,
            width=110,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._test_smtp,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            scroll,
            text=(
                "IMAP e SMTP usano la stessa password casella. "
                "Dopo Test IMAP OK (o Carica cartelle) scegli la cartella dall'elenco."
            ),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._save_bar(scroll, lambda: self._save_module("Mail"))
        return frame

    def _build_coin_transport_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        from ui.modules.coin_transport_settings_panel import CoinTransportSettingsPanel

        panel = CoinTransportSettingsPanel(
            scroll,
            self.db,
            on_status=lambda msg, ok: self._set_status(msg, ok=ok),
        )
        # fill=x only: height must follow children so parent CTkScrollableFrame scrolls
        panel.pack(fill="x", expand=False, anchor="n")
        frame._coin_panel = panel  # noqa: SLF001
        return frame

    def _build_stampa_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "Stampa / Download",
            "Cartelle output, stampante e PDF",
        )

        dl = self._group(scroll, "Download")
        self._label(dl, "Cartella download")
        dl_row = ctk.CTkFrame(dl, fg_color="transparent")
        dl_row.pack(fill="x", pady=(0, 4))
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
            dl,
            text="Apri cartella dopo download",
            variable=self.open_folder_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        pr = self._group(scroll, "Stampa e PDF")
        self._label(pr, "Stampante (vuoto = predefinita Windows)")
        self.jarvis_printer_entry = self._entry(pr)
        self._label(pr, "Cartella download supervisore (vuoto = cartella globale)")
        jdl_row = ctk.CTkFrame(pr, fg_color="transparent")
        jdl_row.pack(fill="x", pady=(0, 4))
        self.jarvis_dl_entry = ctk.CTkEntry(
            jdl_row, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.jarvis_dl_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            jdl_row,
            text="Sfoglia",
            width=90,
            height=36,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self._browse_jarvis_folder,
        ).pack(side="left", padx=(8, 0))
        self.jarvis_keep_pdfs_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            pr,
            text="Mantieni PDF scaricati",
            variable=self.jarvis_keep_pdfs_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        self._save_bar(scroll, lambda: self._save_module("Stampa / Download"))
        return frame

    def _build_remote_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "Remote & Cloud",
            "Canale sottile Agent: messaggi/stato in ingresso, "
            "WAKE / DEACTIVATE Supervisor in uscita (non orchestrazione job).",
        )
        card = self._group(scroll, "Configurazione Agent remota")
        self._remote_labels: dict[str, ctk.CTkLabel] = {}
        for key, title in [
            ("enabled", "Remote abilitato"),
            ("mode", "Modalità"),
            ("device_id", "Device ID"),
            ("device_name", "Device name"),
            ("policy", "Execution policy"),
            ("supabase_url", "Supabase URL"),
            ("anon", "Supabase anon key"),
            ("token", "VISION_AGENT_TOKEN"),
            ("heartbeat", "Heartbeat (s)"),
            ("poll", "Command poll (s)"),
        ]:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row,
                text=title,
                anchor="w",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, sticky="w", padx=(0, 16))
            lab = ctk.CTkLabel(
                row,
                text="—",
                anchor="w",
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            lab.grid(row=0, column=1, sticky="ew")
            self._remote_labels[key] = lab
        ctk.CTkLabel(
            card,
            text=(
                "I valori provengono da .env / remote.env. "
                "Il token non viene mai mostrato in chiaro. "
                "Nessuna service_role in questa UI. "
                "Policy tipica: status_only = GET_STATUS + WAKE_SUPERVISOR + "
                "DEACTIVATE_SUPERVISOR."
            ),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(10, 0))

        live = self._group(scroll, "Stato runtime Agent")
        self._remote_live_labels: dict[str, ctk.CTkLabel] = {}
        for key, title in [
            ("runtime", "Stato Agent"),
            ("last_error", "Ultimo errore"),
        ]:
            row = ctk.CTkFrame(live, fg_color="transparent")
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row,
                text=title,
                anchor="w",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, sticky="w", padx=(0, 16))
            lab = ctk.CTkLabel(
                row,
                text="—",
                anchor="w",
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=12, weight="bold"),
                wraplength=520,
                justify="left",
            )
            lab.grid(row=0, column=1, sticky="ew")
            self._remote_live_labels[key] = lab

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(anchor="w", padx=8, pady=(4, 16))
        ctk.CTkButton(
            btn_row,
            text="Aggiorna stato",
            height=36,
            width=160,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._refresh_remote_panel,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Testa connessione Agent",
            height=36,
            width=200,
            fg_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._test_remote_agent_connection,
        ).pack(side="left")
        return frame

    def _find_remote_agent(self):
        w = self
        for _ in range(8):
            if w is None:
                break
            agent = getattr(w, "remote_agent", None)
            if agent is not None:
                return agent
            w = getattr(w, "master", None)
        return None

    def _refresh_remote_panel(self) -> None:
        try:
            from app.remote.config import RemoteConfig

            cfg = RemoteConfig.load()
        except Exception as exc:
            for lab in self._remote_labels.values():
                lab.configure(text="Errore lettura config")
            self._set_status(f"Remote: {exc}", ok=False)
            return
        token_state = "Configurato" if bool(cfg.vision_agent_token) else "Non configurato"
        anon_state = "Presente" if bool(cfg.supabase_anon_key) else "Assente"
        url = cfg.supabase_url or "—"
        if len(url) > 64:
            url = url[:61] + "…"
        values = {
            "enabled": "Sì" if cfg.enabled else "No",
            "mode": cfg.mode or "—",
            "device_id": cfg.device_id or "—",
            "device_name": cfg.device_name or "—",
            "policy": cfg.remote_execution_policy or "—",
            "supabase_url": url,
            "anon": anon_state,
            "token": token_state,
            "heartbeat": str(cfg.heartbeat_seconds),
            "poll": str(cfg.command_poll_seconds),
        }
        for key, val in values.items():
            self._remote_labels[key].configure(text=val)

        runtime = "Disabilitato" if not cfg.enabled else f"Abilitato ({cfg.mode})"
        last_err = "—"
        agent = self._find_remote_agent()
        if agent is not None:
            st = str(getattr(agent, "status", "") or "—")
            en = bool(getattr(agent, "enabled", False))
            running = bool(getattr(agent, "is_running", False))
            runtime = f"{st}" + (" · running" if running else "")
            if not en:
                runtime = f"DISABLED ({st})"
            err = str(getattr(agent, "last_error", "") or "").strip()
            last_err = err or "—"
        if hasattr(self, "_remote_live_labels"):
            self._remote_live_labels["runtime"].configure(text=runtime)
            self._remote_live_labels["last_error"].configure(text=last_err)
        self._set_status("Stato Remote aggiornato", ok=True)

    def _test_remote_agent_connection(self) -> None:
        def _work() -> None:
            try:
                from app.remote.client import create_backend
                from app.remote.config import RemoteConfig

                cfg = RemoteConfig.load()
                if not cfg.enabled:
                    msg = "Remote disabilitato (VISION_REMOTE_ENABLED=false)"
                    self.after(0, lambda: self._finish_remote_probe(False, msg))
                    return
                if cfg.mode == "mock":
                    msg = "Modalità mock — nessun cloud da testare"
                    self.after(0, lambda: self._finish_remote_probe(True, msg))
                    return
                backend = create_backend(cfg)
                probe = getattr(backend, "probe_agent_rpc", None)
                if callable(probe):
                    ok, msg = probe()
                else:
                    backend.connect()
                    ok, msg = True, "Backend raggiungibile"
                self.after(0, lambda o=ok, m=msg: self._finish_remote_probe(o, m))
            except Exception as exc:
                err = str(exc)[:240]
                self.after(0, lambda e=err: self._finish_remote_probe(False, e))

        self._set_status("Test connessione Agent in corso…", ok=True)
        threading.Thread(target=_work, name="remote-probe", daemon=True).start()

    def _finish_remote_probe(self, ok: bool, msg: str) -> None:
        if hasattr(self, "_remote_live_labels"):
            self._remote_live_labels["last_error"].configure(text=("—" if ok else msg))
            if ok:
                self._remote_live_labels["runtime"].configure(text="PROBE OK")
            else:
                self._remote_live_labels["runtime"].configure(text="PROBE FAILED")
        self._set_status(
            ("Connessione Agent OK" if ok else f"Agent irraggiungibile: {msg}"),
            ok=ok,
        )
        if ok:
            messagebox.showinfo(APP_NAME, msg)
        else:
            messagebox.showerror(APP_NAME, f"Agent irraggiungibile:\n\n{msg}")

    def _build_supervisor_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "Supervisor",
            "VISION Supervisor — preferenze runtime (chiavi config invariate)",
        )

        g = self._group(scroll, "Avvio e comportamento")
        self.jarvis_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            g,
            text="Abilita VISION Supervisor (preferenza; avvio da tab Assistente o autostart)",
            variable=self.jarvis_enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        self.jarvis_autostart_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            g,
            text="Avvio automatico Supervisor all'apertura programma",
            variable=self.jarvis_autostart_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        self.jarvis_simulation_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            g,
            text="Modalità simulazione (NO download finale / NO stampa)",
            variable=self.jarvis_simulation_var,
            text_color=COLORS["text"],
            fg_color="#f59e0b",
            hover_color="#d97706",
        ).pack(anchor="w", pady=4)
        ctk.CTkLabel(
            g,
            text="Se attiva, in UI compare il banner «VISION — SIMULAZIONE».",
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 4))

        self._label(g, "Intervallo controllo mail (secondi, default 60)")
        self.jarvis_interval_entry = self._entry(g)
        self._label(g, "Numero massimo retry")
        self.jarvis_retries_entry = self._entry(g)

        dbg = self._group(scroll, "Debug supervisore")
        self.jarvis_debug_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dbg,
            text="Debug Supervisor",
            variable=self.jarvis_debug_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        avatar = self._group(scroll, "Avatar VISION")
        from utils.avatar_models import (
            AVATAR_MODE_3D,
            DEFAULT_AVATAR_MODEL_ID,
            avatar_mode_label,
            avatar_model_label,
            list_avatar_models,
        )

        self._label(avatar, "Modalità avatar")
        self.jarvis_avatar_mode_var = tk.StringVar(value=avatar_mode_label(AVATAR_MODE_3D))
        self.jarvis_avatar_mode_menu = ctk.CTkOptionMenu(
            avatar,
            values=["Avatar 3D (GLB)", "Avatar PNG"],
            variable=self.jarvis_avatar_mode_var,
            command=lambda _v: self._sync_avatar_mode_controls(),
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["panel"],
            height=36,
        )
        self.jarvis_avatar_mode_menu.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            avatar,
            text=(
                "Avatar 3D usa i modelli GLB e i pack sprite "
                "(clip Meshy in glb_frames, oppure model_frames/<id>/clips). "
                "Avatar PNG usa le lastre Character Bible; gli occhi cambiano "
                "colore in base allo stato (idle, ascolto, parlato, lavorazione, alert)."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self._label(avatar, "Modello 3D")
        self._avatar_model_choices = list_avatar_models()
        labels = [lab for _, lab in self._avatar_model_choices] or [
            avatar_model_label(DEFAULT_AVATAR_MODEL_ID)
        ]
        self.jarvis_avatar_model_var = tk.StringVar(value=labels[0])
        self.jarvis_avatar_model_menu = ctk.CTkOptionMenu(
            avatar,
            values=labels,
            variable=self.jarvis_avatar_model_var,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["panel"],
            height=36,
        )
        self.jarvis_avatar_model_menu.pack(fill="x", pady=(0, 4))
        self.jarvis_avatar_add_glb_btn = ctk.CTkButton(
            avatar,
            text="Aggiungi modello GLB…",
            command=self._add_avatar_glb,
            fg_color=COLORS["panel"],
            hover_color=COLORS["accent_hover"],
            border_width=1,
            border_color=COLORS["accent"],
            text_color=COLORS["text"],
            height=34,
        )
        self.jarvis_avatar_add_glb_btn.pack(fill="x", pady=(0, 4))
        self.jarvis_avatar_import_sprite_btn = ctk.CTkButton(
            avatar,
            text="Importa pack sprite…",
            command=self._import_avatar_sprite_pack,
            fg_color=COLORS["panel"],
            hover_color=COLORS["accent_hover"],
            border_width=1,
            border_color=COLORS["accent"],
            text_color=COLORS["text"],
            height=34,
        )
        self.jarvis_avatar_import_sprite_btn.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            avatar,
            text=(
                "Scegli il pack 3D mostrato nel pannello avatar. "
                "Meshy usa i clip in glb_frames; altri modelli usano "
                "model_frames/<id>/ (clip animati o anteprima statica). "
                "Importa un pack sprite (cartella con clips/ + manifest.json) "
                "o aggiungi un GLB. Solo UI — vedi SPRITE_PACK_SPEC.md."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w")
        self._sync_avatar_mode_controls()

        self._save_bar(scroll, lambda: self._save_module("Supervisor"))
        return frame

    def _build_diagnostica_panel(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        scroll = self._scroll(frame)
        self._module_title(
            scroll,
            "Diagnostica",
            "Debug applicazione, strumenti portale e log",
        )

        dbg = self._group(scroll, "Debug applicazione")
        self.debug_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dbg,
            text="Modalità DEBUG",
            variable=self.debug_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        ctk.CTkLabel(
            dbg,
            text="Quando attiva: logga URL, azioni, elementi ed errori nel log tecnico.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        logs = self._group(scroll, "Log")
        try:
            from utils.paths import logs_dir

            log_path = str(logs_dir())
        except Exception:
            log_path = "logs/"
        ctk.CTkLabel(
            logs,
            text="Directory log (sola lettura)",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")
        ctk.CTkLabel(
            logs,
            text=log_path,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        tools = self._group(scroll, "Strumenti portale EniSpace")
        for text, cmd, border in [
            ("Test accesso EniSpace", self._test_access, COLORS["accent"]),
            ("Apri Chrome (mappa portale)", self._record_nav, "#f59e0b"),
            ("Apri flusso documenti (Ordini→Market→Filtri)", self._open_document_flow, COLORS["accent"]),
            ("Apri Ordini e Consuntivi (eniSpace)", self._open_ordini, "#4ade80"),
            ("Apri Marketplace (ultimo URL imparato)", self._open_marketplace, "#38bdf8"),
        ]:
            ctk.CTkButton(
                tools,
                text=text,
                height=38,
                fg_color=COLORS["panel"],
                hover_color=COLORS["border"],
                border_width=1,
                border_color=border,
                command=cmd,
            ).pack(fill="x", pady=4)

        ctk.CTkLabel(
            scroll,
            text=(
                "«Apri Chrome» NON registra un account: apre il browser "
                "controllato dal programma. Tu navighi eniSpace; il log salva le URL visitate.\n"
                "Il link Marketplace può cambiare: il programma lo impara automaticamente."
            ),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self._save_bar(scroll, lambda: self._save_module("Diagnostica"))
        return frame

    def _save_module(self, module_name: str) -> None:
        try:
            self._save_all(module_name=module_name)
        except Exception as exc:
            self._set_status(f"Errore salvataggio {module_name}", ok=False)
            messagebox.showerror(
                "Impostazioni",
                f"Errore nel salvataggio del modulo {module_name}.\n{exc}",
                parent=self,
            )

    def _browse_jarvis_folder(self) -> None:
        current = self.jarvis_dl_entry.get().strip() or self.download_entry.get().strip()
        if not current:
            current = str(default_download_dir())
        chosen = filedialog.askdirectory(initialdir=current, parent=self)
        if chosen:
            self.jarvis_dl_entry.delete(0, "end")
            self.jarvis_dl_entry.insert(0, chosen)

    def _toggle_mail_password(self) -> None:
        self.imap_pass_entry.configure(
            show="" if self._show_mail_password.get() else "•"
        )

    def _section(self, parent, title: str) -> None:
        """Compat: intestazione sezione (legacy helpers / wizard-like callers)."""
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
        if hasattr(self, "chrome_system_var"):
            self.chrome_system_var.set(bool(getattr(settings, "chrome_use_system_profile", False)))
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
        if hasattr(self, "jarvis_avatar_mode_var"):
            from utils.avatar_models import avatar_mode_label, normalize_avatar_mode

            mode = normalize_avatar_mode(
                getattr(settings, "jarvis_avatar_mode", None)
            )
            self.jarvis_avatar_mode_var.set(avatar_mode_label(mode))
        if hasattr(self, "jarvis_avatar_model_var"):
            from utils.avatar_models import (
                avatar_model_label,
                list_avatar_models,
                normalize_avatar_model_id,
            )

            mid = normalize_avatar_model_id(
                getattr(settings, "jarvis_avatar_model", None)
            )
            choices = list_avatar_models()
            labels = [lab for _, lab in choices]
            if labels and hasattr(self, "jarvis_avatar_model_menu"):
                try:
                    self.jarvis_avatar_model_menu.configure(values=labels)
                except Exception:
                    pass
            self.jarvis_avatar_model_var.set(avatar_model_label(mid))
        if hasattr(self, "_sync_avatar_mode_controls"):
            self._sync_avatar_mode_controls()

    def _sync_avatar_mode_controls(self) -> None:
        """Enable GLB picker only in Avatar 3D mode."""
        from utils.avatar_models import AVATAR_MODE_3D, AVATAR_MODE_PNG, avatar_mode_from_label

        mode = AVATAR_MODE_3D
        if hasattr(self, "jarvis_avatar_mode_var"):
            mode = avatar_mode_from_label(self.jarvis_avatar_mode_var.get())
        png = mode == AVATAR_MODE_PNG
        state = "disabled" if png else "normal"
        for widget_name in (
            "jarvis_avatar_model_menu",
            "jarvis_avatar_add_glb_btn",
            "jarvis_avatar_import_sprite_btn",
        ):
            w = getattr(self, widget_name, None)
            if w is None:
                continue
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _refresh_avatar_model_menu(self, *, select_id: str = "") -> None:
        from utils.avatar_models import (
            DEFAULT_AVATAR_MODEL_ID,
            avatar_model_label,
            list_avatar_models,
            normalize_avatar_model_id,
        )

        choices = list_avatar_models()
        self._avatar_model_choices = choices
        labels = [lab for _, lab in choices] or [
            avatar_model_label(DEFAULT_AVATAR_MODEL_ID)
        ]
        mid = normalize_avatar_model_id(select_id) if select_id else ""
        label = avatar_model_label(mid) if mid else (
            self.jarvis_avatar_model_var.get() if hasattr(self, "jarvis_avatar_model_var") else labels[0]
        )
        if label not in labels:
            label = labels[0]
        if hasattr(self, "jarvis_avatar_model_menu"):
            try:
                self.jarvis_avatar_model_menu.configure(values=labels)
            except Exception:
                pass
        if hasattr(self, "jarvis_avatar_model_var"):
            self.jarvis_avatar_model_var.set(label)

    def _add_avatar_glb(self) -> None:
        """Copy a user GLB into assets/avatar/models and refresh the dropdown."""
        from utils.avatar_models import (
            AVATAR_MODE_PNG,
            avatar_mode_from_label,
            avatar_model_label,
            import_avatar_glb,
            try_render_avatar_preview,
        )

        if hasattr(self, "jarvis_avatar_mode_var"):
            if avatar_mode_from_label(self.jarvis_avatar_mode_var.get()) == AVATAR_MODE_PNG:
                messagebox.showinfo(
                    "Avatar PNG",
                    "Passa a «Avatar 3D (GLB)» per aggiungere un modello.",
                    parent=self,
                )
                return
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Seleziona modello GLB",
            filetypes=[("glTF Binary", "*.glb"), ("Tutti i file", "*.*")],
        )
        if not chosen:
            return
        try:
            mid, dest = import_avatar_glb(chosen, render_preview=False)
        except Exception as exc:
            messagebox.showerror(
                "Import GLB",
                f"Impossibile importare il modello:\n{exc}",
                parent=self,
            )
            return
        self._refresh_avatar_model_menu(select_id=mid)

        def _bg_preview() -> None:
            try:
                try_render_avatar_preview(mid)
            except Exception:
                pass

        threading.Thread(target=_bg_preview, daemon=True).start()
        messagebox.showinfo(
            "Modello aggiunto",
            (
                f"Importato «{avatar_model_label(mid)}» → {dest.name}\n"
                "Anteprima in generazione in background (Blender se disponibile)."
            ),
            parent=self,
        )

    def _import_avatar_sprite_pack(self) -> None:
        """Copy a sprite pack folder into model_frames/<id>/ and refresh dropdown."""
        from utils.avatar_models import (
            AVATAR_MODE_PNG,
            avatar_mode_from_label,
            avatar_model_label,
            import_avatar_sprite_pack,
        )

        if hasattr(self, "jarvis_avatar_mode_var"):
            if avatar_mode_from_label(self.jarvis_avatar_mode_var.get()) == AVATAR_MODE_PNG:
                messagebox.showinfo(
                    "Avatar PNG",
                    "Passa a «Avatar 3D (GLB)» per importare un pack sprite.",
                    parent=self,
                )
                return
        chosen = filedialog.askdirectory(
            parent=self,
            title="Seleziona cartella pack sprite (con clips/)",
        )
        if not chosen:
            return
        try:
            mid, dest = import_avatar_sprite_pack(chosen)
        except Exception as exc:
            messagebox.showerror(
                "Import pack sprite",
                f"Impossibile importare il pack:\n{exc}",
                parent=self,
            )
            return
        self._refresh_avatar_model_menu(select_id=mid)
        messagebox.showinfo(
            "Pack sprite importato",
            (
                f"Importato «{avatar_model_label(mid)}» → {dest}\n"
                "Seleziona il modello e salva. Clip mancanti usano idle/preview."
            ),
            parent=self,
        )

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
        if hasattr(self, "chrome_system_var"):
            settings.chrome_use_system_profile = bool(self.chrome_system_var.get())
            settings.chrome_profile_directory = "Default"
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
        if hasattr(self, "jarvis_avatar_mode_var"):
            from utils.avatar_models import avatar_mode_from_label

            settings.jarvis_avatar_mode = avatar_mode_from_label(
                self.jarvis_avatar_mode_var.get()
            )
        if hasattr(self, "jarvis_avatar_model_var"):
            from utils.avatar_models import (
                DEFAULT_AVATAR_MODEL_ID,
                avatar_model_id_from_label,
            )

            settings.jarvis_avatar_model = avatar_model_id_from_label(
                self.jarvis_avatar_model_var.get() or DEFAULT_AVATAR_MODEL_ID
            )
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

    def _save_all(self, module_name: Optional[str] = None) -> None:
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
        label = module_name or "Impostazioni"
        messagebox.showinfo(
            "Impostazioni",
            f"{label}: modifiche salvate.",
            parent=self,
        )
        self._set_status(f"{label}: salvato", ok=True)
        if self.on_activity:
            self.on_activity(f"{label}: impostazioni aggiornate.")

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



class SettingsWindow(ctk.CTkToplevel):
    """Dialog Impostazioni — monta SettingsPage (compat)."""

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
        self.title(f"Impostazioni — {APP_NAME}")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        self.grab_set()
        apply_app_icon(self)
        try:
            from ui.glass import schedule_window_glass
            from ui.theme import GLASS_ACRYLIC_ALPHA, GLASS_TINT, GLASS_WINDOW_ALPHA

            schedule_window_glass(
                self,
                delay_ms=80,
                alpha=GLASS_WINDOW_ALPHA,
                tint=GLASS_TINT,
                acrylic_alpha=GLASS_ACRYLIC_ALPHA,
            )
        except Exception:
            pass
        self.page = SettingsPage(
            self,
            db,
            credentials,
            enispace,
            on_saved=on_saved,
            on_test_access=on_test_access,
            on_record_navigation=on_record_navigation,
            on_open_marketplace=on_open_marketplace,
            on_open_ordini=on_open_ordini,
            on_open_document_flow=on_open_document_flow,
            on_activity=on_activity,
            show_chrome=True,
        )
        self.page.pack(fill="both", expand=True)
        self.after(50, self.focus)



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
