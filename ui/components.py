"""Componenti UI riutilizzabili (CustomTkinter) — solo presentazione."""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from ui import theme
from ui.icons import brand_logo_image, ctk_icon, jarvis_mark
from ui.theme import (
    ACCENT,
    ACTIVE_NAV_BG,
    BG,
    BTN_HEIGHT,
    CARD,
    CARD_ALT,
    COLORS,
    CONSOLE_BG,
    ERROR,
    HEADER_HEIGHT,
    INFO,
    MUTED,
    PRIMARY,
    RADIUS_LG,
    RADIUS_MD,
    SIDEBAR,
    SIDEBAR_WIDTH,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)


def _font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=font_family(), size=size, weight=weight)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text: str = "", **kwargs):
        kwargs.setdefault("height", BTN_HEIGHT)
        kwargs.setdefault("corner_radius", RADIUS_MD)
        kwargs.setdefault("fg_color", PRIMARY)
        kwargs.setdefault("hover_color", ACCENT)
        kwargs.setdefault("text_color", TEXT)
        kwargs.setdefault("font", _font(13, "bold"))
        super().__init__(master, text=text, **kwargs)


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, text: str = "", **kwargs):
        kwargs.setdefault("height", BTN_HEIGHT)
        kwargs.setdefault("corner_radius", RADIUS_MD)
        kwargs.setdefault("fg_color", CARD_ALT)
        kwargs.setdefault("hover_color", COLORS["border"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        kwargs.setdefault("text_color", TEXT)
        kwargs.setdefault("font", _font(13))
        super().__init__(master, text=text, **kwargs)


class DangerButton(ctk.CTkButton):
    def __init__(self, master, text: str = "", **kwargs):
        kwargs.setdefault("height", BTN_HEIGHT)
        kwargs.setdefault("corner_radius", RADIUS_MD)
        kwargs.setdefault("fg_color", CARD_ALT)
        kwargs.setdefault("hover_color", COLORS["border"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", ERROR)
        kwargs.setdefault("text_color", TEXT)
        kwargs.setdefault("font", _font(13))
        super().__init__(master, text=text, **kwargs)


class Badge(ctk.CTkLabel):
    """Status badge (success / warning / error / info / muted)."""

    _PALETTE = {
        "success": (SUCCESS, "#052e16"),
        "warning": (WARNING, "#422006"),
        "error": (ERROR, "#450a0a"),
        "info": (INFO, "#0c4a6e"),
        "muted": (MUTED, CARD_ALT),
        "primary": (PRIMARY, "#082f49"),
    }

    def __init__(
        self,
        master,
        text: str = "",
        variant: str = "muted",
        **kwargs,
    ):
        fg, bg = self._PALETTE.get(variant, self._PALETTE["muted"])
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("fg_color", bg)
        kwargs.setdefault("text_color", fg)
        kwargs.setdefault("font", _font(11, "bold"))
        kwargs.setdefault("padx", 8)
        kwargs.setdefault("height", 22)
        super().__init__(master, text=f"  {text}  ", **kwargs)

    def set_variant(self, text: str, variant: str) -> None:
        fg, bg = self._PALETTE.get(variant, self._PALETTE["muted"])
        self.configure(text=f"  {text}  ", text_color=fg, fg_color=bg)


class Card(ctk.CTkFrame):
    def __init__(
        self,
        master,
        title: str = "",
        subtitle: str = "",
        accent_border: bool = False,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", RADIUS_LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault(
            "border_color", PRIMARY if accent_border else COLORS["border"]
        )
        super().__init__(master, **kwargs)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if title:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(12, 0))
            ctk.CTkLabel(
                head,
                text=title,
                font=_font(13, "bold"),
                text_color=TEXT,
            ).pack(side="left")
            if subtitle:
                ctk.CTkLabel(
                    head,
                    text=subtitle,
                    font=_font(11),
                    text_color=MUTED,
                ).pack(side="left", padx=(10, 0))
            self.body.pack(fill="both", expand=True, padx=14, pady=(8, 14))
        else:
            self.body.pack(fill="both", expand=True, padx=14, pady=14)


class MetricCard(ctk.CTkFrame):
    def __init__(
        self,
        master,
        label: str,
        value: str = "0",
        hint: str = "",
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", RADIUS_LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)
        ctk.CTkLabel(
            self, text=label.upper(), font=_font(11), text_color=MUTED
        ).pack(anchor="w", padx=14, pady=(12, 0))
        self.value_label = ctk.CTkLabel(
            self, text=value, font=_font(26, "bold"), text_color=TEXT
        )
        self.value_label.pack(anchor="w", padx=14, pady=(2, 0))
        self.hint_label = ctk.CTkLabel(
            self, text=hint, font=_font(11), text_color=MUTED
        )
        self.hint_label.pack(anchor="w", padx=14, pady=(0, 12))

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_label.configure(text=value)
        if hint is not None:
            self.hint_label.configure(text=hint)


class StatusIndicator(ctk.CTkFrame):
    def __init__(self, master, label: str = "Status", **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.dot = ctk.CTkLabel(
            self, text="●", font=_font(12), text_color=MUTED, width=16
        )
        self.dot.pack(side="left")
        self.text = ctk.CTkLabel(
            self, text=label, font=_font(12), text_color=MUTED
        )
        self.text.pack(side="left", padx=(4, 0))

    def set_status(self, online: bool, text: str | None = None) -> None:
        if online:
            self.dot.configure(text_color=SUCCESS)
            self.text.configure(
                text=text or "ONLINE", text_color=SUCCESS, font=_font(12, "bold")
            )
        else:
            self.dot.configure(text_color=MUTED)
            self.text.configure(
                text=text or "OFFLINE", text_color=MUTED, font=_font(12)
            )


class SectionHeader(ctk.CTkFrame):
    def __init__(
        self,
        master,
        title: str,
        subtitle: str = "",
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        ctk.CTkLabel(
            self, text=title, font=_font(20, "bold"), text_color=TEXT
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                self, text=subtitle, font=_font(12), text_color=MUTED
            ).pack(anchor="w", pady=(2, 0))


class WorkflowStrip(ctk.CTkFrame):
    """Horizontal workflow: Mail → Analisi → eniSpace → Download → Stampa → Completato."""

    STEPS = ("Mail", "Analisi", "eniSpace", "Download", "Stampa", "Completato")
    _STATE_COLORS = {
        "waiting": MUTED,
        "active": PRIMARY,
        "done": SUCCESS,
        "error": ERROR,
    }

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._labels: list[ctk.CTkLabel] = []
        self._arrows: list[ctk.CTkLabel] = []
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        for i, name in enumerate(self.STEPS):
            lab = ctk.CTkLabel(
                row,
                text=f"  {name}  ",
                font=_font(11, "bold"),
                text_color=MUTED,
                fg_color=CARD_ALT,
                corner_radius=6,
                height=28,
            )
            lab.pack(side="left", padx=(0, 4))
            self._labels.append(lab)
            if i < len(self.STEPS) - 1:
                arr = ctk.CTkLabel(
                    row, text="→", font=_font(12), text_color=MUTED
                )
                arr.pack(side="left", padx=(0, 4))
                self._arrows.append(arr)

    def set_states(self, states: list[str] | dict[str, str]) -> None:
        if isinstance(states, dict):
            seq = [states.get(s, "waiting") for s in self.STEPS]
        else:
            seq = list(states) + ["waiting"] * (len(self.STEPS) - len(states))
        for lab, st in zip(self._labels, seq):
            color = self._STATE_COLORS.get(st, MUTED)
            bg = CARD_ALT
            if st == "active":
                bg = "#0E1A2E"
            elif st == "done":
                bg = "#052e16"
            elif st == "error":
                bg = "#450a0a"
            lab.configure(text_color=color, fg_color=bg)


class JarvisSupervisorCard(ctk.CTkFrame):
    def __init__(self, master, on_open: Optional[Callable] = None, **kwargs):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", RADIUS_LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", PRIMARY)
        super().__init__(master, **kwargs)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        try:
            icon = ctk.CTkLabel(top, text="", image=jarvis_mark(32, PRIMARY))
            icon.pack(side="left", padx=(0, 10))
            self._icon_ref = icon.cget("image")
        except Exception:
            ctk.CTkLabel(
                top, text="J", font=_font(22, "bold"), text_color=PRIMARY, width=32
            ).pack(side="left", padx=(0, 10))
        titles = ctk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titles,
            text="JARVIS SUPERVISORE",
            font=_font(14, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        self.status = StatusIndicator(titles, label="OFFLINE")
        self.status.pack(anchor="w", pady=(2, 0))
        self.meta = ctk.CTkLabel(
            self,
            text="In coda: 0  ·  Ultimo controllo: —",
            font=_font(12),
            text_color=MUTED,
            anchor="w",
            justify="left",
        )
        self.meta.pack(fill="x", padx=14, pady=(4, 8))
        if on_open:
            SecondaryButton(
                self, text="Apri JARVIS", height=32, width=120, command=on_open
            ).pack(anchor="e", padx=14, pady=(0, 12))


class AppHeader(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_settings: Optional[Callable] = None,
        on_record: Optional[Callable] = None,
        on_help: Optional[Callable] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("height", HEADER_HEIGHT)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y", padx=16)
        self.title_label = ctk.CTkLabel(
            left, text="Dashboard", font=_font(16, "bold"), text_color=TEXT
        )
        self.title_label.pack(anchor="w", pady=(10, 0))
        self.subtitle_label = ctk.CTkLabel(
            left,
            text="Panoramica operativa",
            font=_font(11),
            text_color=MUTED,
        )
        self.subtitle_label.pack(anchor="w")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=12)

        self.session_label = ctk.CTkLabel(
            right, text="eniSpace · offline", font=_font(11), text_color=MUTED
        )
        self.session_label.pack(side="left", padx=(0, 12))

        self.jarvis_header = StatusIndicator(right, label="JARVIS OFFLINE")
        self.jarvis_header.pack(side="left", padx=(0, 12))

        self.user_label = ctk.CTkLabel(
            right, text="Operatore", font=_font(11), text_color=MUTED
        )
        self.user_label.pack(side="left", padx=(0, 8))

        if on_help:
            SecondaryButton(
                right, text="?", width=36, height=32, command=on_help
            ).pack(side="left", padx=4)
        if on_record:
            SecondaryButton(
                right,
                text="Mappa portale",
                width=120,
                height=32,
                command=on_record,
            ).pack(side="left", padx=4)
        if on_settings:
            try:
                img = ctk_icon("settings", 16, MUTED)
                btn = ctk.CTkButton(
                    right,
                    text="",
                    image=img,
                    width=36,
                    height=32,
                    fg_color=CARD_ALT,
                    hover_color=COLORS["border"],
                    corner_radius=RADIUS_MD,
                    command=on_settings,
                )
                btn._icon_ref = img  # noqa: SLF001
                btn.pack(side="left", padx=4)
            except Exception:
                SecondaryButton(
                    right, text="⚙", width=36, height=32, command=on_settings
                ).pack(side="left", padx=4)

    def set_page(self, title: str, subtitle: str = "") -> None:
        self.title_label.configure(text=title)
        self.subtitle_label.configure(text=subtitle)


class Sidebar(ctk.CTkFrame):
    # Layout modulare VIS•ION (eniSpace resta area operativa esistente)
    ITEMS = [
        ("dashboard", "Dashboard", "dashboard"),
        ("assistente", "Assistente", "jarvis"),
        ("moduli", "Moduli", "docs"),
        ("enispace", "  eniSpace", "search"),
        ("coin_transport", "  Trasporto Monete", "mail"),
        ("lavorazioni", "Lavorazioni", "history"),
        ("attivita", "Attività", "print"),
        ("notifiche", "Notifiche", "mail"),
        ("jarvis", "JARVIS (eniSpace)", "jarvis"),
        ("ricerca", "Ricerca", "search"),
        ("mail", "Mail", "mail"),
        ("documenti", "Documenti", "docs"),
        ("coda", "Coda stampa", "print"),
        ("storico", "Storico", "history"),
        ("impostazioni", "Impostazioni", "settings"),
    ]

    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None],
        version: str = "1.0",
        **kwargs,
    ):
        kwargs.setdefault("fg_color", SIDEBAR)
        kwargs.setdefault("width", SIDEBAR_WIDTH)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        self._on_navigate = on_navigate
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active = "dashboard"
        self._pulse_job = None
        self._jarvis_online = False

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=14, pady=(16, 12))
        logo_row = ctk.CTkFrame(brand, fg_color="transparent")
        logo_row.pack(fill="x")
        try:
            logo = brand_logo_image(56)
        except Exception:
            logo = None
        if logo is not None:
            logo_lbl = ctk.CTkLabel(logo_row, text="", image=logo)
            logo_lbl.pack(side="left", padx=(0, 10))
            self._brand_logo_ref = logo  # keep CTkImage alive
            titles = ctk.CTkFrame(logo_row, fg_color="transparent")
            titles.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                titles, text="VIS•ION", font=_font(18, "bold"), text_color=PRIMARY
            ).pack(anchor="w")
            ctk.CTkLabel(
                titles,
                text="Intelligent Operations",
                font=_font(11),
                text_color=MUTED,
            ).pack(anchor="w")
        else:
            ctk.CTkLabel(
                brand, text="VIS•ION", font=_font(22, "bold"), text_color=PRIMARY
            ).pack(anchor="w")
            ctk.CTkLabel(
                brand,
                text="Intelligent Operations",
                font=_font(12),
                text_color=MUTED,
            ).pack(anchor="w")

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="both", expand=True, padx=8, pady=4)

        for key, label, icon_name in self.ITEMS:
            try:
                img = ctk_icon(icon_name, 16, MUTED)
            except Exception:
                img = None
            btn = ctk.CTkButton(
                nav,
                text=f"  {label}",
                image=img,
                anchor="w",
                height=38,
                corner_radius=RADIUS_MD,
                fg_color="transparent",
                hover_color=ACTIVE_NAV_BG,
                text_color=MUTED,
                font=_font(13),
                command=lambda k=key: self._click(k),
            )
            if img:
                btn._icon_ref = img  # noqa: SLF001
            btn.pack(fill="x", pady=2)
            self._buttons[key] = btn

            # Left accent bar via nested frame overlay — store ref
            bar = ctk.CTkFrame(btn, fg_color=PRIMARY, width=3, corner_radius=1)
            bar.place(x=0, y=6, relheight=0.7)
            bar.lower()
            btn._active_bar = bar  # noqa: SLF001
            bar.place_forget()

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", side="bottom", padx=14, pady=14)
        self.footer_status = ctk.CTkLabel(
            footer, text="Sistema pronto", font=_font(10), text_color=MUTED
        )
        self.footer_status.pack(anchor="w")
        ctk.CTkLabel(
            footer,
            text=f"v{version}",
            font=_font(10),
            text_color=MUTED,
        ).pack(anchor="w")

        self.set_active("dashboard")

    def _click(self, key: str) -> None:
        self._on_navigate(key)

    def set_active(self, key: str) -> None:
        self._active = key
        for k, btn in self._buttons.items():
            bar = getattr(btn, "_active_bar", None)
            if k == key:
                btn.configure(fg_color=ACTIVE_NAV_BG, text_color=TEXT)
                if bar:
                    bar.place(x=0, y=6, relheight=0.7)
            else:
                btn.configure(fg_color="transparent", text_color=MUTED)
                if bar:
                    bar.place_forget()

    def set_system_status(self, text: str) -> None:
        self.footer_status.configure(text=text)


class PageNavigator:
    """Compat layer for legacy self.tabs.set / self.tabs.get."""

    TAB_TO_PAGE = {
        "RICERCA": "ricerca",
        "CODA STAMPA": "coda",
        "JARVIS": "jarvis",
        "REGISTRO": "mail",
        "CRONOLOGIA": "storico",
    }
    PAGE_TO_TAB = {v: k for k, v in TAB_TO_PAGE.items()}

    def __init__(self, navigate: Callable[[str], None], get_page: Callable[[], str]):
        self._navigate = navigate
        self._get_page = get_page

    def set(self, tab_name: str) -> None:
        page = self.TAB_TO_PAGE.get(tab_name, tab_name.lower())
        self._navigate(page)

    def get(self) -> str:
        page = self._get_page()
        return self.PAGE_TO_TAB.get(page, "RICERCA")

    def add(self, name: str):
        """Unused — pages are pre-built frames."""
        raise NotImplementedError("PageNavigator does not create tabs")


def styled_entry(master, **kwargs) -> ctk.CTkEntry:
    kwargs.setdefault("height", BTN_HEIGHT)
    kwargs.setdefault("fg_color", CONSOLE_BG)
    kwargs.setdefault("border_color", COLORS["border"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("text_color", TEXT)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    return ctk.CTkEntry(master, **kwargs)


def styled_textbox(master, **kwargs) -> ctk.CTkTextbox:
    kwargs.setdefault("fg_color", CONSOLE_BG)
    kwargs.setdefault("text_color", TEXT)
    kwargs.setdefault("border_color", COLORS["border"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("corner_radius", RADIUS_MD)
    kwargs.setdefault("font", ctk.CTkFont(family="Consolas", size=12))
    return ctk.CTkTextbox(master, **kwargs)
