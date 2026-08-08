# VIS•ION API Contract v1

**VIS Intelligent Operations Network**  
**Contratto ufficiale di sistema — Costituzione tecnica**

| Campo | Valore |
|-------|--------|
| Documento | `VISION_API_CONTRACT_v1.md` |
| Contract version | `1.0.0` |
| API version | `v1` |
| Stato | DRAFT → BASELINE UFFICIALE |
| Ambito | Core · Remote Agent · Mobile PWA · Supabase · Moduli |
| Progetto | `vis-ion` (non legacy `VIS eniSpace Utility`) |
| Data riferimento | 2026-08-08 |

> **Regola di adesione:** tutto ciò che entra in VIS•ION deve rispettare questo contratto.  
> Qualunque modulo futuro comunica **solo** tramite Core (comandi / eventi / job), senza conoscere gli altri moduli, la PWA o Supabase.

---

## Indice

1. [Architettura](#capitolo-1--architettura)
2. [Entity](#capitolo-2--entity)
3. [Device](#capitolo-3--device)
4. [Module](#capitolo-4--module)
5. [Command](#capitolo-5--command)
6. [Job](#capitolo-6--job)
7. [Event](#capitolo-7--event)
8. [Notification](#capitolo-8--notification)
9. [Approval](#capitolo-9--approval)
10. [Heartbeat](#capitolo-10--heartbeat)
11. [Module Interface](#capitolo-11--module-interface)
12. [Command Dispatcher](#capitolo-12--command-dispatcher)
13. [Event Bus](#capitolo-13--event-bus)
14. [Permessi](#capitolo-14--permessi)
15. [Versioning](#capitolo-15--versioning)
16. [Futuri moduli](#capitolo-16--futuri-moduli)
17. [Sequenze](#capitolo-17--sequenze)
18. [Best practices](#capitolo-18--best-practices)
19. [Regole non negoziabili](#capitolo-19--regole-non-negoziabili)
20. [Output e governance](#capitolo-20--output-e-governance)
21. [Valutazione modularità](#valutazione-modularità-piattaforma-aziendale)

---

## Capitolo 1 — Architettura

### 1.1 Principio

VIS•ION è una **piattaforma operativa modulare**.  
Il **Core** è l’unico orchestratore.  
Il **Remote Agent** è l’unico componente PC che parla con il backend (solo connessioni **in uscita** HTTPS/WSS).  
La **PWA** non raggiunge mai direttamente il PC.  
I **moduli** non conoscono PWA, Supabase, né altri moduli.

### 1.2 Diagramma completo

```
┌─────────────────────────────────────────────────────────────────┐
│                     VIS•ION Mobile (PWA)                        │
│              UI · notifiche · approvazioni · comandi            │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS / Realtime (in / out)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Backend VIS•ION (Supabase / futuro)                │
│   devices · commands · jobs · events · notifications · RLS      │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS / WSS  ★ SOLO IN USCITA DAL PC
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VIS•ION Remote Agent                         │
│   identity · heartbeat · poll/realtime · validate · idempotency │
│   sync events/jobs · kill switch locale                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ adapter (in-process)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       VIS•ION Core                              │
│   VisionCore · EventBus · JobManager · ModuleManager            │
│   NotificationService · HealthMonitor · MailRouter              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Module Manager                             │
└───┬───────┬──────────┬──────────┬──────────┬──────────┬─────────┘
    │       │          │          │          │          │
    ▼       ▼          ▼          ▼          ▼          ▼
 eniSpace  Trasporto  Protocollo  HR      EasyPlan  Trasporto
           Monete                           /Gare    Valori
                                              │
                                              ▼
                                         Contestazioni
                                         (+ futuri)
```

### 1.3 Confini di responsabilità

| Componente | Fa | Non fa |
|------------|----|--------|
| PWA | UI, comandi autorizzati, visualizzazione stato | Automazione PC, browser, stampa |
| Backend | Persistenza, RLS, push, offline detection | Logica di dominio operativa |
| Remote Agent | Trasporto sicuro comandi/eventi | Logica eniSpace / PEC / browser |
| Core | Coordinamento, job, eventi, moduli | Dettaglio workflow di dominio |
| Modulo | Dominio specifico | Conoscere PWA/Supabase/altri moduli |

### 1.4 Sicurezza di rete (non negoziabile)

- Nessuna porta aperta sul PC verso Internet
- Nessun port-forwarding
- Nessuna API FastAPI pubblica sul PC
- Nessuna esposizione IP aziendale
- Solo outbound HTTPS/WSS dal Remote Agent

---

## Capitolo 2 — Entity

### 2.1 Catalogo entità fondamentali

| Entità | Scopo sintetico |
|--------|-----------------|
| **Device** | Installazione PC / agent VIS•ION |
| **Module** | Plugin operativo registrato nel Core |
| **Command** | Ordine remoto/locale verso un device/modulo |
| **Job** | Lavorazione operativa tracciabile (`VISION-YYYY-NNNNNN`) |
| **JobEvent** | Evento storico legato a un job (o al sistema) |
| **Notification** | Avviso destinato a utente/PWA |
| **Approval** | Gate umano (es. PEC) |
| **Audit** | Traccia immutabile di azioni sensibili |
| **Heartbeat** | Pulsazione periodica device → backend |
| **User** | Identità umana (PWA / backend) |
| **Role** | Ruolo autorizzativo |

### 2.2 Matrice CRUD (chi fa cosa)

Legenda: **C** create · **U** update · **R** read · **D** delete/archive

| Entità | Crea | Aggiorna | Legge | Elimina / archivia |
|--------|------|----------|-------|---------------------|
| Device | Agent (registrazione) / Admin | Agent (heartbeat) | PWA, Admin | Admin |
| Module | Core (register) | Modulo / Core (status) | Tutti (via Core) | Core (unregister) |
| Command | PWA / Backend | Agent / Core | PWA, Agent, Audit | Backend (retention) |
| Job | Core / Modulo (via Core) | Core / Modulo (via Core) | PWA, Agent, UI locale | Retention policy |
| JobEvent | Core / Agent sync | — (append-only) | PWA, Audit | Retention |
| Notification | Backend (su evento) | PWA (read/ack) | User | User / retention |
| Approval | Modulo (via Core) / PWA request | Approver | Stakeholder | Retention |
| Audit | Sistema | — (immutabile) | Admin / Compliance | Mai (solo retention legale) |
| Heartbeat | Agent | — (nuova riga o upsert) | Backend / PWA | Retention |
| User | Admin / Auth provider | Admin / Self (profilo) | Autorizzati | Admin |
| Role | Admin | Admin | Sistema auth | Admin |

### 2.3 Schemi sintetici (riferimento)

Dettaglio campi nei capitoli 3–10. Qui lo scopo di ciascuna entità:

| Entità | Scopo |
|--------|-------|
| Device | Sapere *quale PC* è online e cosa può fare |
| Module | Sapere *quali capacità* sono disponibili |
| Command | Trasportare *intenti autorizzati* verso il Core |
| Job | Rappresentare *una lavorazione* end-to-end |
| JobEvent | Ricostruire *timeline* e progress |
| Notification | Informare *persone* senza esporre dati sensibili |
| Approval | Bloccare azioni irreversibili fino a OK umano |
| Audit | Compliance e forensics |
| Heartbeat | Liveness device |
| User / Role | Autorizzazione |

---

## Capitolo 3 — Device

### 3.1 Scopo

Identità stabile di un’installazione VIS•ION sul PC aziendale.

### 3.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `device_id` | string | sì | ID univoco stabile (es. `VIS-TARANTO-01`) |
| `device_name` | string | sì | Nome umano (es. `PC VIS Taranto`) |
| `hostname` | string | sì | Hostname OS |
| `agent_version` | string | sì | Versione Remote Agent |
| `vision_version` | string | sì | Versione Core / prodotto |
| `status` | enum | sì | `ONLINE` \| `DEGRADED` \| `OFFLINE` \| `DISABLED` |
| `modules` | array\<ModuleRef\> | sì | Snapshot moduli noti |
| `current_job` | string \| null | no | `job_id` in elaborazione |
| `last_seen` | datetime ISO | sì | Ultimo heartbeat ricevuto (backend) |
| `metadata` | object | no | Extra non sensibili |

**Nota status:**

- `ONLINE` / `DEGRADED` / `DISABLED` → possono essere dichiarati dall’Agent
- `OFFLINE` → **determinato dal backend/PWA** quando `last_seen` supera soglia (l’Agent non auto-scrive OFFLINE per perdita rete)

### 3.3 Esempio JSON

```json
{
  "device_id": "VIS-TARANTO-01",
  "device_name": "PC VIS Taranto",
  "hostname": "VIS-TAR-PC01",
  "agent_version": "0.1.0",
  "vision_version": "2.0-vision",
  "status": "ONLINE",
  "modules": [
    { "module_id": "enispace", "status": "ONLINE", "version": "1.0" },
    { "module_id": "coin_transport", "status": "IN_DEVELOPMENT", "version": "0.1" }
  ],
  "current_job": "VISION-2026-000129",
  "last_seen": "2026-08-08T10:15:00+02:00",
  "metadata": {
    "site": "Taranto",
    "remote_mode": "mock"
  }
}
```

### 3.4 CRUD

| Azione | Attore |
|--------|--------|
| Crea / registra | Agent al primo connect (o Admin) |
| Aggiorna | Agent (heartbeat), Admin (metadata) |
| Legge | PWA, Admin, Backend health |
| Elimina | Solo Admin (soft-delete consigliato) |

---

## Capitolo 4 — Module

### 4.1 Scopo

Dichiarazione di capacità di un plugin operativo.

### 4.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `module_id` | string | sì | ID stabile snake/lower (`enispace`) |
| `display_name` | string | sì | Nome UI |
| `version` | string | sì | SemVer modulo |
| `status` | enum | sì | `ONLINE` \| `OFFLINE` \| `DISABLED` \| `ERROR` \| `IN_DEVELOPMENT` |
| `commands_supported` | string[] | sì | Tipi comando accettati |
| `events_supported` | string[] | sì | Tipi evento emessi |
| `permissions` | string[] | no | Capability / permessi dichiarati |
| `description` | string | no | Descrizione |
| `metadata` | object | no | Extra |

### 4.3 Esempio JSON

```json
{
  "module_id": "enispace",
  "display_name": "eniSpace Automation",
  "version": "1.0.0",
  "status": "ONLINE",
  "commands_supported": [
    "CHECK_ENISPACE_MAIL",
    "RETRY_JOB",
    "PAUSE_MODULE",
    "RESUME_MODULE"
  ],
  "events_supported": [
    "MAIL_RECEIVED",
    "MAIL_ANALYZED",
    "JOB_STARTED",
    "JOB_PROGRESS",
    "JOB_COMPLETED",
    "JOB_FAILED",
    "DOWNLOAD_STARTED",
    "DOWNLOAD_COMPLETED",
    "PRINT_STARTED",
    "PRINT_COMPLETED",
    "PRINT_FAILED",
    "NEEDS_ATTENTION",
    "MODULE_ONLINE",
    "MODULE_OFFLINE"
  ],
  "permissions": [
    "mail_watch",
    "enispace_login",
    "document_download",
    "print_queue"
  ],
  "description": "Automazione mail ENI/MdA, download e stampa"
}
```

### 4.4 CRUD

| Azione | Attore |
|--------|--------|
| Crea | Core (`register_module`) all’avvio |
| Aggiorna | Modulo (status) / Core |
| Legge | Core, Agent (heartbeat), PWA |
| Elimina | Core unregister (raro) |

### 4.5 Catalogo moduli previsti

| module_id | display_name | Stato contratto v1 |
|-----------|--------------|--------------------|
| `enispace` | eniSpace Automation | ONLINE (implementato) |
| `coin_transport` | Trasporto Monete | IN_DEVELOPMENT |
| `protocollo` | VIS Protocollo | FUTURE |
| `hr` | HR | FUTURE |
| `easyplan` | EasyPlan | FUTURE |
| `valori` | Trasporto Valori | FUTURE |
| `gare` | Gare e Costi Manodopera | FUTURE |
| `contestazioni` | Contestazioni / Elogi | FUTURE |

---

## Capitolo 5 — Command

### 5.1 Scopo

Unità di intento remoto (o locale) verso un device/modulo, con ciclo di vita tracciato e idempotente.

### 5.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `command_id` | uuid/string | sì | ID univoco globale |
| `command_type` | string | sì | Deve essere in whitelist |
| `module_id` | string \| null | no* | Target modulo (*obbligatorio se non core) |
| `device_id` | string | sì | Deve coincidere con Agent locale |
| `parameters` | object | sì | Schema per `command_type` (sanitizzato) |
| `requested_by` | string | sì | User id / system |
| `requested_at` | datetime | sì | Creazione |
| `expires_at` | datetime \| null | no | Se scaduto → `REJECTED` |
| `status` | enum | sì | Ciclo sotto |
| `result` | object \| null | no | Payload esito non sensibile |
| `error` | string \| null | no | Messaggio errore |

### 5.3 Ciclo di vita

```
PENDING
   │
   ▼
ACKNOWLEDGED          ← Agent ha ricevuto e validato
   │
   ▼
EXECUTING             ← Dispatcher in esecuzione
   │
   ├──► COMPLETED
   ├──► FAILED
   └──► REJECTED      ← validazione fallita / scaduto / device mismatch / non whitelist
```

Ogni transizione **deve** avere timestamp (`acknowledged_at`, `started_at`, `finished_at`).

### 5.4 Whitelist comandi v1

| command_type | Modulo tipico | Ruolo minimo | Stato implementazione |
|--------------|---------------|--------------|------------------------|
| `GET_STATUS` | core | OPERATOR | Implementato (primo test cloud) |
| `CHECK_ENISPACE_MAIL` | enispace | OPERATOR | Implementato (mock dry_run; cloud solo dopo autorizzazione) |
| `RETRY_JOB` | enispace / * | SUPERVISOR | Implementato base |
| `PAUSE_MODULE` | * | SUPERVISOR | Implementato base |
| `RESUME_MODULE` | * | SUPERVISOR | Implementato base |
| `PREPARE_COIN_TRANSPORT` | coin_transport | OPERATOR | Stub → `NOT_IMPLEMENTED` |
| `APPROVE_JOB` | * | DIREZIONE / SUPERVISOR | Stub → `NOT_IMPLEMENTED` |
| `REJECT_JOB` | * | DIREZIONE / SUPERVISOR | Stub → `NOT_IMPLEMENTED` |

**Vietati per sempre (non whitelist):** shell, PowerShell, CMD, Python arbitrario, `eval`/`exec`, script remoto, SQL arbitrario, path/URL arbitrari, remote desktop.

### 5.5 Esempio JSON

```json
{
  "command_id": "8f2a1c6e-4b9d-4e2a-9c11-0a1b2c3d4e5f",
  "command_type": "GET_STATUS",
  "module_id": "core",
  "device_id": "VIS-TARANTO-01",
  "parameters": {},
  "requested_by": "user:anna.rossi",
  "requested_at": "2026-08-08T10:20:00+02:00",
  "expires_at": "2026-08-08T10:30:00+02:00",
  "status": "PENDING",
  "result": null,
  "error": null
}
```

### 5.6 Validazione obbligatoria (Agent)

Prima di eseguire:

1. `command_id` valido
2. `command_type` ∈ whitelist
3. `device_id` == device locale
4. non già gestito (idempotenza)
5. `status == PENDING`
6. parametri conformi allo schema
7. autorizzazione backend (provenienza)
8. `expires_at` non superato → altrimenti `REJECTED`

### 5.7 CRUD

| Azione | Attore |
|--------|--------|
| Crea | PWA → Backend |
| Aggiorna status | Agent |
| Legge | PWA, Agent, Audit |
| Elimina | Retention backend |

---

## Capitolo 6 — Job

### 6.1 Scopo

Rappresentazione unica di una lavorazione operativa, indipendente dal modulo.

### 6.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `job_id` | string | sì | Formato `VISION-{YYYY}-{NNNNNN}` |
| `module_id` | string | sì | Modulo owner |
| `device_id` | string | sì | Device esecutore |
| `title` | string | sì | Titolo breve |
| `description` | string | no | Dettaglio |
| `status` | enum | sì | Vedi 6.3 |
| `progress` | int 0–100 | sì | Avanzamento |
| `current_step` | string | no | Step corrente |
| `created_at` | datetime | sì | |
| `started_at` | datetime \| null | no | |
| `completed_at` | datetime \| null | no | |
| `requires_attention` | bool | sì | |
| `error` | string \| null | no | |
| `metadata` | object | no | **No secret / no PII non necessari** |

### 6.3 Stati job globali

```
PENDING | QUEUED | PROCESSING | WAITING_APPROVAL
COMPLETED | PARTIAL | NEEDS_ATTENTION | FAILED | CANCELLED
```

I moduli possono avere **sotto-stati** in `current_step` / `metadata.substatus`, senza rompere lo schema globale.

### 6.4 Esempio JSON

```json
{
  "job_id": "VISION-2026-000129",
  "module_id": "enispace",
  "device_id": "VIS-TARANTO-01",
  "title": "MdA ordine 4310758365",
  "description": "Download e stampa documenti Marketplace",
  "status": "PROCESSING",
  "progress": 65,
  "current_step": "DOCUMENT_SEARCH",
  "created_at": "2026-08-08T09:12:01+02:00",
  "started_at": "2026-08-08T09:12:05+02:00",
  "completed_at": null,
  "requires_attention": false,
  "error": null,
  "metadata": {
    "source_type": "mail",
    "source_id": "INBOX.MdA_Eni:12345",
    "order_number": "4310758365"
  }
}
```

### 6.5 Progress mapping (eniSpace — solo step reali)

| Step | Progress indicativo |
|------|---------------------|
| CHECK MAIL | 10% |
| MAIL FOUND | 20% |
| ANALYSIS | 35% |
| ENISPACE LOGIN | 50% |
| DOCUMENT SEARCH | 65% |
| DOWNLOAD | 80% |
| PRINTING | 90% |
| COMPLETED | 100% |

> Non inventare progress se lo step non è osservabile dagli eventi reali.

### 6.6 CRUD

| Azione | Attore |
|--------|--------|
| Crea | Core (`create_job`) su richiesta modulo |
| Aggiorna | Core / modulo via Core |
| Legge | PWA (sync Agent), UI locale |
| Elimina | Retention |

---

## Capitolo 7 — Event

### 7.1 Scopo

Unità di osservabilità e sincronizzazione. Fonte primaria: **VisionCore EventBus**.

### 7.2 Campi (JobEvent / VisionEvent)

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `event_id` | uuid/string | sì | |
| `job_id` | string \| null | no | Se legato a job |
| `device_id` | string | sì | |
| `module_id` | string | sì | `core` \| `remote` \| module_id |
| `event_type` | string | sì | Catalogo sotto |
| `severity` | enum | sì | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` |
| `timestamp` | datetime | sì | |
| `message` | string | sì | Messaggio umano, senza secret |
| `payload` | object | no | Metadata non sensibili |

### 7.3 Esempio JSON

```json
{
  "event_id": "e1b2c3d4-5678-90ab-cdef-1234567890ab",
  "job_id": "VISION-2026-000129",
  "device_id": "VIS-TARANTO-01",
  "module_id": "enispace",
  "event_type": "JOB_PROGRESS",
  "severity": "INFO",
  "timestamp": "2026-08-08T09:14:10+02:00",
  "message": "Ricerca documenti Marketplace",
  "payload": {
    "progress": 65,
    "current_step": "DOCUMENT_SEARCH"
  }
}
```

### 7.4 Catalogo eventi iniziali

#### Comandi / Agent

| event_type | Severity tipica |
|------------|-----------------|
| `COMMAND_RECEIVED` | INFO |
| `COMMAND_STARTED` | INFO |
| `COMMAND_COMPLETED` | INFO |
| `COMMAND_FAILED` | ERROR |

#### Mail / Job

| event_type | Severity tipica |
|------------|-----------------|
| `MAIL_RECEIVED` | INFO |
| `MAIL_ANALYZED` | INFO |
| `JOB_CREATED` | INFO |
| `JOB_STARTED` | INFO |
| `JOB_PROGRESS` | INFO |
| `JOB_COMPLETED` | INFO |
| `JOB_FAILED` | ERROR |
| `NEEDS_ATTENTION` | WARNING |

#### Documenti / stampa

| event_type | Severity tipica |
|------------|-----------------|
| `DOWNLOAD_STARTED` | INFO |
| `DOWNLOAD_COMPLETED` | INFO |
| `PRINT_STARTED` | INFO |
| `PRINT_COMPLETED` | INFO |
| `PRINT_FAILED` | ERROR |
| `DOCUMENT_CREATED` | INFO |

#### Moduli / device

| event_type | Severity tipica |
|------------|-----------------|
| `MODULE_ONLINE` | INFO |
| `MODULE_OFFLINE` | WARNING |
| `DEVICE_DEGRADED` | WARNING |
| `WAITING_APPROVAL` | WARNING |
| `PEC_PREPARED` | INFO |
| `PEC_SENT` | INFO |
| `JARVIS_STATE_CHANGED` | INFO |

### 7.5 Regola avatar / Supervisor

Gli stessi eventi aggiornano lo stato assistente (JARVIS / VIS•ION Supervisor):

| Condizione | Assistant state |
|------------|-----------------|
| Nessun lavoro | `IDLE` |
| Mail rilevata | `MAIL_RECEIVED` |
| Analisi | `ANALYSIS` |
| Job attivo | `PROCESSING` |
| Download | (mappa su PROCESSING / step) |
| Stampa | (mappa su PROCESSING / step) |
| Completato | `SUCCESS` |
| Errore | `ERROR` |
| Intervento | `NEEDS_ATTENTION` |

**Una sola fonte di verità:** EventBus del Core.

### 7.6 CRUD

Append-only. Nessun update in-place. Lettura: PWA, UI, Audit.

---

## Capitolo 8 — Notification

### 8.1 Scopo

Canale verso persone (PWA / futuri provider).  
Il Python Agent **non** invia Web Push: pubblica evento → backend crea notifica.

### 8.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `notification_id` | uuid | sì | |
| `type` | string | sì | Es. `JOB_COMPLETED` |
| `title` | string | sì | |
| `message` | string | sì | |
| `priority` | enum | sì | `LOW` \| `NORMAL` \| `HIGH` \| `URGENT` |
| `module_id` | string \| null | no | |
| `job_id` | string \| null | no | |
| `user_id` | string \| null | no | Destinatario |
| `device_id` | string \| null | no | |
| `created_at` | datetime | sì | |
| `status` | enum | sì | `UNREAD` \| `READ` \| `ARCHIVED` |
| `payload` | object | no | Non sensibile |

### 8.3 Tipi iniziali

`JOB_COMPLETED` · `JOB_FAILED` · `NEEDS_ATTENTION` · `DEVICE_DEGRADED` · `WAITING_APPROVAL`

### 8.4 Esempio JSON

```json
{
  "notification_id": "n-9aa1",
  "type": "NEEDS_ATTENTION",
  "title": "Intervento richiesto",
  "message": "Job VISION-2026-000129 richiede attenzione su eniSpace",
  "priority": "HIGH",
  "module_id": "enispace",
  "job_id": "VISION-2026-000129",
  "user_id": "user:anna.rossi",
  "device_id": "VIS-TARANTO-01",
  "created_at": "2026-08-08T09:20:00+02:00",
  "status": "UNREAD",
  "payload": {}
}
```

### 8.5 CRUD

| Azione | Attore |
|--------|--------|
| Crea | Backend (da evento Agent) |
| Aggiorna (read) | User / PWA |
| Legge | User |
| Elimina | User / retention |

---

## Capitolo 9 — Approval

### 9.1 Scopo

Gate umano per azioni irreversibili (es. invio PEC Trasporto Monete).  
**Default:** nessun invio automatico.

### 9.2 Campi

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `approval_id` | uuid | sì | |
| `job_id` | string | sì | |
| `module_id` | string | sì | |
| `device_id` | string | sì | |
| `request_type` | string | sì | Es. `PEC_SEND` |
| `requested_by` | string | sì | system / user |
| `approver_user_id` | string \| null | no | Chi approva |
| `approver_role` | string \| null | no | Ruolo richiesto |
| `status` | enum | sì | `PENDING` \| `APPROVED` \| `REJECTED` \| `EXPIRED` |
| `expires_at` | datetime \| null | no | |
| `reason` | string \| null | no | Motivazione |
| `created_at` | datetime | sì | |
| `decided_at` | datetime \| null | no | |
| `actions` | string[] | no | Es. `APRI`, `MODIFICA`, `APPROVA E INVIA` |

### 9.3 Workflow

```
Modulo prepara artefatto (es. PEC)
        │
        ▼
Job → WAITING_APPROVAL + Approval PENDING
        │
        ├── PWA: APPROVE_JOB  → (futuro) esecuzione autorizzata
        └── PWA: REJECT_JOB   → chiusura / revisione
```

In contract v1 i comandi `APPROVE_JOB` / `REJECT_JOB` possono essere **ricevuti e validati** ma rispondere `NOT_IMPLEMENTED` finché il workflow non è autorizzato.

### 9.4 Esempio JSON

```json
{
  "approval_id": "ap-1001",
  "job_id": "VISION-2026-000200",
  "module_id": "coin_transport",
  "device_id": "VIS-TARANTO-01",
  "request_type": "PEC_SEND",
  "requested_by": "system:coin_transport",
  "approver_user_id": null,
  "approver_role": "DIREZIONE",
  "status": "PENDING",
  "expires_at": "2026-08-09T18:00:00+02:00",
  "reason": null,
  "created_at": "2026-08-08T11:00:00+02:00",
  "decided_at": null,
  "actions": ["APRI", "MODIFICA", "APPROVA E INVIA"]
}
```

---

## Capitolo 10 — Heartbeat

### 10.1 Scopo

Liveness e inventario minimo del device. Intervallo default: **15 secondi**.

### 10.2 Campi

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `device_id` | string | |
| `device_name` | string | |
| `status` | enum | `ONLINE` \| `DEGRADED` \| `DISABLED` (non `OFFLINE` da agent) |
| `agent_version` | string | |
| `vision_version` | string | |
| `hostname` | string | |
| `current_job_id` | string \| null | |
| `modules` | array | id/status/version |
| `timestamp` | datetime | `last_seen_at` |

### 10.3 Esempio JSON

```json
{
  "device_id": "VIS-TARANTO-01",
  "device_name": "PC VIS Taranto",
  "status": "ONLINE",
  "agent_version": "0.1.0",
  "vision_version": "2.0-vision",
  "hostname": "VIS-TAR-PC01",
  "current_job_id": null,
  "modules": [
    { "module_id": "enispace", "status": "ONLINE", "version": "1.0" },
    { "module_id": "coin_transport", "status": "IN_DEVELOPMENT", "version": "0.1" }
  ],
  "timestamp": "2026-08-08T10:15:00+02:00"
}
```

### 10.4 Regole

- Nessun dato personale / credenziali / cookie
- Backend marca `OFFLINE` se `now - last_seen > soglia` (es. 45–60s, da definire in PWA)
- Kill switch locale `VISION_REMOTE_ENABLED=false` → Agent non invia heartbeat (`DISABLED`)

---

## Capitolo 11 — Module Interface

### 11.1 Contratto astratto (normativo)

Ogni modulo **deve** esporre (nominalmente) questa interfaccia.  
I nomi possono adattarsi allo stack Python, ma il **contratto semantico** è vincolante.

```
VisionModule
├── initialize(context)      # DI: core, config, logger — no side effect di rete
├── start()                  # porta status ONLINE / IN_DEVELOPMENT
├── stop()                   # OFFLINE / DISABLED
├── health() -> HealthReport
├── supported_commands() -> list[str]
├── execute_command(cmd) -> Result   # opzionale se Dispatcher chiama metodi tipizzati
├── publish_event(...)       # SOLO tramite Core.EventBus (mai bus diretto esterno)
├── create_job(...)          # SOLO tramite Core.JobManager
└── get_status() -> ModuleStatusSnapshot
```

### 11.2 Contesto di inizializzazione (`context`)

| Campo | Descrizione |
|-------|-------------|
| `core` | Riferimento VisionCore (API pubblica) |
| `module_config` | Config dedicata (`config/<module_id>/`) |
| `logger` | Logger di modulo |
| `device_id` | Device locale |

### 11.3 Cosa un modulo NON può fare

- Importare/chiamare un altro modulo
- Aprire connessioni a Supabase
- Esporre endpoint HTTP
- Eseguire comandi fuori whitelist
- Loggare secret

### 11.4 HealthReport (minimo)

```json
{
  "module_id": "enispace",
  "status": "ONLINE",
  "ok": true,
  "message": "ready",
  "checked_at": "2026-08-08T10:15:00+02:00"
}
```

---

## Capitolo 12 — Command Dispatcher

### 12.1 Flusso end-to-end

```
PWA
 │  crea Command PENDING (autorizzato + ruolo)
 ▼
Backend (Supabase)
 │  persistenza + (opz.) Realtime
 ▼
Remote Agent
 │  fetch (poll e/o realtime) + validate + idempotency
 │  ACKNOWLEDGED → EXECUTING
 ▼
Command Dispatcher
 │  mappa command_type → handler
 ▼
VisionCore
 │  coordina / crea job / pubblica eventi
 ▼
Modulo target
 │  esegue dominio
 ▼
EventBus (Core)
 │  eventi normalizzati
 ▼
Remote Agent (EventSync)
 │  publish_event / sync_job / create_notification request
 ▼
Backend
 │
 ▼
PWA (UI aggiornata)
```

### 12.2 Responsabilità Dispatcher

- Conoscere la whitelist
- Non contenere logica di dominio
- Restituire `result` strutturato
- Propagare errori come `FAILED` senza crashare l’Agent
- Per stub: `NOT_IMPLEMENTED` senza side effect

### 12.3 Kill switch

```
VISION_REMOTE_ENABLED=false
        │
        ▼
Nessun fetch / nessuna esecuzione remota
UI locale: REMOTE ○ DISABLED
```

Disattivabile **dal PC** senza dipendere dal cloud.

---

## Capitolo 13 — Event Bus

### 13.1 Comportamento

1. **Il Core genera (o media) gli eventi.** I moduli pubblicano **attraverso** il Core/EventBus, non verso il backend.
2. **Mai il contrario:** la PWA non “scrive eventi operativi” nel Core; crea *comandi*.
3. **I moduli non comunicano tra loro.** Se A deve influenzare B: evento → Core → (eventuale) comando/policy → B.
4. Observer pattern in-process; fan-out a UI locale, Agent sync, NotificationService.
5. Eventi append-only, con `event_id` per deduplica in sync.

### 13.2 Diagramma

```
[Modulo A] --publish--> [EventBus / Core] --subscribe--> [UI Avatar]
                              │
                              ├──> [JobManager / stato]
                              ├──> [NotificationService]
                              └──> [Remote Agent EventSync] --> Backend --> PWA

[Modulo B] ✗──non chiama──✗ [Modulo A]
```

---

## Capitolo 14 — Permessi

### 14.1 Ruoli

| Role | Descrizione |
|------|-------------|
| `ADMIN` | Configurazione sistema, device, retention, override |
| `SUPERVISOR` | Supervisione operativa, pause/resume, retry |
| `OPERATORE` | Comandi operativi quotidiani (check mail, prepare…) |
| `DIREZIONE` | Approvazioni ad alto impatto (PEC, reject strategici) |

### 14.2 Matrice comando → ruolo minimo

| command_type | ADMIN | SUPERVISOR | OPERATORE | DIREZIONE |
|--------------|:-----:|:----------:|:---------:|:---------:|
| `GET_STATUS` | ✓ | ✓ | ✓ | ✓ |
| `CHECK_ENISPACE_MAIL` | ✓ | ✓ | ✓ | —* |
| `RETRY_JOB` | ✓ | ✓ | — | — |
| `PAUSE_MODULE` | ✓ | ✓ | — | — |
| `RESUME_MODULE` | ✓ | ✓ | — | — |
| `PREPARE_COIN_TRANSPORT` | ✓ | ✓ | ✓ | — |
| `APPROVE_JOB` | ✓ | ✓** | — | ✓ |
| `REJECT_JOB` | ✓ | ✓** | — | ✓ |

\* DIREZIONE può avere read-only status; esecuzione operativa non necessaria.  
\*\* SUPERVISOR può approvare solo se policy modulo lo consente; PEC ad alto impatto → DIREZIONE.

### 14.3 Enforcement

- **PWA/Backend:** enforcement primario (RLS + claims ruolo)
- **Agent:** defense-in-depth (whitelist + device_id + schema); **non** sostituisce auth utente
- Ogni comando dichiara `min_role` nel catalogo comandi backend

---

## Capitolo 15 — Versioning

### 15.1 Versioni

| Tipo | Campo | Esempio | Significato |
|------|-------|---------|-------------|
| Contract | `contract_version` | `1.0.0` | Questo documento |
| API | `api_version` | `v1` | Shape wire PWA↔Backend↔Agent |
| Agent | `agent_version` | `0.1.0` | Remote Agent |
| Vision | `vision_version` | `2.0-vision` | Core/prodotto |
| Module | `version` | `1.0.0` | Singolo modulo |

### 15.2 Compatibilità

| Cambio | Regola |
|--------|--------|
| Aggiungere campo opzionale | Compatibile (minor) |
| Aggiungere `command_type` / `event_type` | Compatibile se consumer ignora unknown |
| Rinominare/rimuovere campo obbligatorio | Breaking → `v2` |
| Cambiare semantica stati | Breaking → `v2` |
| Nuovo modulo | Non breaking per Core se rispetta interfaccia |

### 15.3 Header / metadata consigliati

```json
{
  "api_version": "v1",
  "contract_version": "1.0.0",
  "producer": "vision-remote-agent",
  "producer_version": "0.1.0"
}
```

Unknown fields: **ignore** (forward compatibility).  
Unknown `command_type` sull’Agent: **REJECTED** (sicurezza > forward-compat sui comandi).

---

## Capitolo 16 — Futuri moduli

### 16.1 Come aggiungere un modulo senza rompere nulla

```
1. Creare cartella modules/<module_id>/
2. Implementare VisionModule (Cap. 11)
3. Dichiarare commands_supported / events_supported
4. Registrare in bootstrap Core (register_module)
5. Aggiungere config/<module_id>/ (secret via keyring/env)
6. (Opz.) regole MailRouter
7. Pubblicare catalogo comandi su Backend/PWA (feature flag)
8. Nessuna modifica agli altri moduli
9. Nessuna modifica al protocollo PWA oltre nuovi command_type (additive)
```

### 16.2 Cosa NON fare

- Hard-code nel Core della logica di dominio
- Chiamate cross-module
- Nuove tabelle Supabase “private” lette dal modulo PC
- Bypass EventBus

### 16.3 Checklist accettazione modulo

- [ ] `module_id` stabile
- [ ] Health / start / stop isolati (errore non blocca altri)
- [ ] Solo comandi whitelist
- [ ] Eventi nel catalogo o estensione documentata
- [ ] Job con ID `VISION-YYYY-NNNNNN`
- [ ] Nessun secret in log
- [ ] Test mock senza side effect esterni

---

## Capitolo 17 — Sequenze

### 17.1 `GET_STATUS` (primo test cloud autorizzato)

```
PWA                Backend              Agent               Core
 │                    │                   │                   │
 │── POST command ───►│                   │                   │
 │   GET_STATUS       │                   │                   │
 │                    │◄── poll/realtime ─│                   │
 │                    │── command PENDING►│                   │
 │                    │                   │─ validate ───────►│
 │                    │◄─ ACKNOWLEDGED ───│                   │
 │                    │◄─ EXECUTING ──────│                   │
 │                    │                   │── get snapshot ──►│
 │                    │                   │◄─ status JSON ────│
 │                    │◄─ COMPLETED+result│                   │
 │◄── realtime/UI ────│                   │                   │
```

### 17.2 `CHECK_ENISPACE_MAIL`

```
PWA → Backend → Agent (validate)
                    │
                    ▼
              Dispatcher
                    │
                    ▼
              VisionCore
                    │
                    ▼
           enispace.check_mail_now()
                    │
                    ▼
         JARVIS run_mail_check_once()   ★ logica esistente, non duplicata
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   MAIL_* events  Jobs      PRINT_* (se workflow reale)
        │
        ▼
  EventSync → Backend → PWA
```

> Cloud operativo solo dopo autorizzazione esplicita. Test automatici: `dry_run=true`.

### 17.3 `PREPARE_COIN_TRANSPORT`

```
PWA → Backend → Agent → Dispatcher → Core → coin_transport
                                              │
                                              ▼
                                    workflow prepara documento/PEC
                                              │
                                              ▼
                                    Job WAITING_APPROVAL
                                    Approval PENDING
                                    Event WAITING_APPROVAL / PEC_PREPARED
                                              │
                                              ▼
                                    PWA mostra [APRI][MODIFICA][APPROVA E INVIA]
```

In v1 foundation: può terminare con `NOT_IMPLEMENTED` se workflow non abilitato.

### 17.4 `APPROVE_JOB`

```
PWA (DIREZIONE) → Backend Command APPROVE_JOB
        → Agent validate
        → Dispatcher
        → se policy assente: COMPLETED + code=NOT_IMPLEMENTED
        → se policy attiva (futuro): Core → modulo → azione autorizzata
        → events + audit
```

**Mai** invio PEC implicito senza Approval esplicita.

---

## Capitolo 18 — Best practices

| Pattern | Applicazione in VIS•ION |
|---------|-------------------------|
| **Single Responsibility** | Agent=trasporto, Core=orchestrazione, Modulo=dominio |
| **Dependency Injection** | Context al `initialize()` del modulo |
| **Adapter** | RemoteBackend (mock \| supabase) |
| **Command** | RemoteCommand + Dispatcher |
| **Observer / EventBus** | VisionEvent bus locale |
| **Plugin Architecture** | ModuleManager + register |
| **Kill switch** | Controllo locale indipendente dal cloud |
| **Idempotency** | Store comandi già gestiti |
| **Defense in depth** | RLS backend + whitelist agent |
| **Least privilege** | Secret per modulo; no credential sharing indiscriminato |
| **Fail isolation** | Errore modulo A ≠ blocco modulo B |
| **Offline-first locale** | Core/eniSpace funzionano senza Internet |

---

## Capitolo 19 — Regole non negoziabili

1. **Un modulo non chiama direttamente un altro modulo.**
2. **Il Core coordina tutto** (job, eventi, registrazione moduli).
3. **Ogni comunicazione inter-componente passa da comandi o eventi.**
4. **Nessun modulo conosce Supabase.**
5. **Nessun modulo conosce la PWA.**
6. **Solo il Remote Agent comunica col backend** (outbound only).
7. **Nessuna remote shell / eval / SQL arbitrario / path arbitrari.**
8. **Nessun secret in log, codice, commit, eventi sync.**
9. **Idempotenza comandi obbligatoria** (anche dopo restart).
10. **Kill switch locale** può spegnere il remoto senza cloud.
11. **Legacy `VIS eniSpace Utility` non si tocca** finché non autorizzato.
12. **Approvazioni umane** per azioni irreversibili (PEC): default no auto-send.
13. **OFFLINE device** lo decide il backend da `last_seen`, non l’agent in perdita rete.
14. **Breaking changes** richiedono nuova major (`v2`) del contract.

---

## Capitolo 20 — Output e governance

### 20.1 Questo documento è

- La **Costituzione tecnica** di VIS•ION
- Il contratto wire tra Core ↔ Agent ↔ PWA ↔ Backend ↔ Moduli
- La checklist di accettazione per ogni nuovo pezzo

### 20.2 Cosa non è

- Schema SQL definitivo Supabase (da fornire dalla PWA / DBA)
- Implementazione runtime
- Licenza a bypassare whitelist o kill switch

### 20.3 Processo di evoluzione

```
Proposta modifica contract
        │
        ▼
Review (architettura + sicurezza)
        │
        ▼
Bump version (SemVer)
        │
        ▼
Aggiornamento Agent / PWA / Backend in ordine compatibile
        │
        ▼
Feature flag / rollout
```

### 20.4 Artefatti correlati (implementazione attuale, non normativi SQL)

| Artefatto | Ruolo |
|-----------|--------|
| `app/core/*` | VisionCore, EventBus, JobManager, ModuleManager |
| `app/remote/*` | Remote Agent foundation |
| `app/modules/*` | Plugin eniSpace / coin_transport |
| `.env.example` | Kill switch e config remote |
| `docs/VISION_API_CONTRACT_v1.md` | Questo contratto |

### 20.5 Dipendenze ancora necessarie dalla PWA/Supabase

Prima del collegamento cloud reale:

1. `SUPABASE_URL`
2. Schema SQL reale + nomi colonne
3. RLS / policy agent
4. Metodo autenticazione Agent
5. Soglia OFFLINE su `last_seen`
6. Mapping tabelle: `devices`, `modules`, `device_modules`, `vision_jobs`, `job_events`, `commands`, `notifications`, `approvals`, `audit_logs`, `user_devices`

---

## Valutazione modularità (piattaforma aziendale)

**Sì — l’architettura è sufficientemente modulare per crescere fino a una piattaforma aziendale completa**, a condizione di rispettare questo contratto.

### Perché sì

| Criterio | Copertura |
|----------|-----------|
| Separazione UI cloud / PC | PWA ↔ Backend ↔ Agent outbound |
| Plugin moduli | ModuleManager + interfaccia standard |
| Estensione senza big-bang | Nuovi `command_type` / `event_type` additivi |
| Isolamento guasti | Moduli indipendenti; Agent failure ≠ stop eniSpace |
| Osservabilità unica | Job + Event + Notification |
| Governance | Ruoli, approval, audit, versioning |
| Sicurezza operativa | Whitelist, idempotenza, kill switch, no inbound |

### Rischi da governare (non bloccanti se monitorati)

1. **Disciplina del contratto:** bypass “temporanei” tra moduli distruggono la modularità.
2. **Schema cloud:** senza contratto SQL/RLS chiaro l’Agent resta stub (corretto).
3. **Catalogo comandi:** crescita incontrollata senza review sicurezza.
4. **Progress/eventi:** mapping inconsistente → UX PWA confusa (mitigare con Cap. 6–7).
5. **Segreti e PII:** tentazione di sync eccessivo verso cloud (vietato dal Cap. 19).

### Verdetto

Con Core come unico orchestratore, Agent come unico adapter cloud, moduli a plugin e questo contract v1 come legge, VIS•ION può scalare a Protocollo, HR, EasyPlan, Valori, Gare, Contestazioni **senza riscrivere il nucleo**.

Il prossimo passo naturale non è nuovo codice operativo, ma: **allineare lo schema Supabase/PWA a questo contratto**, poi abilitare il primo comando cloud `GET_STATUS`.

---

*Fine — VIS•ION API Contract v1.0.0*  
*Documento generato come baseline ufficiale. Nessuna modifica a codice operativo o progetto legacy in questa consegna.*
