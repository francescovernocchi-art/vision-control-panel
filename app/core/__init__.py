"""VIS•ION Core — piattaforma centrale senza logica di dominio dei moduli."""

from app.core.event_bus import EventBus, VisionEvent, EventType
from app.core.job_manager import JobManager, VisionJob
from app.core.module_manager import ModuleManager, ModuleInfo
from app.core.notification_service import VisionNotificationService
from app.core.supervisor import VisionCore
from app.core.states import VisionJobStatus, AssistantState, ModuleStatus
from app.core.mail_router import MailRouter, MailRouteDecision

__all__ = [
    "VisionCore",
    "EventBus",
    "VisionEvent",
    "EventType",
    "JobManager",
    "VisionJob",
    "ModuleManager",
    "ModuleInfo",
    "ModuleStatus",
    "VisionNotificationService",
    "VisionJobStatus",
    "AssistantState",
    "MailRouter",
    "MailRouteDecision",
]
