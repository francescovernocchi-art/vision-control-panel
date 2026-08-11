"""ModuleOnlineGuard: Supervisor verifica moduli e attiva login."""

from __future__ import annotations

from services.jarvis.module_guard import (
    EniSpaceModuleProvider,
    MailModuleProvider,
    ModuleOnlineGuard,
    PrintModuleProvider,
)


class _FakeEni:
    def __init__(self, *, private: bool = False, ensure_ok: bool = True) -> None:
        self.private = private
        self.ensure_ok = ensure_ok
        self.ensure_calls = 0

    def _enispace_private_online(self) -> bool:
        return self.private

    def ensure_enispace_online(self) -> bool:
        self.ensure_calls += 1
        if self.ensure_ok:
            self.private = True
            return True
        return False


def test_guard_skips_ensure_when_already_online() -> None:
    eni = _FakeEni(private=True)
    guard = ModuleOnlineGuard([EniSpaceModuleProvider(eni)])
    statuses = guard.check_and_ensure(ensure=True)
    assert statuses[0].online is True
    assert eni.ensure_calls == 0
    assert guard.all_required_online() is True


def test_guard_progress_on_activation() -> None:
    eni = _FakeEni(private=False, ensure_ok=True)
    guard = ModuleOnlineGuard([EniSpaceModuleProvider(eni)])
    seen: list[str] = []
    statuses = guard.check_and_ensure(
        ensure=True, on_progress=lambda m: seen.append(m)
    )
    assert statuses[0].online is True
    assert any("eniSpace" in m for m in seen)


def test_guard_reports_offline_when_login_fails() -> None:
    eni = _FakeEni(private=False, ensure_ok=False)
    guard = ModuleOnlineGuard([EniSpaceModuleProvider(eni)])
    statuses = guard.check_and_ensure(ensure=True)
    assert statuses[0].online is False
    assert guard.all_required_online() is False


def test_optional_print_does_not_block_required() -> None:
    eni = _FakeEni(private=True)

    class _Cfg:
        username = "u"
        host = "imap.example"

    guard = ModuleOnlineGuard(
        [
            EniSpaceModuleProvider(eni),
            MailModuleProvider(lambda: _Cfg(), test_connection=lambda _c: (True, "ok")),
            PrintModuleProvider(lambda: ""),
        ]
    )
    statuses = guard.check_and_ensure(ensure=True)
    assert guard.all_required_online() is True
    print_st = next(s for s in statuses if s.module_id == "print")
    assert print_st.online is False
    assert print_st.required is False
