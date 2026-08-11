/**
 * GET_STATUS read-only — contratto VISION_REMOTE_PWA_CONTRACT.md
 * RPC: create_get_status_command(p_device_id text)
 * Nessun VISION_AGENT_TOKEN / service_role nel frontend.
 */

import { supabase } from "@/integrations/supabase/client";

export const DEFAULT_DEVICE_ID = import.meta.env["VITE_DEVICE_ID"] || "VIS-TARANTO-01";

export const GET_STATUS_TIMEOUT_MS = Number(
  import.meta.env["VITE_GET_STATUS_TIMEOUT_MS"] || 30_000,
);
export const GET_STATUS_POLL_MS = Number(import.meta.env["VITE_POLL_INTERVAL_MS"] || 4_000);
export const OFFLINE_THRESHOLD_SECONDS = Number(
  import.meta.env["VITE_OFFLINE_THRESHOLD_SECONDS"] || 60,
);

export const AGENT_TIMEOUT_MESSAGE = "VIS•ION Agent non ha risposto";
export const REMOTE_NOT_ENABLED = "NON ANCORA ABILITATO";

/** Comandi remoti thin channel */
export const REMOTE_COMMAND_ENABLED: Record<string, boolean> = {
  GET_STATUS: true,
  WAKE_SUPERVISOR: true,
  DEACTIVATE_SUPERVISOR: true,
  CHECK_ENISPACE_MAIL: false,
  RETRY_JOB: false,
  PAUSE_MODULE: false,
  RESUME_MODULE: false,
  PREPARE_COIN_TRANSPORT: false,
  APPROVE_JOB: false,
  REJECT_JOB: false,
};

export type GetStatusResult = {
  ok?: boolean;
  api_version?: string;
  contract_version?: string;
  device_id?: string;
  device_name?: string;
  agent_version?: string;
  vision_version?: string;
  platform_version?: string;
  timestamp?: string;
  core_status?: string;
  supervisor_status?: string;
  overall_health?: string;
  current_job?: Record<string, unknown> | null;
  queue_size?: number;
  modules?: Array<{
    module_id: string;
    display_name?: string;
    version?: string;
    status?: string;
    health?: string;
    enabled?: boolean;
    current_job?: string | null;
  }>;
  skills?: Array<{
    skill_id: string;
    name?: string;
    enabled?: boolean;
    module_id?: string;
    health?: string;
  }>;
  services?: Array<{
    service_id: string;
    available?: boolean;
    health?: string;
  }>;
  warnings?: Array<{
    code: string;
    severity?: string;
    component?: string;
    message?: string;
  }>;
  remote_control_enabled?: boolean;
  agent?: {
    status?: string;
    connected_backend?: string;
    remote_mode?: string;
    last_heartbeat?: string;
    last_error?: string;
  };
  partial?: boolean;
  missing_sections?: string[];
  vision_core?: {
    online?: boolean;
    product?: string;
    product_name?: string;
    assistant?: string;
    assistant_state?: string;
    started_at?: string;
    error?: string;
  };
  /** Phase 3D/3E — EniSpace runtime (additive, nullable fields) */
  enispace_runtime?: {
    status?: string;
    available?: boolean;
    active?: boolean | null;
    pending_jobs?: number | null;
    current_job?: Record<string, unknown> | null;
    last_job?: Record<string, unknown> | null;
    last_mail_check?: string | null;
    last_error?: string | null;
    detail_state?: string | null;
  };
};

export type CommandStatus =
  "PENDING" | "ACKNOWLEDGED" | "EXECUTING" | "COMPLETED" | "FAILED" | "REJECTED" | string;

export type CommandRow = {
  /** Canonical Agent field: commands.command_id */
  id: string;
  command_id?: string;
  command_type: string;
  status: CommandStatus;
  result: GetStatusResult | null;
  error: string | null;
  requested_at: string;
  expires_at?: string | null;
  acknowledged_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  executed_at?: string | null;
  target_device_id?: string | null;
};

export function isCloudConfigured(): boolean {
  const url = import.meta.env["VITE_SUPABASE_URL"];
  const key =
    import.meta.env["VITE_SUPABASE_ANON_KEY"] || import.meta.env["VITE_SUPABASE_PUBLISHABLE_KEY"];
  return Boolean(url && key);
}

export function dataMode(): "CLOUD" | "DEMO" {
  return isCloudConfigured() ? "CLOUD" : "DEMO";
}

/** Canonical Agent row uses command_id; accept legacy id only as fallback. */
export function normalizeCommandRow(raw: Record<string, unknown> | null): CommandRow | null {
  if (!raw) return null;
  const commandId = String(raw["command_id"] ?? raw["id"] ?? "");
  if (!commandId) return null;
  return {
    id: commandId,
    command_id: commandId,
    command_type: String(raw["command_type"] ?? ""),
    status: String(raw["status"] ?? "PENDING"),
    result:
      raw["result"] && typeof raw["result"] === "object"
        ? (raw["result"] as GetStatusResult)
        : null,
    error: (raw["error"] as string | null) ?? null,
    requested_at: String(raw["requested_at"] ?? raw["created_at"] ?? ""),
    expires_at: (raw["expires_at"] as string | null) ?? null,
    acknowledged_at: (raw["acknowledged_at"] as string | null) ?? null,
    started_at: (raw["started_at"] as string | null) ?? null,
    finished_at: (raw["finished_at"] as string | null) ?? null,
    executed_at: (raw["executed_at"] as string | null) ?? null,
    target_device_id: raw["target_device_id"] != null ? String(raw["target_device_id"]) : null,
  };
}

export async function createGetStatusCommand(
  deviceId: string = DEFAULT_DEVICE_ID,
): Promise<CommandRow> {
  const { data, error } = await supabase.rpc(
    "create_get_status_command" as never,
    {
      p_device_id: deviceId,
    } as never,
  );
  if (error) throw error;
  const row = normalizeCommandRow(data as Record<string, unknown>);
  if (!row) throw new Error("create_get_status_command: empty response");
  return row;
}

export type ThinSupervisorCommand =
  | "WAKE_SUPERVISOR"
  | "DEACTIVATE_SUPERVISOR"
  | "GET_STATUS";

/** Enqueue thin lifecycle command (PWA → Agent via Supabase). */
export async function enqueueSupervisorCommand(
  deviceId: string,
  commandType: ThinSupervisorCommand,
): Promise<string> {
  const { data, error } = await supabase.rpc("enqueue_supervisor_command" as never, {
    p_device_id: deviceId,
    p_command_type: commandType,
  } as never);
  if (error) throw error;
  return String(data ?? "");
}

export async function fetchCommand(commandId: string): Promise<CommandRow | null> {
  // Agent contract PK: command_id
  const byCanonical = await supabase
    .from("commands")
    .select("*")
    .eq("command_id" as never, commandId)
    .maybeSingle();
  if (!byCanonical.error && byCanonical.data) {
    return normalizeCommandRow(byCanonical.data as Record<string, unknown>);
  }
  // Legacy Lovable fallback during cutover (id)
  const byLegacy = await supabase.from("commands").select("*").eq("id", commandId).maybeSingle();
  if (byLegacy.error) throw byLegacy.error;
  return normalizeCommandRow(byLegacy.data as Record<string, unknown> | null);
}

export type WaitOutcome =
  | { ok: true; command: CommandRow; result: GetStatusResult | null }
  | {
      ok: false;
      reason: "timeout" | "error";
      message: string;
      command?: CommandRow;
    };

/**
 * Attende COMPLETED/FAILED/REJECTED via Realtime + poll 4s.
 * Timeout 30s → messaggio Agent senza impostare FAILED lato client.
 */
export function waitForGetStatusResult(
  commandId: string,
  opts?: {
    timeoutMs?: number;
    pollMs?: number;
    /** test injection */
    fetchFn?: (id: string) => Promise<CommandRow | null>;
    now?: () => number;
    setTimeoutFn?: typeof setTimeout;
    clearTimeoutFn?: typeof clearTimeout;
    setIntervalFn?: typeof setInterval;
    clearIntervalFn?: typeof clearInterval;
    subscribe?: (commandId: string, onRow: (row: CommandRow) => void) => () => void;
  },
): Promise<WaitOutcome> {
  const timeoutMs = opts?.timeoutMs ?? GET_STATUS_TIMEOUT_MS;
  const pollMs = opts?.pollMs ?? GET_STATUS_POLL_MS;
  const fetchFn = opts?.fetchFn ?? fetchCommand;
  const setTimeoutFn = opts?.setTimeoutFn ?? setTimeout;
  const clearTimeoutFn = opts?.clearTimeoutFn ?? clearTimeout;
  const setIntervalFn = opts?.setIntervalFn ?? setInterval;
  const clearIntervalFn = opts?.clearIntervalFn ?? clearInterval;

  return new Promise((resolve) => {
    let settled = false;
    let unsub: (() => void) | null = null;
    let channel: { topic?: string } | null = null;
    const timers: {
      poll?: ReturnType<typeof setInterval>;
      timeout?: ReturnType<typeof setTimeout>;
    } = {};

    const finish = (value: WaitOutcome) => {
      if (settled) return;
      settled = true;
      if (timers.poll) clearIntervalFn(timers.poll);
      if (timers.timeout) clearTimeoutFn(timers.timeout);
      if (unsub) unsub();
      if (channel) void supabase.removeChannel(channel as never);
      resolve(value);
    };

    const inspect = (row: CommandRow | null) => {
      if (!row) return;
      const st = row.status;
      if (st === "COMPLETED") {
        finish({ ok: true, command: row, result: row.result });
      } else if (st === "FAILED" || st === "REJECTED") {
        finish({
          ok: false,
          reason: "error",
          message: row.error || st,
          command: row,
        });
      }
    };

    if (opts?.subscribe) {
      unsub = opts.subscribe(commandId, (row) => inspect(row));
    } else {
      channel = supabase
        .channel(`get-status-${commandId}`)
        .on(
          "postgres_changes",
          {
            event: "UPDATE",
            schema: "public",
            table: "commands",
            filter: `command_id=eq.${commandId}`,
          },
          (payload) => inspect(normalizeCommandRow(payload.new as Record<string, unknown>)),
        )
        .subscribe();
    }

    timers.poll = setIntervalFn(() => {
      void fetchFn(commandId)
        .then(inspect)
        .catch(() => undefined);
    }, pollMs);

    timers.timeout = setTimeoutFn(() => {
      finish({
        ok: false,
        reason: "timeout",
        message: AGENT_TIMEOUT_MESSAGE,
      });
    }, timeoutMs);

    void fetchFn(commandId)
      .then(inspect)
      .catch(() => undefined);
  });
}

export function uniqueWarnings(
  warnings: GetStatusResult["warnings"] | undefined,
): NonNullable<GetStatusResult["warnings"]> {
  if (!warnings?.length) return [];
  const seen = new Set<string>();
  const out: NonNullable<GetStatusResult["warnings"]> = [];
  for (const w of warnings) {
    const key = w.code || w.message || "";
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(w);
  }
  return out;
}

export function moduleFromResult(result: GetStatusResult | null | undefined, moduleId: string) {
  return result?.modules?.find(
    (m) => m.module_id === moduleId || m.module_id === moduleId.replace("_", ""),
  );
}

export function serviceFromResult(result: GetStatusResult | null | undefined, serviceId: string) {
  return result?.services?.find((s) => s.service_id === serviceId);
}

/** Agent queue size — never invent from demo job tables. */
export function agentQueueSizeDisplay(
  result: GetStatusResult | null | undefined,
): number | "—" {
  if (result?.queue_size != null && Number.isFinite(Number(result.queue_size))) {
    return Number(result.queue_size);
  }
  return "—";
}

/**
 * Live module status for Agent observability.
 * Seed/localStorage module rows must not be painted as Agent status.
 */
export function moduleLiveStatus(
  remote: { status?: string; health?: string } | null | undefined,
  _seedStatus?: string,
): string {
  return remote?.status ?? remote?.health ?? "—";
}

export function isAgentOffline(
  lastSeenAt: string | null | undefined,
  thresholdSeconds: number = OFFLINE_THRESHOLD_SECONDS,
  nowMs: number = Date.now(),
): boolean {
  if (!lastSeenAt) return true;
  return nowMs - new Date(lastSeenAt).getTime() > thresholdSeconds * 1000;
}

export function derivedAgentStatus(
  device: {
    status?: string;
    last_seen_at?: string | null;
    heartbeat_threshold_seconds?: number | null;
  } | null,
  result?: GetStatusResult | null,
  nowMs: number = Date.now(),
): string {
  if (device?.status === "DISABLED") return "DISABLED";
  const threshold = device?.heartbeat_threshold_seconds ?? OFFLINE_THRESHOLD_SECONDS;
  if (isAgentOffline(device?.last_seen_at, threshold, nowMs)) {
    return "OFFLINE";
  }
  return device?.status || result?.agent?.status || "ONLINE";
}

export function isRemoteCommandEnabled(commandType: string): boolean {
  return REMOTE_COMMAND_ENABLED[commandType] === true;
}

/** Ultimo GET_STATUS per device (lista già ordinata per requested_at desc). */
export function pickLatestGetStatusCommand<
  T extends { target_device_id?: string | null; command_type?: string },
>(commands: T[], deviceId: string): T | null {
  return (
    commands.find((c) => c.target_device_id === deviceId && c.command_type === "GET_STATUS") ?? null
  );
}
