"""Workflow Trasporto Monete — scheletro step fino ad approvazione PEC."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.job_manager import VisionJob
from app.core.states import VisionJobStatus

FINAL_STATUS = "PEC PRONTA PER APPROVAZIONE"

COIN_TRANSPORT_STEPS = [
    "MAIL_SALA_CONTA",
    "ANALISI",
    "ESTRAZIONE_ALLEGATI",
    "RICONOSCIMENTO_ATTIVITA",
    "MEZZI",
    "ITINERARI",
    "PROVINCE",
    "QUESTURE",
    "GENERAZIONE_DOCUMENTO",
    "PROTOCOLLAZIONE",
    "PREPARAZIONE_PEC",
    "APPROVAZIONE",  # stop qui — nessun INVIO_PEC automatico
]


class CoinTransportWorkflow:
    """Scheletro: avanza metadati step; NON invia PEC."""

    auto_send_pec = False
    final_status = FINAL_STATUS

    def run(self, job: VisionJob) -> VisionJob:
        job.status = VisionJobStatus.PROCESSING
        job.started_at = job.started_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history: list[dict[str, Any]] = list(job.metadata.get("steps") or [])
        total = len(COIN_TRANSPORT_STEPS)
        for idx, step in enumerate(COIN_TRANSPORT_STEPS, start=1):
            job.current_step = step
            job.progress = int((idx / total) * 95)
            history.append(
                {
                    "step": step,
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ok": True,
                }
            )
        job.metadata["steps"] = history
        job.metadata["pec"] = {
            "status": FINAL_STATUS,
            "auto_send": False,
            "actions": ["APRI", "MODIFICA", "APPROVA E INVIA"],
        }
        job.status = VisionJobStatus.WAITING_APPROVAL
        job.requires_attention = True
        job.current_step = FINAL_STATUS
        job.progress = 95
        return job
