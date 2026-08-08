"""Validazione manifest skill.json — fail soft (no crash app)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([.-][A-Za-z0-9._-]+)?$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)?$")
_FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "credential",
        "credentials",
        "cookie",
        "authorization",
    }
)
_VALID_CATEGORIES = frozenset(
    {
        "automation",
        "operations",
        "logistics",
        "hr",
        "ai",
        "security",
        "reporting",
        "general",
        "core",
    }
)
_VALID_VISIBILITY = frozenset({"public", "internal", "hidden"})


@dataclass
class SkillValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if not self.ok:
            return "ERROR"
        if self.warnings:
            return "WARNING"
        return "OK"


def validate_skill_manifest(data: Any) -> SkillValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return SkillValidationResult(False, ["manifest non è un oggetto JSON"])

    for key in data.keys():
        if str(key).lower() in _FORBIDDEN_KEYS:
            errors.append(f"campo sensibile non consentito: {key}")

    sid = str(data.get("id") or "").strip()
    if not sid:
        errors.append("id mancante")
    elif not _ID_RE.match(sid):
        errors.append(f"id non valido: {sid}")

    mid = str(data.get("module_id") or "").strip()
    if not mid:
        errors.append("module_id mancante")

    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("name mancante")

    version = str(data.get("version") or "").strip()
    if not version:
        errors.append("version mancante")
    elif not _SEMVER_RE.match(version):
        warnings.append(f"version non semver stretta: {version}")

    rcv = data.get("required_core_version")
    if rcv is not None and not isinstance(rcv, str):
        errors.append("required_core_version deve essere string")

    for field_name in ("commands", "events", "permissions", "dependencies"):
        val = data.get(field_name, [])
        if val is None:
            val = []
        if not isinstance(val, list):
            errors.append(f"{field_name} deve essere array")
        else:
            for item in val:
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{field_name} contiene elemento non stringa")

    if "enabled" in data and not isinstance(data.get("enabled"), bool):
        errors.append("enabled deve essere boolean")

    category = str(data.get("category") or "general").lower()
    if category not in _VALID_CATEGORIES:
        warnings.append(f"category sconosciuta: {category}")

    visibility = str(data.get("visibility") or "public").lower()
    if visibility not in _VALID_VISIBILITY:
        warnings.append(f"visibility sconosciuta: {visibility}")

    meta = data.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        errors.append("metadata deve essere object")
    elif isinstance(meta, dict):
        for k in meta.keys():
            if str(k).lower() in _FORBIDDEN_KEYS:
                errors.append(f"metadata sensibile non consentito: {k}")

    return SkillValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
