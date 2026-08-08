"""Test Platform Layer foundation — dual-registration, zero side-effect operativi."""

from __future__ import annotations

from app.bootstrap import create_vision_core
from app.platform import bootstrap_platform, get_platform_context


def test_platform_bootstrap_registers_core_enispace_supervisor():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert ctx is not None
    assert get_platform_context() is ctx

    mods = {m.id for m in ctx.capability.list_modules()}
    assert "core" in mods
    assert "enispace" in mods
    assert "supervisor" in mods

    assert ctx.health.get("core") is not None
    assert ctx.health.get("enispace") is not None
    assert ctx.health.get("supervisor") is not None

    assert ctx.services.has("logger")
    assert ctx.services.has("configuration")
    assert ctx.services.has("storage")
    assert ctx.services.has("event_bus")
    assert ctx.services.has("notification")

    assert ctx.capability.get_command("GET_STATUS") is not None
    assert ctx.capability.get_command("CHECK_ENISPACE_MAIL") is not None
    assert ctx.capability.supports_command("enispace", "CHECK_ENISPACE_MAIL")

    # Core operativo invariato
    assert core.is_online is True
    assert core.modules.get("enispace") is not None
    core.stop()


def test_platform_idempotent_without_force():
    core = create_vision_core()
    a = bootstrap_platform(core, force=True)
    b = bootstrap_platform(core, force=False)
    assert a is b
    core.stop()


def test_enispace_module_still_works_after_platform():
    core = create_vision_core()
    bootstrap_platform(core, force=True)
    mod = core.modules.get("enispace")
    assert mod is not None
    # dry_run: nessun IMAP
    result = mod.check_mail_now(dry_run=True)
    assert result.get("ok") is True
    assert result.get("dry_run") is True
    core.stop()


def test_service_registry_does_not_duplicate_event_bus():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    bus = ctx.services.get("event_bus")
    assert bus is core.event_bus
    # re-register same → ok; different would be ignored
    ctx.services.register("event_bus", bus)
    assert ctx.services.get("event_bus") is core.event_bus
    core.stop()
