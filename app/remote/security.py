"""Sicurezza Remote Agent — sanitizzazione, niente remote shell."""

from __future__ import annotations

import re
from typing import Any

# Pattern vietati nei parametri (difesa in profondità)
_FORBIDDEN_PARAM_RE = re.compile(
    r"(?i)(\beval\s*\(|\bexec\s*\(|\b__import__\b|\bos\.system\b|"
    r"\bsubprocess\b|\bpowershell\b|\bcmd\.exe\b|\b\/bin\/sh\b|"
    r"\bSELECT\b.+\bFROM\b|\bDROP\b\s+TABLE|\bINSERT\b\s+INTO)"
)

FORBIDDEN_KEYS = frozenset(
    {
        "shell",
        "cmd",
        "command_line",
        "powershell",
        "script",
        "code",
        "sql",
        "eval",
        "exec",
        "path",
        "url",
        "filepath",
        "file_path",
        "python",
    }
)


def sanitize_params(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in params.items():
        k = str(key).strip()
        if not k or k.lower() in FORBIDDEN_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and _FORBIDDEN_PARAM_RE.search(value):
                continue
            if isinstance(value, str) and len(value) > 2000:
                value = value[:2000]
            out[k] = value
        elif isinstance(value, list):
            clean_list = []
            for item in value[:50]:
                if isinstance(item, (str, int, float, bool)):
                    if isinstance(item, str) and _FORBIDDEN_PARAM_RE.search(item):
                        continue
                    clean_list.append(item if not isinstance(item, str) else item[:500])
            out[k] = clean_list
    return out


def redact_secrets(text: str) -> str:
    """Rimuove pattern tipici di secret dai log."""
    if not text:
        return text
    patterns = [
        (re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+"), r"\1=***"),
        (re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"), "Bearer ***"),
    ]
    out = text
    for cre, repl in patterns:
        out = cre.sub(repl, out)
    return out
