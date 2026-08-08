# VISION Control Panel — Lovable guide

## Product

**VISION** is the private control-panel PWA for the VISION desktop Agent.  
Full name: VIS Intelligent Operations Network.

User-facing brand is always **VISION**. Never use **JARVIS** in UI copy.

## Architecture

```text
PWA (this repo)  →  Supabase  ←  VISION Agent (desktop, outbound only)
```

Source of truth for runtime: **VISION Agent** (`GET_STATUS` payload + heartbeat).  
This repository is the canonical Control Panel + Supabase contract for Lovable.

## Security

- Browser does **not** connect to the Agent.
- Never put `VISION_AGENT_TOKEN`, `SUPABASE_SERVICE_ROLE_KEY`, or passwords in frontend env.
- Remote commands: **GET_STATUS only** (`status_only`).

## Supabase (canonical)

See `docs/architecture/SUPABASE_CONTRACT.md`.

Important tables: `devices` (PK `device_id` text), `commands` (PK `command_id`), `agent_api_tokens`, `profiles`, `user_devices`, `heartbeats`.

RPC: `create_get_status_command`, `agent_heartbeat`, `agent_fetch_pending_commands`, `agent_update_command`.

## Agent contract

See `docs/architecture/VISION_AGENT_CONTRACT.md` and `docs/architecture/vision-agent-contract.json`.  
TypeScript: `src/types/vision-contract.ts`.

## UI routes

| Route | Purpose |
|-------|---------|
| `/auth` | Login |
| `/dashboard` | Devices overview (real data) |
| `/dispositivi` | Device list |
| `/dispositivi/$code` | Device detail + GET_STATUS |
| `/attivita` | Activity (VISION / EniSpace) |
| `/moduli` | Module catalog |
| `/moduli/enispace` | EniSpace runtime |
| `/lavorazioni` | Jobs (`is_demo` → DEMO badge) |
| `/approvazioni` | Approvals (if used) |
| `/impostazioni` | Settings |

Legacy `/supervisor` → redirect to `/attivita`.

## Demo rule

Never use demo/mock rows as fallback for Agent health, online state, Core job, or EniSpace runtime.  
If `is_demo=true`, show a clear **DEMO** badge only.

## What Lovable MAY change

- Layout, spacing, typography, color tokens  
- Responsive behavior  
- Component polish / accessibility  
- Empty/loading copy (without inventing runtime data)  
- Non-contract UX improvements  

## What Lovable must NOT change without explicit request

- Database tables / columns / FK  
- RPC signatures or security  
- RLS policies  
- Agent token model  
- Command lifecycle / `status_only`  
- GET_STATUS payload schema  
- Browser ↔ Agent direct channels  
- Product branding away from VISION  

## Env (PWA only)

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
# or VITE_SUPABASE_ANON_KEY=
VITE_DEVICE_ID=VIS-TARANTO-01
```

## Further reading

- `README.md` — setup & develop  
- `docs/architecture/VISION_AGENT_CONTRACT.md`  
- `docs/architecture/SUPABASE_CONTRACT.md`  
- `supabase/README.md`
