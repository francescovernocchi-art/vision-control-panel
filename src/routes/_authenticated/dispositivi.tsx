import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge, StatusDot } from "@/components/vision/StatusBadge";
import { useRoles } from "@/hooks/useAuth";
import { formatDateTime, formatRelative, isDeviceOnline } from "@/lib/vision";
import { sendCommand, useCommands, useDevices, useJobs, useModules } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/dispositivi")({
  head: () => ({
    meta: [
      { title: "Dispositivi — VIS•ION" },
      { name: "description", content: "PC e agent VIS•ION registrati, heartbeat e stato." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Dispositivi — VIS•ION" },
      { property: "og:description", content: "Agent VIS•ION registrati." },
    ],
  }),
  component: DispositiviPage,
});

const STATUS_TONE: Record<string, string> = {
  PENDING: "text-muted-foreground",
  ACKNOWLEDGED: "text-primary",
  EXECUTING: "text-primary",
  COMPLETED: "text-emerald-400",
  FAILED: "text-destructive",
  EXPIRED: "text-destructive",
};

function StatusReadout({ command }: { command: any }) {
  if (!command) {
    return (
      <p className="rounded-md border border-dashed border-border p-2 text-[0.7rem] text-muted-foreground">
        Nessuna lettura GET_STATUS registrata per questo agent.
      </p>
    );
  }
  const result = command.result as Record<string, unknown> | null;
  const entries = result && typeof result === "object" ? Object.entries(result) : [];
  return (
    <div className="space-y-2 rounded-md border border-border bg-background/40 p-2">
      <div className="flex items-center justify-between gap-2 text-[0.7rem]">
        <span className="text-muted-foreground">Ultimo GET_STATUS</span>
        <span className={`font-mono font-bold ${STATUS_TONE[command.status] ?? ""}`}>
          {command.status}
        </span>
      </div>
      <p className="text-[0.65rem] text-muted-foreground">
        Richiesto {formatRelative(command.requested_at)}
        {command.executed_at ? ` · risposta ${formatRelative(command.executed_at)}` : ""}
      </p>
      {command.error && (
        <p className="font-mono text-[0.65rem] text-destructive">{command.error}</p>
      )}
      {entries.length > 0 && (
        <dl className="grid grid-cols-2 gap-1 text-[0.65rem]">
          {entries.slice(0, 8).map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="truncate text-muted-foreground">{k}</dt>
              <dd className="truncate font-mono">
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function DispositiviPage() {
  const { data: devices = [] } = useDevices();
  const { data: modules = [] } = useModules();
  const { data: jobs = [] } = useJobs();
  const { data: commands = [] } = useCommands();
  const { canOperate } = useRoles();

  return (
    <AppShell title="Dispositivi" subtitle="PC / Agent VIS•ION">
      <div className="grid gap-3 md:grid-cols-2">
        {devices.map((d: any) => {
          const online = isDeviceOnline(d.last_seen_at, d.heartbeat_threshold_seconds ?? 120);
          const effective = d.status === "DISABLED" ? "DISABLED" : online ? d.status : "OFFLINE";
          const currentJob = jobs.find((j: any) => j.id === d.current_job_id);
          const lastStatus = commands.find(
            (c: any) => c.target_device_id === d.id && c.command_type === "GET_STATUS",
          );
          return (

            <div key={d.id} className="hud-panel space-y-3 p-4">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-mono text-sm font-bold">
                    <StatusDot status={effective} /> {d.code}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {d.name} · {d.location ?? "—"}
                  </p>
                </div>
                <StatusBadge status={effective} />
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Ultimo heartbeat</dt>
                  <dd className="font-mono">{formatDateTime(d.last_seen_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Scarto</dt>
                  <dd className="font-mono">{formatRelative(d.last_seen_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Versione agent</dt>
                  <dd className="font-mono">{d.agent_version ?? "—"}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-muted-foreground">Job corrente</dt>
                  <dd className="truncate font-mono">{currentJob?.code ?? "—"}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-1.5">
                {modules.map((m: any) => (
                  <span
                    key={m.id}
                    className="rounded-md border border-border px-2 py-0.5 text-[0.65rem] text-muted-foreground"
                  >
                    {m.name}
                  </span>
                ))}
              </div>
              <StatusReadout command={lastStatus} />

              <CommandButton
                label="Richiedi stato"
                disabled={!canOperate || !online}
                disabledReason={
                  !canOperate
                    ? "Il tuo ruolo non consente l'invio di comandi."
                    : `AGENT OFFLINE — ${d.code} non è raggiungibile.`
                }
                onConfirm={async () => {
                  try {
                    await sendCommand({ command_type: "GET_STATUS", target_device_id: d.id });
                    toast.success("Comando GET_STATUS inviato");
                  } catch (e) {
                    toast.error("COMANDO FALLITO", { description: (e as Error).message });
                  }
                }}
              />
            </div>
          );
        })}
        {devices.length === 0 && (
          <p className="hud-panel p-6 text-sm text-muted-foreground">
            Nessun dispositivo registrato.
          </p>
        )}
      </div>
    </AppShell>
  );
}
