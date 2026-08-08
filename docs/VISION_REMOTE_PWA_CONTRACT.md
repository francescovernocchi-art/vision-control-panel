# VIS•ION Remote — contratto cloud per PWA Lovable (READ-ONLY / GET_STATUS only)
#
# Questo documento è il contratto operativo tra:
#   - Repository Python VIS•ION (Remote Agent + migration)
#   - PWA VIS•ION Mobile su Lovable (progetto separato)
#
# Il repo Python NON contiene la PWA.
# api_version=v1 · contract_version=1.0.0 · device seed: VIS-TARANTO-01

## 1. Scope

La PWA può **osservare** VIS•ION e richiedere solo:

```text
GET_STATUS
```

NON abilitare in UI / RPC client:

- CHECK_ENISPACE_MAIL
- RETRY_JOB
- PAUSE_MODULE
- RESUME_MODULE
- PREPARE_COIN_TRANSPORT
- APPROVE_JOB
- REJECT_JOB

Doppia protezione già presente lato cloud/Agent:

1. **SQL trigger** `enforce_status_only_commands` → INSERT ≠ GET_STATUS rifiutato  
2. **Python** `VISION_REMOTE_EXECUTION_POLICY=status_only` → REJECTED `REMOTE_OPERATION_NOT_ENABLED`

## 2. Migration

File (da applicare solo quando autorizzato, non in produzione senza OK):

```text
supabase/migrations/20260808_vision_remote_readonly.sql
```

## 3. Tabelle

| Tabella | Uso PWA |
|---------|---------|
| `profiles` | ruolo OPERATORE / ADMIN / DIREZIONE / AGENT |
| `devices` | stato device, last_seen_at, versions |
| `heartbeats` | storico leggero (read) |
| `commands` | coda comandi + result GET_STATUS |
| `agent_api_tokens` | **solo ADMIN** — hash token Agent (mai plaintext) |
| `agent_sessions` | sessioni Agent (read) |
| `user_devices` | autorizzazione utente↔device |
| `audit_logs` | audit minimo CREATE_GET_STATUS (read; write solo RPC) |

## 4. View

| View | Uso |
|------|-----|
| `devices_with_derived_status` | status derivato OFFLINE se `now - last_seen_at > threshold` (default 60s da `devices.metadata.offline_threshold_seconds`). L’Agent **non** scrive OFFLINE. |

## 5. RPC

### PWA (authenticated)

```text
create_get_status_command(p_device_id text) → commands row
```

- Richiede `auth.uid()`
- Blocca DIREZIONE
- Richiede `user_can_command_device`
- Crea `GET_STATUS`, `module_id=core`, `expires_at=now()+2min`
- Scrive `audit_logs`

### Agent (anon key + token arg — NON service_role)

```text
agent_heartbeat(p_device_id, p_agent_token, p_status, p_agent_version, p_vision_version,
                p_platform_version, p_current_job_id, p_modules, p_timestamp)

agent_fetch_pending_commands(p_device_id, p_agent_token, p_limit)

agent_update_command(p_device_id, p_agent_token, p_command_id, p_status,
                     p_result, p_error, p_acknowledged_at, p_started_at, p_finished_at)
```

Token: raw `VISION_AGENT_TOKEN` → SHA-256 hex confrontato con `agent_api_tokens.token_hash`.

## 6. Realtime

Sottoscrivere:

- `public.commands` (filter `command_id=eq.<uuid>` e/o `target_device_id=eq.VIS-TARANTO-01`)
- `public.devices` (filter `device_id=eq.VIS-TARANTO-01`)

Fallback polling: 3–5s sul `command_id` corrente.  
Timeout UI GET_STATUS: 30s → messaggio “VIS•ION Agent non ha risposto” **senza** marcare FAILED lato client.

## 7. Flusso GET_STATUS

```text
PWA (OPERATORE/ADMIN)
  → RPC create_get_status_command('VIS-TARANTO-01')
  → commands.status = PENDING
Agent
  → agent_fetch_pending_commands
  → ACKNOWLEDGED → EXECUTING → COMPLETED
  → result JSON v1
PWA Realtime/poll
  → legge commands.result
```

## 8. Shape `commands.result` (v1)

Campi attesi (compatibili RemoteStatusResponse Agent):

```text
api_version, contract_version,
device_id, device_name, agent_version, vision_version, platform_version, timestamp,
core_status, supervisor_status, overall_health,
current_job, queue_size,
modules[], skills[], services[], warnings[],
remote_control_enabled, agent{},
partial, missing_sections[]
```

`overall_health=DEGRADED` **non** è errore generale (es. coin_transport IN_DEVELOPMENT, notification stub).

## 9. UI Lovable (obblighi)

- Badge **REMOTE CONTROL / READ ONLY** (cyan/blu)
- Pulsante unico operativo remoto: **Aggiorna stato** (= GET_STATUS)
- Altri comandi: nascosti o badge “Non ancora abilitato”
- Mostrare: Core, Supervisor, Agent, eniSpace, Trasporto Monete, Platform Health, Servizi, Warning, ultimo aggiornamento
- Se `partial=true` → “Stato parziale” + `missing_sections`
- Offline device: `derived_status` / soglia last_seen (configurabile)
- Nessun secret eniSpace/PEC/cookie in DB

## 10. Ruoli

| Ruolo | Leggere stato | Creare GET_STATUS |
|-------|---------------|-------------------|
| OPERATORE | sì (device autorizzati) | sì |
| ADMIN | sì | sì |
| DIREZIONE | sì | no |
| anon | no tabelle | no |
| Agent token RPC | via RPC | n/a |

## 11. Env Agent Python (riferimento Lovable / ops)

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=eyJ...          # publishable / anon — NON service_role
VISION_AGENT_TOKEN=<raw secret>   # dedicato Agent, NON chiave Supabase
VISION_REMOTE_MODE=supabase
VISION_REMOTE_ENABLED=true
VISION_REMOTE_EXECUTION_POLICY=status_only
VISION_DEVICE_ID=VIS-TARANTO-01
```

Legacy alias ancora letto: `SUPABASE_AGENT_KEY` → stesso valore di `VISION_AGENT_TOKEN`.

## 12. Env PWA Lovable

```env
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_DEVICE_ID=VIS-TARANTO-01
```

## 13. Setup token (ops)

```bash
python scripts/hash_agent_token.py <RAW_TOKEN>
```

Poi INSERT hash in `agent_api_tokens` per `VIS-TARANTO-01`.

## 14. Riferimenti repo Python

- `docs/VISION_REMOTE_CLOUD_SETUP.md` — setup operativo Agent
- `app/remote/backends/supabase.py` — client RPC
- `app/remote/status_service.py` — payload GET_STATUS
- Policy Python: `app/remote/models.py` `is_remote_command_allowed`
