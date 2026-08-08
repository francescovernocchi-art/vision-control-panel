# VIS•ION Mobile — integrazione Agent (GET_STATUS / READ ONLY)

Contratto ufficiale (repo Python, sola lettura):
`vis-ion/docs/VISION_REMOTE_PWA_CONTRACT.md`

La PWA è un **terminale remoto in sola lettura**.
Comunicazione **solo** via Supabase (PostgreSQL + Realtime).

## Env PWA

```env
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_DEVICE_ID=VIS-TARANTO-01
```

Alias Lovable ancora accettato: `VITE_SUPABASE_PUBLISHABLE_KEY` → stesso ruolo di anon.

**Mai** in PWA: `VISION_AGENT_TOKEN`, `SUPABASE_AGENT_KEY`, `service_role`.

## RPC

```text
create_get_status_command(p_device_id text)  -- es. 'VIS-TARANTO-01'
```

Nessun insert diretto client su `commands` per GET_STATUS.

## Lifecycle

`PENDING → ACKNOWLEDGED → EXECUTING → COMPLETED | FAILED | REJECTED`

Realtime su `commands` + `devices`; fallback poll **4s**; timeout UI **30s** →
«VIS•ION Agent non ha risposto» **senza** FAILED lato client.

## Migration PWA (bridge schema Lovable)

`supabase/migrations/20260808140000_get_status_readonly.sql`

Adatta il contratto allo schema esistente (`devices.code`, `commands.id`).
`user_devices` Lovable = push; autorizzazione device = `device_access`.

## UI

- Badge **REMOTE CONTROL / READ ONLY**
- Modalità **CLOUD** vs **DEMO / NON COLLEGATO**
- Unico comando remoto: **Aggiorna stato**
- Altri: **NON ANCORA ABILITATO**
