# Lovable prompt — Agent ↔ PWA thin channel (wake / status / messages)

Copia questo prompt in Lovable **solo** se il push su `main` non è disponibile o se Lovable propone di sovrascrivere la chat.

## Obiettivo
PWA e Agent desktop comunicano **solo via Supabase** (niente merge repo).
Device: `VIS-TARANTO-01`.

**Home dopo login = chat mobile-first con VISION Supervisor** (non dashboard ops).

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

## UI chat (canonical su `/chat`)

1. Dopo login → redirect a `/chat` (non dashboard).
2. Una composizione: avatar Supervisor + chip **Agent** / **Supervisor** + feed messaggi full-width + sticky **Sveglia** / **Disattiva** + composer.
3. Feed da `agent_messages` via `useAgentMessages` (`src/lib/vision-data.ts`):
   - select `*` order `created_at` desc, poll 5s + realtime INSERT
   - normalizza sia schema thin (`message`/`source`/`metadata`) sia chat Lovable (`body`/`direction`/`title`)
4. Progress Agent («Risveglio eseguito», «Inizio analisi», «Attivazione modulo eniSpace», …) appaiono come bolle VISION nel feed.
5. **Sveglia** → `enqueueSupervisorCommand(deviceId, "WAKE_SUPERVISOR")`
6. **Disattiva** → stesso helper con `DEACTIVATE_SUPERVISOR` + conferma keyword `DISATTIVA`
7. Design: navy / silver / electric cyan; layout mobile-first, thumb zone in basso.
8. Non mettere `VISION_AGENT_TOKEN` nella PWA. Non abilitare comandi job (mail/retry/approve).

## Helper

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

## Pagina dispositivo (`dispositivi/$code`)
Mantiene Sveglia / Disattiva / Messaggi Agent / GET_STATUS (ops dettaglio). La home resta la chat.

## Verifica
Agent con `VISION_REMOTE_ENABLED=true` → PWA login → chat → device ONLINE → Sveglia → righe progress in feed.
