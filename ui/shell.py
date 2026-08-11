"""VISION desktop shell — structural presentation (reference fidelity).

Three real regions: LEFT NAV | MAIN WORKSPACE | ASSISTANT RAIL (+ footer).
Presentation only; callers bind real status/data.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from ui.icons import brand_lockup_image, brand_logo_image, brand_title_lockup_image, ctk_icon
from ui.theme import (
    ACTIVE_NAV_BG,
    ACTIVE_NAV_SOFT,
    ASSISTANT_RAIL_WIDTH,
    AVATAR_DISPLAY_SIZE,
    BG,
    BORDER,
    BORDER_DIM,
    BORDER_FROST,
    CARD,
    CARD_ALT,
    COLORS,
    GLOW,
    HEADER_HEIGHT,
    MUTED,
    NAV_BTN_HEIGHT,
    PRIMARY,
    RADIUS_LG,
    RADIUS_MD,
    SIDEBAR,
    SIDEBAR_WIDTH,
    STATUS_FOOTER_HEIGHT,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)
from utils.paths import PRODUCT_NAME, PRODUCT_FULL_NAME, PRODUCT_TAGLINE_IT, ASSISTANT_TAGLINE


def _font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=font_family(), size=size, weight=weight)


class VisionSidebar(ctk.CTkFrame):
    """Left structural region ~15–17% — large VIS logo + reference nav."""

    # Reference nav (label, route key, icon)
    ITEMS = [
        ("Chat Supervisor", "dashboard", "dashboard"),
        ("Dispositivi", "dispositivi", "devices"),
        ("Attività", "attivita", "history"),
        ("EniSpace", "enispace", "search"),
        ("Lavorazioni", "lavorazioni", "docs"),
        ("Approvazioni", "approvazioni", "approvals"),
        ("Impostazioni", "impostazioni", "settings"),
        ("Log & Diagnostica", "diagnostica_nav", "log"),
        ("Supporto", "supporto", "support"),
    ]

    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None],
        version: str = "2.0-vision",
        **kwargs,
    ):
        kwargs.setdefault("fg_color", SIDEBAR)
        kwargs.setdefault("width", SIDEBAR_WIDTH)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_FROST)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._on_navigate = on_navigate
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active = "dashboard"
        self._version = version

        # HUD edge glow (top + right)
        ctk.CTkFrame(self, fg_color=GLOW, height=2, corner_radius=0).place(
            relx=0, rely=0, relwidth=1
        )
        ctk.CTkFrame(self, fg_color=GLOW, width=2, corner_radius=0).place(
            relx=1.0, rely=0, relheight=1, anchor="ne"
        )

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=14, pady=(22, 8))
        lockup = None
        try:
            lockup = brand_lockup_image(128)
        except Exception:
            lockup = None
        if lockup is None:
            try:
                lockup = brand_logo_image(120)
            except Exception:
                lockup = None
        if lockup is not None:
            lbl = ctk.CTkLabel(brand, text="", image=lockup)
            lbl.pack(anchor="center")
            self._logo_ref = lockup
        else:
            ctk.CTkLabel(
                brand, text=PRODUCT_NAME, font=_font(28, "bold"), text_color=PRIMARY
            ).pack(anchor="center")
        ctk.CTkLabel(
            brand,
            text=PRODUCT_FULL_NAME.upper(),
            font=_font(10, "bold"),
            text_color=GLOW,
            wraplength=SIDEBAR_WIDTH - 36,
            justify="center",
        ).pack(anchor="center", pady=(6, 0))
        ctk.CTkLabel(
            brand,
            text=PRODUCT_TAGLINE_IT,
            font=_font(9),
            text_color=MUTED,
            wraplength=SIDEBAR_WIDTH - 36,
            justify="center",
        ).pack(anchor="center", pady=(2, 0))

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        for label, key, icon_name in self.ITEMS:
            try:
                img = ctk_icon(icon_name, 20, MUTED)
            except Exception:
                img = None
            btn = ctk.CTkButton(
                nav,
                text=f"  {label.upper()}",
                image=img,
                compound="left",
                anchor="w",
                height=NAV_BTN_HEIGHT,
                corner_radius=RADIUS_MD,
                fg_color="transparent",
                hover_color=ACTIVE_NAV_SOFT,
                text_color=MUTED,
                font=_font(13, "bold"),
                border_width=0,
                border_color=BORDER_DIM,
                command=lambda k=key: self._click(k),
            )
            if img:
                btn._icon_ref = img  # noqa: SLF001
            btn.pack(fill="x", pady=3)
            self._buttons[key] = btn
            bar = ctk.CTkFrame(btn, fg_color=PRIMARY, width=4, corner_radius=2)
            btn._active_bar = bar  # noqa: SLF001
            bar.place_forget()

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", side="bottom", padx=18, pady=(8, 20))
        ctk.CTkLabel(
            foot,
            text=PRODUCT_NAME,
            font=_font(20, "bold"),
            text_color=PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            foot,
            text=PRODUCT_FULL_NAME,
            font=_font(11),
            text_color=MUTED,
        ).pack(anchor="w", pady=(2, 10))
        self.footer_status = ctk.CTkLabel(
            foot,
            text="●  Sistema operativo in funzione",
            font=_font(12),
            text_color=SUCCESS,
            anchor="w",
        )
        self.footer_status.pack(anchor="w")
        ctk.CTkLabel(
            foot,
            text=f"v{version}",
            font=_font(11),
            text_color=MUTED,
        ).pack(anchor="w", pady=(4, 0))

        self.set_active("dashboard")

    def _click(self, key: str) -> None:
        self._on_navigate(key)

    def set_active(self, key: str) -> None:
        # Map aliases
        alias = {
            "jarvis": "dashboard",
            "assistente": "dashboard",
            "mail": "attivita",
            "coda": "lavorazioni",
            "storico": "lavorazioni",
            "moduli": "dashboard",
            "coin_transport": "lavorazioni",
            "notifiche": "approvazioni",
        }
        visual = alias.get(key, key)
        if visual not in self._buttons and key in self._buttons:
            visual = key
        self._active = visual if visual in self._buttons else key
        for k, btn in self._buttons.items():
            bar = getattr(btn, "_active_bar", None)
            if k == self._active:
                btn.configure(
                    fg_color=ACTIVE_NAV_BG,
                    text_color=TEXT,
                    hover_color=ACTIVE_NAV_BG,
                    border_width=1,
                    border_color=GLOW,
                )
                if bar:
                    bar.configure(fg_color=GLOW)
                    bar.place(x=0, y=8, relheight=0.65)
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=MUTED,
                    hover_color=ACTIVE_NAV_SOFT,
                    border_width=0,
                    border_color=BORDER_DIM,
                )
                if bar:
                    bar.place_forget()

    def set_system_status(self, text: str) -> None:
        t = (text or "").strip()
        if not t.startswith("●") and not t.startswith("○"):
            t = f"●  {t}"
        self.footer_status.configure(text=t)


class VisionTopHeader(ctk.CTkFrame):
    """Reference-like top header spanning workspace + rail area."""

    def __init__(
        self,
        master,
        *,
        on_settings: Optional[Callable] = None,
        on_minimize: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("height", HEADER_HEIGHT)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_FROST)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)

        # Scan-line HUD sotto header
        ctk.CTkFrame(self, fg_color=GLOW, height=2, corner_radius=0).place(
            relx=0, rely=1.0, relwidth=1, anchor="sw"
        )

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y", padx=18)
        title_img = None
        try:
            title_img = brand_title_lockup_image(58)
        except Exception:
            title_img = None
        if title_img is not None:
            self.brand_label = ctk.CTkLabel(left, text="", image=title_img)
            self.brand_label.pack(anchor="w", pady=(8, 0))
            self._title_lockup_ref = title_img
            self.tagline = ctk.CTkLabel(
                left,
                text="",
                font=_font(1),
                text_color=MUTED,
                height=1,
            )
            # tagline already inside lockup image
            self.tagline.pack_forget()
        else:
            self.brand_label = ctk.CTkLabel(
                left,
                text=PRODUCT_NAME,
                font=_font(22, "bold"),
                text_color=TEXT,
            )
            self.brand_label.pack(anchor="w", pady=(12, 0))
            self.tagline = ctk.CTkLabel(
                left,
                text=PRODUCT_FULL_NAME,
                font=_font(12),
                text_color=GLOW,
            )
            self.tagline.pack(anchor="w")
            ctk.CTkLabel(
                left,
                text=PRODUCT_TAGLINE_IT,
                font=_font(10),
                text_color=MUTED,
            ).pack(anchor="w")

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.pack(side="left", expand=True, fill="y")
        self.supervisor_pill = ctk.CTkLabel(
            center,
            text="  ○  VISION Supervisor Offline  ",
            font=_font(13, "bold"),
            text_color=MUTED,
            fg_color=CARD_ALT,
            corner_radius=20,
            height=32,
        )
        self.supervisor_pill.pack(pady=18)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=16)
        self.device_label = ctk.CTkLabel(
            right,
            text="  PC-AGENT-01  ",
            font=_font(12, "bold"),
            text_color=TEXT,
            fg_color=CARD_ALT,
            corner_radius=8,
            height=30,
        )
        self.device_label.pack(side="left", padx=(0, 12), pady=18)

        # Decorative window controls (bind real window actions)
        ctrl = ctk.CTkFrame(right, fg_color="transparent")
        ctrl.pack(side="left", pady=14)
        for txt, cmd in (
            ("—", on_minimize),
            ("□", None),
            ("✕", on_close),
        ):
            ctk.CTkButton(
                ctrl,
                text=txt,
                width=34,
                height=28,
                fg_color="transparent",
                hover_color=ACTIVE_NAV_SOFT,
                text_color=MUTED,
                font=_font(14),
                command=cmd if cmd else (lambda: None),
            ).pack(side="left", padx=2)

        # Hidden compatibility hooks used by MainWindow
        self.title_label = self.brand_label
        self.subtitle_label = self.tagline
        self.session_label = ctk.CTkLabel(self, text="eniSpace · offline", text_color=MUTED)
        # keep off-layout but queryable
        self.session_label.place_forget()
        # Compat bridge for MainWindow legacy jarvis_header.set_status / .dot
        header_self = self

        class _SupervisorCompat:
            def set_status(self, online: bool, text: str | None = None) -> None:
                header_self.set_supervisor(bool(online), label=text)

            class _Dot:
                def configure(self, **kwargs) -> None:
                    color = kwargs.get("text_color")
                    if color:
                        header_self.supervisor_pill.configure(text_color=color)

            @property
            def dot(self) -> "_SupervisorCompat._Dot":
                return _SupervisorCompat._Dot()

        self.jarvis_header = _SupervisorCompat()
        self._on_settings = on_settings

    def set_page(self, title: str, subtitle: str = "") -> None:
        # Page title lives in workspace; header keeps brand lockup identity
        _ = title
        _ = subtitle
        tag = getattr(self, "tagline", None)
        if tag is None:
            return
        try:
            if tag.winfo_manager():
                tag.configure(text=PRODUCT_FULL_NAME)
        except Exception:
            pass

    def set_supervisor(self, online: bool, label: Optional[str] = None) -> None:
        if online:
            self.supervisor_pill.configure(
                text=f"  ●  {label or 'VISION Supervisor Online'}  ",
                text_color=SUCCESS,
            )
        else:
            self.supervisor_pill.configure(
                text=f"  ○  {label or 'VISION Supervisor Offline'}  ",
                text_color=MUTED,
            )

    def set_device(self, name: str) -> None:
        self.device_label.configure(text=f"  {name}  ")


# Backward-compatible alias used by older imports
AppHeader = VisionTopHeader


class VisionAssistantRail(ctk.CTkFrame):
    """Right structural region ~18–21% — large humanoid profile + system status."""

    def __init__(
        self,
        master,
        *,
        avatar_factory: Optional[Callable] = None,
        on_console: Optional[Callable] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("width", ASSISTANT_RAIL_WIDTH)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_FROST)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)

        ctk.CTkFrame(self, fg_color=GLOW, width=2, corner_radius=0).place(
            relx=0, rely=0, relheight=1
        )
        ctk.CTkFrame(self, fg_color=GLOW, height=2, corner_radius=0).place(
            relx=0, rely=0, relwidth=1
        )

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(18, 6))
        ctk.CTkLabel(head, text="VISION", font=_font(18, "bold"), text_color=TEXT).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            head, text=ASSISTANT_TAGLINE, font=_font(11, "bold"), text_color=GLOW
        ).pack(anchor="w", pady=(2, 0))

        self.avatar_host = ctk.CTkFrame(
            self, fg_color=CARD_ALT, corner_radius=RADIUS_LG, border_width=1, border_color=BORDER_FROST
        )
        self.avatar_host.pack(fill="x", padx=14, pady=(8, 8))
        self.avatar = None
        if avatar_factory is not None:
            try:
                self.avatar = avatar_factory(self.avatar_host)
                if self.avatar is not None:
                    self.avatar.pack(fill="x", padx=6, pady=6)
            except Exception:
                self.avatar = None
        if self.avatar is None:
            ctk.CTkLabel(
                self.avatar_host, text="VISION", font=_font(28, "bold"), text_color=PRIMARY
            ).pack(pady=40)

        bubble = ctk.CTkFrame(
            self, fg_color=CARD_ALT, corner_radius=RADIUS_MD, border_width=1, border_color=BORDER_FROST
        )
        bubble.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(
            bubble,
            text="Sono VISION.\nIl tuo assistente operativo.\nCome posso aiutarti?",
            font=_font(13),
            text_color=TEXT,
            justify="left",
            wraplength=ASSISTANT_RAIL_WIDTH - 48,
        ).pack(anchor="w", padx=14, pady=12)

        status = ctk.CTkFrame(
            self, fg_color=CARD_ALT, corner_radius=RADIUS_MD, border_width=1, border_color=BORDER_FROST
        )
        status.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        ctk.CTkLabel(
            status, text="STATO SISTEMA", font=_font(13, "bold"), text_color=TEXT
        ).pack(anchor="w", padx=14, pady=(14, 8))
        self._status_labels: dict[str, ctk.CTkLabel] = {}
        for key, title in (
            ("supervisor", "Supervisor"),
            ("enispace", "EniSpace"),
            ("mail", "Mail"),
            ("devices", "Dispositivi"),
            ("jobs", "Lavorazioni"),
        ):
            row = ctk.CTkFrame(status, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row, text=title, font=_font(13), text_color=MUTED).pack(side="left")
            lab = ctk.CTkLabel(row, text="—", font=_font(13, "bold"), text_color=TEXT)
            lab.pack(side="right")
            self._status_labels[key] = lab

        if on_console:
            ctk.CTkButton(
                self,
                text=">_  Apri Console",
                height=44,
                corner_radius=RADIUS_MD,
                fg_color=CARD_ALT,
                border_width=2,
                border_color=PRIMARY,
                hover_color=ACTIVE_NAV_SOFT,
                text_color=TEXT,
                font=_font(14, "bold"),
                command=on_console,
            ).pack(fill="x", padx=14, pady=(8, 18), side="bottom")

    def set_status(self, key: str, value: str, *, ok: Optional[bool] = None) -> None:
        # Map legacy remote key → devices
        if key == "remote":
            key = "devices"
        lab = self._status_labels.get(key)
        if lab is None:
            return
        color = TEXT
        if ok is True:
            color = SUCCESS
        elif ok is False:
            color = WARNING
        lab.configure(text=value, text_color=color)


AssistantRail = VisionAssistantRail


class VisionStatusFooter(ctk.CTkFrame):
    def __init__(self, master, *, version: str = "2.0-vision", **kwargs):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("height", STATUS_FOOTER_HEIGHT)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_FROST)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        ctk.CTkFrame(self, fg_color=GLOW, height=2, corner_radius=0).place(
            relx=0, rely=0, relwidth=1
        )
        self.left = ctk.CTkLabel(
            self,
            text="●  Sistema operativo in funzione",
            font=_font(12),
            text_color=SUCCESS,
        )
        self.left.pack(side="left", padx=18)
        self.center = ctk.CTkLabel(
            self, text=f"Versione {version}  ·  Modulo: Dashboard", font=_font(12), text_color=MUTED
        )
        self.center.pack(side="left", padx=20)
        self.right = ctk.CTkLabel(
            self, text="VISION AGENT  ·  —", font=_font(12), text_color=MUTED
        )
        self.right.pack(side="right", padx=18)

    def set_module(self, name: str) -> None:
        # preserve version prefix if present
        self.center.configure(text=f"Modulo: {name}")

    def set_connection(self, text: str, *, ok: Optional[bool] = None) -> None:
        color = MUTED
        if ok is True:
            color = SUCCESS
        elif ok is False:
            color = WARNING
        self.right.configure(text=text, text_color=color)


StatusFooter = VisionStatusFooter


class WorkspacePageTitle(ctk.CTkFrame):
    """Large page title block for main workspace (IMPOSTAZIONI, DASHBOARD, …)."""

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.title_label = ctk.CTkLabel(
            self, text=title.upper(), font=_font(28, "bold"), text_color=TEXT
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            self, text=subtitle, font=_font(14), text_color=MUTED
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 12))

    def set(self, title: str, subtitle: str = "") -> None:
        self.title_label.configure(text=title.upper())
        self.subtitle_label.configure(text=subtitle)
