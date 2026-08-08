"""Bootstrap VIS•ION Core + moduli."""

from __future__ import annotations

from typing import Any, Optional

from app.core.supervisor import VisionCore
from app.modules.coin_transport import CoinTransportModule
from app.modules.enispace import EniSpaceModule
from utils.logger import get_logger

logger = get_logger("vision.bootstrap")

_CORE: Optional[VisionCore] = None


def get_vision_core() -> VisionCore:
    global _CORE
    if _CORE is None:
        _CORE = create_vision_core()
    return _CORE


def create_vision_core(*, jarvis: Any = None) -> VisionCore:
    """Crea Core, registra moduli, avvia."""
    global _CORE
    core = VisionCore()
    core.start()

    enispace = EniSpaceModule(event_bus=core.event_bus, jarvis=jarvis)
    coin = CoinTransportModule(core=core)

    core.register_module(enispace)
    core.register_module(coin)

    try:
        enispace.start()
        core.modules.set_status(enispace.MODULE_ID, enispace.info.status)
    except Exception as exc:  # noqa: BLE001
        logger.error("eniSpace start failed (isolato): %s", exc)
        core.modules.set_status(enispace.MODULE_ID, "ERROR")

    try:
        coin.start()
        core.modules.set_status(coin.MODULE_ID, coin.info.status)
    except Exception as exc:  # noqa: BLE001
        logger.error("coin_transport start failed (isolato): %s", exc)
        core.modules.set_status(coin.MODULE_ID, "ERROR")

    _CORE = core
    logger.info(
        "Bootstrap completo — moduli: %s",
        [m.id for m in core.list_modules()],
    )
    return core


def bind_jarvis(jarvis: Any) -> None:
    core = get_vision_core()
    mod = core.modules.get("enispace")
    if mod and hasattr(mod, "bind_jarvis"):
        mod.bind_jarvis(jarvis)
