"""
Impostazioni → Trasporto Monete (VISION desktop).

UI adapted to VISION SettingsShell; field contract and save/load behavior
extracted from VIS Protocollo TransportMailSettingsPage + TransportPrintSettings
(see app.modules.coin_transport.settings_form).
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Optional

import customtkinter as ctk

from app.modules.coin_transport.settings_form import (
    ALLOWED_FONTS,
    KEYRING_COIN_TRANSPORT_MAIL,
    CoinTransportFormState,
    form_validation_errors,
    load_form_state,
    save_form,
)
from app.modules.coin_transport.workflow import COIN_TRANSPORT_STEPS, FINAL_STATUS
from app.modules.config.validate import ModuleConfigValidationError
from services.credential_service import CredentialService
from services.imap_mail_service import ImapConfig, ImapMailService
from ui.theme import COLORS, SUCCESS, WARNING, font_family

if TYPE_CHECKING:
    from database.db import Database


class CoinTransportSettingsPanel(ctk.CTkFrame):
    """Modular settings content for Trasporto Monete only."""

    def __init__(
        self,
        master,
        db: "Database",
        *,
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.db = db
        self.on_status = on_status
        self._creds = CredentialService(KEYRING_COIN_TRANSPORT_MAIL)
        self._show_imap_pass = tk.BooleanVar(value=False)
        self._build()
        self.reload()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        # Content packs into self — parent SettingsWindow supplies the scroll host.
        inner = self

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 4))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titles,
            text="Trasporto Monete",
            font=ctk.CTkFont(family=font_family(), size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="Configura e avvia il processo di Trasporto Monete su VIS Protocollo",
            font=ctk.CTkFont(family=font_family(), size=12),
            text_color=COLORS["muted"],
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        actions = ctk.CTkFrame(head, fg_color="transparent")
        actions.pack(side="right")
        ctk.CTkButton(
            actions,
            text="Apri VIS Protocollo",
            height=34,
            width=160,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._open_protocollo,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Salva impostazioni",
            height=34,
            width=150,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self.save,
        ).pack(side="left")

        # Status cards (real config/health only)
        status_row = ctk.CTkFrame(inner, fg_color="transparent")
        status_row.pack(fill="x", padx=8, pady=(10, 8))
        self._status_cards: dict[str, ctk.CTkLabel] = {}
        for key, title in (
            ("portal", "Stato portale"),
            ("session", "Sessione"),
            ("workflow", "Workflow"),
            ("document", "Documento"),
        ):
            card = ctk.CTkFrame(
                status_row,
                fg_color=COLORS["panel_alt"],
                corner_radius=10,
                border_width=1,
                border_color=COLORS["border"],
            )
            card.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(
                card, text=title, font=ctk.CTkFont(size=11), text_color=COLORS["muted"]
            ).pack(anchor="w", padx=10, pady=(8, 0))
            lab = ctk.CTkLabel(
                card,
                text="—",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text"],
            )
            lab.pack(anchor="w", padx=10, pady=(2, 10))
            self._status_cards[key] = lab

        # Workflow stepper from real COIN_TRANSPORT_STEPS
        wf = self._group(inner, "Workflow Trasporto Monete")
        self._step_labels: list[ctk.CTkLabel] = []
        for i, step in enumerate(COIN_TRANSPORT_STEPS[:6], start=1):
            row = ctk.CTkFrame(wf, fg_color="transparent")
            row.pack(fill="x", pady=2)
            lab = ctk.CTkLabel(
                row,
                text=f"{i}. {step.replace('_', ' ').title()}  ·  In attesa",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["muted"],
                anchor="w",
            )
            lab.pack(side="left", fill="x", expand=True)
            self._step_labels.append(lab)
        ctk.CTkLabel(
            wf,
            text=f"Stop operativo Agent: {FINAL_STATUS} (nessun invio PEC automatico).",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))
        gen_row = ctk.CTkFrame(wf, fg_color="transparent")
        gen_row.pack(fill="x", pady=(8, 0))
        self._btn_generate = ctk.CTkButton(
            gen_row,
            text="Genera documento",
            height=36,
            width=160,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["border"],
            state="disabled",
            command=self._generate_document_stub,
        )
        self._btn_generate.pack(side="left")
        ctk.CTkLabel(
            gen_row,
            text="Disponibile quando il runtime Trasporto Monete sarà operativo.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=12)

        mod = self._group(inner, "Modulo")
        self.enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            mod,
            text="Modulo Trasporto Monete abilitato (configurazione)",
            variable=self.enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)
        self._label(mod, "URL Protocollo")
        self.protocollo_url = self._entry(
            mod, placeholder_text="https://protocollo.example/..."
        )
        ctk.CTkLabel(
            mod,
            text='Usato dal pulsante "Apri VIS Protocollo".',
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 4))

        mail = self._group(inner, "Posta Trasporto (Sala Conta)")
        ctk.CTkLabel(
            mail,
            text=(
                "Casella IMAP dedicata per l'acquisizione allegati Sala Conta. "
                "Indipendente dalla Mail EniSpace e dalla PEC aziendale."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self.mailbox_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            mail,
            text="Abilita casella Posta Trasporto",
            variable=self.mailbox_enabled_var,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        self._label(mail, "Server IMAP")
        self.imap_host = self._entry(mail, placeholder_text="imap.provider.it")
        row = ctk.CTkFrame(mail, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Porta", text_color=COLORS["muted"]).pack(side="left")
        self.imap_port = ctk.CTkEntry(
            row, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.imap_port.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row, text="Sicurezza", text_color=COLORS["muted"]).pack(side="left")
        self.imap_security = tk.StringVar(value="SSL")
        ctk.CTkOptionMenu(
            row,
            values=["SSL", "STARTTLS", "NONE"],
            variable=self.imap_security,
            width=120,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(8, 0))

        self._label(mail, "Utente IMAP")
        self.imap_user = self._entry(mail)
        self._label(mail, "Password IMAP")
        pass_row = ctk.CTkFrame(mail, fg_color="transparent")
        pass_row.pack(fill="x", pady=(0, 4))
        self.imap_pass = ctk.CTkEntry(
            pass_row,
            height=36,
            show="•",
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
            placeholder_text="Lascia vuoto per mantenere la password salvata",
        )
        self.imap_pass.pack(side="left", fill="x", expand=True)
        ctk.CTkCheckBox(
            pass_row,
            text="Mostra",
            variable=self._show_imap_pass,
            command=lambda: self.imap_pass.configure(
                show="" if self._show_imap_pass.get() else "•"
            ),
            text_color=COLORS["muted"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(10, 0))
        self.pass_hint = ctk.CTkLabel(
            mail, text="", text_color=COLORS["muted"], font=ctk.CTkFont(size=11)
        )
        self.pass_hint.pack(anchor="w")

        self._label(mail, "Cartella / inbox da sincronizzare (obbligatoria)")
        self.imap_folder = self._entry(mail, placeholder_text="INBOX")

        smtp = self._group(inner, "SMTP opzionale (usi futuri)")
        self._label(smtp, "Server SMTP")
        self.smtp_host = self._entry(smtp, placeholder_text="smtp.provider.it")
        row_s = ctk.CTkFrame(smtp, fg_color="transparent")
        row_s.pack(fill="x", pady=4)
        ctk.CTkLabel(row_s, text="Porta", text_color=COLORS["muted"]).pack(side="left")
        self.smtp_port = ctk.CTkEntry(
            row_s, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.smtp_port.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_s, text="Sicurezza", text_color=COLORS["muted"]).pack(side="left")
        self.smtp_security = tk.StringVar(value="STARTTLS")
        ctk.CTkOptionMenu(
            row_s,
            values=["SSL", "STARTTLS", "NONE"],
            variable=self.smtp_security,
            width=120,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(8, 0))
        self._label(smtp, "Utente SMTP")
        self.smtp_user = self._entry(smtp)
        self._label(smtp, "Mittente")
        self.smtp_sender = self._entry(smtp)

        print_g = self._group(inner, "Documento / stampa (PDF)")
        self._label(print_g, "Carattere")
        self.font_family = tk.StringVar(value="Times New Roman")
        ctk.CTkOptionMenu(
            print_g,
            values=list(ALLOWED_FONTS),
            variable=self.font_family,
            fg_color=COLORS["input"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            height=36,
        ).pack(fill="x", pady=(0, 4))
        row_f = ctk.CTkFrame(print_g, fg_color="transparent")
        row_f.pack(fill="x", pady=4)
        ctk.CTkLabel(row_f, text="Dimensione (pt)", text_color=COLORS["muted"]).pack(
            side="left"
        )
        self.font_size = ctk.CTkEntry(
            row_f, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.font_size.pack(side="left", padx=(8, 16))
        ctk.CTkLabel(row_f, text="Interlinea", text_color=COLORS["muted"]).pack(side="left")
        self.line_spacing = ctk.CTkEntry(
            row_f, width=80, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.line_spacing.pack(side="left", padx=(8, 0))
        self._label(print_g, "Stampante (ref)")
        self.printer_ref = self._entry(print_g, placeholder_text="default")

        pec = self._group(inner, "Modalità prova PEC Trasporto")
        ctk.CTkLabel(
            pec,
            text=(
                "Quando attiva, la preparazione PEC deve usare l'indirizzo di test "
                "(le Questure reali non vengono contattate). Allineato a VIS Protocollo."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self.pec_test_mode = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            pec,
            text="Modalità prova attiva",
            variable=self.pec_test_mode,
            text_color=COLORS["text"],
            fg_color="#f59e0b",
            hover_color="#d97706",
        ).pack(anchor="w", pady=4)
        self._label(pec, "Indirizzo di test")
        self.pec_test_recipient = self._entry(pec, placeholder_text="test@esempio.it")
        self.pec_auto_send = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            pec,
            text="Auto-invio PEC (preferenza config; runtime Agent invariato)",
            variable=self.pec_auto_send,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(anchor="w", pady=4)

        paths = self._group(inner, "Template")
        self._label(paths, "Directory template")
        trow = ctk.CTkFrame(paths, fg_color="transparent")
        trow.pack(fill="x", pady=(0, 4))
        self.templates_dir = ctk.CTkEntry(
            trow, height=36, fg_color=COLORS["input"], border_color=COLORS["border"]
        )
        self.templates_dir.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            trow,
            text="Sfoglia",
            width=90,
            height=36,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self._browse_templates,
        ).pack(side="left", padx=(8, 0))

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=(4, 16))
        ctk.CTkButton(
            actions,
            text="Verifica IMAP",
            height=36,
            width=130,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self._test_imap,
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Salva modifiche",
            height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            command=self.save,
        ).pack(side="left", padx=(8, 0))

        self.feedback = ctk.CTkLabel(
            inner,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            wraplength=720,
            justify="left",
        )
        self.feedback.pack(anchor="w", padx=16, pady=(0, 12))

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

    # ------------------------------------------------------------------ data
    def _collect(self) -> CoinTransportFormState:
        def _int(entry: ctk.CTkEntry, default: int) -> int:
            try:
                return int(entry.get().strip() or str(default))
            except ValueError:
                return default

        def _float(entry: ctk.CTkEntry, default: float) -> float:
            try:
                return float(entry.get().strip().replace(",", ".") or str(default))
            except ValueError:
                return default

        return CoinTransportFormState(
            enabled=bool(self.enabled_var.get()),
            protocollo_url=self.protocollo_url.get().strip(),
            mailbox_enabled=bool(self.mailbox_enabled_var.get()),
            imap_host=self.imap_host.get().strip(),
            imap_port=_int(self.imap_port, 993),
            imap_security=self.imap_security.get() or "SSL",
            imap_username=self.imap_user.get().strip(),
            imap_password=self.imap_pass.get(),
            imap_folder=self.imap_folder.get().strip() or "INBOX",
            smtp_host=self.smtp_host.get().strip(),
            smtp_port=_int(self.smtp_port, 587),
            smtp_security=self.smtp_security.get() or "STARTTLS",
            smtp_username=self.smtp_user.get().strip(),
            smtp_password="",
            smtp_sender=self.smtp_sender.get().strip(),
            font_family=self.font_family.get() or "Times New Roman",
            font_size=_float(self.font_size, 9.0),
            line_spacing=_float(self.line_spacing, 1.5),
            pec_test_mode=bool(self.pec_test_mode.get()),
            pec_test_recipient=self.pec_test_recipient.get().strip(),
            pec_auto_send=bool(self.pec_auto_send.get()),
            templates_dir=self.templates_dir.get().strip(),
            printer_ref=self.printer_ref.get().strip() or "default",
        )

    def _apply_state(self, state: CoinTransportFormState) -> None:
        self.enabled_var.set(state.enabled)
        self.mailbox_enabled_var.set(state.mailbox_enabled)
        for entry, value in (
            (self.protocollo_url, state.protocollo_url),
            (self.imap_host, state.imap_host),
            (self.imap_port, str(state.imap_port)),
            (self.imap_user, state.imap_username),
            (self.imap_folder, state.imap_folder),
            (self.smtp_host, state.smtp_host),
            (self.smtp_port, str(state.smtp_port)),
            (self.smtp_user, state.smtp_username),
            (self.smtp_sender, state.smtp_sender),
            (self.font_size, str(state.font_size)),
            (self.line_spacing, str(state.line_spacing)),
            (self.pec_test_recipient, state.pec_test_recipient),
            (self.templates_dir, state.templates_dir),
            (self.printer_ref, state.printer_ref),
        ):
            entry.delete(0, "end")
            entry.insert(0, value or "")
        self.imap_pass.delete(0, "end")
        self.imap_security.set(state.imap_security or "SSL")
        self.smtp_security.set(state.smtp_security or "STARTTLS")
        self.font_family.set(state.font_family or "Times New Roman")
        self.pec_test_mode.set(state.pec_test_mode)
        self.pec_auto_send.set(state.pec_auto_send)
        if state.password_configured:
            self.pass_hint.configure(
                text="Password IMAP: configurata (Credential Manager)."
            )
        else:
            self.pass_hint.configure(text="Password IMAP: non configurata.")

    def reload(self) -> None:
        env = self.db.get_module_settings("coin_transport")
        creds = self._creds.load()
        state = load_form_state(
            env,
            password_configured=bool(creds and creds.password),
        )
        if creds and creds.username and not state.imap_username:
            state.imap_username = creds.username
        self._apply_state(state)
        self._refresh_status_cards(env, state)

    def _refresh_status_cards(
        self, env: Optional[dict], state: CoinTransportFormState
    ) -> None:
        enabled = bool(env and env.get("enabled")) if env else state.enabled
        mb_ok = bool(state.mailbox_enabled and state.imap_host and state.imap_username)
        self._status_cards["portal"].configure(
            text="Config locale" if enabled else "Modulo off",
            text_color=SUCCESS if enabled else COLORS["muted"],
        )
        self._status_cards["session"].configure(
            text="Mailbox OK" if mb_ok else "Mailbox da configurare",
            text_color=SUCCESS if mb_ok else WARNING,
        )
        self._status_cards["workflow"].configure(
            text="Pronto config" if mb_ok and enabled else "In attesa",
            text_color=SUCCESS if (mb_ok and enabled) else COLORS["muted"],
        )
        self._status_cards["document"].configure(
            text="Nessun documento",
            text_color=COLORS["muted"],
        )
        # Reflect last known steps if any job metadata were stored later
        for lab in self._step_labels:
            lab.configure(text_color=COLORS["muted"])

    def _open_protocollo(self) -> None:
        url = self.protocollo_url.get().strip()
        if not url:
            url = (
                os.environ.get("VISION_PROTOCOLLO_URL")
                or os.environ.get("VIS_PROTOCOLLO_URL")
                or ""
            ).strip()
        if not url:
            env = self.db.get_module_settings("coin_transport") or {}
            specific = env.get("module_specific") if isinstance(env, dict) else {}
            ops = (
                specific.get("operations")
                if isinstance(specific, dict)
                else {}
            )
            if isinstance(ops, dict):
                url = str(ops.get("portal_url") or ops.get("protocollo_url") or "").strip()
        if not url:
            messagebox.showinfo(
                "VIS Protocollo",
                "URL VIS Protocollo non configurato.\n"
                "Imposta il campo «URL Protocollo» nelle Impostazioni "
                "Trasporto Monete (oppure VISION_PROTOCOLLO_URL nell'ambiente).",
                parent=self._toplevel(),
            )
            self._feedback("URL Protocollo non configurato", ok=False)
            return
        try:
            webbrowser.open(url)
            self._feedback(f"Apertura Protocollo: {url}", ok=True)
        except Exception as exc:
            messagebox.showerror(
                "VIS Protocollo",
                f"Impossibile aprire il browser.\n{exc}",
                parent=self._toplevel(),
            )

    def _generate_document_stub(self) -> None:
        messagebox.showinfo(
            "Trasporto Monete",
            "Generazione documento non ancora disponibile nel runtime Agent.\n"
            "Il workflow skeleton si ferma a: "
            f"{FINAL_STATUS}.",
            parent=self._toplevel(),
        )

    def save(self) -> None:
        state = self._collect()
        try:
            save_form(self.db, state, credentials=self._creds)
        except ModuleConfigValidationError as exc:
            msg = "; ".join(exc.errors) if exc.errors else str(exc)
            self._feedback(msg, ok=False)
            messagebox.showerror("Trasporto Monete", msg, parent=self._toplevel())
            return
        except Exception as exc:
            self._feedback(f"Errore salvataggio: {exc}", ok=False)
            messagebox.showerror(
                "Trasporto Monete",
                f"Salvataggio non riuscito.\n{exc}",
                parent=self._toplevel(),
            )
            return
        self.reload()
        self._feedback("Configurazione Trasporto Monete salvata.", ok=True)
        messagebox.showinfo(
            "Trasporto Monete",
            "Modifiche salvate.",
            parent=self._toplevel(),
        )

    def _toplevel(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return None

    def _browse_templates(self) -> None:
        current = self.templates_dir.get().strip() or str(Path.cwd())
        chosen = filedialog.askdirectory(
            initialdir=current, parent=self._toplevel()
        )
        if chosen:
            self.templates_dir.delete(0, "end")
            self.templates_dir.insert(0, chosen)

    def _test_imap(self) -> None:
        state = self._collect()
        errs = form_validation_errors(state)
        # folder-only soft for test
        password = state.imap_password
        if not password:
            creds = self._creds.load()
            password = creds.password if creds else ""
        if not state.imap_host or not state.imap_username or not password:
            self._feedback(
                "Per Verifica IMAP servono host, utente e password (o password già salvata).",
                ok=False,
            )
            return
        if errs and any("font" in e.lower() or "interlinea" in e.lower() for e in errs):
            pass  # print fields irrelevant for IMAP test

        cfg = ImapConfig(
            host=state.imap_host,
            port=int(state.imap_port),
            security=state.imap_security,
            username=state.imap_username,
            password=password,
            folder=state.imap_folder or "INBOX",
        )
        self._feedback("Verifica IMAP in corso…", ok=None)

        def work() -> None:
            try:
                ok, info, _folders = ImapMailService(cfg).test_connection()
            except Exception as exc:
                ok, info = False, str(exc)
            self.after(0, lambda: self._feedback(info, ok=ok))

        threading.Thread(target=work, daemon=True).start()

    def _feedback(self, message: str, *, ok: Optional[bool]) -> None:
        color = COLORS["muted"]
        if ok is True:
            color = COLORS["success"]
        elif ok is False:
            color = COLORS["danger"]
        self.feedback.configure(text=message, text_color=color)
        if self.on_status:
            self.on_status(message, ok)
