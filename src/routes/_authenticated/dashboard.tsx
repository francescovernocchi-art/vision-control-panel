import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock, Loader2, Play } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge, StatusDot } from "@/components/vision/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  formatRelative,
  formatDateTime,
  isDeviceOnline,
} from "@/lib/vision";
import { useApprovals, useDevices, useJobs, useModules } from "@/lib/vision-data";
import { useOnlineStatus } from "@/hooks/useAuth";

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
  const online = useOnlineStatus();
  const { data: devices = [] } = useDevices();
  const { data: modules = [] } = useModules();
  const { data: jobs = [], isLoading } = useJobs();
  const { data: approvals = [] } = useApprovals();

  const mainDevice = devices[0];
  const agentOnline =
    mainDevice &&
    isDeviceOnline(mainDevice.last_seen_at, mainDevice.heartbeat_threshold_seconds ?? 120);

  const today = new Date().toDateString();
  const todayJobs = jobs.filter((j: any) => new Date(j.created_at).toDateString() === today);
  const count = (statuses: string[]) => jobs.filter((j: any) => statuses.includes(j.status)).length;
  const pendingApprovals = approvals.filter((a: any) => a.status === "PENDING").length;
  const recent = jobs.slice(0, 5);

  return (
    <AppShell title="Dashboard" subtitle="Centro di controllo VIS•ION">
      <div className="space-y-4">
        <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-[0.7rem] text-warning">
          DATI DIMOSTRATIVI — le righe contrassegnate come demo saranno sostituite dai dati reali
          inviati dal VIS•ION Agent Python.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="hud-panel p-4">
            <p className="hud-title">VIS•ION Core</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={online ? "ONLINE" : "OFFLINE"} />
              <span className="font-mono text-lg font-bold">
                {online ? "ONLINE" : "OFFLINE"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Connessione cloud e realtime {online ? "attiva" : "assente"}
            </p>
          </div>
          <div className="hud-panel p-4">
            <p className="hud-title">Agent principale</p>
            <div className="mt-2 flex items-center gap-2">
              <StatusDot status={agentOnline ? "ONLINE" : "OFFLINE"} />
              <span className="truncate font-mono text-lg font-bold">
                {mainDevice?.code ?? "NESSUN AGENT"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Ultimo heartbeat: {formatRelative(mainDevice?.last_seen_at)} ·{" "}
              {formatDateTime(mainDevice?.last_seen_at)}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi label="Oggi" value={todayJobs.length} />
          <Kpi label="In elaborazione" value={count(["PROCESSING"])} tone="text-info" />
          <Kpi label="In coda" value={count(["QUEUED", "PENDING"])} />
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
                Operazioni sensibili bloccate finché non vengono confermate.
              </p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          </Link>
        )}

        <section className="space-y-3">
          <h2 className="hud-title">Moduli operativi</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {modules.map((m: any) => {
              const current = jobs.find((j: any) => j.id === m.current_job_id);
              const route = MODULE_ROUTES[m.key];
              return (
                <div key={m.id} className="hud-panel space-y-2 p-4">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{m.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{m.description}</p>
                    </div>
                    <StatusBadge status={m.status} />
                  </div>
                  <dl className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Ultima attività</dt>
                      <dd className="font-mono">{formatRelative(m.last_activity_at)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-muted-foreground">Job corrente</dt>
                      <dd className="truncate font-mono">{current?.code ?? "—"}</dd>
                    </div>
                  </dl>
                  {m.error_message && (
                    <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                      {m.error_message}
                    </p>
                  )}
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
