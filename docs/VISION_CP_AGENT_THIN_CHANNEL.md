# VIS•ION — canale sottile Control Panel ↔ Agent

**Ruolo Control Panel (desktop):** non è una console di orchestrazione job.

| Direzione | Cosa fa |
|-----------|---------|
| **In** | Riceve messaggi / stato dal Supervisor dell’Agent (console locale + heartbeat remoto) |
| **Out** | Invia solo comandi di lifecycle Supervisor: **sveglia** / **disattiva** |

Niente pipeline job remote (retry, approve, coin transport, ecc.) da questa UI.

## Contratto minimo (cloud)

Device logico Agent: `VISION_DEVICE_ID` (es. `VIS-TARANTO-01`).  
Su schema PWA Lovable la tabella `devices` ha PK `id` (uuid) + `code`; il contratto Agent usa la colonna additiva `device_id` (text) = stesso codice.

### RPC Agent (obbligatorie)

| RPC | Args principali | Uso |
|-----|-----------------|-----|
| `agent_heartbeat` | `p_device_id`, `p_agent_token`, `p_status`, versions… | Presence / stato |
| `agent_fetch_pending_commands` | `p_device_id`, `p_agent_token`, `p_limit` | Coda comandi thin |
| `agent_update_command` | `p_device_id`, `p_agent_token`, `p_command_id`, `p_status`… | ACK / result |

Auth: raw `VISION_AGENT_TOKEN` → SHA-256 hex vs `agent_api_tokens.token_hash`.  
Client Python: `SUPABASE_URL` + `SUPABASE_ANON_KEY` + token — **no** `service_role`.

### Comandi outbound consentiti (thin)

| `command_type` | Effetto sul desktop |
|----------------|---------------------|
| `WAKE_SUPERVISOR` | Avvia Supervisor (equiv. ATTIVA) |
| `DEACTIVATE_SUPERVISOR` | Arresta Supervisor (equiv. DISATTIVA) |
| `GET_STATUS` | Snapshot read-only (compat / probe) |

Policy Agent: `status_only` consente **solo** questi tre (non job operativi).

### Messaggi inbound

- **Locale (Control Panel):** console Supervisor / activity già esistenti.
- **Cloud:** tabella `agent_messages` + RPC `agent_publish_message` — feed leggero, non job store.
- Sequenze mermaid e verifica E2E: [`VISION_AGENT_PWA_COMMUNICATION.md`](./VISION_AGENT_PWA_COMMUNICATION.md).

## Migration da applicare

```text
supabase/migrations/20260811_agent_thin_channel_pwa_compat.sql
```

**Non** applicare `20260808_vision_remote_readonly.sql` su un progetto PWA già popolato (crea `devices` con PK text e confligge). Vedi `supabase/migrations/README.md`.

## Verifica rapida

1. Applicare SQL in Supabase SQL Editor.
2. Inserire hash token in `agent_api_tokens` (vedi setup cloud).
3. Desktop: Impostazioni → **Testa connessione Agent** → heartbeat OK.
4. REMOTE CONTROL ON; inserire comando `WAKE_SUPERVISOR` pending → Supervisor si attiva; messaggio in console.
5. Inserire `DEACTIVATE_SUPERVISOR` → Supervisor si spegne.
