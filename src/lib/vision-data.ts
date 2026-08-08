import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { supabase } from "@/integrations/supabase/client";
import type { AppRole, CommandType } from "@/lib/vision";

/** Generic table reader. RLS decides what the signed-in user can see. */
function useTable<T = Record<string, unknown>>(
  key: string,
  table: string,
  build?: (q: any) => any,
) {
  return useQuery<T[]>({
    queryKey: [key],
    queryFn: async () => {
      let q: any = supabase.from(table as any).select("*");
      if (build) q = build(q);
      const { data, error } = await q;
      if (error) throw error;
      return (data ?? []) as T[];
    },
  });
}

/** Normalize Agent (device_id) and legacy Lovable (id/code) device rows. */
export function normalizeDeviceRow(raw: Record<string, unknown>): {
  device_id: string;
  id: string;
  code: string;
  name: string;
  device_name: string;
  location: string | null;
  status: string;
  last_seen_at: string | null;
  agent_version: string | null;
  vision_version: string | null;
  platform_version: string | null;
  heartbeat_threshold_seconds: number | null;
  metadata: Record<string, unknown>;
  is_demo: boolean;
  hostname?: string | null;
} {
  const deviceId = String(raw["device_id"] ?? raw["code"] ?? raw["id"] ?? "");
  const name = String(raw["device_name"] ?? raw["name"] ?? deviceId);
  const metadata = (raw["metadata"] as Record<string, unknown> | undefined) ?? {};
  const metaThreshold = metadata["offline_threshold_seconds"];
  const hb = raw["heartbeat_threshold_seconds"];
  const threshold =
    typeof hb === "number"
      ? hb
      : typeof metaThreshold === "number"
        ? metaThreshold
        : 60;
  return {
    device_id: deviceId,
    id: deviceId,
    code: deviceId,
    name,
    device_name: name,
    location: (raw["location"] as string | null) ?? null,
    status: String(raw["status"] ?? "OFFLINE"),
    last_seen_at: (raw["last_seen_at"] as string | null) ?? null,
    agent_version: (raw["agent_version"] as string | null) ?? null,
    vision_version: (raw["vision_version"] as string | null) ?? null,
    platform_version: (raw["platform_version"] as string | null) ?? null,
    heartbeat_threshold_seconds: threshold,
    metadata,
    is_demo: Boolean(raw["is_demo"]),
    hostname: (raw["hostname"] as string | null) ?? null,
  };
}

export const useDevices = () => {
  const q = useTable<Record<string, unknown>>("devices", "devices", (query) =>
    query.order("last_seen_at", { ascending: false }),
  );
  return {
    ...q,
    data: (q.data ?? []).map((row) => normalizeDeviceRow(row)),
  };
};
export const useModules = () =>
  useTable<any>("modules", "modules", (q) => q.order("name"));
export const useJobs = () =>
  useTable<any>("vision_jobs", "vision_jobs", (q) =>
    q.order("created_at", { ascending: false }).limit(200),
  );
export const useNotifications = () =>
  useTable<any>("notifications", "notifications", (q) =>
    q.order("created_at", { ascending: false }).limit(100),
  );
export const useApprovals = () =>
  useTable<any>("approvals", "approvals", (q) =>
    q.order("requested_at", { ascending: false }),
  );
export const useCommands = () =>
  useTable<any>("commands", "commands", (q) =>
    q.order("requested_at", { ascending: false }).limit(100),
  );
export const useAuditLogs = () =>
  useTable<any>("audit_logs", "audit_logs", (q) =>
    q.order("created_at", { ascending: false }).limit(200),
  );
export const useProfiles = () => useTable<any>("profiles", "profiles");
export const useUserRoles = () => useTable<any>("user_roles", "user_roles");

export function useJob(id: string) {
  return useQuery({
    queryKey: ["vision_job", id],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("vision_jobs")
        .select("*")
        .eq("id", id)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useJobEvents(jobId: string) {
  return useQuery({
    queryKey: ["job_events", jobId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("job_events")
        .select("*")
        .eq("job_id", jobId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
  });
}

export type RealtimeState = "CONNECTING" | "LIVE" | "ERROR";

/**
 * Subscribe to realtime changes and refresh the matching caches.
 * Returns the channel state so the UI can show whether the stream is live.
 */
export function useVisionRealtime(tables: string[]): RealtimeState {
  const queryClient = useQueryClient();
  const key = tables.join(",");
  const [state, setState] = useState<RealtimeState>("CONNECTING");

  useEffect(() => {
    const list = key.split(",");
    const refresh = (table: string) => {
      void queryClient.invalidateQueries({ queryKey: [table] });
      if (table === "vision_jobs") {
        void queryClient.invalidateQueries({ queryKey: ["vision_job"] });
      }
      if (table === "job_events") {
        void queryClient.invalidateQueries({ queryKey: ["job_events"] });
      }
    };

    const channel = supabase.channel(`vision-${key}`);
    for (const table of list) {
      channel.on("postgres_changes", { event: "*", schema: "public", table }, () =>
        refresh(table),
      );
    }
    channel.subscribe((status) => {
      if (status === "SUBSCRIBED") {
        setState("LIVE");
        // Resync after (re)connection: events missed while offline are not replayed.
        for (const table of list) refresh(table);
      } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
        setState("ERROR");
      }
    });

    // Devices go OFFLINE by elapsed heartbeat time, which emits no realtime event.
    const tick = window.setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ["devices"] });
    }, 30_000);

    const onFocus = () => {
      for (const table of list) refresh(table);
    };
    window.addEventListener("focus", onFocus);

    return () => {
      window.clearInterval(tick);
      window.removeEventListener("focus", onFocus);
      void supabase.removeChannel(channel);
    };
  }, [key, queryClient]);

  return state;
}


export async function logAudit(entry: {
  action: string;
  module_id?: string | null;
  job_id?: string | null;
  device_id?: string | null;
  outcome?: string;
  metadata?: Record<string, unknown>;
}) {
  const { data } = await supabase.auth.getUser();
  if (!data.user) return;
  await supabase.from("audit_logs").insert({
    user_id: data.user.id,
    action: entry.action,
    module_id: entry.module_id ?? null,
    job_id: entry.job_id ?? null,
    device_id: entry.device_id ?? null,
    outcome: entry.outcome ?? "OK",
    metadata: (entry.metadata ?? {}) as never,
  });
}

export const REMOTE_NOT_ENABLED = "NON ANCORA ABILITATO";

export async function sendCommand(input: {
  command_type: CommandType;
  module_id?: string | null;
  target_device_id?: string | null;
  job_id?: string | null;
  parameters?: Record<string, unknown>;
}) {
  // Fase status_only: solo GET_STATUS via RPC contratto (nessun insert diretto).
  if (input.command_type !== "GET_STATUS") {
    throw new Error(REMOTE_NOT_ENABLED);
  }

  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) throw new Error("Sessione scaduta. Effettua di nuovo il login.");

  let deviceCode = "VIS-TARANTO-01";
  if (input.target_device_id) {
    const { data: device } = await supabase
      .from("devices")
      .select("code")
      .eq("id", input.target_device_id)
      .maybeSingle();
    if (device?.code) deviceCode = device.code;
  }

  const { data, error } = await supabase.rpc("create_get_status_command" as never, {
    p_device_id: deviceCode,
  } as never);
  if (error) throw error;
  return data;
}

export function roleCan(roles: AppRole[], command: CommandType, allowed: AppRole[]) {
  return roles.some((r) => allowed.includes(r)) && command != null;
}
