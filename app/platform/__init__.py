"""VIS•ION Platform Layer — fondamenta (cataloghi, dual-registration).

Non sostituisce ModuleManager/bootstrap esistenti.
Nessun discover dinamico / PluginManager in questa fase.
"""

from app.platform.bootstrap import bootstrap_platform, get_platform_context
from app.platform.context import PlatformContext
from app.platform.descriptors import (
    CommandDescriptor,
    EventDescriptor,
    HealthReport,
    ModuleDescriptor,
    ServiceDescriptor,
)
from app.platform.skill_descriptor import SkillDescriptor
from app.platform.supervisor_view import (
    SupervisorCapabilityView,
    SupervisorHealthView,
    SupervisorPlatformView,
    SupervisorServiceView,
    SupervisorSkillView,
    SupervisorSnapshot,
    SupervisorWarning,
)

__all__ = [
    "PlatformContext",
    "ModuleDescriptor",
    "CommandDescriptor",
    "EventDescriptor",
    "HealthReport",
    "ServiceDescriptor",
    "SkillDescriptor",
    "SupervisorPlatformView",
    "SupervisorSnapshot",
    "SupervisorSkillView",
    "SupervisorHealthView",
    "SupervisorServiceView",
    "SupervisorCapabilityView",
    "SupervisorWarning",
    "bootstrap_platform",
    "get_platform_context",
]
