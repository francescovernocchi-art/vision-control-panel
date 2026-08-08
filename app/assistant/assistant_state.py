"""Stato assistente VIS•ION (wrapper leggero)."""

from __future__ import annotations

from app.core.states import AssistantState


class AssistantStateTracker:
    def __init__(self) -> None:
        self.state: str = AssistantState.IDLE

    def set(self, state: str | AssistantState) -> None:
        self.state = str(state)
