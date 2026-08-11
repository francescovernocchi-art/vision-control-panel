"""Chat UI con VISION Supervisor — presentazione Control Panel (thin channel)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ui.theme import (
    ACCENT,
    BORDER_FROST,
    CARD,
    CARD_ALT,
    COLORS,
    CONSOLE_BG,
    ERROR,
    GLOW,
    MUTED,
    PRIMARY,
    RADIUS_LG,
    RADIUS_MD,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)


def _font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=font_family(), size=size, weight=weight)


class StatusChip(ctk.CTkFrame):
    """Minimal status pill — Agent / Supervisor."""

    def __init__(self, master, label: str, **kwargs):
        kwargs.setdefault("fg_color", CARD_ALT)
        kwargs.setdefault("corner_radius", 20)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)
        self._title = label
        self._dot = ctk.CTkLabel(
            self, text="○", font=_font(12, "bold"), text_color=MUTED, width=18
        )
        self._dot.pack(side="left", padx=(10, 2), pady=6)
        self._text = ctk.CTkLabel(
            self,
            text=f"{label}: —",
            font=_font(12, "bold"),
            text_color=MUTED,
        )
        self._text.pack(side="left", padx=(0, 12), pady=6)

    def set_state(self, value: str, *, tone: str = "muted") -> None:
        colors = {
            "ok": SUCCESS,
            "warn": WARNING,
            "err": ERROR,
            "info": ACCENT,
            "muted": MUTED,
        }
        color = colors.get(tone, MUTED)
        mark = "●" if tone in ("ok", "warn", "info") else "○"
        self._dot.configure(text=mark, text_color=color)
        self._text.configure(text=f"{self._title}: {value}", text_color=color)
        try:
            self.configure(border_color=color if tone != "muted" else COLORS["border"])
        except Exception:
            pass


class ChatBubble(ctk.CTkFrame):
    """Single transcript bubble (supervisor / system / user)."""

    def __init__(
        self,
        master,
        *,
        role: str,
        text: str,
        timestamp: str = "",
        level: str = "INFO",
        **kwargs,
    ):
        role = (role or "supervisor").lower()
        level = (level or "INFO").upper()
        if role == "user":
            bg, border, align = "#0B3D91", PRIMARY, "e"
        elif role == "system":
            bg, border, align = CARD_ALT, COLORS["border"], "w"
        else:
            bg, border, align = "#0A2238", BORDER_FROST, "w"
        kwargs.setdefault("fg_color", bg)
        kwargs.setdefault("corner_radius", RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", border)
        super().__init__(master, **kwargs)
        self._align = align

        who = {
            "supervisor": "VISION Supervisor",
            "system": "Sistema",
            "user": "Tu",
        }.get(role, "VISION")
        level_color = {
            "SUCCESS": SUCCESS,
            "WARNING": WARNING,
            "ERROR": ERROR,
            "INFO": GLOW,
        }.get(level, MUTED)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(
            head, text=who, font=_font(11, "bold"), text_color=level_color
        ).pack(side="left")
        if timestamp:
            ctk.CTkLabel(
                head, text=timestamp, font=_font(10), text_color=MUTED
            ).pack(side="right")

        ctk.CTkLabel(
            self,
            text=text,
            font=_font(13),
            text_color=TEXT,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", padx=12, pady=(4, 10))


class SupervisorChatTranscript(ctk.CTkScrollableFrame):
    """Scrollable chat history."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", CONSOLE_BG)
        kwargs.setdefault("corner_radius", RADIUS_LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_FROST)
        super().__init__(master, **kwargs)
        self._bubbles: list[ChatBubble] = []
        self._max = 200

    def clear(self) -> None:
        for b in self._bubbles:
            try:
                b.destroy()
            except Exception:
                pass
        self._bubbles.clear()

    def append(
        self,
        text: str,
        *,
        role: str = "supervisor",
        level: str = "INFO",
        timestamp: Optional[str] = None,
    ) -> None:
        msg = (text or "").strip()
        if not msg:
            return
        ts = timestamp or datetime.now().strftime("%H:%M")
        bubble = ChatBubble(
            self, role=role, text=msg, timestamp=ts, level=level
        )
        side = "right" if role == "user" else "left"
        bubble.pack(fill="x", padx=(12 if side == "left" else 48, 12 if side == "right" else 48), pady=6, anchor=side[0])
        self._bubbles.append(bubble)
        while len(self._bubbles) > self._max:
            old = self._bubbles.pop(0)
            try:
                old.destroy()
            except Exception:
                pass
        try:
            self._parent_canvas.yview_moveto(1.0)  # noqa: SLF001
        except Exception:
            pass


class SupervisorComposer(ctk.CTkFrame):
    """Wake / deactivate actions — thin channel outbound."""

    def __init__(
        self,
        master,
        *,
        on_wake: Optional[Callable[[], None]] = None,
        on_deactivate: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
        on_remote_toggle: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", RADIUS_LG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            top,
            text="Comandi al Supervisor",
            font=_font(12, "bold"),
            text_color=GLOW,
        ).pack(side="left")
        ctk.CTkLabel(
            top,
            text="Sveglia / Disattiva — canale sottile",
            font=_font(11),
            text_color=MUTED,
        ).pack(side="left", padx=(10, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(4, 12))

        self.btn_wake = ctk.CTkButton(
            row,
            text="Sveglia",
            height=42,
            width=140,
            corner_radius=RADIUS_MD,
            fg_color=PRIMARY,
            hover_color=ACCENT,
            font=_font(14, "bold"),
            command=on_wake,
        )
        self.btn_wake.pack(side="left", padx=(0, 8))

        self.btn_sleep = ctk.CTkButton(
            row,
            text="Disattiva",
            height=42,
            width=140,
            corner_radius=RADIUS_MD,
            fg_color=CARD_ALT,
            hover_color=COLORS["border"],
            border_width=1,
            border_color=ERROR,
            font=_font(14, "bold"),
            command=on_deactivate,
        )
        self.btn_sleep.pack(side="left", padx=(0, 8))

        if on_remote_toggle is not None:
            self.btn_remote = ctk.CTkButton(
                row,
                text="Remote OFF",
                height=42,
                width=130,
                corner_radius=RADIUS_MD,
                fg_color=CARD_ALT,
                hover_color=COLORS["border"],
                border_width=1,
                border_color=COLORS["border"],
                font=_font(12, "bold"),
                command=on_remote_toggle,
            )
            self.btn_remote.pack(side="left", padx=(0, 8))
        else:
            self.btn_remote = None

        if on_settings is not None:
            ctk.CTkButton(
                row,
                text="⚙",
                width=42,
                height=42,
                corner_radius=RADIUS_MD,
                fg_color=CARD_ALT,
                hover_color=COLORS["border"],
                border_width=1,
                border_color=COLORS["border"],
                font=_font(16),
                command=on_settings,
            ).pack(side="right")
