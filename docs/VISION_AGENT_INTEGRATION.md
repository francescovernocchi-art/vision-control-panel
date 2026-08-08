# VIS•ION — Integrazione VIS•ION Agent (Python)

La PWA è **solo un terminale remoto**. Tutta l'automazione (eniSpace, stampa, PEC,
browser automation) resta sul PC aziendale, eseguita dall'Agent Python.
La PWA e l'Agent comunicano **esclusivamente** tramite il database Lovable Cloud
(PostgreSQL + Realtime), mai con connessioni dirette al PC.

## Connessione

L'Agent usa la libreria `supabase-py` con:

- `SUPABASE_URL` — URL del progetto (fornito nelle impostazioni del progetto)
- `SUPABASE_SERVICE_ROLE_KEY` — **solo lato PC**, mai nella PWA

```python
from supabase import create_client
sb = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
```

## Cicli di lavoro dell'Agent

### 1. Heartbeat (ogni 30–60 s)

```sql
UPDATE devices
SET last_seen_at = now(), status = 'ONLINE',
    agent_version = '1.0', current_job_id = :job_id, metadata = :metadata
WHERE code = 'VIS-TARANTO-01';
```

La UI considera OFFLINE un device che non aggiorna `last_seen_at` entro
`heartbeat_threshold_seconds` (default 120).

### 2. Lettura comandi PENDING

```sql
SELECT * FROM commands
WHERE status = 'PENDING' AND target_device_id = :device_id
ORDER BY requested_at;
```

Ciclo di stato: `PENDING → ACKNOWLEDGED → EXECUTING → COMPLETED | FAILED | REJECTED`.

```sql
UPDATE commands
SET status = 'COMPLETED', executed_at = now(), result = :json, error = NULL
WHERE id = :command_id;
```

Comandi in whitelist (nessun codice arbitrario):
`GET_STATUS`, `CHECK_ENISPACE_MAIL`, `RETRY_JOB`, `PAUSE_MODULE`,
`RESUME_MODULE`, `PREPARE_COIN_TRANSPORT`, `APPROVE_JOB`, `REJECT_JOB`.

### 3. Creazione e aggiornamento lavorazioni

```sql
INSERT INTO vision_jobs (code, module_id, title, source, status, progress,
                         current_step, started_at, device_id, metadata)
VALUES ('VISION-2026-000130', :module_id, 'Ordine eniSpace 45001...', 'MAIL',
        'PROCESSING', 10, 'ANALYSIS', now(), :device_id, '{}'::jsonb);
```

Stati job: `PENDING, QUEUED, PROCESSING, WAITING_APPROVAL, COMPLETED, PARTIAL,
NEEDS_ATTENTION, FAILED, CANCELLED`.

### 4. Eventi

```sql
INSERT INTO job_events (job_id, event_type, message, metadata)
VALUES (:job_id, 'DOWNLOAD', 'Scaricati 3 documenti', '{}'::jsonb);
```

### 5. Stato modulo

```sql
UPDATE modules
SET status = 'ONLINE', last_activity_at = now(),
    current_job_id = :job_id, error_message = NULL
WHERE key = 'enispace';
```

### 6. Notifiche

```sql
INSERT INTO notifications (notification_type, title, message, module_id, job_id)
VALUES ('JOB_FAILED', 'Lavorazione fallita', 'Login eniSpace non riuscito.',
        :module_id, :job_id);
```

Tipi: `JOB_COMPLETED, JOB_FAILED, NEEDS_ATTENTION, WAITING_APPROVAL,
MODULE_OFFLINE, DEVICE_OFFLINE`.

### 7. Approvazioni (Trasporto Monete)

Quando la PEC è pronta, l'Agent porta il job in `WAITING_APPROVAL` e crea:

```sql
INSERT INTO approvals (job_id, module_id, title, description, status, metadata)
VALUES (:job_id, :module_id, 'PEC pronta — Trasporto Monete',
        'Province: TA / BR / LE', 'PENDING',
        '{"province":["TA","BR","LE"],"mezzi":3}'::jsonb);
```

L'Agent attende poi un comando `APPROVE_JOB` / `REJECT_JOB`.
**L'invio PEC non è implementato**: il flusso si ferma a
`PEC PRONTA PER APPROVAZIONE`.

## Realtime (opzionale ma consigliato)

L'Agent può sottoscrivere `commands` invece di fare polling:

```python
sb.channel("agent").on_postgres_changes(
    event="INSERT", schema="public", table="commands",
    callback=handle_command).subscribe()
```

## Regole di sicurezza

- Nessuna credenziale eniSpace / PEC / browser è salvata nel cloud o nella PWA.
- La PWA non espone endpoint verso il PC: nessun IP pubblico, nessuna porta aperta.
- L'Agent è l'unico componente che esegue automazioni.
- La service role key resta sul PC aziendale, in un file di configurazione locale
  non versionato.

## Configurazioni mancanti / da completare

1. **Ruoli reali**: i nuovi account ricevono `OPERATORE`. Gli `ADMIN` vanno
   assegnati inserendo una riga in `user_roles`.
2. **Notifiche push**: servono chiavi VAPID, un service worker di messaggistica e
   un servizio d'invio; la tabella `user_devices` è già pronta.
3. **2FA/MFA**: prevista in fase successiva.
4. **Dati demo**: le righe con `is_demo = true` vanno eliminate quando l'Agent
   inizia a scrivere dati reali.
