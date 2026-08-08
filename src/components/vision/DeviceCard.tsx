import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { StatusBadge, StatusDot } from "@/components/vision/StatusBadge";
import { formatRelative } from "@/lib/vision";
import { displayValue, jobSummaryLabel, statusLabel } from "@/lib/vision-status";
import type { GetStatusResult } from "@/lib/vision-remote-status";

export type DeviceCardModel = {
  id: string;
  code: string;
  name?: string | null;
  location?: string | null;
  last_seen_at?: string | null;
  agent_version?: string | null;
  vision_version?: string | null;
  platform_version?: string | null;
  heartbeat_threshold_seconds?: number | null;
};

export function DeviceCard({
  device,
  onlineStatus,
  result,
}: {
  device: DeviceCardModel;
  onlineStatus: string;
  result?: GetStatusResult | null;
}) {
  const health = result?.overall_health ?? (onlineStatus === "OFFLINE" ? "OFFLINE" : "—");
  const eni = result?.enispace_runtime;
  const eniStatus = eni?.available === false ? "UNAVAILABLE" : (eni?.status ?? "—");
  const coreJob = jobSummaryLabel(result?.current_job ?? null);
  const eniJob = jobSummaryLabel(eni?.current_job ?? null);

  return (
    <Link
      to="/dispositivi/$code"
      params={{ code: device.code }}
      className="group block rounded-xl border border-border/80 bg-card/50 p-4 transition-colors hover:border-accent/50 hover:bg-card/80"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-mono text-sm font-semibold tracking-wide">
            <StatusDot status={onlineStatus} />
            <span className="truncate">{device.code}</span>
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {device.name || "Dispositivo VISION"}
            {device.location ? ` · ${device.location}` : ""}
          </p>
        </div>
        <StatusBadge status={onlineStatus} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Ultimo contatto</dt>
          <dd className="font-mono">{formatRelative(device.last_seen_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Health</dt>
          <dd className="font-mono">{health === "—" ? "—" : statusLabel(health)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">VISION</dt>
          <dd className="font-mono">{displayValue(device.vision_version ?? result?.vision_version)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Agent</dt>
          <dd className="font-mono">{displayValue(device.agent_version ?? result?.agent_version)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Job Core</dt>
          <dd className="truncate font-mono">{coreJob}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">EniSpace</dt>
          <dd className="truncate font-mono">
            {eni?.available === false
              ? "Non disponibile"
              : eniStatus === "—"
                ? "—"
                : statusLabel(String(eniStatus))}
            {eniJob !== "—" ? ` · ${eniJob}` : ""}
          </dd>
        </div>
      </dl>

      <p className="mt-4 flex items-center gap-1 text-xs text-accent opacity-80 group-hover:opacity-100">
        Dettaglio stato <ArrowRight className="size-3.5" aria-hidden />
      </p>
    </Link>
  );
}
