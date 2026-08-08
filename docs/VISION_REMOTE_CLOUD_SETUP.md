# VIS•ION Remote Cloud — setup Agent (READ-ONLY / GET_STATUS)

Nota tecnica operativa (non modifica i contract ufficiali).  
PWA reale: progetto **Lovable separato** — vedi `docs/VISION_REMOTE_PWA_CONTRACT.md`.  
Questo repo Python **non** contiene frontend PWA.

## Auth Agent

**Metodo:** token dedicato per device (`VISION_AGENT_TOKEN`).

1. Genera token casuale lungo (≥16 char; consigliato 32+ byte hex).
2. Salva **solo in chiaro** in env Agent: `VISION_AGENT_TOKEN`.
3. In Supabase salva **solo SHA-256 hex** in `agent_api_tokens.token_hash`.
4. Agent chiama RPC con `p_agent_token` (plaintext).
5. Client Python: `SUPABASE_URL` + `SUPABASE_ANON_KEY` + `VISION_AGENT_TOKEN`.
6. **No** `service_role`. **No** credenziali utente umano.

`VISION_AGENT_TOKEN` **non** è una chiave nativa Supabase.  
Alias legacy ancora accettato: `SUPABASE_AGENT_KEY`.

## Migration

```text
supabase/migrations/20260808_vision_remote_readonly.sql
```

**Non applicare in produzione senza autorizzazione.**

Token SQL:

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

Helper:

```bash
python scripts/hash_agent_token.py YOUR_RAW_TOKEN
```

## Env Agent

```env
VISION_REMOTE_ENABLED=true
VISION_REMOTE_MODE=supabase
VISION_REMOTE_EXECUTION_POLICY=status_only
VISION_DEVICE_ID=VIS-TARANTO-01
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=eyJ...
VISION_AGENT_TOKEN=YOUR_RAW_TOKEN
```

## Policy

- SQL: solo GET_STATUS in INSERT  
- Python: `status_only` → altri comandi `REMOTE_OPERATION_NOT_ENABLED`
