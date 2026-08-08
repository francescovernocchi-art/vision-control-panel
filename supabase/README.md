# VISION Supabase

## Canonical migration

Apply **only**:

```text
migrations/20260809000000_vision_canonical_remote.sql
```

This matches the VISION Agent remote contract (`device_id` text PK, `command_id` uuid, GET_STATUS RPCs).

## Legacy

`migrations/legacy/` contains the previous Lovable UUID-based schema.  
**Do not apply** on new Agent-first projects. Kept for archaeology / archive only.

## Bootstrap checklist

1. Create/select Supabase project  
2. Apply canonical migration  
3. Confirm seed device `VIS-TARANTO-01`  
4. Insert `agent_api_tokens.token_hash` = SHA-256(raw) for the device  
5. Configure Agent `.env` + PWA `VITE_SUPABASE_*`  
6. Never put service_role or Agent token in the PWA  

Hash helper (Agent repo): `python scripts/hash_agent_token.py <RAW_TOKEN>`

## Docs

- `docs/architecture/SUPABASE_CONTRACT.md`
- `docs/architecture/VISION_AGENT_CONTRACT.md`
- `LOVABLE.md`
