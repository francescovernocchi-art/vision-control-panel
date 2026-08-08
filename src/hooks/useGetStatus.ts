import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useDevices } from "@/lib/vision-data";
import { supabase } from "@/integrations/supabase/client";
import {
  DEFAULT_DEVICE_ID,
  createGetStatusCommand,
  dataMode,
  derivedAgentStatus,
  isCloudConfigured,
  moduleFromResult,
  serviceFromResult,
  uniqueWarnings,
  waitForGetStatusResult,
  type GetStatusResult,
} from "@/lib/vision-remote-status";

const STORAGE_KEY = "vision.get_status.last_result";

function loadCached(): GetStatusResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as GetStatusResult) : null;
  } catch {
    return null;
  }
}

function saveCached(result: GetStatusResult | null) {
  if (typeof window === "undefined") return;
  try {
    if (result) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(result));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function useGetStatus(deviceId: string = DEFAULT_DEVICE_ID) {
  const queryClient = useQueryClient();
  const { data: devices = [] } = useDevices();
  const device =
    devices.find((d: { code?: string }) => d.code === deviceId) ?? devices[0] ?? null;

  const [result, setResult] = useState<GetStatusResult | null>(() => loadCached());
  const [commandStatus, setCommandStatus] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [timeoutMessage, setTimeoutMessage] = useState("");
  const [hasEverSynced, setHasEverSynced] = useState(() => !!loadCached());
  const mode = dataMode();
  const cloudConfigured = isCloudConfigured();

  // Realtime devices (contratto): invalidazione cache device
  useEffect(() => {
    if (!cloudConfigured || !device?.id) return;
    const channel = supabase
      .channel(`device-${device.id}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "devices",
          filter: `id=eq.${device.id}`,
        },
        () => {
          void queryClient.invalidateQueries({ queryKey: ["devices"] });
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [cloudConfigured, device?.id, queryClient]);

  const refresh = useCallback(async () => {
    if (!cloudConfigured) {
      setError("DEMO / NON COLLEGATO — configura VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY");
      return;
    }
    setRefreshing(true);
    setError("");
    setTimeoutMessage("");
    setCommandStatus("PENDING");
    try {
      const cmd = await createGetStatusCommand(deviceId);
      setCommandStatus(cmd.status);

      const wait = await waitForGetStatusResult(cmd.id);
      if (!wait.ok && wait.reason === "timeout") {
        setTimeoutMessage(wait.message);
        setCommandStatus(wait.command?.status ?? "PENDING");
      } else if (!wait.ok) {
        setError(wait.message);
        setCommandStatus(wait.command?.status ?? "FAILED");
      } else {
        setResult(wait.result);
        saveCached(wait.result);
        setHasEverSynced(true);
        setCommandStatus("COMPLETED");
        setLastUpdated(
          wait.result?.timestamp ||
            wait.command.finished_at ||
            wait.command.executed_at ||
            new Date().toISOString(),
        );
      }
      void queryClient.invalidateQueries({ queryKey: ["commands"] });
      void queryClient.invalidateQueries({ queryKey: ["devices"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setCommandStatus(null);
    } finally {
      setRefreshing(false);
    }
  }, [cloudConfigured, deviceId, queryClient]);

  const agentStatus = useMemo(
    () => derivedAgentStatus(device, result),
    [device, result],
  );

  const warnings = useMemo(() => uniqueWarnings(result?.warnings), [result]);

  return {
    device,
    deviceId,
    deviceCode: deviceId,
    result,
    commandStatus,
    lastUpdated,
    refreshing,
    error,
    timeoutMessage,
    hasEverSynced,
    agentStatus,
    warnings,
    partial: Boolean(result?.partial),
    missingSections: result?.missing_sections ?? [],
    cloudConfigured,
    mode,
    moduleFromResult: (id: string) => moduleFromResult(result, id),
    serviceFromResult: (id: string) => serviceFromResult(result, id),
    refresh,
  };
}
