"""VIS•ION Platform Layer — fondamenta (cataloghi, dual-registration).

Non sostituisce ModuleManager/bootstrap esistenti.
Nessun discover dinamico / PluginManager in questa fase.
"""

from app.platform.bootstrap import bootstrap_platform, get_platform_context
from app.platform.context import PlatformContext
from app.platform.descriptors import (
    CommandDescriptor,
    EventDescriptor,
    ModuleDescriptor,
)
from app.platform.skill_descriptor import SkillDescriptor

__all__ = [
    "PlatformContext",
    "ModuleDescriptor",
    "CommandDescriptor",
    "EventDescriptor",
    "SkillDescriptor",
    "bootstrap_platform",
    "get_platform_context",
]
