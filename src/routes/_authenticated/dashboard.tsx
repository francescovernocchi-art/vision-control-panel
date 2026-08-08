import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  RefreshCw,
} from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge, StatusDot } from "@/components/vision/StatusBadge";
import { Button } from "@/components/ui/button";
import { useGetStatus } from "@/hooks/useGetStatus";
import { useRoles } from "@/hooks/useAuth";
import {
  formatRelative,
  formatDateTime,
  REMOTE_NOT_ENABLED_LABEL,
} from "@/lib/vision";
import { useApprovals, useJobs, useModules } from "@/lib/vision-data";
import { moduleFromResult, serviceFromResult } from "@/lib/vision-remote-status";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — VIS•ION" },
      { name: "description", content: "Stato in tempo reale di VIS•ION Core, agent e moduli." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Dashboard — VIS•ION" },
      { property: "og:description", content: "Stato in tempo reale delle operazioni VIS." },
    ],
  }),
  component: Dashboard,
});

const MODULE_ROUTES: Record<string, "/moduli/enispace" | "/moduli/trasporto-monete"> = {
  enispace: "/moduli/enispace",
  coin_transport: "/moduli/trasporto-monete",
};

const MODULE_ID_BY_KEY: Record<string, string> = {
  enispace: "enispace",
  coin_transport: "coin_transport",
};

const PLATFORM_SERVICES = [
  "logger",
  "configuration",
  "storage",
  "event_bus",
  "notification",
  "jobs",
] as const;

function Kpi({
  label,
  value,
  tone = "",
}: {
  label: string;
  value: number | string;
  tone?: string;
}) {
  return (
    <div className="hud-panel p-3">
      <p className="hud-title">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${tone}`}>{value}</p>
    </div>
  );
}

function Dashboard() {
  const { canOperate } = useRoles();
  const {
    device,
    deviceId,
    result,
    refreshing,
    error,
    timeoutMessage,
    hasEverSynced,
    agentStatus,
    warnings,
    partial,
    missingSections,
    lastUpdated,
    mode,
    cloudConfigured,
    refresh,
  } = useGetStatus();
  const { data: modules = [] } = useModules();
  const { data: jobs = [], isLoading } = useJobs();
  const { data: approvals = [] } = useApprovals();

  const coreStatus = result?.core_status ?? "—";
  const supervisorStatus = result?.supervisor_status ?? "—";
  const platformHealth = result?.overall_health ?? "—";
  const today = new Date().toDateString();
  const todayJobs = jobs.filter((j: any) => new Date(j.created_at).toDateString() === today);
  const count = (statuses: string[]) => jobs.filter((j: any) => statuses.includes(j.status)).length;
  const pendingApprovals = approvals.filter((a: any) => a.status === "PENDING").length;
  const recent = jobs.slice(0, 5);
  const queueSize = result?.queue_size ?? count(["QUEUED", "PENDING"]);
  const showDemoBanner = mode === "DEMO" || (mode === "CLOUD" && !hasEverSynced);
  const currentJobLabel =
    (result?.current_job as { code?: string; id?: string } | null)?.code ||
    (result?.current_job as { id?: string } | null)?.id ||
    "—";

  return (
    <AppShell title="Dashboard" subtitle="Centro di controllo VIS•ION — READ ONLY">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[0.65rem] tracking-widest text-accent">
            REMOTE CONTROL / READ ONLY
          </span>
          <span className="rounded-md border border-border px-2 py-0.5 font-mono text-[0.65rem] text-muted-foreground">
            GET_STATUS only
          </span>
          <span
            className={`rounded-md border px-2 py-0.5 font-mono text-[0.65rem] tracking-widest ${
              mode === "CLOUD"
                ? "border-success/40 bg-success/10 text-success"
                : "border-warning/40 bg-warning/10 text-warning"
            }`}
          >
            {mode === "CLOUD" ? "CLOUD" : "DEMO / NON COLLEGATO"}
          </span>
          {partial && (
            <span className="rounded-md border border-warning/40 bg-warning/10 px-2 py-0.5 font-mono text-[0.65rem] text-warning">
              STATO PARZIALE
              {missingSections.length > 0 ? ` · ${missingSections.join(", ")}` : ""}
            </span>
          )}
          {agentStatus === "OFFLINE" && (
            <span className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-0.5 font-mono text-[0.65rem] text-destructive">
              AGENT OFFLINE
            </span>
          )}
        </div>

        {showDemoBanner && (
          <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-[0.7rem] text-warning">
            {mode === "DEMO"
              ? "DEMO / NON COLLEGATO — i dati sotto possono essere dimostrativi. Configura VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY."
              : "CLOUD attivo ma nessuno GET_STATUS sincronizzato — premi «Aggiorna stato». I KPI lavorazioni cloud non sono lo stato Agent finché non arriva un result reale."}
          </p>
        )}

        {(error || timeoutMessage) && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.7rem] text-destructive">
            {timeoutMessage || error}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Device {deviceId}
            {lastUpdated ? ` · last update ${formatRelative(lastUpdated)}` : ""}
          </p>
          <Button
            size="sm"
            variant="secondary"
            disabled={!canOperate || refreshing || !cloudConfigured}
            title={
              !cloudConfigured
                ? "DEMO / NON COLLEGATO"
                : !canOperate
                  ? "Ruolo non autorizzato"
                  : undefined
            }
            onClick={() => void refresh()}
          >
            {refreshing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            Aggiorna stato
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="hud-panel p-4">
            <p className="hud-title">VIS•ION Core</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={coreStatus === "—" ? "OFFLINE" : coreStatus} />
              <span className="font-mono text-lg font-bold">{coreStatus}</span>
            </div>
          </div>
          <div className="hud-panel p-4">
            <p className="hud-title">Supervisor</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={supervisorStatus === "—" ? "OFFLINE" : supervisorStatus} />
              <span className="font-mono text-lg font-bold">{supervisorStatus}</span>
            </div>
          </div>
          <div className="hud-panel p-4">
            <p className="hud-title">Agent</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={agentStatus} />
              <span className="truncate font-mono text-lg font-bold">
                {device?.code ?? result?.device_id ?? "NESSUN AGENT"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Heartbeat: {formatRelative(device?.last_seen_at)} · soglia{" "}
              {device?.heartbeat_threshold_seconds ?? 60}s
            </p>
          </div>
          <div className="hud-panel p-4">
            <p className="hud-title">Platform health</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={platformHealth === "—" ? "OFFLINE" : platformHealth} />
              <span className="font-mono text-lg font-bold">{platformHealth}</span>
            </div>
            <p className="mt-1 font-mono text-[0.65rem] text-muted-foreground">
              platform {result?.platform_version ?? device?.platform_version ?? "—"} · vision{" "}
              {result?.vision_version ?? device?.vision_version ?? "—"}
            </p>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="hud-panel p-4">
            <p className="hud-title">Current job</p>
            <p className="mt-1 font-mono text-sm">{currentJobLabel}</p>
          </div>
          <div className="hud-panel p-4">
            <p className="hud-title">Queue size</p>
            <p className="mt-1 font-mono text-2xl font-bold">{queueSize}</p>
          </div>
        </div>

        <section className="space-y-2">
          <h2 className="hud-title">Services</h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {PLATFORM_SERVICES.map((sid) => {
              const svc = serviceFromResult(result, sid);
              const status = svc
                ? svc.available === false
                  ? "OFFLINE"
                  : svc.health || "ONLINE"
                : hasEverSynced
                  ? "—"
                  : "—";
              return (
                <div key={sid} className="hud-panel p-3">
                  <p className="truncate font-mono text-[0.65rem] text-muted-foreground">{sid}</p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <StatusDot status={status === "—" ? "OFFLINE" : status} />
                    <span className="font-mono text-xs font-bold">{status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {warnings.length > 0 && (
          <div className="hud-panel border-warning/40 space-y-2 p-4">
            <p className="hud-title text-warning">Warnings</p>
            <ul className="space-y-1 text-xs">
              {warnings.map((w) => (
                <li key={w.code} className="font-mono">
                  [{w.severity ?? "—"}] {w.code}
                  {w.message ? `: ${w.message}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi label="Oggi" value={todayJobs.length} />
          <Kpi label="In elaborazione" value={count(["PROCESSING"])} tone="text-info" />
          <Kpi label="In coda" value={queueSize} />
          <Kpi label="Completate" value={count(["COMPLETED"])} tone="text-success" />
          <Kpi
            label="Interventi"
            value={count(["NEEDS_ATTENTION", "WAITING_APPROVAL"])}
            tone="text-warning"
          />
          <Kpi label="Errori" value={count(["FAILED"])} tone="text-destructive" />
        </div>

        {pendingApprovals > 0 && (
          <Link
            to="/approvazioni"
            className="hud-panel flex items-center gap-3 p-4 transition-colors hover:border-warning/60"
          >
            <AlertTriangle className="size-5 shrink-0 text-warning" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">
                {pendingApprovals} approvazione/i in attesa
              </p>
              <p className="truncate text-xs text-muted-foreground">
                Azioni remote operative: {REMOTE_NOT_ENABLED_LABEL} (solo lettura stato).
              </p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          </Link>
        )}

        <section className="space-y-3">
          <h2 className="hud-title">Moduli operativi</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {modules.map((m: any) => {
              const remote = moduleFromResult(result, MODULE_ID_BY_KEY[m.key] ?? m.key);
              const status = remote?.status ?? remote?.health ?? (hasEverSynced ? "—" : m.status);
              const current =
                remote?.current_job != null
                  ? { code: String(remote.current_job) }
                  : jobs.find((j: any) => j.id === m.current_job_id);
              const route = MODULE_ROUTES[m.key];
              return (
                <div key={m.id} className="hud-panel space-y-2 p-4">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">
                        {remote?.display_name ?? m.name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {remote?.version ? `v${remote.version}` : m.description}
                      </p>
                    </div>
                    <StatusBadge status={status} />
                  </div>
                  <dl className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Ultima attività</dt>
                      <dd className="font-mono">{formatRelative(m.last_activity_at)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-muted-foreground">Job corrente</dt>
                      <dd className="truncate font-mono">
                        {(current as any)?.code ?? "—"}
                      </dd>
                    </div>
                  </dl>
                  {route && (
                    <Button asChild size="sm" variant="secondary" className="w-full">
                      <Link to={route}>
                        Apri modulo <ArrowRight className="size-4" />
                      </Link>
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="hud-title">Attività recente</h2>
            <Link to="/lavorazioni" className="text-xs text-accent hover:underline">
              Tutte le lavorazioni
            </Link>
          </div>
          {isLoading && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Caricamento…
            </p>
          )}
          <ul className="space-y-2">
            {recent.map((j: any) => (
              <li key={j.id}>
                <Link
                  to="/jobs/$id"
                  params={{ id: j.id }}
                  className="hud-panel flex items-center gap-3 p-3 transition-colors hover:border-accent/50"
                >
                  {j.status === "COMPLETED" ? (
                    <CheckCircle2 className="size-4 shrink-0 text-success" />
                  ) : j.status === "FAILED" ? (
                    <AlertTriangle className="size-4 shrink-0 text-destructive" />
                  ) : j.status === "PROCESSING" ? (
                    <Play className="size-4 shrink-0 text-info" />
                  ) : (
                    <Clock className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{j.title}</p>
                    <p className="truncate font-mono text-[0.65rem] text-muted-foreground">
                      {j.code} · {formatRelative(j.created_at)}
                      {j.is_demo ? " · DEMO" : ""}
                    </p>
                  </div>
                  <StatusBadge status={j.status} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
