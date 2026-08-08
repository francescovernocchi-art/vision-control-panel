# VISION Control Panel

Private PWA control panel for the **VISION** desktop Agent  
(VIS Intelligent Operations Network).

## What is VISION?

| Piece | Role |
|-------|------|
| **VISION Agent** (desktop Python) | Runtime source of truth — heartbeat + GET_STATUS |
| **Supabase** | Auth, RLS, commands, device state |
| **This PWA** | Authenticated read-only operations console |

Architecture:

```text
PWA → Supabase ← VISION Agent (outbound HTTPS only)
```

## Stack

React · TypeScript · Vite · TanStack Router/Query · Supabase JS · Tailwind · shadcn/ui

## Branding

User-facing name: **VISION**. Do not use JARVIS in the UI.

## Setup

```bash
npm install
cp .env.example .env
# set VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY (or ANON)
npm run dev
```

### PWA `.env` (public only)

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
VITE_DEVICE_ID=VIS-TARANTO-01
```

Never put `SERVICE_ROLE` or `VISION_AGENT_TOKEN` here.

### Agent env (desktop — not this repo)

```env
VISION_REMOTE_ENABLED=true
VISION_REMOTE_MODE=supabase
VISION_REMOTE_EXECUTION_POLICY=status_only
VISION_DEVICE_ID=VIS-TARANTO-01
SUPABASE_URL=
SUPABASE_ANON_KEY=
VISION_AGENT_TOKEN=
```

`VISION_AGENT_TOKEN` must never be exposed to the PWA.

## Supabase

Canonical schema: `supabase/migrations/20260809000000_vision_canonical_remote.sql`  
See `supabase/README.md` and `docs/architecture/SUPABASE_CONTRACT.md`.

## Auth

Supabase Auth. Protected routes under `/_authenticated/*`. Roles via `profiles.role`.

## GET_STATUS

1. PWA calls `create_get_status_command('VIS-TARANTO-01')`  
2. Row appears in `commands` (`PENDING`)  
3. Agent polls, executes, writes `result`  
4. PWA renders `vision_core` + `enispace_runtime` (jobs kept separate)

## Scripts

```bash
npm test
npx tsc --noEmit
npm run build
npm run lint
```

## Lovable

Read **`LOVABLE.md`** first. Lovable may polish UI; must not change DB/RPC/RLS/token/command contracts without explicit request.

## Architecture docs

- `docs/architecture/VISION_AGENT_CONTRACT.md`
- `docs/architecture/SUPABASE_CONTRACT.md`
- `docs/architecture/vision-agent-contract.json`
- `src/types/vision-contract.ts`

## Legacy baseline

Recoverable Git history:

- Branch: `archive/pre-agent-contract-rebuild`
- Tag: `archive/pre-agent-contract-rebuild-v1`

## Security

- No browser → Agent  
- No Agent token in frontend  
- No service_role in frontend  
- Remote: GET_STATUS only (`status_only`)
