# Supabase migrations — VIS•ION Remote / Agent

## Quale file applicare

| File | Quando |
|------|--------|
| `20260811_agent_thin_channel_pwa_compat.sql` | **Usare questo** su progetto Supabase con schema PWA Lovable già esistente (`devices.id` uuid + `code`, senza `device_id`). Additive: non DROP. |
| `20260811b_agent_publish_message_p_token.sql` | Allinea `agent_publish_message` a arg **`p_token`** (come heartbeat live). |
| `20260808_vision_remote_readonly.sql` | Solo progetto **greenfield** vuoto (crea `devices` con PK text `device_id`). **Non** applicare se `devices` PWA esiste già. |

Contratto canale sottile: [`docs/VISION_CP_AGENT_THIN_CHANNEL.md`](../../docs/VISION_CP_AGENT_THIN_CHANNEL.md).

## Coesistenza Agent ↔ PWA `devices`

- PWA continua a usare `id` (uuid), `code`, `name`, `status`, …
- Agent usa `device_id` (text, es. `VIS-TARANTO-01`) aggiunto in ALTER
- Backfill: `device_id ← code`
- RPC Agent risolvono `p_device_id` → riga via `device_id` **o** `code`
- `commands.target_device_id` resta uuid PWA; le RPC espongono `target_device_id` testuale all’Agent

## Come applicare (SQL Editor — consigliato)

1. Dashboard Supabase → **SQL** → New query  
2. Incolla l’intero contenuto di `20260811_agent_thin_channel_pwa_compat.sql`  
3. Run  
4. Seed token (sostituisci `YOUR_RAW_TOKEN`):

```sql
insert into public.agent_api_tokens (device_id, token_hash, label)
values (
  'VIS-TARANTO-01',
  encode(digest('YOUR_RAW_TOKEN', 'sha256'), 'hex'),
  'default'
)
on conflict (device_id, label) do update
set token_hash = excluded.token_hash, revoked_at = null;
```

Oppure: `python scripts/hash_agent_token.py YOUR_RAW_TOKEN`

5. Verifica:

```sql
select device_id, code, name, status from public.devices
where device_id = 'VIS-TARANTO-01' or code = 'VIS-TARANTO-01';

select proname from pg_proc
where proname in (
  'agent_heartbeat',
  'agent_fetch_pending_commands',
  'agent_update_command',
  'agent_publish_message',
  'enqueue_supervisor_command'
);
```

6. Desktop: Impostazioni → **Testa connessione Agent**.

## Enqueue wake / deactivate (test)

Come `authenticated` (SQL Editor usa ruolo privilegiato):

```sql
select public.enqueue_supervisor_command('VIS-TARANTO-01', 'WAKE_SUPERVISOR');
-- poi
select public.enqueue_supervisor_command('VIS-TARANTO-01', 'DEACTIVATE_SUPERVISOR');
```

## Rischi residui

- Se `devices.status` è un enum PWA diverso da text, l’UPDATE in heartbeat può fallire su valori non ammessi → allineare etichette (`ONLINE`/`OFFLINE`/…) o cast.
- Policy RLS su `agent_api_tokens` è permissiva per `authenticated` (da restringere ad ADMIN quando i ruoli PWA sono stabili).
- `anon` non legge tabelle; scrive solo via RPC SECURITY DEFINER + token.
- Non applicare la migration greenfield `20260808_*` sullo stesso progetto.
