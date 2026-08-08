import { createFileRoute, Link } from "@tanstack/react-router";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { SupervisorAvatar } from "@/components/vision/SupervisorAvatar";
import { Progress } from "@/components/ui/progress";
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

function deriveState(job: any): SupervisorState {
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
  const { data: jobs = [] } = useJobs();
  const { data: modules = [] } = useModules();

  const active =
    jobs.find((j: any) => j.status === "PROCESSING") ??
    jobs.find((j: any) => j.status === "WAITING_APPROVAL") ??
    jobs[0];
  const state = deriveState(active);
  const activeModule = modules.find((m: any) => m.id === active?.module_id);

  return (
    <AppShell title="VIS•ION Supervisor" subtitle="Supervisore intelligente delle operazioni VIS">
      <div className="space-y-4">
        <div className="hud-panel grid gap-4 p-5 sm:grid-cols-[auto_minmax(0,1fr)]">
          <SupervisorAvatar state={state} />
          <div className="min-w-0 space-y-3">
            <div>
              <p className="hud-title">Stato generale</p>
              <p className="font-mono text-xl font-bold tracking-wide">
                {SUPERVISOR_LABEL[state]}
              </p>
              <StatusBadge status={state} className="mt-1" />
            </div>
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <div className="min-w-0">
                <dt className="text-muted-foreground">Modulo attivo</dt>
                <dd className="truncate">{activeModule?.name ?? "—"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Lavorazione</dt>
                <dd className="truncate font-mono">{active?.code ?? "—"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Step corrente</dt>
                <dd className="truncate font-mono">{active?.current_step ?? "—"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Ultimo evento</dt>
                <dd className="truncate">{formatRelative(active?.updated_at)}</dd>
              </div>
            </dl>
            <div>
              <div className="mb-1 flex justify-between text-[0.65rem] text-muted-foreground">
                <span>Progress</span>
                <span className="font-mono">{active?.progress ?? 0}%</span>
              </div>
              <Progress value={active?.progress ?? 0} />
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
