# VISION Agent Contract (canonical)

**Product:** VISION — VIS Intelligent Operations Network  
**Source of truth:** VISION Desktop Agent (`vis-ion`)  
**API version:** `v1` · **Contract version:** `1.0.0`  
**Remote policy:** `status_only` — only `GET_STATUS`

User-facing brand: **VISION**. Never show **JARVIS** in the PWA UI.  
Internal Agent field `vision_core.assistant` may still say `JARVIS` (legacy); treat as internal only.

---

## Architecture

```text
VISION Control Panel (PWA)
        ↓ HTTPS (authenticated user)
     Supabase
        ↑ HTTPS outbound (anon key + VISION_AGENT_TOKEN in RPC body)
VISION Remote Agent (desktop)
```

- Browser never talks to Agent.
- No Agent inbound API / WebSocket.
- No `service_role` or `VISION_AGENT_TOKEN` in the frontend.

---

## Device identity

| Field | Type | Meaning |
|-------|------|---------|
| `device_id` | text PK | Public logical code, e.g. `VIS-TARANTO-01` |
| `device_name` | text | Display name |
| `status` | `ONLINE` \| `DEGRADED` \| `OFFLINE` \| `DISABLED` | Last Agent-reported status |
| `last_seen_at` | timestamptz | Updated by heartbeat |
| `agent_version` | text | |
| `vision_version` | text | |
| `platform_version` | text | |
| `current_job_id` | text | Core job hint (heartbeat-level) |
| `modules` | jsonb | Lightweight module list from heartbeat |

**Online rule (PWA):** device is online if `last_seen_at` is within `metadata.offline_threshold_seconds` (default **60**). Do not invent online from jobs.

Agent env: `VISION_DEVICE_ID` (default `VIS-TARANTO-01`).

---

## Agent authentication

| Location | Value |
|----------|--------|
| Agent process only | raw `VISION_AGENT_TOKEN` (alias `SUPABASE_AGENT_KEY`) |
| Database | SHA-256 hex in `agent_api_tokens.token_hash` |
| Browser | never |

Validation: RPC computes `encode(digest(p_agent_token,'sha256'),'hex')` and matches `(device_id, token_hash)` with `revoked_at IS NULL`.

Rotation: upsert new hash for `(device_id, label)`; set previous `revoked_at` or replace hash; update Agent `.env` only.

---

## Heartbeat

- Interval default: **15s** (`VISION_HEARTBEAT_SECONDS`, min 5)
- Poll interval default: **3s** (`VISION_COMMAND_POLL_SECONDS`, min 2)
- RPC: `agent_heartbeat(...)`
- Updates `devices.last_seen_at`, status, versions, modules; appends `heartbeats`

Agent never intentionally writes `OFFLINE` (coerced to `DEGRADED`).

---

## Commands

Statuses (exact):

```text
PENDING → ACKNOWLEDGED → EXECUTING → COMPLETED | FAILED | REJECTED
```

| Field | Type |
|-------|------|
| `command_id` | uuid PK |
| `command_type` | text |
| `target_device_id` | text → `devices.device_id` |
| `parameters` | jsonb |
| `requested_by` | uuid (auth user) |
| `requested_at` | timestamptz |
| `expires_at` | timestamptz |
| `status` | enum above |
| `acknowledged_at` / `started_at` / `finished_at` | timestamptz |
| `result` | jsonb (GET_STATUS payload) |
| `error` | text |

**Remote allow-list:** only `GET_STATUS`. Other types → `REJECTED` / `REMOTE_OPERATION_NOT_ENABLED`.

---

## GET_STATUS payload (top-level)

```text
ok, api_version, contract_version,
device_id, device_name, agent_version, vision_version, platform_version, timestamp,
core_status, supervisor_status, overall_health,
current_job, queue_size,
modules, skills, services, warnings,
remote_control_enabled, agent,
partial, missing_sections,
vision_core,
enispace_runtime   (when present)
```

### `vision_core`

```text
online, product, product_name, assistant, assistant_state, started_at
```

- User-facing product: `product_name` = **`VISION`**
- `assistant` may be legacy `JARVIS` — do not display as brand

### `enispace_runtime`

```text
status          # IDLE|PROCESSING|DEGRADED|OFFLINE|UNKNOWN
available
active?
pending_jobs?
current_job     # null or sanitized job
last_job
last_mail_check
last_error
detail_state?
```

**Job separation:** top-level `current_job` / `queue_size` = VISION Core.  
`enispace_runtime.current_job` = EniSpace. Never merge.

### Arrays

- `modules[]`: `module_id`, `display_name`, `version`, `status`, `health`, `enabled`, `current_job`
- `services[]`: `service_id`, `available`, `health`
- `warnings[]`: `code`, `severity`, `component`, `message`
- `missing_sections[]`: string names when payload is partial

---

## RPC (exact names)

| RPC | Caller |
|-----|--------|
| `agent_heartbeat` | Agent |
| `agent_fetch_pending_commands` | Agent |
| `agent_update_command` | Agent |
| `create_get_status_command(p_device_id text)` | PWA authenticated |

`p_device_id` is always the **text code** (e.g. `VIS-TARANTO-01`).

---

## Agent env (never in PWA)

```env
VISION_REMOTE_ENABLED=true
VISION_REMOTE_MODE=supabase
VISION_REMOTE_EXECUTION_POLICY=status_only
VISION_DEVICE_ID=VIS-TARANTO-01
VISION_DEVICE_NAME=PC VIS Taranto
SUPABASE_URL=
SUPABASE_ANON_KEY=
VISION_AGENT_TOKEN=
```

`VISION_AGENT_TOKEN` must never be exposed to the PWA.
