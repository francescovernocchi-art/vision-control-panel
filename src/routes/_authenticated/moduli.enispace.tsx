import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Mail, RefreshCw, History, ListOrdered } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useRoles } from "@/hooks/useAuth";
import {
  formatDateTime,
  formatRelative,
  isDeviceOnline,
  REMOTE_NOT_ENABLED_LABEL,
} from "@/lib/vision";
import { useDevices, useJobs, useModules } from "@/lib/vision-data";
import { createGetStatusCommand, waitForGetStatusResult } from "@/lib/vision-remote-status";

export const Route = createFileRoute("/_authenticated/moduli/enispace")({
  head: () => ({
    meta: [
      { title: "eniSpace Automation — VIS•ION" },
      { name: "description", content: "Stato del modulo eniSpace Automation e comandi autorizzati." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "eniSpace Automation — VIS•ION" },
      { property: "og:description", content: "Modulo eniSpace del sistema VIS•ION." },
    ],
  }),
  component: EnispacePage,
});

function EnispacePage() {
  const queryClient = useQueryClient();
  const { canOperate } = useRoles();
  const { data: modules = [] } = useModules();
  const { data: jobs = [] } = useJobs();
  const { data: devices = [] } = useDevices();

  const module = modules.find((m: any) => m.key === "enispace");
  const device = devices[0];
  const agentOnline =
    device && isDeviceOnline(device.last_seen_at, device.heartbeat_threshold_seconds ?? 120);
  const moduleJobs = jobs.filter((j: any) => j.module_id === module?.id);
  const current = moduleJobs.find((j: any) => j.id === module?.current_job_id) ?? moduleJobs[0];
  const meta = (current?.metadata ?? {}) as Record<string, unknown>;

  const remoteBlocked = REMOTE_NOT_ENABLED_LABEL;
  const statusDisabledReason = !canOperate
    ? "Il tuo ruolo non consente l'invio di comandi."
    : !agentOnline
      ? `Impossibile inviare il comando: ${device?.code ?? "agent"} non è raggiungibile.`
      : undefined;

  async function runGetStatus() {
    try {
      const cmd = await createGetStatusCommand(device?.code ?? "VIS-TARANTO-01");
      const wait = await waitForGetStatusResult(cmd.id);
      if (!wait.ok) {
        toast.error(wait.reason === "timeout" ? wait.message : "GET_STATUS fallito", {
          description: wait.message,
        });
      } else {
        toast.success("Stato aggiornato", { description: device?.code });
      }
      void queryClient.invalidateQueries({ queryKey: ["commands"] });
      void queryClient.invalidateQueries({ queryKey: ["devices"] });
    } catch (e) {
      toast.error("COMANDO FALLITO", {
        description: `GET_STATUS: ${(e as Error).message}`,
      });
    }
  }

  return (
    <AppShell title="eniSpace Automation" subtitle="Modulo operativo — controllo mail, documenti, stampa">
      <div className="space-y-4">
        {!agentOnline && (
          <div className="hud-panel border-destructive/40 p-4">
            <p className="font-mono text-sm font-bold text-destructive">AGENT OFFLINE</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Non è possibile inviare comandi perché {device?.code ?? "l'agent"} non è
              raggiungibile.
            </p>
          </div>
        )}

        <div className="hud-panel space-y-3 p-4">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
            <div className="min-w-0">
              <p className="hud-title">Stato modulo</p>
              <p className="truncate text-sm">{module?.description ?? "—"}</p>
            </div>
            <StatusBadge status={module?.status ?? "OFFLINE"} />
          </div>
          <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Ultimo controllo mail</dt>
              <dd className="font-mono">{formatRelative(module?.last_activity_at)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-muted-foreground">Ultima lavorazione</dt>
              <dd className="truncate font-mono">{moduleJobs[0]?.code ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Mail rilevate</dt>
              <dd className="font-mono">{String(meta["mail_rilevate"] ?? moduleJobs.length)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-muted-foreground">Ordine corrente</dt>
              <dd className="truncate font-mono">{String(meta["ordine"] ?? current?.title ?? "—")}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Documenti trovati</dt>
              <dd className="font-mono">{String(meta["documenti_trovati"] ?? "—")}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Documenti elaborati</dt>
              <dd className="font-mono">{String(meta["documenti_elaborati"] ?? "—")}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Stato stampa</dt>
              <dd className="font-mono">{String(meta["stato_stampa"] ?? "—")}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Aggiornato</dt>
              <dd className="font-mono">{formatDateTime(module?.updated_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="hud-panel space-y-3 p-4">
          <p className="hud-title">Comandi autorizzati</p>
          <p className="text-[0.65rem] text-muted-foreground">
            Fase remota status_only — comandi operativi: {REMOTE_NOT_ENABLED_LABEL}.
          </p>
          <div className="flex flex-wrap gap-2">
            <CommandButton
              label="Controlla ora le mail"
              icon={<Mail className="size-4" />}
              disabled
              disabledReason={remoteBlocked}
              onConfirm={async () => {
                toast.error(remoteBlocked);
              }}
            />
            <CommandButton
              label="Riprova ultimo job"
              sensitive
              icon={<RefreshCw className="size-4" />}
              disabled
              disabledReason={remoteBlocked}
              description={`Verrà richiesto al Core di rieseguire ${current?.code ?? "l'ultimo job"}.`}
              onConfirm={async () => {
                toast.error(remoteBlocked);
              }}
            />
            <CommandButton
              label="Stato agent"
              disabled={!!statusDisabledReason}
              disabledReason={statusDisabledReason}
              onConfirm={() => runGetStatus()}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              to="/lavorazioni"
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:border-accent/50"
            >
              <ListOrdered className="size-4" /> Apri coda
            </Link>
            <Link
              to="/lavorazioni"
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:border-accent/50"
            >
              <History className="size-4" /> Apri storico
            </Link>
          </div>
        </div>

        <div className="hud-panel p-4">
          <p className="hud-title">Storico recente</p>
          <ul className="mt-2 space-y-2">
            {moduleJobs.slice(0, 8).map((j: any) => (
              <li key={j.id}>
                <Link
                  to="/jobs/$id"
                  params={{ id: j.id }}
                  className="flex items-center gap-3 rounded-lg border border-border px-3 py-2 hover:border-accent/50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{j.title}</p>
                    <p className="font-mono text-[0.65rem] text-muted-foreground">
                      {j.code} · {formatRelative(j.created_at)}
                    </p>
                  </div>
                  <StatusBadge status={j.status} />
                </Link>
              </li>
            ))}
            {moduleJobs.length === 0 && (
              <li className="text-xs text-muted-foreground">Nessuna lavorazione registrata.</li>
            )}
          </ul>
        </div>
      </div>
    </AppShell>
  );
}
