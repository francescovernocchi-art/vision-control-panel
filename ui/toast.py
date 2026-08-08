"""Toast discreti top-right — non sostituiscono i dialoghi critici."""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from ui.theme import (
    CARD_ALT,
    ERROR,
    INFO,
    MUTED,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)


_VARIANT = {
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "info": INFO,
    "jarvis": "#1585D8",
}


class ToastManager:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self._toasts: list[ctk.CTkFrame] = []

    def show(
        self,
        message: str,
        *,
        variant: str = "info",
        duration_ms: int = 3200,
        title: str = "",
    ) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        color = _VARIANT.get(variant, INFO)
        frame = ctk.CTkFrame(
            self.root,
            fg_color=CARD_ALT,
            corner_radius=8,
            border_width=1,
            border_color=color,
            width=320,
        )
        # Do not pack — place top-right
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        if title:
            ctk.CTkLabel(
                inner,
                text=title,
                font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
                text_color=color,
                anchor="w",
            ).pack(fill="x")
        ctk.CTkLabel(
            inner,
            text=message,
            font=ctk.CTkFont(family=font_family(), size=12),
            text_color=TEXT,
            wraplength=280,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        self._toasts.append(frame)
        self._reposition()
        frame.after(duration_ms, lambda f=frame: self._dismiss(f))

    def _reposition(self) -> None:
        try:
            self.root.update_idletasks()
            rw = self.root.winfo_width()
        except Exception:
            return
        y = 64
        for frame in self._toasts:
            try:
                frame.place(x=max(8, rw - 340), y=y)
                frame.lift()
                y += frame.winfo_reqheight() + 8
            except Exception:
                pass

    def _dismiss(self, frame: ctk.CTkFrame) -> None:
        try:
            if frame in self._toasts:
                self._toasts.remove(frame)
            frame.place_forget()
            frame.destroy()
        except Exception:
            pass
        self._reposition()
