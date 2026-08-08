"""SkillRegistry — catalogo skill STATICO (no discovery, no start moduli)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from app.platform.skill_descriptor import SkillDescriptor
from app.platform.skill_validator import SkillValidationResult, validate_skill_manifest
from utils.logger import get_logger

logger = get_logger("platform.skills")


class SkillRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._skills: dict[str, SkillDescriptor] = {}

    def register_skill(self, skill: SkillDescriptor) -> bool:
        if not skill.id:
            logger.error("Skill non registrata: id mancante")
            return False
        with self._lock:
            self._skills[skill.id] = skill
        logger.info(
            "Skill registered id=%s module=%s enabled=%s version=%s",
            skill.id,
            skill.module_id,
            skill.enabled,
            skill.version,
        )
        return True

    def get_skill(self, skill_id: str) -> Optional[SkillDescriptor]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self) -> list[SkillDescriptor]:
        with self._lock:
            return list(self._skills.values())

    def get_enabled_skills(self) -> list[SkillDescriptor]:
        return [s for s in self.list_skills() if s.enabled]

    def enable_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return False
            skill.enabled = True
            return True

    def disable_skill(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                return False
            skill.enabled = False
            return True

    def validate_skill(self, data: dict) -> SkillValidationResult:
        return validate_skill_manifest(data)

    def load_skill_manifest(self, path: str | Path) -> Optional[SkillDescriptor]:
        """Carica UN percorso dichiarato esplicitamente — non è discovery."""
        p = Path(path)
        if not p.is_file():
            logger.warning("Skill manifest assente: %s", p)
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.error("Skill manifest non leggibile (%s): %s", p, exc)
            return None
        result = validate_skill_manifest(data)
        for w in result.warnings:
            logger.warning("Skill manifest warning (%s): %s", p.name, w)
        if not result.ok:
            for e in result.errors:
                logger.error("Skill manifest invalid (%s): %s", p.name, e)
            logger.error("Skill NON registrata: %s", p)
            return None
        skill = SkillDescriptor.from_dict(data)
        self.register_skill(skill)
        return skill
