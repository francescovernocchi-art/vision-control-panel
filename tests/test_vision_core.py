"""Test architettura VIS•ION (core / moduli / router / job id)."""

from __future__ import annotations

from app.bootstrap import create_vision_core
from app.core.mail_router import MailHints, MailRouter
from app.core.states import ModuleStatus, VisionJobStatus
from app.modules.coin_transport.workflow import FINAL_STATUS
from utils.paths import (
    ASSISTANT_NAME,
    PRODUCT_NAME,
    database_path,
    default_download_dir,
    project_root,
)


def test_branding_and_isolation():
    assert PRODUCT_NAME == "VIS•ION"
    assert ASSISTANT_NAME == "JARVIS"
    assert database_path().name == "vision.db"
    assert "vis-ion" in str(project_root()).lower().replace("\\", "/")
    assert default_download_dir().name == "VIS-ION"


def test_vision_core_modules():
    core = create_vision_core()
    ids = {m.id for m in core.list_modules()}
    assert "enispace" in ids
    assert "coin_transport" in ids
    eni = core.modules.get_info("enispace")
    assert eni is not None
    assert eni.status == ModuleStatus.ONLINE
    coin = core.modules.get_info("coin_transport")
    assert coin is not None
    assert coin.status == ModuleStatus.IN_DEVELOPMENT
    snap = core.snapshot()
    assert snap["core_online"] is True
    core.stop()


def test_mail_router_rules():
    router = MailRouter()
    d1 = router.route(
        MailHints(
            subject="Modulo di Acquisizione 123",
            sender="noreply@eni.com",
            folder="INBOX.MdA_Eni",
        )
    )
    assert d1.action == "ROUTE"
    assert d1.module_id == "enispace"
    d2 = router.route(
        MailHints(
            subject="Trasporto Monete - Sala Conta",
            sender="sala conta@example.com",
            attachment_names=["piano.pdf"],
        )
    )
    assert d2.action == "ROUTE"
    assert d2.module_id == "coin_transport"
    d3 = router.route(MailHints(subject="Newsletter generica", sender="news@x.it"))
    assert d3.action == "NEEDS_CLASSIFICATION"


def test_coin_transport_skeleton_stops_at_approval():
    core = create_vision_core()
    mod = core.modules.get("coin_transport")
    assert mod is not None
    job = mod.create_job_from_mail(subject="Test Sala Conta", source_id="t1")
    assert job is not None
    assert job.job_id.startswith("VISION-")
    assert job.status == VisionJobStatus.WAITING_APPROVAL
    assert FINAL_STATUS in (job.current_step, job.metadata.get("pec", {}).get("status", ""))
    assert job.metadata.get("pec", {}).get("auto_send") is False
    core.stop()


def test_job_id_sequence():
    core = create_vision_core()
    j1 = core.create_job(module_id="enispace", title="a")
    j2 = core.create_job(module_id="enispace", title="b")
    assert j1.job_id != j2.job_id
    assert j1.job_id.startswith("VISION-")
    core.stop()
