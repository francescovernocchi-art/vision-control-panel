# Lovable prompt — Agent ↔ PWA thin channel (wake / status / messages)

Copia questo prompt in Lovable se il push su `main` non è disponibile.

## Obiettivo
PWA e Agent desktop comunicano **solo via Supabase** (niente merge repo).
Device: `VIS-TARANTO-01`.

## Già su Supabase
RPCs: `agent_heartbeat`, `agent_fetch_pending_commands`, `agent_update_command`,
`agent_publish_message`, `enqueue_supervisor_command`
(+ `create_get_status_command` se presente).
Tabelle: `devices.device_id`, `agent_messages`, `heartbeats`, `agent_api_tokens`.

Se `agent_publish_message` usa ancora `p_agent_token`, applica:

```sql
-- file: supabase/migrations/20260811b_agent_publish_message_p_token.sql
-- (contenuto nel repo Agent vision-main)
```

## Modifiche UI / client (incolla)

1. **Tipi comandi** — abilita `WAKE_SUPERVISOR` e `DEACTIVATE_SUPERVISOR` in `COMMAND_WHITELIST` / `REMOTE_COMMAND_ENABLED` (`remoteEnabled: true`).

2. **Helper** in `src/lib/vision-remote-status.ts`:

```ts
export async function enqueueSupervisorCommand(
  deviceId: string,
  commandType: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR" | "GET_STATUS",
): Promise<string> {
  const { data, error } = await supabase.rpc("enqueue_supervisor_command", {
    p_device_id: deviceId,
    p_command_type: commandType,
  });
  if (error) throw error;
  return String(data ?? "");
}
```

3. **Hook messaggi** — `useAgentMessages(deviceId)` su tabella `agent_messages`:
   - select `*` order `created_at desc` limit 40
   - poll 5s + realtime INSERT su `agent_messages`

4. **Pagina dispositivo** (`dispositivi/$code`):
   - Bottoni **Sveglia** → `enqueueSupervisorCommand(code, "WAKE_SUPERVISOR")`
   - **Disattiva** → `enqueueSupervisorCommand(code, "DEACTIVATE_SUPERVISOR")` con conferma keyword `DISATTIVA`
   - Sezione **Messaggi Agent** che lista `useAgentMessages`
   - Mantieni **Aggiorna stato** via `create_get_status_command`

5. **normalizeDeviceRow**: conserva `id` uuid Lovable; `code` / `device_id` restano il codice logico (`VIS-TARANTO-01`).

6. Non abilitare comandi job (mail/retry/approve) — restano `NON ANCORA ABILITATO`.

## Verifica
Agent con `VISION_REMOTE_ENABLED=true` → PWA vede device ONLINE → Sveglia → messaggio «Supervisor attivato» in feed.
