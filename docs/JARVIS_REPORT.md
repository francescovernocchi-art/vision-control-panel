# JARVIS — Report analisi (FASE 2)

## File coinvolti

| Area | File |
|------|------|
| UI | `ui/main_window.py`, `ui/settings_window.py` |
| Mail | `services/imap_mail_service.py`, `services/email_parser.py` |
| Batch | `services/batch_service.py` |
| Portale | `services/enispace_service.py`, `services/browser_service.py` |
| Download | `services/download_service.py` |
| Stampa | `services/print_queue_service.py` |
| Persistenza | `database/db.py`, `database/models.py` |
| Credenziali | `services/credential_service.py` (keyring) |
| Worker UI | `services/worker.py`, pattern `_post_ui` / `_pump_ui` |

## Architettura attuale

1. **SYNC / Autosync / RIELABORA OGGI** → `BackgroundWorker` → `BatchService.process_imap_folder`
2. IMAP legge cartella MdA → `email_parser` estrae ordine / MdA / contratto
3. Anti-dup: `imap_processed` (solo success) + registro `mail_register`
4. eniSpace: login/sessione → ricerca ordine → download PDF MdA
5. PDF in **coda stampa** (senza stampa automatica); bottone **STAMPA CODA** invia a stampante OS
6. Tra una mail e l’altra: `return_to_dashboard_filters()`; browser hide; UI non bloccante

## Parti riutilizzabili (nessuna duplicazione logica)

- `ImapMailService` + `parse_notification_text` / `AcquisitionNotification`
- `BatchService._process_notice` (ricerca + download + return-to-filters)
- `PrintQueueService.print_file` / coda esistente
- `Database` settings + keyring casella / eniSpace
- Pattern `_post_ui` + `BackgroundWorker` per non congelare la GUI

## Modifiche previste

- Pacchetto `services/jarvis/`: Supervisor, MailWatcher, JobQueue, JobRepository, JobProcessor, Logger, NotificationService (stub)
- Tabelle SQLite `jarvis_jobs`, `jarvis_job_events` + settings JARVIS
- Tab UI **JARVIS** (stato, ON/OFF, console, storico) + sezione Impostazioni
- Modalità **simulazione** (analisi senza download finale / stampa)
- Auto-stampa **solo** per job Jarvis (non simulazione); sync manuale resta coda-only
- Recovery crash: job `PROCESSING` → `NEEDS_ATTENTION` (no ristampa automatica)

## Criticità / rischi

1. **Stampe duplicate** — rischio principale; mitigazione: mail_id persistente, recovery PROCESSING → intervento, mai ristampa automatica su dubbio
2. **Concorrenza** con SYNC manuale / autosync sul browser Playwright — un solo job Jarvis alla volta + blocco se app già busy
3. OS non conferma stampa fisica → messaggio «INVIATO CORRETTAMENTE ALLA CODA DI STAMPA»
4. Non cancellare mail né azioni distruttive su eniSpace
