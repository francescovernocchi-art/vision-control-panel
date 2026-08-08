"""Finestra principale VIS | eniSpace Utility."""

from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

import customtkinter as ctk

from database.db import Database
from database.models import Document, DocumentStatus, OperationResult
from services.batch_service import BatchItemResult, BatchService
from services.browser_service import BrowserConfig, BrowserService
from services.credential_service import CredentialService
from services.download_service import DownloadService
from services.email_parser import AcquisitionNotification, parse_eml_file
from services.enispace_service import AttachmentInfo, EniSpaceService
from services.exceptions import (
    EniSpaceError,
    SelectorsNotConfiguredError,
)
from services.print_queue_service import PrintQueueService
from services.worker import BackgroundWorker
from services.jarvis import JarvisSupervisor
from services.jarvis.models import JarvisSettings
from services.jarvis.states import LogLevel
from ui.components import (
    AppHeader,
    Card,
    JarvisSupervisorCard,
    MetricCard,
    PageNavigator,
    Sidebar,
    WorkflowStrip,
    styled_textbox,
)
from ui.settings_window import SettingsWindow, SetupWizard
from ui.icons import apply_app_icon
from ui.jarvis_avatar import JarvisAvatarPanel
from ui.theme import APP_VERSION, COLORS, SUCCESS, apply_treeview_style, font_family
from ui.toast import ToastManager
from utils.logger import drain_gui_log_queue, get_logger, set_debug_mode
from utils.paths import APP_NAME, default_download_dir
from utils.pdf_preview import render_pdf_thumbnail

logger = get_logger("ui")


STATUS_ICON = {
    DocumentStatus.DOWNLOADED: "✓",
    DocumentStatus.AVAILABLE: "○",
    DocumentStatus.NEW: "●",
    DocumentStatus.FAILED: "✗",
    DocumentStatus.SKIPPED: "○",
}

_PAGE_META = {
    "dashboard": ("Dashboard", "Panoramica operativa"),
    "ricerca": ("Ricerca", "Cerca ordini e scarica allegati"),
    "mail": ("Mail", "Registro mail gestite"),
    "documenti": ("Documenti", "Allegati e download"),
    "coda": ("Coda stampa", "PDF in attesa di stampa"),
    "jarvis": ("JARVIS", "Supervisore automatico"),
    "storico": ("Storico", "Contratti ricercati"),
}


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(f"VIS | eniSpace Utility")
        self.geometry("1280x820")
        self.minsize(1024, 700)
        self.configure(fg_color=COLORS["bg"])
        apply_app_icon(self)
        self._current_page = "dashboard"
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._toasts = ToastManager(self)
        self._jarvis_pulse_job: Optional[str] = None

        self.db = Database()
        settings = self.db.get_settings()
        set_debug_mode(settings.debug_mode)

        self.credentials = CredentialService()
        self.browser = BrowserService(
            BrowserConfig(
                headless=False,
                hidden=bool(settings.browser_hidden),
                timeout_ms=settings.browser_timeout_ms,
                debug=settings.debug_mode,
            )
        )
        self.download_service = DownloadService(
            settings.download_folder or str(default_download_dir())
        )
        self.enispace = EniSpaceService(
            self.browser,
            self.credentials,
            base_url=settings.enispace_base_url,
            timeout_ms=settings.browser_timeout_ms,
            debug=settings.debug_mode,
            db=self.db,
        )
        self.print_queue = PrintQueueService(self.db)
        self.batch_service = BatchService(
            db=self.db,
            enispace=self.enispace,
            download_service=self.download_service,
            print_queue=self.print_queue,
        )
        self.worker = BackgroundWorker()
        self.jarvis = JarvisSupervisor(
            db=self.db,
            batch=self.batch_service,
            print_queue=self.print_queue,
            imap_config_factory=self._jarvis_imap_config,
            settings_factory=self._jarvis_settings,
            is_app_busy=self._jarvis_app_busy,
            on_ui_refresh=self._jarvis_ui_refresh,
        )
        self.jarvis.logger.add_listener(self._on_jarvis_log_entry)
        try:
            self.jarvis.notifications.add_listener(self._on_jarvis_notify)
        except Exception:
            pass

        self._current_contract: Optional[str] = None
        self._current_notification: Optional[AcquisitionNotification] = None
        self._documents: list[Document] = []
        self._doc_vars: list[tk.BooleanVar] = []
        self._busy = False
        self._settings_win: Optional[SettingsWindow] = None
        self._autosync_after_id: Optional[str] = None
        self._autosync_running = False
        self._jarvis_selected_id: Optional[int] = None
        # Coda callables UI: i worker NON devono chiamare after()/widget direttamente
        # (su Windows tk.call cross-thread + lock logging = deadlock «App non risponde»).
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._ui_pump_alive = True
        self._extracted_pdf_paths: list[Path] = []
        self._pdf_preview_image = None  # keep CTkImage ref alive

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(50, self._pump_ui)
        self.after(200, self._post_init)

    # ================================================================== UI
    def _build_ui(self) -> None:
        shell = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        shell.pack(fill="both", expand=True)

        self.sidebar = Sidebar(
            shell,
            on_navigate=self._navigate,
            version=APP_VERSION,
        )
        self.sidebar.pack(side="left", fill="y")

        right = ctk.CTkFrame(shell, fg_color=COLORS["bg"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self.app_header = AppHeader(
            right,
            on_settings=self.open_settings,
            on_record=self._start_recording,
            on_help=self.show_recording_help,
        )
        self.app_header.pack(fill="x")
        # Legacy alias used by set_session_ui
        self.session_label = self.app_header.session_label

        self.content = ctk.CTkFrame(right, fg_color=COLORS["bg"], corner_radius=0)
        self.content.pack(fill="both", expand=True, padx=16, pady=12)

        # Pages (replace CTkTabview — same widget trees, new chrome)
        self.tab_dashboard = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_search = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_queue = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_jarvis = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_register = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_history = ctk.CTkFrame(self.content, fg_color="transparent")

        self._pages = {
            "dashboard": self.tab_dashboard,
            "ricerca": self.tab_search,
            "mail": self.tab_register,
            "documenti": self.tab_search,
            "coda": self.tab_queue,
            "jarvis": self.tab_jarvis,
            "storico": self.tab_history,
        }

        self.tabs = PageNavigator(self._navigate, lambda: self._current_page)

        self._build_dashboard()
        self._build_search_tab()
        self._build_print_queue_tab()
        self._build_jarvis_tab()
        self._build_register_tab()
        self._build_history_tab()

        self._navigate("dashboard")

    def _navigate(self, key: str) -> None:
        if key == "impostazioni":
            self.open_settings()
            return
        page = self._pages.get(key)
        if page is None:
            return
        self._current_page = key
        seen: set[int] = set()
        for frame in self._pages.values():
            fid = id(frame)
            if fid in seen:
                continue
            seen.add(fid)
            if frame is page:
                continue
            try:
                frame.pack_forget()
            except Exception:
                pass
        page.pack(fill="both", expand=True)
        self.sidebar.set_active(key)
        title, subtitle = _PAGE_META.get(key, ("VIS", ""))
        self.app_header.set_page(title, subtitle)
        if key in ("dashboard", "jarvis", "coda", "mail"):
            try:
                self._refresh_dashboard_metrics()
            except Exception:
                pass

    def _build_dashboard(self) -> None:
        parent = self.tab_dashboard
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        kpi_row = ctk.CTkFrame(scroll, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 10))
        for i in range(4):
            kpi_row.grid_columnconfigure(i, weight=1)

        self.kpi_queue = MetricCard(kpi_row, "In coda stampa", "0", "PDF pending")
        self.kpi_queue.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.kpi_jarvis = MetricCard(kpi_row, "Job JARVIS", "0", "In attesa")
        self.kpi_jarvis.grid(row=0, column=1, sticky="nsew", padx=4)
        self.kpi_mail = MetricCard(kpi_row, "Mail registro", "0", "Ultime voci")
        self.kpi_mail.grid(row=0, column=2, sticky="nsew", padx=4)
        self.kpi_session = MetricCard(kpi_row, "Sessione", "Offline", "eniSpace")
        self.kpi_session.grid(row=0, column=3, sticky="nsew", padx=(8, 0))

        mid = ctk.CTkFrame(scroll, fg_color="transparent")
        mid.pack(fill="x", pady=(0, 10))
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_columnconfigure(2, weight=0, minsize=320)

        self.dash_jarvis_card = JarvisSupervisorCard(
            mid, on_open=lambda: self._navigate("jarvis")
        )
        self.dash_jarvis_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        wf_card = Card(mid, title="Workflow", subtitle="Pipeline operativa")
        wf_card.grid(row=0, column=1, sticky="nsew", padx=4)
        self.dash_workflow = WorkflowStrip(wf_card.body)
        self.dash_workflow.pack(fill="x", pady=4)
        self.dash_workflow.set_states(["waiting"] * 6)

        try:
            self.dash_jarvis_avatar = JarvisAvatarPanel(
                mid,
                size=300,
                level_provider=self._jarvis_avatar_level,
            )
            self.dash_jarvis_avatar.grid(
                row=0, column=2, sticky="n", padx=(8, 0)
            )
        except Exception as exc:
            logger.warning("Avatar dashboard non disponibile: %s", exc)
            self.dash_jarvis_avatar = None

        console_card = Card(scroll, title="ATTIVITÀ JARVIS", subtitle="ORA · TIPO · MESSAGGIO")
        console_card.pack(fill="both", expand=True, pady=(0, 10))
        self.activity_box = styled_textbox(console_card.body, height=160, state="disabled")
        self.activity_box.pack(fill="both", expand=True)
        try:
            tb = self.activity_box._textbox  # noqa: SLF001
            tb.tag_configure("INFO", foreground=COLORS["text"])
            tb.tag_configure("SUCCESS", foreground=SUCCESS)
            tb.tag_configure("WARNING", foreground=COLORS["warning"])
            tb.tag_configure("ERROR", foreground=COLORS["danger"])
        except Exception:
            pass

        jobs_card = Card(scroll, title="Lavorazioni recenti", subtitle="Ultimi job JARVIS")
        jobs_card.pack(fill="both", expand=True, pady=(0, 4))
        style_name = apply_treeview_style("DashJobs.Treeview")
        cols = ("ora", "ordine", "esito", "durata")
        self.dash_jobs_tree = ttk.Treeview(
            jobs_card.body,
            columns=cols,
            show="headings",
            style=style_name,
            height=6,
            selectmode="browse",
        )
        for key, title, w in (
            ("ora", "Ora", 80),
            ("ordine", "Ordine", 120),
            ("esito", "Esito", 140),
            ("durata", "Durata", 80),
        ):
            self.dash_jobs_tree.heading(key, text=title)
            self.dash_jobs_tree.column(key, width=w)
        self.dash_jobs_tree.pack(fill="both", expand=True)

    def _refresh_dashboard_metrics(self) -> None:
        if not hasattr(self, "kpi_queue"):
            return
        try:
            pending = self.print_queue.count_pending()
        except Exception:
            pending = 0
        self.kpi_queue.set_value(str(pending), "PDF pending")

        try:
            snap = self.jarvis.snapshot()
            self.kpi_jarvis.set_value(
                str(snap.get("pending", 0)),
                "ONLINE" if snap.get("active") else "OFFLINE",
            )
            self.dash_jarvis_card.status.set_status(
                bool(snap.get("active")),
                "ONLINE" if snap.get("active") else "OFFLINE",
            )
            self.dash_jarvis_card.meta.configure(
                text=(
                    f"In coda: {snap.get('pending', 0)}  ·  "
                    f"Ultimo controllo: {snap.get('last_check', '—')}\n"
                    f"In lavorazione: {snap.get('current_job', '—')}"
                )
            )
            if getattr(self, "dash_jarvis_avatar", None) is not None:
                try:
                    self.dash_jarvis_avatar.update_from_snapshot(snap)
                except Exception:
                    pass
            # Workflow heuristic from jarvis state
            st = str(snap.get("state", "")).upper()
            if not snap.get("active"):
                self.dash_workflow.set_states(["waiting"] * 6)
            elif "ERROR" in st or "ATTENTION" in st:
                self.dash_workflow.set_states(
                    ["done", "done", "active", "waiting", "waiting", "error"]
                )
            elif snap.get("processing"):
                self.dash_workflow.set_states(
                    ["done", "done", "active", "active", "waiting", "waiting"]
                )
            else:
                self.dash_workflow.set_states(
                    ["done", "done", "done", "done", "done", "done"]
                    if snap.get("last_job") not in (None, "—", "")
                    else ["waiting"] * 6
                )
        except Exception:
            pass

        try:
            regs = self.db.list_mail_register(limit=200)
            self.kpi_mail.set_value(str(len(regs)), "voci recenti")
        except Exception:
            pass

        if hasattr(self, "dash_jobs_tree"):
            for item in self.dash_jobs_tree.get_children():
                self.dash_jobs_tree.delete(item)
            try:
                for job in self.jarvis.repo.list_jobs(limit=12):
                    created = job.created_at or ""
                    ora = created[11:19] if len(created) >= 19 else created
                    self.dash_jobs_tree.insert(
                        "",
                        "end",
                        values=(
                            ora,
                            job.order_number or "—",
                            job.outcome or job.status or "—",
                            job.duration_label,
                        ),
                    )
            except Exception:
                pass

    def _build_search_tab(self) -> None:
        parent = self.tab_search

        # Search section
        search = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        search.pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(
            search,
            text="Numero ordine (dalla mail Marketplace)",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=16, pady=(12, 0))

        row = ctk.CTkFrame(search, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 8))

        self.contract_entry = ctk.CTkEntry(
            row,
            height=42,
            placeholder_text="es. 4310758365",
            font=ctk.CTkFont(size=16),
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
        )
        self.contract_entry.pack(side="left", fill="x", expand=True)
        self.contract_entry.bind("<Return>", lambda _e: self.search_contract())

        self.btn_search = ctk.CTkButton(
            row,
            text="CERCA ORDINE",
            width=160,
            height=42,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self.search_contract,
        )
        self.btn_search.pack(side="left", padx=(10, 0))

        self.btn_import_eml = ctk.CTkButton(
            row,
            text="IMPORTA .EML",
            width=130,
            height=42,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self.import_eml,
        )
        self.btn_import_eml.pack(side="left", padx=(8, 0))

        self.btn_batch_eml = ctk.CTkButton(
            row,
            text="ELABORA MAIL",
            width=140,
            height=42,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            font=ctk.CTkFont(weight="bold"),
            command=self.batch_process_eml,
        )
        self.btn_batch_eml.pack(side="left", padx=(8, 0))

        self.btn_imap = ctk.CTkButton(
            row,
            text="SYNC CASELLA",
            width=140,
            height=42,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(weight="bold"),
            command=self.sync_imap_folder,
        )
        self.btn_imap.pack(side="left", padx=(8, 0))

        self.btn_reprocess_today = ctk.CTkButton(
            row,
            text="RIELABORA OGGI",
            width=150,
            height=42,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            font=ctk.CTkFont(weight="bold"),
            command=self.reprocess_today_imap,
        )
        self.btn_reprocess_today.pack(side="left", padx=(8, 0))

        autosync = ctk.CTkFrame(search, fg_color="transparent")
        autosync.pack(fill="x", padx=16, pady=(0, 4))
        self.autosync_var = tk.BooleanVar(value=False)
        self.chk_autosync = ctk.CTkCheckBox(
            autosync,
            text="Autosync",
            variable=self.autosync_var,
            command=self._on_autosync_toggled,
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        self.chk_autosync.pack(side="left")
        ctk.CTkLabel(
            autosync,
            text="ogni",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(12, 4))
        self.autosync_interval_var = tk.StringVar(value="15")
        self.spin_autosync = ctk.CTkEntry(
            autosync,
            width=56,
            height=28,
            textvariable=self.autosync_interval_var,
            fg_color=COLORS["input"],
            border_color=COLORS["border"],
            font=ctk.CTkFont(size=13),
        )
        self.spin_autosync.pack(side="left")
        self.spin_autosync.bind("<Return>", lambda _e: self._save_autosync_from_ui())
        self.spin_autosync.bind("<FocusOut>", lambda _e: self._save_autosync_from_ui())
        ctk.CTkLabel(
            autosync,
            text="min",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(4, 8))
        self.autosync_status_label = ctk.CTkLabel(
            autosync,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
        )
        self.autosync_status_label.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            search,
            text=(
                "«SYNC CASELLA» / Autosync: mail nuove (non lette). "
                "«RIELABORA OGGI»: ritenta le MdA di oggi fallite/non gestite. "
                "Su errore la mail resta non letta. «ELABORA MAIL» usa file .eml locali."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # Progress
        self.progress_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ricerca ordine in corso...",
            text_color=COLORS["muted"],
        )
        self.progress_label.pack(anchor="w")
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, progress_color=COLORS["accent"]
        )
        self.progress_bar.pack(fill="x", pady=(4, 0))
        self.progress_bar.configure(mode="indeterminate")

        # Results summary
        self.summary_frame = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        self.summary_frame.pack(fill="x", pady=(0, 10))
        self.summary_label = ctk.CTkLabel(
            self.summary_frame,
            text="Nessun ordine caricato.",
            text_color=COLORS["muted"],
            justify="left",
            font=ctk.CTkFont(size=14),
        )
        self.summary_label.pack(anchor="w", padx=16, pady=14)

        # Documents list
        docs_header = ctk.CTkFrame(parent, fg_color="transparent")
        docs_header.pack(fill="x")
        ctk.CTkLabel(
            docs_header,
            text="Documenti / allegati",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")

        self.docs_container = ctk.CTkScrollableFrame(
            parent, fg_color=COLORS["panel"], corner_radius=10, height=280
        )
        self.docs_container.pack(fill="both", expand=True, pady=(6, 10))

        # Column header
        cols = ctk.CTkFrame(self.docs_container, fg_color="transparent")
        cols.pack(fill="x", padx=8, pady=(4, 2))
        for text, width in [
            ("", 28),
            ("Stato", 50),
            ("Nome documento", 280),
            ("Tipo", 60),
            ("Dimensione", 90),
            ("Data", 100),
            ("Azione", 90),
        ]:
            ctk.CTkLabel(
                cols,
                text=text,
                width=width,
                anchor="w",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=4)

        self.docs_list = ctk.CTkFrame(self.docs_container, fg_color="transparent")
        self.docs_list.pack(fill="both", expand=True)

        # Actions
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 8))

        self.btn_dl_all = ctk.CTkButton(
            actions,
            text="SCARICA TUTTO",
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self.download_all,
        )
        self.btn_dl_all.pack(side="left", padx=(0, 8))

        self.btn_dl_sel = ctk.CTkButton(
            actions,
            text="SCARICA SELEZIONATI",
            height=36,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["accent"],
            hover_color=COLORS["border"],
            command=self.download_selected,
        )
        self.btn_dl_sel.pack(side="left", padx=(0, 8))

        self.btn_open_folder = ctk.CTkButton(
            actions,
            text="APRI CARTELLA",
            height=36,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self.open_download_folder,
        )
        self.btn_open_folder.pack(side="left", padx=(0, 8))

        self.btn_refresh = ctk.CTkButton(
            actions,
            text="AGGIORNA CONTRATTO",
            height=36,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self.refresh_contract,
        )
        self.btn_refresh.pack(side="left")

    def _build_print_queue_tab(self) -> None:
        parent = self.tab_queue

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(
            top,
            text="Coda di stampa (PDF da elaborazione mail)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")

        self.btn_print_queue = ctk.CTkButton(
            top,
            text="STAMPA CODA",
            width=140,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self.print_queue_cascade,
        )
        self.btn_print_queue.pack(side="right")

        ctk.CTkButton(
            top,
            text="Svuota",
            width=90,
            height=32,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["border"],
            hover_color=COLORS["border"],
            command=self.clear_print_queue,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            top,
            text="Rimuovi",
            width=90,
            height=32,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self.remove_selected_print_item,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            top,
            text="Aggiorna",
            width=90,
            height=32,
            fg_color=COLORS["panel"],
            hover_color=COLORS["border"],
            command=self.refresh_print_queue,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkLabel(
            parent,
            text=(
                "Durante sync/batch i PDF estratti compaiono qui man mano. "
                "La coda stampa si riempie automaticamente (senza chiedere conferma). "
                "«STAMPA CODA» invia i pending alla stampante predefinita Windows."
            ),
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        # --- PDF estratti (aggiornamento progressivo) ---
        extracted = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        extracted.pack(fill="x", pady=(0, 10))
        head = ctk.CTkFrame(extracted, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            head,
            text="PDF ESTRATTI",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        ctk.CTkButton(
            head,
            text="Apri cartella",
            width=110,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=COLORS["border"],
            hover_color=COLORS["border"],
            command=self._open_latest_extracted_folder,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            head,
            text="Apri PDF",
            width=90,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=COLORS["border"],
            hover_color=COLORS["border"],
            command=self._open_selected_extracted_pdf,
        ).pack(side="right")

        body = ctk.CTkFrame(extracted, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)

        list_wrap = ctk.CTkFrame(body, fg_color=COLORS["input"], corner_radius=6)
        list_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.extracted_listbox = tk.Listbox(
            list_wrap,
            height=5,
            bg=COLORS["input"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground=COLORS["text"],
            highlightthickness=0,
            borderwidth=0,
            font=("Segoe UI", 11),
            activestyle="none",
        )
        self.extracted_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self.extracted_listbox.bind(
            "<<ListboxSelect>>", lambda _e: self._on_extracted_select()
        )

        preview_col = ctk.CTkFrame(body, fg_color="transparent", width=160)
        preview_col.grid(row=0, column=1, sticky="ns")
        preview_col.grid_propagate(False)
        self.extracted_latest_label = ctk.CTkLabel(
            preview_col,
            text="Nessun PDF estratto in questa sessione.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
            wraplength=150,
            justify="left",
            anchor="nw",
        )
        self.extracted_latest_label.pack(anchor="w", fill="x")
        self.extracted_preview_label = ctk.CTkLabel(
            preview_col,
            text="",
            text_color=COLORS["muted"],
            width=140,
            height=160,
        )
        self.extracted_preview_label.pack(anchor="w", pady=(6, 0))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        apply_treeview_style("Queue.Treeview")
        style.configure(
            "Queue.Treeview",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["panel"],
            rowheight=30,
            borderwidth=0,
        )
        style.configure(
            "Queue.Treeview.Heading",
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
            relief="flat",
        )
        style.map("Queue.Treeview", background=[("selected", COLORS["accent"])])

        tree_frame = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        tree_frame.pack(fill="both", expand=True)

        columns = ("ordine", "modulo", "file", "eml", "stato", "quando")
        self.queue_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Queue.Treeview",
            selectmode="browse",
        )
        self.queue_tree.heading("ordine", text="Ordine")
        self.queue_tree.heading("modulo", text="MdA")
        self.queue_tree.heading("file", text="File PDF")
        self.queue_tree.heading("eml", text="Mail .eml")
        self.queue_tree.heading("stato", text="Stato")
        self.queue_tree.heading("quando", text="In coda")
        self.queue_tree.column("ordine", width=120)
        self.queue_tree.column("modulo", width=120)
        self.queue_tree.column("file", width=220)
        self.queue_tree.column("eml", width=200)
        self.queue_tree.column("stato", width=90)
        self.queue_tree.column("quando", width=140)
        self.queue_tree.pack(fill="both", expand=True, padx=8, pady=8)

        self.queue_status_label = ctk.CTkLabel(
            parent,
            text="Coda vuota.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        )
        self.queue_status_label.pack(anchor="w", pady=(8, 0))

    def _build_jarvis_tab(self) -> None:
        parent = self.tab_jarvis

        self.jarvis_sim_banner = ctk.CTkLabel(
            parent,
            text="JARVIS — SIMULAZIONE",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#0f172a",
            fg_color="#f59e0b",
            corner_radius=6,
            height=28,
        )
        # mostrato solo se simulazione attiva

        status = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["accent"],
        )
        self._jarvis_status_frame = status
        status.pack(fill="x", pady=(4, 8))

        status_body = ctk.CTkFrame(status, fg_color="transparent")
        status_body.pack(fill="x", padx=10, pady=8)
        status_body.grid_columnconfigure(0, weight=1)
        status_body.grid_columnconfigure(1, weight=0)

        left_status = ctk.CTkFrame(status_body, fg_color="transparent")
        left_status.grid(row=0, column=0, sticky="nsew", padx=(4, 8))

        head = ctk.CTkFrame(left_status, fg_color="transparent")
        head.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(
            head,
            text="JARVIS SUPERVISORE",
            font=ctk.CTkFont(family=font_family(), size=16, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        self.jarvis_online_label = ctk.CTkLabel(
            head,
            text="○ OFFLINE",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["muted"],
        )
        self.jarvis_online_label.pack(side="right")

        self.jarvis_state_label = ctk.CTkLabel(
            left_status,
            text="Stato: OFFLINE",
            font=ctk.CTkFont(size=15),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
        )
        self.jarvis_state_label.pack(fill="x", padx=4, pady=2)

        self.jarvis_meta_label = ctk.CTkLabel(
            left_status,
            text="Ultimo controllo: —\nUltima lavorazione: —\nIn coda: 0\nIn lavorazione: —",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self.jarvis_meta_label.pack(fill="x", padx=4, pady=(2, 10))

        try:
            self.jarvis_avatar = JarvisAvatarPanel(
                status_body,
                size=320,
                level_provider=self._jarvis_avatar_level,
            )
            self.jarvis_avatar.grid(row=0, column=1, sticky="ne", padx=(8, 4))
        except Exception as exc:
            logger.warning("Avatar tab JARVIS non disponibile: %s", exc)
            self.jarvis_avatar = None

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 8))
        self.btn_jarvis_on = ctk.CTkButton(
            btns,
            text="ATTIVA JARVIS",
            height=36,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._jarvis_activate,
        )
        self.btn_jarvis_on.pack(side="left", padx=(0, 8))
        self.btn_jarvis_off = ctk.CTkButton(
            btns,
            text="DISATTIVA JARVIS",
            height=36,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["danger"],
            hover_color=COLORS["border"],
            command=self._jarvis_deactivate,
        )
        self.btn_jarvis_off.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btns,
            text="Aggiorna storico",
            height=36,
            width=140,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["border"],
            hover_color=COLORS["border"],
            command=self.refresh_jarvis_history,
        ).pack(side="right")

        # Console + storico affiancati
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)

        left = ctk.CTkFrame(body, fg_color=COLORS["panel"], corner_radius=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        console_head = ctk.CTkFrame(left, fg_color="transparent")
        console_head.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            console_head,
            text="CONSOLE JARVIS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")
        ctk.CTkButton(
            console_head,
            text="SVUOTA LOG VISIVO",
            width=150,
            height=28,
            fg_color=COLORS["panel"],
            border_width=1,
            border_color=COLORS["border"],
            hover_color=COLORS["border"],
            command=self._jarvis_clear_console,
        ).pack(side="right")
        self.jarvis_console = ctk.CTkTextbox(
            left,
            height=220,
            fg_color=COLORS["input"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled",
        )
        self.jarvis_console.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        # Tag colori
        try:
            self.jarvis_console._textbox.tag_configure(  # noqa: SLF001
                "INFO", foreground="#e2e8f0"
            )
            self.jarvis_console._textbox.tag_configure(  # noqa: SLF001
                "SUCCESS", foreground="#4ade80"
            )
            self.jarvis_console._textbox.tag_configure(  # noqa: SLF001
                "WARNING", foreground="#fb923c"
            )
            self.jarvis_console._textbox.tag_configure(  # noqa: SLF001
                "ERROR", foreground="#f87171"
            )
        except Exception:
            pass

        right = ctk.CTkFrame(body, fg_color=COLORS["panel"], corner_radius=10)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(
            right,
            text="JARVIS STORICO",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=10, pady=(8, 0))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Jarvis.Treeview",
            background=COLORS["input"],
            fieldbackground=COLORS["input"],
            foreground=COLORS["text"],
            rowheight=24,
        )
        style.configure(
            "Jarvis.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
        )

        cols = ("data", "ora", "mail", "ordine", "contratto", "docs", "stampa", "esito", "durata")
        self.jarvis_tree = ttk.Treeview(
            right,
            columns=cols,
            show="headings",
            style="Jarvis.Treeview",
            selectmode="browse",
            height=8,
        )
        headings = {
            "data": ("Data", 80),
            "ora": ("Ora", 60),
            "mail": ("Mail", 140),
            "ordine": ("Ordine", 90),
            "contratto": ("Contratto", 90),
            "docs": ("Doc", 40),
            "stampa": ("Stampa", 50),
            "esito": ("Esito", 110),
            "durata": ("Durata", 60),
        }
        for key, (title, width) in headings.items():
            self.jarvis_tree.heading(key, text=title)
            self.jarvis_tree.column(key, width=width, stretch=True)
        self.jarvis_tree.pack(fill="both", expand=True, padx=8, pady=6)
        self.jarvis_tree.bind("<<TreeviewSelect>>", lambda _e: self._jarvis_show_detail())
        self.jarvis_tree.bind("<Double-1>", lambda _e: self._jarvis_show_detail())

        self.jarvis_detail = ctk.CTkTextbox(
            right,
            height=140,
            fg_color=COLORS["input"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
        )
        self.jarvis_detail.pack(fill="x", padx=8, pady=(0, 10))

    def _build_register_tab(self) -> None:
        parent = self.tab_register
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(
            top,
            text="Registro cronologico mail gestite",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")
        ctk.CTkButton(
            top,
            text="Aggiorna",
            width=100,
            height=30,
            fg_color=COLORS["panel"],
            command=self.refresh_mail_register,
        ).pack(side="right")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Register.Treeview",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["panel"],
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Register.Treeview.Heading",
            background=COLORS["input"],
            foreground=COLORS["muted"],
            relief="flat",
        )
        style.map("Register.Treeview", background=[("selected", COLORS["accent"])])

        tree_frame = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        tree_frame.pack(fill="both", expand=True)

        columns = ("when", "status", "mda", "order", "note")
        self.register_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Register.Treeview",
            selectmode="browse",
        )
        self.register_tree.heading("when", text="Data/ora")
        self.register_tree.heading("status", text="Esito")
        self.register_tree.heading("mda", text="MdA")
        self.register_tree.heading("order", text="Ordine")
        self.register_tree.heading("note", text="Nota")
        self.register_tree.column("when", width=140)
        self.register_tree.column("status", width=70, anchor="center")
        self.register_tree.column("mda", width=110)
        self.register_tree.column("order", width=110)
        self.register_tree.column("note", width=480)
        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.register_tree.yview
        )
        self.register_tree.configure(yscrollcommand=scroll.set)
        self.register_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        self.register_status_label = ctk.CTkLabel(
            parent,
            text="",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        )
        self.register_status_label.pack(anchor="w", padx=4, pady=(4, 0))

    def _build_history_tab(self) -> None:
        parent = self.tab_history
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(
            top,
            text="Contratti ricercati",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")
        ctk.CTkButton(
            top,
            text="Aggiorna elenco",
            width=130,
            height=30,
            fg_color=COLORS["panel"],
            command=self.refresh_history,
        ).pack(side="right")
        ctk.CTkButton(
            top,
            text="APRI",
            width=80,
            height=30,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self.open_selected_history,
        ).pack(side="right", padx=(0, 8))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "History.Treeview",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["panel"],
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "History.Treeview.Heading",
            background=COLORS["input"],
            foreground=COLORS["muted"],
            relief="flat",
        )
        style.map("History.Treeview", background=[("selected", COLORS["accent"])])

        tree_frame = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=10)
        tree_frame.pack(fill="both", expand=True)

        columns = ("contract", "last_checked", "docs", "new", "status")
        self.history_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="History.Treeview",
            selectmode="browse",
        )
        self.history_tree.heading("contract", text="Numero contratto")
        self.history_tree.heading("last_checked", text="Ultimo controllo")
        self.history_tree.heading("docs", text="Documenti")
        self.history_tree.heading("new", text="Nuovi")
        self.history_tree.heading("status", text="Stato")
        self.history_tree.column("contract", width=160)
        self.history_tree.column("last_checked", width=160)
        self.history_tree.column("docs", width=90, anchor="center")
        self.history_tree.column("new", width=70, anchor="center")
        self.history_tree.column("status", width=120)
        self.history_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.history_tree.bind("<Double-1>", lambda _e: self.open_selected_history())

    # ================================================================== lifecycle
    def _post_init(self) -> None:
        self.append_activity("Applicazione avviata.")
        self.refresh_history()
        self.refresh_print_queue()
        self.refresh_mail_register()
        self.refresh_jarvis_history()
        self._refresh_jarvis_status_ui()
        self._load_autosync_ui()
        self._schedule_autosync()
        settings = self.db.get_settings()
        if not settings.setup_completed or not self.credentials.has_credentials():
            self.after(300, self._show_wizard)
        elif settings.jarvis_autostart:
            self.after(800, self._jarvis_activate)

    def _show_wizard(self) -> None:
        SetupWizard(
            self,
            self.db,
            self.credentials,
            on_complete=lambda: self.append_activity("Configurazione iniziale completata."),
            on_test_access=self._wizard_test_access,
        )

    def _wizard_test_access(self, callback) -> None:
        self._run_test_access(callback)

    def _on_close(self) -> None:
        self._ui_pump_alive = False
        self._cancel_autosync()
        try:
            self.jarvis.stop()
        except Exception:
            pass
        try:
            self.browser.close()
        except Exception:
            pass
        self.destroy()

    # ================================================================== UI marshal
    def _post_ui(self, fn: Callable[[], None]) -> None:
        """Schedula lavoro UI dal worker senza tk.call cross-thread."""
        try:
            self._ui_queue.put_nowait(fn)
        except Exception:
            pass

    def _pump_ui(self) -> None:
        """Heartbeat: drena log + callback worker; tiene viva la message pump Windows."""
        if not self._ui_pump_alive:
            return
        try:
            for msg in drain_gui_log_queue(80):
                try:
                    self.append_activity(msg, from_logger=True)
                except Exception:
                    pass
            for _ in range(40):
                try:
                    fn = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    logger.exception("Errore callback UI da worker")
        finally:
            if self._ui_pump_alive:
                self.after(50, self._pump_ui)

    # ================================================================== activity
    def append_activity(self, text: str, *, from_logger: bool = False) -> None:
        self.activity_box.configure(state="normal")
        if from_logger:
            self.activity_box.insert("end", text + "\n")
        else:
            from datetime import datetime

            ts = datetime.now().strftime("%H:%M")
            self.activity_box.insert("end", f"{ts} {text}\n")
            logger.info(text)
        self.activity_box.see("end")
        self.activity_box.configure(state="disabled")

    def set_session_ui(self, active: bool) -> None:
        if active:
            self.session_label.configure(
                text="eniSpace · online", text_color=SUCCESS
            )
            if hasattr(self, "kpi_session"):
                self.kpi_session.set_value("Online", "eniSpace")
        else:
            self.session_label.configure(
                text="eniSpace · offline", text_color=COLORS["muted"]
            )
            if hasattr(self, "kpi_session"):
                self.kpi_session.set_value("Offline", "eniSpace")

    def _set_busy(self, busy: bool, message: str = "Operazione in corso...") -> None:
        self._busy = busy
        buttons = [
            self.btn_search,
            self.btn_dl_all,
            self.btn_dl_sel,
            self.btn_refresh,
            self.btn_import_eml,
            self.btn_batch_eml,
            self.btn_imap,
            self.btn_reprocess_today,
            self.btn_print_queue,
        ]
        state = "disabled" if busy else "normal"
        for btn in buttons:
            try:
                btn.configure(state=state)
            except Exception:
                pass

        if busy:
            self.progress_label.configure(text=message)
            self.progress_frame.pack(fill="x", pady=(0, 8), before=self.summary_frame)
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_frame.pack_forget()

    # ================================================================== settings
    def open_settings(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return
        self._settings_win = SettingsWindow(
            self,
            self.db,
            self.credentials,
            self.enispace,
            on_saved=self._apply_settings,
            on_test_access=lambda: self._run_test_access(None),
            on_record_navigation=self._start_recording,
            on_open_marketplace=self._open_marketplace,
            on_open_ordini=self._open_ordini,
            on_open_document_flow=self._open_document_flow,
            on_activity=self.append_activity,
        )

    def _apply_settings(self) -> None:
        settings = self.db.get_settings()
        set_debug_mode(settings.debug_mode)
        self.download_service.set_base_folder(settings.download_folder)
        self.enispace.base_url = settings.enispace_base_url
        self.enispace.configure_browser(
            hidden=settings.browser_hidden,
            timeout_ms=settings.browser_timeout_ms,
            debug=settings.debug_mode,
        )
        self._load_autosync_ui()
        self._schedule_autosync()
        # Propaga livello animazioni avatar (solo UI)
        level = (settings.jarvis_avatar_level or "full").strip().lower()
        for panel in (
            getattr(self, "jarvis_avatar", None),
            getattr(self, "dash_jarvis_avatar", None),
        ):
            if panel is None:
                continue
            try:
                panel.set_level(level)
            except Exception:
                pass
        self._refresh_jarvis_status_ui()
        # Cartella download dedicata Jarvis (se impostata)
        jfolder = (settings.jarvis_download_folder or "").strip()
        if jfolder:
            try:
                Path(jfolder).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    # ================================================================== autosync
    def _load_autosync_ui(self) -> None:
        settings = self.db.get_settings()
        if hasattr(self, "autosync_var"):
            self.autosync_var.set(bool(settings.autosync_enabled))
        if hasattr(self, "autosync_interval_var"):
            self.autosync_interval_var.set(
                str(max(1, int(settings.autosync_interval_minutes or 15)))
            )
        self._update_autosync_status()

    def _autosync_interval_minutes(self) -> int:
        try:
            return max(1, int((self.autosync_interval_var.get() or "15").strip()))
        except (TypeError, ValueError):
            return 15

    def _save_autosync_from_ui(self) -> None:
        settings = self.db.get_settings()
        settings.autosync_enabled = bool(self.autosync_var.get())
        settings.autosync_interval_minutes = self._autosync_interval_minutes()
        self.db.save_settings(settings)
        self._schedule_autosync()
        self._update_autosync_status()

    def _on_autosync_toggled(self) -> None:
        self._save_autosync_from_ui()
        if self.autosync_var.get():
            self.append_activity(
                f"Autosync attivo ogni {self._autosync_interval_minutes()} min."
            )
            # Avvio immediato (in background) se non già busy
            self.after(500, lambda: self.sync_imap_folder(silent=True))
        else:
            self.append_activity("Autosync disattivato.")

    def _update_autosync_status(self) -> None:
        if not hasattr(self, "autosync_status_label"):
            return
        if self.autosync_var.get():
            self.autosync_status_label.configure(
                text=f"Attivo — poll ogni {self._autosync_interval_minutes()} min",
                text_color="#4ade80",
            )
        else:
            self.autosync_status_label.configure(
                text="Disattivo",
                text_color=COLORS["muted"],
            )

    def _cancel_autosync(self) -> None:
        if self._autosync_after_id is not None:
            try:
                self.after_cancel(self._autosync_after_id)
            except Exception:
                pass
            self._autosync_after_id = None

    def _schedule_autosync(self) -> None:
        self._cancel_autosync()
        settings = self.db.get_settings()
        if not settings.autosync_enabled:
            self._update_autosync_status()
            return
        minutes = max(1, int(settings.autosync_interval_minutes or 15))
        ms = minutes * 60 * 1000
        self._autosync_after_id = self.after(ms, self._autosync_tick)
        self._update_autosync_status()

    def _autosync_tick(self) -> None:
        self._autosync_after_id = None
        settings = self.db.get_settings()
        if not settings.autosync_enabled:
            return
        if self._busy or self.worker.is_running or self._autosync_running:
            self.append_activity(
                "Autosync: sync già in corso — riprovo al prossimo intervallo."
            )
        else:
            self.sync_imap_folder(silent=True)
        self._schedule_autosync()

    # ================================================================== actions
    def refresh_mail_register(self) -> None:
        if not hasattr(self, "register_tree"):
            return
        for item in self.register_tree.get_children():
            self.register_tree.delete(item)
        entries = self.db.list_mail_register(limit=400)
        for e in entries:
            status_lbl = {
                "success": "OK",
                "error": "ERR",
                "skipped": "SKIP",
                "info": "INFO",
            }.get((e.status or "").lower(), (e.status or "—").upper()[:6])
            self.register_tree.insert(
                "",
                "end",
                iid=str(e.id) if e.id is not None else None,
                values=(
                    e.processed_at or "—",
                    status_lbl,
                    e.acquisition_module or "—",
                    e.order_number or "—",
                    e.note or e.subject or "—",
                ),
            )
        if hasattr(self, "register_status_label"):
            self.register_status_label.configure(
                text=f"{len(entries)} voci nel registro (più recenti in alto)."
                if entries
                else "Nessuna mail gestita ancora."
            )

    # ================================================================== actions
    def import_eml(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleziona notifica Marketplace (.eml)",
            filetypes=[("Email", "*.eml"), ("Tutti i file", "*.*")],
            initialdir=str(Path.home() / "Downloads"),
        )
        if not path:
            return
        try:
            notice = parse_eml_file(path)
        except Exception as exc:
            logger.error("Parse EML fallito: %s", exc)
            messagebox.showerror(
                "Importa .eml",
                "Impossibile leggere il file email.\nConsultare il log tecnico.",
                parent=self,
            )
            return

        if not notice.search_key:
            messagebox.showwarning(
                "Importa .eml",
                "Nella mail non sono stati trovati ordine/modulo di acquisizione.",
                parent=self,
            )
            return

        self._current_notification = notice
        self.contract_entry.delete(0, "end")
        self.contract_entry.insert(0, notice.search_key)

        self.db.upsert_contract(
            notice.search_key,
            order_number=notice.order_number or None,
            framework_contract=notice.contract_number or None,
            acquisition_module=notice.acquisition_module or None,
        )
        self._current_contract = notice.search_key
        self._render_summary(
            notice.search_key,
            0,
            "Da email",
            notification=notice,
        )
        self.refresh_history()
        self.append_activity(
            f"Email importata: ordine {notice.order_number}, "
            f"modulo {notice.acquisition_module}, contratto {notice.contract_number}"
        )
        self.db.log_operation(
            "import_eml",
            OperationResult.SUCCESS,
            (
                f"ordine={notice.order_number}; "
                f"contratto={notice.contract_number}; "
                f"modulo={notice.acquisition_module}"
            ),
            contract_number=notice.search_key,
        )

    def batch_process_eml(self) -> None:
        """Seleziona più .eml e li elabora in sequenza (download + coda stampa)."""
        if self._busy:
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso.",
                parent=self,
            )
            return

        paths = filedialog.askopenfilenames(
            parent=self,
            title="Seleziona una o più notifiche Marketplace (.eml)",
            filetypes=[("Email", "*.eml"), ("Tutti i file", "*.*")],
            initialdir=str(Path.home() / "Downloads"),
        )
        if not paths:
            return

        eml_list = [Path(p) for p in paths]
        self._set_busy(True, f"Elaborazione {len(eml_list)} mail...")
        self.append_activity(f"Batch avviato: {len(eml_list)} file .eml")
        self._clear_extracted_pdfs()
        self._apply_settings()

        def work():
            def progress(msg: str) -> None:
                self._post_ui(lambda m=msg: self.append_activity(m))

            def on_item(item: BatchItemResult) -> None:
                self._post_ui(lambda i=item: self._on_pdf_extracted(i))

            return self.batch_service.process_eml_files(
                eml_list,
                on_progress=progress,
                on_item_done=on_item,
                enqueue=True,
                continue_on_error=True,
            )

        def on_ok(run) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(True)
                self.refresh_print_queue()
                self.refresh_history()
                self.refresh_mail_register()
                self.append_activity(
                    f"Batch terminato: {run.ok_count} ok, {run.fail_count} errori."
                )
                pending = self.print_queue.count_pending()
                msg = (
                    f"Elaborate {len(run.results)} mail.\n"
                    f"OK: {run.ok_count}\n"
                    f"Errori: {run.fail_count}\n"
                    f"In coda stampa: {pending} PDF."
                )
                messagebox.showinfo("Batch", msg, parent=self)
                if pending > 0:
                    self.tabs.set("CODA STAMPA")

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = (
                    exc.message
                    if isinstance(exc, EniSpaceError)
                    else "Elaborazione batch fallita. Consultare il log."
                )
                self.append_activity(msg.split("\n")[0])
                self.refresh_print_queue()
                messagebox.showerror("Batch", msg, parent=self)

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="batch"):
            self._set_busy(False)

    def sync_imap_folder(self, *, silent: bool = False) -> None:
        """Legge cartella IMAP e lancia batch + coda stampa (sempre off-main-thread).

        silent=True (autosync): niente dialoghi; solo log attività / Registro.
        """
        if self._busy or self.worker.is_running or self.jarvis.is_processing:
            if silent:
                return
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso"
                + (" (JARVIS in lavorazione)." if self.jarvis.is_processing else "."),
                parent=self,
            )
            return

        settings = self.db.get_settings()
        folder = settings.imap_folder or "INBOX.MdA_Eni"
        unread_only = bool(settings.imap_unread_only)

        from services.credential_service import CredentialService
        from services.imap_mail_service import ImapConfig
        from utils.paths import KEYRING_MAIL_SERVICE

        mail_creds = CredentialService(KEYRING_MAIL_SERVICE).load()
        username = (mail_creds.username if mail_creds else "") or settings.imap_username
        password = mail_creds.password if mail_creds else ""
        if not username or not password:
            if silent:
                self.append_activity(
                    "Autosync: credenziali casella mancanti — sync saltato."
                )
                return
            messagebox.showwarning(
                "Casella IMAP",
                "Credenziali casella mancanti.\n\n"
                "Apri Impostazioni → Casella IMAP / SMTP,\n"
                "inserisci utente/password e premi «SALVA CRED. CASELLA».",
                parent=self,
            )
            return

        if not silent:
            if not messagebox.askyesno(
                "Sync casella IMAP",
                f"Host: {settings.imap_host or 'pop.securemail.pro'}\n"
                f"Cartella: {folder}\n"
                f"Filtro: mail {'non lette' if unread_only else 'tutte'}\n\n"
                "Elaborare le mail (download MdA + coda stampa)?",
                parent=self,
            ):
                return

        self._autosync_running = bool(silent)
        self._set_busy(
            True,
            "Autosync IMAP in corso..." if silent else "Sync casella IMAP in corso...",
        )
        self.append_activity(
            f"{'Autosync' if silent else 'Sync'} IMAP avviato: {folder}"
        )
        if not silent:
            self._clear_extracted_pdfs()
        self._apply_settings()

        def work():
            def progress(msg: str) -> None:
                # Solo coda UI (mai after/widget dal worker). L'activity arriva
                # dal drain dei log (batch/imap già fanno logger.info).
                def ui(m: str = msg) -> None:
                    try:
                        short = m if len(m) <= 90 else m[:87] + "..."
                        self.progress_label.configure(text=short)
                    except Exception:
                        pass

                self._post_ui(ui)

            def on_item(item: BatchItemResult) -> None:
                self._post_ui(lambda i=item: self._on_pdf_extracted(i))

            cfg = ImapConfig(
                host=settings.imap_host or "pop.securemail.pro",
                port=int(settings.imap_port or 993),
                security=settings.imap_security or "SSL",
                username=username,
                password=password,
                folder=folder,
                unread_only=unread_only,
                smtp_host=settings.smtp_host or "authsmtp.securemail.pro",
                smtp_port=int(settings.smtp_port or 465),
                smtp_security=settings.smtp_security or "SSL",
            )
            # Una sola connessione IMAP (niente test_connection prima):
            # doppio login consecutivo su SecureMail poteva bloccare SYNC.
            progress(
                f"Lettura casella {cfg.host} / {folder} "
                f"({'non lette' if unread_only else 'tutte'})..."
            )
            return self.batch_service.process_imap_folder(
                cfg,
                unread_only=unread_only,
                mark_read=True,
                skip_processed=True,
                on_progress=progress,
                on_item_done=on_item,
                enqueue=True,
                continue_on_error=True,
            )

        def on_ok(run) -> None:
            def ui() -> None:
                try:
                    self.set_session_ui(True)
                    self.refresh_print_queue()
                    self.refresh_history()
                    self.refresh_mail_register()
                    self.append_activity(
                        f"{'Autosync' if silent else 'Sync'} IMAP terminato: "
                        f"{run.ok_count} ok, {run.fail_count} errori."
                    )
                    if silent:
                        return
                    pending = self.print_queue.count_pending()
                    msg = (
                        f"Mail elaborate: {len(run.results)}\n"
                        f"OK: {run.ok_count}\n"
                        f"Errori: {run.fail_count}\n"
                        f"In coda stampa: {pending} PDF."
                    )
                    messagebox.showinfo("Sync casella", msg, parent=self)
                    if pending > 0:
                        self.tabs.set("CODA STAMPA")
                finally:
                    self._autosync_running = False
                    self._set_busy(False)

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                try:
                    if isinstance(exc, EniSpaceError):
                        msg = exc.message
                    else:
                        msg = str(exc) or "Sync IMAP fallito. Consultare il log."
                    self.append_activity(str(msg).split("\n")[0])
                    self.refresh_print_queue()
                    self.refresh_mail_register()
                    if not silent:
                        messagebox.showerror("Sync casella", msg, parent=self)
                finally:
                    self._autosync_running = False
                    self._set_busy(False)

            self._post_ui(ui)

        if not self.worker.run(
            work, on_success=on_ok, on_error=on_err, name="imap-sync"
        ):
            self._autosync_running = False
            self._set_busy(False)
            if not silent:
                messagebox.showwarning(
                    "Occupato",
                    "Un'operazione è già in corso.",
                    parent=self,
                )

    def reprocess_today_imap(self) -> None:
        """Rielabora le mail MdA con data odierna (errori / non ancora gestite)."""
        from datetime import date as date_cls

        if self._busy or self.worker.is_running or self.jarvis.is_processing:
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso.",
                parent=self,
            )
            return

        settings = self.db.get_settings()
        folder = settings.imap_folder or "INBOX.MdA_Eni"
        today = date_cls.today().isoformat()

        from services.credential_service import CredentialService
        from services.imap_mail_service import ImapConfig
        from utils.paths import KEYRING_MAIL_SERVICE

        mail_creds = CredentialService(KEYRING_MAIL_SERVICE).load()
        username = (mail_creds.username if mail_creds else "") or settings.imap_username
        password = mail_creds.password if mail_creds else ""
        if not username or not password:
            messagebox.showwarning(
                "Casella IMAP",
                "Credenziali casella mancanti.\n\n"
                "Apri Impostazioni → Casella IMAP / SMTP,\n"
                "inserisci utente/password e premi «SALVA CRED. CASELLA».",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Rielabora oggi",
            f"Rielaborare le mail MdA del {today}?\n\n"
            f"Cartella: {folder}\n"
            "Vengono riprese le mail fallite o non ancora gestite "
            "(quelle già OK restano saltate).\n"
            "Download MdA + coda stampa; su errore restano non lette.",
            parent=self,
        ):
            return

        self._set_busy(True, f"Rielaborazione mail del {today}...")
        self.append_activity(f"Rielabora oggi avviato: {folder} ({today})")
        self._clear_extracted_pdfs()
        self._apply_settings()

        def work():
            def progress(msg: str) -> None:
                def ui(m: str = msg) -> None:
                    try:
                        short = m if len(m) <= 90 else m[:87] + "..."
                        self.progress_label.configure(text=short)
                    except Exception:
                        pass

                self._post_ui(ui)

            def on_item(item: BatchItemResult) -> None:
                self._post_ui(lambda i=item: self._on_pdf_extracted(i))

            cfg = ImapConfig(
                host=settings.imap_host or "pop.securemail.pro",
                port=int(settings.imap_port or 993),
                security=settings.imap_security or "SSL",
                username=username,
                password=password,
                folder=folder,
                unread_only=False,
                smtp_host=settings.smtp_host or "authsmtp.securemail.pro",
                smtp_port=int(settings.smtp_port or 465),
                smtp_security=settings.smtp_security or "SSL",
            )
            progress(f"Rielaborazione mail del {today} da {cfg.host} / {folder}...")
            return self.batch_service.process_imap_folder(
                cfg,
                unread_only=False,
                mark_read=True,
                skip_processed=True,
                on_date=today,
                clear_error_skips=True,
                on_progress=progress,
                on_item_done=on_item,
                enqueue=True,
                continue_on_error=True,
                limit=100,
            )

        def on_ok(run) -> None:
            def ui() -> None:
                try:
                    self.set_session_ui(True)
                    self.refresh_print_queue()
                    self.refresh_history()
                    self.refresh_mail_register()
                    self.append_activity(
                        f"Rielabora oggi terminato ({today}): "
                        f"{run.ok_count} ok, {run.fail_count} errori."
                    )
                    pending = self.print_queue.count_pending()
                    msg = (
                        f"Mail del {today}:\n"
                        f"Elaborate: {len(run.results)}\n"
                        f"OK: {run.ok_count}\n"
                        f"Errori: {run.fail_count}\n"
                        f"In coda stampa: {pending} PDF."
                    )
                    messagebox.showinfo("Rielabora oggi", msg, parent=self)
                    if pending > 0:
                        self.tabs.set("CODA STAMPA")
                finally:
                    self._set_busy(False)

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                try:
                    if isinstance(exc, EniSpaceError):
                        msg = exc.message
                    else:
                        msg = str(exc) or "Rielaborazione fallita. Consultare il log."
                    self.append_activity(str(msg).split("\n")[0])
                    self.refresh_print_queue()
                    self.refresh_mail_register()
                    messagebox.showerror("Rielabora oggi", msg, parent=self)
                finally:
                    self._set_busy(False)

            self._post_ui(ui)

        if not self.worker.run(
            work, on_success=on_ok, on_error=on_err, name="imap-reprocess-today"
        ):
            self._set_busy(False)
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso.",
                parent=self,
            )

    def refresh_print_queue(self) -> None:
        if not hasattr(self, "queue_tree"):
            return
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        items = self.print_queue.list(pending_only=False)
        pending = 0
        for q in items:
            if q.status == "pending":
                pending += 1
            self.queue_tree.insert(
                "",
                "end",
                iid=str(q.id),
                values=(
                    q.order_number or "—",
                    q.acquisition_module or "—",
                    q.filename or Path(q.local_path).name,
                    q.eml_name or "—",
                    q.status,
                    q.created_at or "—",
                ),
            )
        self.queue_status_label.configure(
            text=f"{len(items)} elementi in coda ({pending} da stampare)."
            if items
            else "Coda vuota."
        )

    def _clear_extracted_pdfs(self) -> None:
        self._extracted_pdf_paths.clear()
        if hasattr(self, "extracted_listbox"):
            self.extracted_listbox.delete(0, "end")
        if hasattr(self, "extracted_latest_label"):
            self.extracted_latest_label.configure(
                text="Nessun PDF estratto in questa sessione."
            )
        self._set_pdf_preview(None)

    def _on_pdf_extracted(self, item: BatchItemResult) -> None:
        """Aggiorna pannello PDF estratti + coda (chiamare solo dal pump UI)."""
        if not item.success or not (item.pdf_path or "").strip():
            return
        path = Path(item.pdf_path)
        self._extracted_pdf_paths.append(path)
        label = path.name
        if item.order_number:
            label = f"{item.order_number} · {label}"
        if hasattr(self, "extracted_listbox"):
            self.extracted_listbox.insert("end", label)
            last = self.extracted_listbox.size() - 1
            self.extracted_listbox.selection_clear(0, "end")
            if last >= 0:
                self.extracted_listbox.selection_set(last)
                self.extracted_listbox.see(last)
        if hasattr(self, "extracted_latest_label"):
            self.extracted_latest_label.configure(
                text=f"Ultimo:\n{path.name}\n{path}"
            )
        self._set_pdf_preview(path)
        self.refresh_print_queue()
        try:
            if self.tabs.get() != "CODA STAMPA" and not self._autosync_running:
                self.tabs.set("CODA STAMPA")
        except Exception:
            pass

    def _on_extracted_select(self) -> None:
        path = self._selected_extracted_path()
        if path:
            if hasattr(self, "extracted_latest_label"):
                self.extracted_latest_label.configure(
                    text=f"Selezionato:\n{path.name}\n{path}"
                )
            self._set_pdf_preview(path)

    def _selected_extracted_path(self) -> Optional[Path]:
        if not hasattr(self, "extracted_listbox"):
            return None
        sel = self.extracted_listbox.curselection()
        if not sel:
            return self._extracted_pdf_paths[-1] if self._extracted_pdf_paths else None
        idx = int(sel[0])
        if 0 <= idx < len(self._extracted_pdf_paths):
            return self._extracted_pdf_paths[idx]
        return None

    def _set_pdf_preview(self, path: Optional[Path]) -> None:
        if not hasattr(self, "extracted_preview_label"):
            return
        if path is None:
            self._pdf_preview_image = None
            self.extracted_preview_label.configure(image=None, text="")
            return
        rendered = render_pdf_thumbnail(path, max_width=140, max_height=160)
        if not rendered:
            self._pdf_preview_image = None
            self.extracted_preview_label.configure(
                image=None, text="(anteprima non disponibile)"
            )
            return
        pil_img, _size = rendered
        try:
            ctk_img = ctk.CTkImage(
                light_image=pil_img,
                dark_image=pil_img,
                size=(pil_img.width, pil_img.height),
            )
            self._pdf_preview_image = ctk_img
            self.extracted_preview_label.configure(image=ctk_img, text="")
        except Exception:
            self._pdf_preview_image = None
            self.extracted_preview_label.configure(
                image=None, text="(anteprima non disponibile)"
            )

    def _open_selected_extracted_pdf(self) -> None:
        path = self._selected_extracted_path()
        if not path or not path.is_file():
            messagebox.showinfo(
                "PDF estratti",
                "Nessun PDF selezionato.",
                parent=self,
            )
            return
        try:
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror(
                "PDF estratti",
                f"Impossibile aprire il file.\n{exc}",
                parent=self,
            )

    def _open_latest_extracted_folder(self) -> None:
        path = self._selected_extracted_path()
        if path is None and self._extracted_pdf_paths:
            path = self._extracted_pdf_paths[-1]
        if path is None:
            settings = self.db.get_settings()
            folder = Path(settings.download_folder or default_download_dir())
        else:
            folder = path.parent if path.is_file() else path
        try:
            import os

            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror(
                "PDF estratti",
                f"Impossibile aprire la cartella.\n{exc}",
                parent=self,
            )

    def remove_selected_print_item(self) -> None:
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Coda stampa",
                "Selezionare un elemento da rimuovere.",
                parent=self,
            )
            return
        try:
            item_id = int(sel[0])
        except ValueError:
            return
        self.print_queue.remove(item_id)
        self.refresh_print_queue()
        self.append_activity(f"Rimosso dalla coda stampa id={item_id}")

    def clear_print_queue(self) -> None:
        if not self.print_queue.list():
            return
        if not messagebox.askyesno(
            "Svuota coda",
            "Rimuovere tutti gli elementi dalla coda di stampa?",
            parent=self,
        ):
            return
        n = self.print_queue.clear()
        self.refresh_print_queue()
        self.append_activity(f"Coda stampa svuotata ({n}).")

    def print_queue_cascade(self) -> None:
        if self._busy or self.worker.is_running or self.jarvis.is_processing:
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso.",
                parent=self,
            )
            return
        pending = self.print_queue.list(pending_only=True)
        if not pending:
            messagebox.showinfo(
                "Stampa coda",
                "Nessun PDF in coda da stampare.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Stampa coda",
            f"Inviare {len(pending)} PDF alla stampante predefinita Windows?\n"
            "(Stampa a cascata)",
            parent=self,
        ):
            return

        if self._busy:
            messagebox.showwarning("Occupato", "Operazione già in corso.", parent=self)
            return

        self._set_busy(True, "Stampa coda in corso...")
        self.append_activity(f"Stampa a cascata di {len(pending)} PDF...")

        def work():
            return self.print_queue.print_all(pending_only=True, delay_seconds=2.5)

        def on_ok(results) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.refresh_print_queue()
                ok = sum(1 for r in results if r.success)
                fail = len(results) - ok
                self.append_activity(f"Stampa coda: {ok} ok, {fail} errori.")
                self.db.log_operation(
                    "print_queue",
                    OperationResult.SUCCESS if fail == 0 else OperationResult.WARNING,
                    f"ok={ok} errori={fail}",
                )
                messagebox.showinfo(
                    "Stampa coda",
                    f"Inviati in stampa: {ok}\nErrori: {fail}",
                    parent=self,
                )

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.refresh_print_queue()
                messagebox.showerror(
                    "Stampa coda",
                    str(exc) or "Stampa fallita.",
                    parent=self,
                )

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="print"):
            self._set_busy(False)

    def _validate_contract_number(self, value: str) -> Optional[str]:
        number = value.strip()
        if not number:
            messagebox.showwarning(
                "Validazione",
                "Inserire un numero ordine (o importare la mail .eml).",
                parent=self,
            )
            return None
        if len(number) < 3:
            messagebox.showwarning(
                "Validazione",
                "Il numero ordine sembra troppo corto.",
                parent=self,
            )
            return None
        if any(c in number for c in '<>:"/\\|?*'):
            messagebox.showwarning(
                "Validazione",
                "Il numero contiene caratteri non validi.",
                parent=self,
            )
            return None
        return number

    def search_contract(self) -> None:
        number = self._validate_contract_number(self.contract_entry.get())
        if not number or self._busy:
            return
        self._execute_contract_flow(number)

    def refresh_contract(self) -> None:
        if not self._current_contract:
            messagebox.showinfo(
                "Aggiorna",
                "Nessun contratto caricato. Eseguire prima una ricerca.",
                parent=self,
            )
            return
        self.contract_entry.delete(0, "end")
        self.contract_entry.insert(0, self._current_contract)
        self._execute_contract_flow(self._current_contract)

    def _execute_contract_flow(self, number: str) -> None:
        self._set_busy(True, "Ricerca ordine in corso...")
        self.append_activity(f"Ricerca ordine {number}")

        def work():
            settings = self.db.get_settings()
            self.enispace.configure_browser(
                hidden=settings.browser_hidden,
                timeout_ms=settings.browser_timeout_ms,
                debug=settings.debug_mode,
            )
            notice = self._current_notification
            result = self.enispace.search_contract(
                number,
                order_number=notice.order_number if notice else number,
                framework_contract=notice.contract_number if notice else None,
                acquisition_module=notice.acquisition_module if notice else None,
            )
            if not result.found:
                raise EniSpaceError(
                    result.message or f"Impossibile trovare l'ordine {number}."
                )
            # Flusso portato alla dashboard: allegati già tentati in search_contract
            attachments = list(result.attachments)
            info_message = result.message
            return number, attachments, info_message

        def on_ok(payload) -> None:
            self._post_ui(lambda: self._on_search_success(*payload))

        def on_err(exc: Exception) -> None:
            self._post_ui(lambda: self._on_search_error(number, exc))

        started = self.worker.run(work, on_success=on_ok, on_error=on_err, name="search")
        if not started:
            self._set_busy(False)
            messagebox.showwarning(
                "Occupato",
                "Un'operazione è già in corso.",
                parent=self,
            )

    def _on_search_success(self, number: str, attachments, info_message: str = "") -> None:
        self._set_busy(False)
        self.set_session_ui(True)
        contract = self.db.upsert_contract(
            number,
            order_number=(
                self._current_notification.order_number
                if self._current_notification
                else number
            ),
            framework_contract=(
                self._current_notification.contract_number
                if self._current_notification
                else None
            ),
            acquisition_module=(
                self._current_notification.acquisition_module
                if self._current_notification
                else None
            ),
        )
        assert contract.id is not None

        if not attachments:
            self._current_contract = number
            self._documents = self.db.list_documents(contract.id)
            self._render_summary(
                number,
                len(self._documents),
                "Dashboard filtri aperta",
                notification=self._current_notification,
            )
            self._render_documents(self._documents)
            self.refresh_history()
            self.append_activity("Flusso Ordini → Marketplace → Dashboard raggiunto.")
            if info_message:
                for line in info_message.splitlines():
                    if line.strip():
                        self.append_activity(line.strip())
            self.db.log_operation(
                "search",
                OperationResult.WARNING,
                info_message or "Dashboard aperta; filtri da mappare",
                contract_number=number,
            )
            messagebox.showinfo(
                "Flusso documenti",
                info_message
                or (
                    "Chrome è sulla dashboard filtri Marketplace (#ZMP_DSH-DISPLAY).\n"
                    "Compila i filtri manualmente (ordine/contratto/modulo).\n"
                    "Poi indica i campi usati per automatizzarli."
                ),
                parent=self,
            )
            return

        # Confronta con storico
        previous = {d.remote_id or d.filename: d for d in self.db.list_documents(contract.id)}
        docs: list[Document] = []
        new_count = 0
        for att in attachments:
            key = att.remote_id or att.filename
            existing = previous.get(key)
            if existing and existing.status == DocumentStatus.DOWNLOADED:
                status = DocumentStatus.DOWNLOADED
                local_path = existing.local_path
                sha = existing.sha256
                downloaded_at = existing.downloaded_at
            elif existing:
                status = DocumentStatus.AVAILABLE
                local_path = existing.local_path
                sha = existing.sha256
                downloaded_at = existing.downloaded_at
            else:
                status = DocumentStatus.NEW
                local_path = None
                sha = None
                downloaded_at = None
                new_count += 1

            doc = Document(
                contract_id=contract.id,
                remote_id=att.remote_id,
                filename=att.filename,
                doc_type=att.doc_type,
                remote_date=att.remote_date,
                size=att.size,
                local_path=local_path,
                sha256=sha,
                downloaded_at=downloaded_at,
                status=status,
            )
            docs.append(self.db.upsert_document(doc))

        self._current_contract = number
        self._documents = docs
        already = sum(1 for d in docs if d.status == DocumentStatus.DOWNLOADED)

        self.append_activity("Contratto trovato.")
        self.append_activity(f"Documenti rilevati: {len(docs)}")
        if already:
            self.append_activity(f"{already} già presenti.")
        if new_count:
            self.append_activity(f"{new_count} nuovi documenti.")

        self.db.log_operation(
            "search",
            OperationResult.SUCCESS,
            f"Documenti: {len(docs)}, nuovi: {new_count}",
            contract_number=number,
        )
        self._render_summary(
            number,
            len(docs),
            "Completato",
            notification=self._current_notification,
        )
        self._render_documents(docs)
        self.refresh_history()

    def _on_search_error(self, number: str, exc: Exception) -> None:
        self._set_busy(False)
        if isinstance(exc, SelectorsNotConfiguredError):
            # Predisposizione: salva comunque il contratto in cronologia locale
            contract = self.db.upsert_contract(
                number,
                order_number=(
                    self._current_notification.order_number
                    if self._current_notification
                    else number
                ),
                framework_contract=(
                    self._current_notification.contract_number
                    if self._current_notification
                    else None
                ),
                acquisition_module=(
                    self._current_notification.acquisition_module
                    if self._current_notification
                    else None
                ),
            )
            self._current_contract = number
            self._documents = (
                self.db.list_documents(contract.id) if contract.id else []
            )
            self._render_summary(
                number,
                len(self._documents),
                "In attesa mappatura portale",
                notification=self._current_notification,
            )
            self._render_documents(self._documents)
            self.refresh_history()
            self.append_activity(exc.message.split("\n")[0])
            self.db.log_operation(
                "search",
                OperationResult.WARNING,
                exc.message,
                contract_number=number,
            )
            messagebox.showinfo(
                "Portale da mappare",
                exc.message
                + "\n\nIl numero contratto è stato registrato in cronologia.\n"
                "Usa Impostazioni → REGISTRA NAVIGAZIONE per acquisire i selettori.",
                parent=self,
            )
            return

        msg = exc.message if isinstance(exc, EniSpaceError) else (
            "Si è verificato un errore. Consultare il log tecnico."
        )
        self.append_activity(msg.split("\n")[0])
        self.set_session_ui(self.enispace.is_session_active)
        self.db.log_operation(
            "search",
            OperationResult.ERROR,
            msg,
            contract_number=number,
        )
        messagebox.showerror("Ricerca contratto", msg, parent=self)

    def _render_summary(
        self,
        number: str,
        docs: int,
        status: str,
        *,
        notification: Optional[AcquisitionNotification] = None,
    ) -> None:
        notice = notification or self._current_notification
        lines = [f"Ordine (ricerca):     {number}"]
        if notice:
            if notice.contract_number:
                lines.append(f"Contratto quadro:    {notice.contract_number}")
            if notice.acquisition_module:
                lines.append(f"Modulo acquisizione: {notice.acquisition_module}")
        else:
            stored = self.db.get_contract(number)
            if stored:
                if stored.framework_contract:
                    lines.append(f"Contratto quadro:    {stored.framework_contract}")
                if stored.acquisition_module:
                    lines.append(f"Modulo acquisizione: {stored.acquisition_module}")
        lines.append(f"Stato ricerca:       {status}")
        lines.append(f"Documenti trovati:   {docs}")
        if notice and notice.acquisition_module:
            lines.append(
                f"Documento atteso:    Modulo di Acquisizione {notice.acquisition_module}"
            )
        self.summary_label.configure(
            text="\n".join(lines),
            text_color=COLORS["text"],
            justify="left",
            anchor="w",
        )

    def _render_documents(self, docs: list[Document]) -> None:
        for child in self.docs_list.winfo_children():
            child.destroy()
        self._doc_vars = []
        self._documents = docs

        if not docs:
            ctk.CTkLabel(
                self.docs_list,
                text="Nessun documento in elenco.",
                text_color=COLORS["muted"],
            ).pack(anchor="w", padx=8, pady=12)
            return

        for doc in docs:
            preferred = False
            if self._current_notification and self._current_notification.acquisition_module:
                mod = self._current_notification.acquisition_module
                preferred = (doc.remote_id == mod) or (mod in (doc.filename or ""))
            var = tk.BooleanVar(value=preferred)
            self._doc_vars.append(var)
            row = ctk.CTkFrame(self.docs_list, fg_color=COLORS["input"], corner_radius=6)
            row.pack(fill="x", padx=4, pady=3)

            ctk.CTkCheckBox(
                row, text="", variable=var, width=28, fg_color=COLORS["accent"]
            ).pack(side="left", padx=4)

            icon = STATUS_ICON.get(doc.status, "○")
            ctk.CTkLabel(row, text=icon, width=50, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(
                row, text=doc.filename or "—", width=280, anchor="w"
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                row, text=doc.doc_type or self._guess_type(doc.filename), width=60, anchor="w"
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                row,
                text=self.download_service.format_size(doc.size),
                width=90,
                anchor="w",
            ).pack(side="left", padx=4)
            ctk.CTkLabel(
                row, text=doc.remote_date or "—", width=100, anchor="w"
            ).pack(side="left", padx=4)

            action = "Apri" if doc.status == DocumentStatus.DOWNLOADED and doc.local_path else "Scarica"
            ctk.CTkButton(
                row,
                text=action,
                width=90,
                height=28,
                fg_color=COLORS["panel"],
                hover_color=COLORS["border"],
                command=lambda d=doc: self._doc_action(d),
            ).pack(side="left", padx=4, pady=4)

    @staticmethod
    def _guess_type(filename: str) -> str:
        if not filename or "." not in filename:
            return "—"
        return filename.rsplit(".", 1)[-1].upper()

    def _doc_action(self, doc: Document) -> None:
        if doc.status == DocumentStatus.DOWNLOADED and doc.local_path:
            path = Path(doc.local_path)
            if path.is_file():
                try:
                    import os

                    os.startfile(str(path))  # type: ignore[attr-defined]
                except OSError:
                    messagebox.showerror(
                        "Apri",
                        "Impossibile aprire il file. Verificare i permessi.",
                        parent=self,
                    )
            else:
                messagebox.showwarning(
                    "Apri",
                    "File locale non trovato. Procedere con un nuovo download.",
                    parent=self,
                )
        else:
            self._download_docs([doc])

    def download_all(self) -> None:
        pending = [
            d
            for d in self._documents
            if d.status != DocumentStatus.DOWNLOADED
        ]
        if not pending:
            messagebox.showinfo(
                "Download",
                "Nessun documento da scaricare (tutti già presenti).",
                parent=self,
            )
            return
        self._download_docs(pending)

    def download_selected(self) -> None:
        selected = [
            doc
            for doc, var in zip(self._documents, self._doc_vars)
            if var.get()
        ]
        if not selected:
            messagebox.showwarning(
                "Download",
                "Selezionare almeno un documento.",
                parent=self,
            )
            return
        self._download_docs(selected)

    def _download_docs(self, docs: list[Document]) -> None:
        if not self._current_contract:
            return
        if self._busy:
            return

        number = self._current_contract
        self._set_busy(True, "Download in corso...")
        self.append_activity(f"Download di {len(docs)} documento/i...")

        def work():
            results = []
            for doc in docs:
                prep = self.download_service.prepare_destination(
                    number,
                    doc.filename,
                    expected_sha256=doc.sha256,
                    expected_size=doc.size,
                )
                if prep.skipped:
                    results.append((doc, prep, True))
                    continue
                att = AttachmentInfo(
                    remote_id=doc.remote_id,
                    filename=doc.filename,
                    doc_type=doc.doc_type,
                    remote_date=doc.remote_date,
                    size=doc.size,
                )
                path = self.enispace.download_attachment(att, str(prep.path))
                # Aggiorna metadati locali
                from pathlib import Path
                from datetime import datetime, timezone

                p = Path(path)
                doc.local_path = str(p)
                doc.status = DocumentStatus.DOWNLOADED
                doc.size = p.stat().st_size if p.is_file() else None
                try:
                    doc.sha256 = self.download_service.sha256_file(p)
                except OSError:
                    pass
                doc.downloaded_at = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if True:
                    contract = self.db.get_contract(number)
                    if contract and contract.id:
                        doc.contract_id = contract.id
                        self.db.upsert_document(doc)
                results.append((doc, path, False))
            return results

        def on_ok(results) -> None:
            self._post_ui(lambda: self._on_download_done(results))

        def on_err(exc: Exception) -> None:
            self._post_ui(lambda: self._on_download_error(exc))

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="download"):
            self._set_busy(False)

    def _on_download_done(self, results) -> None:
        self._set_busy(False)
        self.append_activity("Download completato.")
        # Ricarica documenti da DB se aggiornati — per ora refresh UI locale
        if self._current_contract:
            contract = self.db.get_contract(self._current_contract)
            if contract and contract.id:
                self._documents = self.db.list_documents(contract.id)
                self._render_documents(self._documents)
        settings = self.db.get_settings()
        if settings.open_folder_after_download and self._current_contract:
            try:
                self.download_service.open_folder(self._current_contract)
            except RuntimeError as exc:
                messagebox.showwarning("Cartella", str(exc), parent=self)

    def _on_download_error(self, exc: Exception) -> None:
        self._set_busy(False)
        msg = exc.message if isinstance(exc, EniSpaceError) else (
            "Download fallito. Consultare il log tecnico."
        )
        self.append_activity(msg.split("\n")[0])
        messagebox.showerror("Download", msg, parent=self)

    def open_download_folder(self) -> None:
        try:
            self.download_service.open_folder(self._current_contract)
        except RuntimeError as exc:
            messagebox.showerror("Cartella", str(exc), parent=self)

    # ================================================================== history
    def refresh_history(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for contract in self.db.list_contracts():
            stats = self.db.contract_stats(contract.id) if contract.id else {
                "total": 0,
                "new": 0,
            }
            status = "Completato" if stats["total"] else "Registrato"
            self.history_tree.insert(
                "",
                "end",
                iid=str(contract.id),
                values=(
                    contract.contract_number,
                    contract.last_checked or "—",
                    stats["total"],
                    stats["new"],
                    status,
                ),
            )

    def open_selected_history(self) -> None:
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo(
                "Cronologia",
                "Selezionare un contratto.",
                parent=self,
            )
            return
        values = self.history_tree.item(sel[0], "values")
        number = values[0]
        self.tabs.set("RICERCA")
        self.contract_entry.delete(0, "end")
        self.contract_entry.insert(0, number)
        contract = self.db.get_contract(number)
        if contract and contract.id:
            docs = self.db.list_documents(contract.id)
            self._current_contract = number
            self._render_summary(number, len(docs), "Da cronologia")
            self._render_documents(docs)
            self.append_activity(f"Contratto {number} caricato da cronologia.")

    # ================================================================== test / record
    def _run_test_access(self, callback) -> None:
        if self._busy:
            if callback:
                callback(False, "Operazione già in corso.")
            return

        self._set_busy(True, "Test accesso eniSpace...")
        self.append_activity("Connessione a eniSpace...")

        def work():
            self._apply_settings()
            return self.enispace.test_access()

        def on_ok(result) -> None:
            ok, message = result

            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(ok and self.enispace.is_session_active)
                self.append_activity(message)
                if callback:
                    callback(ok, message)
                else:
                    if ok:
                        messagebox.showinfo("Test accesso", message, parent=self)
                    else:
                        messagebox.showerror("Test accesso", message, parent=self)

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = (
                    exc.message
                    if isinstance(exc, EniSpaceError)
                    else "Errore durante il test di accesso."
                )
                self.append_activity(msg)
                if callback:
                    callback(False, msg)
                else:
                    messagebox.showerror("Test accesso", msg, parent=self)

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="test-login"):
            self._set_busy(False)

    def show_recording_help(self) -> None:
        messagebox.showinfo(
            "Come mappare il portale",
            (
                "NON è una registrazione account.\n"
                "Serve solo ad aprire Chrome controllato dal programma,\n"
                "così tu navighi eniSpace e noi vediamo il percorso reale.\n\n"
                "PASSAGGI:\n"
                "1. Clicca «APRI CHROME (mappa portale)» in alto.\n"
                "2. Si apre Google Chrome (finestra del programma).\n"
                "3. Fai login Eni / MFA se richiesto.\n"
                "4. Vai su: Contratti in esecuzione → I miei ordini e consuntivi\n"
                "   oppure Marketplace (se blank: Impostazioni → Apri Marketplace).\n"
                "5. Cerca l'ORDINE (es. 4310758365).\n"
                "6. Apri il Modulo di Acquisizione (es. 2013627410).\n"
                "7. Lascia Chrome aperto e dimmi cosa vedi / a quale URL sei arrivato.\n\n"
                "Il programma scrive le URL nel log (cartella logs/).\n"
                "Quando il percorso è chiaro, colleghiamo la ricerca automatica.\n\n"
                "Per partire dai dati mail: usa «IMPORTA .EML»."
            ),
            parent=self,
        )

    def _start_recording(self) -> None:
        if self._busy:
            return

        proceed = messagebox.askokcancel(
            "Apri Chrome per mappare eniSpace",
            (
                "Sto per aprire Google Chrome collegato a questa utility.\n\n"
                "Cosa fare TU nella finestra Chrome:\n"
                "  1. Login (MFA se compare)\n"
                "  2. Ordini e consuntivi / Marketplace\n"
                "  3. Cerca l'ordine della mail (es. 4310758365)\n"
                "  4. Apri il Modulo di Acquisizione\n\n"
                "Non chiudere subito Chrome: serve per capire i click reali.\n\n"
                "Continuare?"
            ),
            parent=self,
        )
        if not proceed:
            return

        self._set_busy(True, "Apertura Chrome...")
        self.append_activity("Apertura Chrome per mappare il portale...")

        def work():
            self._apply_settings()
            self.enispace.start_navigation_recording()
            return True

        def on_ok(_r) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(True)
                self.append_activity(
                    "Chrome aperto. Naviga tu su eniSpace; le URL finiscono nel log."
                )
                messagebox.showinfo(
                    "Chrome aperto — naviga tu",
                    (
                        "Chrome è pronto.\n\n"
                        "Ora, nella finestra Chrome:\n"
                        "• completa il login se serve\n"
                        "• apri «I miei ordini e consuntivi» oppure Marketplace\n"
                        "• cerca l'ordine (es. 4310758365)\n"
                        "• apri il Modulo di Acquisizione\n\n"
                        "Se Marketplace resta bianco (about:blank):\n"
                        "Impostazioni → APRI MARKETPLACE (URL diretta)\n\n"
                        "Quando hai trovato il documento, torna qui e descrivi\n"
                        "i passaggi: li colleghiamo al programma."
                    ),
                    parent=self,
                )

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = str(exc)
                self.append_activity("Errore avvio browser.")
                messagebox.showerror(
                    "Browser",
                    "Impossibile avviare Google Chrome.\n"
                    "Verificare che Chrome sia installato sul PC.\n\n"
                    "Dettaglio nel log tecnico.",
                    parent=self,
                )
                logger.error("Recording error: %s", msg)

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="record"):
            self._set_busy(False)

    def _open_document_flow(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Apertura flusso documenti...")
        self.append_activity(
            "Flusso: Ordini → Marketplace → Dashboard filtri..."
        )

        def work():
            self._apply_settings()
            return self.enispace.open_document_flow()

        def on_ok(url) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(True)
                self.append_activity(f"Dashboard filtri: {url}")
                messagebox.showinfo(
                    "Flusso documenti",
                    "Percorso completato:\n"
                    "1. Ordini e consuntivi\n"
                    "2. Marketplace Launchpad\n"
                    "3. Dashboard filtri (#ZMP_DSH-DISPLAY&/)\n\n"
                    f"{url}\n\n"
                    "Ora imposta i filtri nella pagina Chrome\n"
                    "(ordine / contratto / modulo acquisizione).",
                    parent=self,
                )

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = (
                    exc.message
                    if isinstance(exc, EniSpaceError)
                    else "Impossibile completare il flusso documenti."
                )
                self.append_activity(msg.split("\n")[0])
                messagebox.showerror("Flusso documenti", msg, parent=self)

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="doc-flow"):
            self._set_busy(False)

    def _open_ordini(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Apertura Ordini e consuntivi...")
        self.append_activity("Apertura Ordini e consuntivi (URL eniSpace stabile)...")

        def work():
            self._apply_settings()
            if not self.browser.is_open:
                self.enispace.login(allow_manual=True)
            return self.enispace.open_ordini()

        def on_ok(url) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(True)
                self.append_activity(f"Ordini: {url}")
                messagebox.showinfo(
                    "Ordini e consuntivi",
                    "Pagina eniSpace aperta (URL stabile).\n\n"
                    "Da qui cerca l'ordine della mail e, se serve,\n"
                    "apri il Marketplace con il click del portale:\n"
                    "il programma imparerà il link aggiornato.",
                    parent=self,
                )

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = (
                    exc.message
                    if isinstance(exc, EniSpaceError)
                    else "Impossibile aprire Ordini e consuntivi."
                )
                self.append_activity(msg.split("\n")[0])
                messagebox.showerror("Ordini", msg, parent=self)

            self._post_ui(ui)

        if not self.worker.run(work, on_success=on_ok, on_error=on_err, name="ordini"):
            self._set_busy(False)

    def _open_marketplace(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Apertura Marketplace...")
        known = self.enispace.resolve_marketplace_url()
        self.append_activity(f"Apertura Marketplace (URL imparato/fallback)...")

        def work():
            self._apply_settings()
            if not self.browser.is_open:
                self.enispace.login(allow_manual=True)
            return self.enispace.open_marketplace(force_direct=True)

        def on_ok(url) -> None:
            def ui() -> None:
                self._set_busy(False)
                self.set_session_ui(True)
                self.append_activity(f"Marketplace: {url}")
                if not url or url == "about:blank":
                    messagebox.showwarning(
                        "Marketplace",
                        "La pagina risulta ancora about:blank.\n"
                        "Meglio: Apri Ordini e consuntivi, poi clicca\n"
                        "Marketplace da eniSpace (link aggiornato).",
                        parent=self,
                    )
                else:
                    messagebox.showinfo(
                        "Marketplace",
                        f"Marketplace aperto con l'URL noto/imparato.\n\n{url}\n\n"
                        "Se non funziona più, aprilo dal menu eniSpace:\n"
                        "il programma salverà il nuovo host.",
                        parent=self,
                    )

            self._post_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._set_busy(False)
                msg = (
                    exc.message
                    if isinstance(exc, EniSpaceError)
                    else "Impossibile aprire il Marketplace."
                )
                self.append_activity(msg.split("\n")[0])
                messagebox.showerror("Marketplace", msg, parent=self)

            self._post_ui(ui)

        if not self.worker.run(
            work, on_success=on_ok, on_error=on_err, name="marketplace"
        ):
            self._set_busy(False)

    # ================================================================== JARVIS
    def _jarvis_avatar_level(self) -> str:
        try:
            return (self.db.get_settings().jarvis_avatar_level or "full").strip().lower()
        except Exception:
            return "full"

    def _jarvis_settings(self) -> JarvisSettings:
        s = self.db.get_settings()
        return JarvisSettings(
            enabled=bool(s.jarvis_enabled),
            interval_seconds=max(15, int(s.jarvis_interval_seconds or 60)),
            autostart=bool(s.jarvis_autostart),
            max_retries=max(1, int(s.jarvis_max_retries or 3)),
            printer=s.jarvis_printer or "",
            download_folder=s.jarvis_download_folder or "",
            keep_pdfs=bool(s.jarvis_keep_pdfs),
            debug=bool(s.jarvis_debug),
            simulation=bool(s.jarvis_simulation),
        )

    def _jarvis_imap_config(self):
        from services.credential_service import CredentialService
        from services.imap_mail_service import ImapConfig
        from utils.paths import KEYRING_MAIL_SERVICE

        settings = self.db.get_settings()
        mail_creds = CredentialService(KEYRING_MAIL_SERVICE).load()
        username = (mail_creds.username if mail_creds else "") or settings.imap_username
        password = mail_creds.password if mail_creds else ""
        if not username or not password:
            return None
        return ImapConfig(
            host=settings.imap_host or "pop.securemail.pro",
            port=int(settings.imap_port or 993),
            security=settings.imap_security or "SSL",
            username=username,
            password=password,
            folder=settings.imap_folder or "INBOX.MdA_Eni",
            unread_only=bool(settings.imap_unread_only),
            smtp_host=settings.smtp_host or "authsmtp.securemail.pro",
            smtp_port=int(settings.smtp_port or 465),
            smtp_security=settings.smtp_security or "SSL",
        )

    def _jarvis_app_busy(self) -> bool:
        return bool(self._busy or self.worker.is_running)

    def _jarvis_ui_refresh(self) -> None:
        self._post_ui(self._refresh_jarvis_status_ui)

    def _on_jarvis_log_entry(self, entry) -> None:
        def ui() -> None:
            if not hasattr(self, "jarvis_console"):
                return
            try:
                self.jarvis_console.configure(state="normal")
                line = f"{entry.timestamp} — {entry.message}\n"
                tag = (entry.level or LogLevel.INFO).upper()
                if tag not in ("INFO", "SUCCESS", "WARNING", "ERROR"):
                    tag = "INFO"
                self.jarvis_console.insert("end", line, tag)
                self.jarvis_console.see("end")
                self.jarvis_console.configure(state="disabled")
            except Exception:
                pass

        self._post_ui(ui)

    def _on_jarvis_notify(self, payload) -> None:
        def ui() -> None:
            try:
                ev = str(getattr(payload, "event", "") or "").lower()
                msg = getattr(payload, "message", "") or ev
                if "error" in ev or "fail" in ev:
                    self._toasts.show(msg[:140], variant="error", title="JARVIS")
                elif "complete" in ev or "success" in ev or "done" in ev or "printed" in ev:
                    self._toasts.show(msg[:140], variant="success", title="Completato")
                elif "warn" in ev:
                    self._toasts.show(msg[:140], variant="warning", title="Attenzione")
            except Exception:
                pass

        self._post_ui(ui)

    def _jarvis_clear_console(self) -> None:
        self.jarvis.logger.clear_visual()
        if hasattr(self, "jarvis_console"):
            self.jarvis_console.configure(state="normal")
            self.jarvis_console.delete("1.0", "end")
            self.jarvis_console.configure(state="disabled")
        self.append_activity("Console JARVIS svuotata (storico persistente intatto).")

    def _jarvis_activate(self) -> None:
        settings = self.db.get_settings()
        settings.jarvis_enabled = True
        self.db.save_settings(settings)
        if self._jarvis_imap_config() is None:
            messagebox.showwarning(
                "JARVIS",
                "Credenziali casella IMAP mancanti.\n"
                "Configurale in Impostazioni prima di attivare JARVIS.",
                parent=self,
            )
            return
        self.jarvis.start()
        self.append_activity("JARVIS attivato.")
        self._refresh_jarvis_status_ui()
        self.refresh_jarvis_history()
        try:
            self._toasts.show("Supervisore avviato", variant="jarvis", title="JARVIS ON")
        except Exception:
            pass

    def _jarvis_deactivate(self) -> None:
        settings = self.db.get_settings()
        settings.jarvis_enabled = False
        self.db.save_settings(settings)
        self.jarvis.stop()
        self.append_activity("JARVIS disattivato.")
        self._refresh_jarvis_status_ui()
        try:
            self._toasts.show(
                "Supervisore arrestato", variant="warning", title="JARVIS OFF"
            )
        except Exception:
            pass

    def _refresh_jarvis_status_ui(self) -> None:
        if not hasattr(self, "jarvis_state_label"):
            return
        snap = self.jarvis.snapshot()
        sim = bool(self._jarvis_settings().simulation)
        if hasattr(self, "jarvis_sim_banner"):
            if sim:
                if not self.jarvis_sim_banner.winfo_ismapped():
                    self.jarvis_sim_banner.pack(
                        fill="x",
                        pady=(4, 4),
                        before=self._jarvis_status_frame,
                    )
            else:
                self.jarvis_sim_banner.pack_forget()

        if snap["active"]:
            self.jarvis_online_label.configure(
                text="● ONLINE", text_color=SUCCESS
            )
            if hasattr(self, "app_header"):
                self.app_header.jarvis_header.set_status(True, "JARVIS ONLINE")
            self._start_jarvis_pulse()
        else:
            self.jarvis_online_label.configure(
                text="○ OFFLINE", text_color=COLORS["muted"]
            )
            if hasattr(self, "app_header"):
                self.app_header.jarvis_header.set_status(False, "JARVIS OFFLINE")
            self._stop_jarvis_pulse()
        self.jarvis_state_label.configure(text=f"Stato: {snap['state']}")
        self.jarvis_meta_label.configure(
            text=(
                f"Ultimo controllo: {snap['last_check']}\n"
                f"Ultima lavorazione: {snap['last_job']}\n"
                f"In coda: {snap['pending']}\n"
                f"In lavorazione: {snap['current_job']}"
            )
        )
        # Avatar: solo da refresh UI (stesso snapshot del supervisore)
        for panel in (
            getattr(self, "jarvis_avatar", None),
            getattr(self, "dash_jarvis_avatar", None),
        ):
            if panel is None:
                continue
            try:
                panel.update_from_snapshot(snap)
            except Exception:
                pass
        if hasattr(self, "sidebar"):
            self.sidebar.set_system_status(
                "JARVIS attivo" if snap["active"] else "Sistema pronto"
            )
        try:
            self._refresh_dashboard_metrics()
        except Exception:
            pass
        # Aggiorna storico se job appena chiuso
        if not snap["processing"]:
            try:
                self.refresh_jarvis_history()
            except Exception:
                pass

    def _start_jarvis_pulse(self) -> None:
        if self._jarvis_pulse_job:
            return

        def pulse(on: bool = True) -> None:
            if not hasattr(self, "app_header"):
                return
            try:
                snap = self.jarvis.snapshot()
                if not snap.get("active"):
                    self._jarvis_pulse_job = None
                    return
                color = SUCCESS if on else "#166534"
                self.app_header.jarvis_header.dot.configure(text_color=color)
                self._jarvis_pulse_job = self.after(900, lambda: pulse(not on))
            except Exception:
                self._jarvis_pulse_job = None

        pulse(True)

    def _stop_jarvis_pulse(self) -> None:
        if self._jarvis_pulse_job:
            try:
                self.after_cancel(self._jarvis_pulse_job)
            except Exception:
                pass
            self._jarvis_pulse_job = None

    def refresh_jarvis_history(self) -> None:
        if not hasattr(self, "jarvis_tree"):
            return
        for item in self.jarvis_tree.get_children():
            self.jarvis_tree.delete(item)
        jobs = self.jarvis.repo.list_jobs(limit=150)
        for job in jobs:
            created = job.created_at or ""
            data = created[:10] if len(created) >= 10 else created
            ora = created[11:19] if len(created) >= 19 else ""
            mail = (job.subject or job.mail_id or "")[:40]
            self.jarvis_tree.insert(
                "",
                "end",
                iid=str(job.id),
                values=(
                    data,
                    ora,
                    mail,
                    job.order_number or "—",
                    job.contract_number or "—",
                    str(job.docs_downloaded or job.docs_found or 0),
                    str(job.docs_printed or 0),
                    job.outcome or job.status or "—",
                    job.duration_label,
                ),
            )

    def _jarvis_show_detail(self) -> None:
        sel = self.jarvis_tree.selection()
        if not sel:
            return
        try:
            job_id = int(sel[0])
        except (TypeError, ValueError):
            return
        job = self.jarvis.repo.get_by_id(job_id)
        if not job:
            return
        events = self.jarvis.repo.list_events(job_id)
        lines = [
            f"ID lavorazione: {job.id}",
            f"ID mail: {job.mail_id}",
            f"Message-ID: {job.message_id or '—'}",
            f"Mittente: {job.sender or '—'}",
            f"Oggetto: {job.subject or '—'}",
            f"Data ricezione: {job.received_at or '—'}",
            f"Ordine: {job.order_number or '—'}",
            f"Contratto: {job.contract_number or '—'}",
            f"MdA: {job.acquisition_module or '—'}",
            f"Data avvio: {job.started_at or '—'}",
            f"Data fine: {job.finished_at or '—'}",
            f"Durata: {job.duration_label}",
            f"Documenti trovati: {job.docs_found}",
            f"Documenti scaricati: {job.docs_downloaded}",
            f"Inviati alla stampa: {job.docs_printed}",
            f"Stampante: {job.printer_name or 'predefinita OS'}",
            f"Esito: {job.outcome or job.status}",
            f"Tentativi: {job.attempts}/{job.max_attempts}",
            f"Simulazione: {'sì' if job.simulation else 'no'}",
            f"Errore: {job.error_message or '—'}",
            "",
            "--- Log lavorazione ---",
        ]
        for ev in events:
            lines.append(f"{ev.timestamp} [{ev.level}] {ev.message}")
        text = "\n".join(lines)
        self.jarvis_detail.configure(state="normal")
        self.jarvis_detail.delete("1.0", "end")
        self.jarvis_detail.insert("1.0", text)
        self.jarvis_detail.configure(state="disabled")


def run_app() -> None:
    app = MainWindow()
    app.mainloop()
