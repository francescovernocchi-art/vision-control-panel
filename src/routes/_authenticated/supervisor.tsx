import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, RefreshCw } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { SupervisorAvatar } from "@/components/vision/SupervisorAvatar";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useGetStatus } from "@/hooks/useGetStatus";
import { useRoles } from "@/hooks/useAuth";
import {
  formatRelative,
  SUPERVISOR_LABEL,
  type SupervisorState,
} from "@/lib/vision";
import { useJobs, useModules } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/supervisor")({
  head: () => ({
    meta: [
      { title: "Supervisor — VIS•ION" },
      { name: "description", content: "Stato del supervisore VIS•ION e lavorazione in corso." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Supervisor — VIS•ION" },
      { property: "og:description", content: "Stato del supervisore VIS•ION." },
    ],
  }),
  component: SupervisorPage,
});

const STATES: SupervisorState[] = [
  "IDLE",
  "MAIL_RECEIVED",
  "ANALYSIS",
  "PROCESSING",
  "DOWNLOAD",
  "PRINTING",
  "WAITING_APPROVAL",
  "SUCCESS",
  "ERROR",
  "NEEDS_ATTENTION",
];

function deriveState(job: any, remoteSupervisor?: string | null): SupervisorState {
  if (remoteSupervisor) {
    const up = remoteSupervisor.toUpperCase();
    if (STATES.includes(up as SupervisorState)) return up as SupervisorState;
    if (up === "IDLE" || up === "ONLINE") return "IDLE";
    if (up.includes("ERROR") || up === "FAILED") return "ERROR";
    if (up.includes("ATTENTION")) return "NEEDS_ATTENTION";
    if (up.includes("APPROVAL")) return "WAITING_APPROVAL";
    if (up.includes("PROCESS")) return "PROCESSING";
  }
  if (!job) return "IDLE";
  const step = (job.current_step ?? "").toUpperCase();
  if (job.status === "FAILED") return "ERROR";
  if (job.status === "NEEDS_ATTENTION") return "NEEDS_ATTENTION";
  if (job.status === "WAITING_APPROVAL") return "WAITING_APPROVAL";
  if (job.status === "COMPLETED") return "SUCCESS";
  if (STATES.includes(step as SupervisorState)) return step as SupervisorState;
  if (job.status === "PROCESSING") return "PROCESSING";
  return "IDLE";
}

function SupervisorPage() {
  const { canOperate } = useRoles();
  const { data: jobs = [] } = useJobs();
  const { data: modules = [] } = useModules();
  const {
    result,
    refreshing,
    error,
    timeoutMessage,
    lastUpdated,
    refresh,
    partial,
    missingSections,
    mode,
    cloudConfigured,
    agentStatus,
  } = useGetStatus();

  const active =
    jobs.find((j: any) => j.status === "PROCESSING") ??
    jobs.find((j: any) => j.status === "WAITING_APPROVAL") ??
    jobs[0];
  const remoteJob = result?.current_job;
  const state = deriveState(active, result?.supervisor_status);
  const activeModule = modules.find((m: any) => m.id === active?.module_id);

  return (
    <AppShell
      title="VIS•ION Supervisor"
      subtitle="REMOTE CONTROL · READ ONLY — solo GET_STATUS"
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[0.65rem] tracking-widest text-accent">
              REMOTE CONTROL / READ ONLY
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
          <Button
            size="sm"
            variant="secondary"
            disabled={!canOperate || refreshing || !cloudConfigured}
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

        {(error || timeoutMessage) && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.7rem] text-destructive">
            {timeoutMessage || error}
          </p>
        )}
        {lastUpdated && (
          <p className="text-xs text-muted-foreground">
            Ultimo GET_STATUS: {formatRelative(lastUpdated)}
          </p>
        )}

        <div className="hud-panel grid gap-4 p-5 sm:grid-cols-[auto_minmax(0,1fr)]">
          <SupervisorAvatar state={state} />
          <div className="min-w-0 space-y-3">
            <div>
              <p className="hud-title">Stato generale</p>
              <p className="font-mono text-xl font-bold tracking-wide">
                {SUPERVISOR_LABEL[state]}
              </p>
              <StatusBadge status={state} className="mt-1" />
              {result?.supervisor_status && (
                <p className="mt-1 font-mono text-[0.65rem] text-muted-foreground">
                  agent: {result.supervisor_status}
                </p>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <div className="min-w-0">
                <dt className="text-muted-foreground">Modulo attivo</dt>
                <dd className="truncate">{activeModule?.name ?? "—"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Lavorazione</dt>
                <dd className="truncate font-mono">
                  {String(
                    (remoteJob as { code?: string } | null)?.code ??
                      active?.code ??
                      "—",
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Step corrente</dt>
                <dd className="truncate font-mono">
                  {String(
                    (remoteJob as { current_step?: string } | null)?.current_step ??
                      active?.current_step ??
                      "—",
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Ultimo evento</dt>
                <dd className="truncate">{formatRelative(active?.updated_at)}</dd>
              </div>
            </dl>
            <div>
              <div className="mb-1 flex justify-between text-[0.65rem] text-muted-foreground">
                <span>Progress</span>
                <span className="font-mono">
                  {(remoteJob as { progress?: number } | null)?.progress ??
                    active?.progress ??
                    0}
                  %
                </span>
              </div>
              <Progress
                value={
                  (remoteJob as { progress?: number } | null)?.progress ??
                  active?.progress ??
                  0
                }
              />
            </div>
            {active && (
              <Link
                to="/jobs/$id"
                params={{ id: active.id }}
                className="inline-block text-xs text-accent hover:underline"
              >
                Apri dettaglio lavorazione →
              </Link>
            )}
          </div>
        </div>

        {(state === "WAITING_APPROVAL" || state === "NEEDS_ATTENTION" || state === "ERROR") && (
          <div className="hud-panel border-warning/40 p-4">
            <p className="hud-title text-warning">Richiesta di intervento</p>
            <p className="mt-1 text-sm">
              {state === "ERROR"
                ? (active?.error ?? "Errore riportato dal dispositivo.")
                : "È richiesta un'azione da parte di un operatore autorizzato."}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Controlli remoti operativi non abilitati in questa fase (solo lettura stato).
            </p>
            <Link to="/approvazioni" className="mt-2 inline-block text-xs text-accent hover:underline">
              Vai alle approvazioni →
            </Link>
          </div>
        )}

        <div className="hud-panel p-4">
          <p className="hud-title">Stati supportati</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {STATES.map((s) => (
              <span
                key={s}
                className={`rounded-md border px-2 py-0.5 font-mono text-[0.6rem] tracking-widest ${
                  s === state ? "border-accent/60 bg-accent/15 text-accent" : "border-border text-muted-foreground"
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
