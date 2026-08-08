# VISION Supabase Contract (canonical)

Aligned 1:1 with the VISION Agent remote contract.  
**One schema.** No Lovable parallel tables. No second command queue.

Migration: `supabase/migrations/20260809000000_vision_canonical_remote.sql`  
Legacy Lovable SQL (do not apply on new projects): `supabase/migrations/legacy/`

---

## Tables (minimum)

| Table | Purpose |
|-------|---------|
| `profiles` | `user_id` PK → auth.users; `role` (`OPERATORE`/`ADMIN`/`DIREZIONE`/`AGENT`) |
| `devices` | PK `device_id` **text** (public code) |
| `agent_api_tokens` | SHA-256 hashes only; FK `device_id` text; unique `(device_id, label)` |
| `commands` | PK `command_id` uuid; FK `target_device_id` → devices |
| `heartbeats` | append-only Agent heartbeats |
| `agent_sessions` | session markers |
| `user_devices` | user ↔ device ACL (`can_command`) |
| `audit_logs` | create/command audit |
| `vision_jobs` | optional cloud job records (PWA); never override Agent health |
| `approvals` | optional; only if product needs them |

View: `devices_with_derived_status` (offline from `last_seen_at`).

---

## Device model (decision)

Agent uses **text** `device_id` as identity on every RPC.  
Therefore canonical PK is:

```text
devices.device_id TEXT PRIMARY KEY  -- e.g. VIS-TARANTO-01
```

No separate UUID required for Agent compatibility.  
(If a future UUID is added, it must be additive; Agent continues to use `device_id` text.)

---

## Token model

```text
agent_api_tokens (
  id uuid PK,
  device_id text FK → devices,
  token_hash text,          -- SHA-256 hex of raw token
  label text default 'default',
  created_at, revoked_at, last_used_at,
  UNIQUE (device_id, label)
)
```

- Raw token: Agent `.env` only  
- Hash: DB only  
- RLS: ADMIN manage; anon no table access  

---

## Commands

```text
command_id uuid PK
command_type text
target_device_id text FK
parameters jsonb
requested_by uuid
requested_at / expires_at
status: PENDING|ACKNOWLEDGED|EXECUTING|COMPLETED|FAILED|REJECTED
acknowledged_at / started_at / finished_at
result jsonb
error text
```

Trigger: INSERT must be `GET_STATUS` in `status_only` phase.

---

## RPC

| Name | Grants |
|------|--------|
| `agent_heartbeat` | anon, authenticated (token in body) |
| `agent_fetch_pending_commands` | anon, authenticated |
| `agent_update_command` | anon, authenticated |
| `create_get_status_command` | authenticated only |

All Agent RPCs: `SECURITY DEFINER`, `search_path = public, pg_temp`, validate SHA-256 token.

---

## RLS summary

- `anon`: no direct table privileges  
- `authenticated`: select devices/commands/heartbeats per policy; insert GET_STATUS via RPC/policy  
- `agent_api_tokens`: ADMIN only  
- No `service_role` in browser  

---

## Applying on a project

1. Prefer a **new** Supabase project or clean schema for Agent-first.  
2. Apply only `20260809000000_vision_canonical_remote.sql`.  
3. Do **not** apply `legacy/*` on that project.  
4. Seed/register `VISION-TARANTO-01` (migration seeds device).  
5. Hash Agent token → upsert `agent_api_tokens`.  
6. Point PWA `VITE_SUPABASE_*` and Agent `SUPABASE_*` at that project.
