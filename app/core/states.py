"""Stati globali VIS•ION e mapping verso avatar assistente."""

from __future__ import annotations

from enum import StrEnum


class VisionJobStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AssistantState(StrEnum):
    """Stati avatar globali (indipendenti dal modulo eniSpace)."""

    IDLE = "IDLE"
    MAIL_RECEIVED = "MAIL_RECEIVED"
    ANALYSIS = "ANALYSIS"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    OFFLINE = "OFFLINE"


class ModuleStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
    IN_DEVELOPMENT = "IN_DEVELOPMENT"
