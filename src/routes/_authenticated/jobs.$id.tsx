import { createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { useRoles } from "@/hooks/useAuth";
import { formatDateTime, formatDuration, REMOTE_NOT_ENABLED_LABEL } from "@/lib/vision";
import {
  useDevices,
  useJob,
  useJobEvents,
  useModules,
} from "@/lib/vision-data";
import { createGetStatusCommand, waitForGetStatusResult } from "@/lib/vision-remote-status";

export const Route = createFileRoute("/_authenticated/jobs/$id")({
  head: () => ({
    meta: [
      { title: "Dettaglio lavorazione — VIS•ION" },
      { name: "description", content: "Timeline, stato ed errori di una lavorazione VIS•ION." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Dettaglio lavorazione — VIS•ION" },
      { property: "og:description", content: "Dettaglio lavorazione VIS•ION." },
    ],
  }),
  component: JobDetail,
});

function JobDetail() {
  const { id } = Route.useParams();
  const { data: job, isLoading } = useJob(id);
  const { data: events = [] } = useJobEvents(id);
  const { data: modules = [] } = useModules();
  const { data: devices = [] } = useDevices();
  const { canOperate } = useRoles();

  if (isLoading) {
    return (
      <AppShell title="Lavorazione">
        <p className="text-sm text-muted-foreground">Caricamento…</p>
      </AppShell>
    );
  }
  if (!job) {
    return (
      <AppShell title="Lavorazione">
        <p className="hud-panel p-6 text-sm text-muted-foreground">
          Lavorazione non trovata o non accessibile con il tuo ruolo.
        </p>
      </AppShell>
    );
  }

  const module = modules.find((m: any) => m.id === job.module_id);
  const device = devices.find((d: any) => d.id === job.device_id);

  return (
    <AppShell
      title={job.code}
      subtitle={job.is_demo ? `${job.title} · DEMO` : job.title}
    >
      <div className="space-y-4">
        {job.is_demo ? (
          <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            Record DEMO — non rappresenta lo stato live di VISION Agent / EniSpace.
          </p>
        ) : null}
        <div className="hud-panel space-y-3 p-4">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
            <div className="min-w-0">
              <p className="hud-title">Stato</p>
              <p className="truncate font-mono text-lg">{job.current_step ?? "—"}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              {job.is_demo ? (
                <span className="rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 font-mono text-[0.6rem] text-warning">
                  DEMO
                </span>
              ) : null}
              <StatusBadge status={job.status} />
            </div>
          </div>
          <Progress value={job.progress ?? 0} />
          <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
            <div className="min-w-0">
              <dt className="text-muted-foreground">Modulo</dt>
              <dd className="truncate">{module?.name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Sorgente</dt>
              <dd className="font-mono">{job.source ?? "—"}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-muted-foreground">Dispositivo</dt>
              <dd className="truncate font-mono">{device?.code ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Creazione</dt>
              <dd>{formatDateTime(job.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Avvio</dt>
              <dd>{formatDateTime(job.started_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Fine</dt>
              <dd>{formatDateTime(job.finished_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Durata</dt>
              <dd>{formatDuration(job.duration_seconds)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Progress</dt>
              <dd className="font-mono">{job.progress}%</dd>
            </div>
          </dl>
          {job.error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3">
              <p className="font-mono text-xs font-bold text-destructive">COMANDO FALLITO</p>
              <p className="mt-1 text-xs text-destructive">{job.error}</p>
            </div>
          )}
        </div>

        <div className="hud-panel space-y-3 p-4">
          <p className="hud-title">Comandi disponibili</p>
          <div className="flex flex-wrap gap-2">
            <CommandButton
              label="Riprova job"
              sensitive
              disabled
              disabledReason={REMOTE_NOT_ENABLED_LABEL}
              onConfirm={async () => {
                toast.error(REMOTE_NOT_ENABLED_LABEL);
              }}
            />
            <CommandButton
              label="Stato agent"
              disabled={!canOperate}
              disabledReason="Il tuo ruolo non consente l'invio di comandi."
              onConfirm={async () => {
                try {
                  const code =
                    devices.find((d: any) => d.id === job.device_id)?.code ?? "VIS-TARANTO-01";
                  const cmd = await createGetStatusCommand(code);
                  const wait = await waitForGetStatusResult(cmd.id);
                  if (!wait.ok) {
                    toast.error(wait.message);
                  } else {
                    toast.success("Stato aggiornato");
                  }
                } catch (e) {
                  toast.error("COMANDO FALLITO", { description: (e as Error).message });
                }
              }}
            />
          </div>
        </div>

        <div className="hud-panel p-4">
          <p className="hud-title">Timeline eventi</p>
          <ol className="mt-3 space-y-3 border-l border-border pl-4">
            {events.map((e: any) => (
              <li key={e.id} className="relative">
                <span className="absolute top-1.5 -left-[21px] size-2 rounded-full bg-accent" />
                <p className="font-mono text-[0.65rem] tracking-widest text-accent">
                  {e.event_type}
                </p>
                <p className="text-sm">{e.message}</p>
                <p className="text-[0.65rem] text-muted-foreground">
                  {formatDateTime(e.created_at)}
                </p>
              </li>
            ))}
            {events.length === 0 && (
              <li className="text-xs text-muted-foreground">Nessun evento registrato.</li>
            )}
          </ol>
        </div>

        <div className="hud-panel p-4">
          <p className="hud-title">Metadata</p>
          <pre className="mt-2 overflow-x-auto rounded-md bg-secondary/40 p-3 font-mono text-[0.65rem]">
            {JSON.stringify(job.metadata ?? {}, null, 2)}
          </pre>
        </div>
      </div>
    </AppShell>
  );
}
