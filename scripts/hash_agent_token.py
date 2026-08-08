"""Hash token Agent per agent_api_tokens (SHA-256 hex)."""

from __future__ import annotations

import hashlib
import sys


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw:
        print("Usage: python scripts/hash_agent_token.py <RAW_TOKEN>", file=sys.stderr)
        raise SystemExit(2)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    print(digest)
    print()
    print("-- SQL:")
    print(
        "insert into public.agent_api_tokens (device_id, token_hash, label) values\n"
        f"('VIS-TARANTO-01', '{digest}', 'default')\n"
        "on conflict (device_id, label) do update set token_hash = excluded.token_hash, revoked_at = null;"
    )


if __name__ == "__main__":
    main()
