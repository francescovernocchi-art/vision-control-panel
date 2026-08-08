import { createFileRoute, Link } from "@tanstack/react-router";
import { Check, FileText, Mail, Truck, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { cn } from "@/lib/utils";
import { COIN_WORKFLOW, formatRelative, REMOTE_NOT_ENABLED_LABEL } from "@/lib/vision";
import {
  useApprovals,
  useDevices,
  useJobs,
  useModules,
} from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/moduli/trasporto-monete")({
  head: () => ({
    meta: [
      { title: "Trasporto Monete — VIS•ION" },
      { name: "description", content: "Flusso Trasporto Monete: mail, mezzi, itinerario, PEC." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Trasporto Monete — VIS•ION" },
      { property: "og:description", content: "Modulo Trasporto Monete del sistema VIS•ION." },
    ],
  }),
  component: CoinPage,
});

function CoinPage() {
  const { data: modules = [] } = useModules();
  const { data: jobs = [] } = useJobs();
  const { data: devices = [] } = useDevices();
  const { data: approvals = [] } = useApprovals();

  const module = modules.find((m: any) => m.key === "coin_transport");
  const device = devices[0];
  const moduleJobs = jobs.filter((j: any) => j.module_id === module?.id);
  const current = moduleJobs.find((j: any) => j.id === module?.current_job_id) ?? moduleJobs[0];
  const approval = approvals.find((a: any) => a.job_id === current?.id && a.status === "PENDING");
  const meta = (approval?.metadata ?? current?.metadata ?? {}) as Record<string, unknown>;
  const province = (meta["province"] as string[] | undefined) ?? [];

  const stepIndex = Math.max(
    0,
    COIN_WORKFLOW.indexOf((current?.current_step ?? "MAIL").toUpperCase() as never),
  );

  const disabledReason = REMOTE_NOT_ENABLED_LABEL;

  async function decide(status: "APPROVED" | "CHANGES_REQUESTED") {
    if (!approval) return;
    toast.error(REMOTE_NOT_ENABLED_LABEL, {
      description: "Comandi remoti APPROVE/REJECT non abilitati in questa fase.",
    });
    void status;
    void device;
  }

  return (
    <AppShell title="Trasporto Monete" subtitle="Sala Conta → documento → PEC (invio non attivo)">
      <div className="space-y-4">
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
              <dt className="text-muted-foreground">Nuove attività</dt>
              <dd className="font-mono">
                {moduleJobs.filter((j: any) => ["QUEUED", "PENDING"].includes(j.status)).length}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Mail Sala Conta</dt>
              <dd className="font-mono">{formatRelative(module?.last_activity_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Allegati acquisiti</dt>
              <dd className="font-mono">{String(meta["allegati"] ?? "—")}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Furgoni riconosciuti</dt>
              <dd className="font-mono">{String(meta["mezzi"] ?? "—")}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-muted-foreground">Itinerario</dt>
              <dd className="truncate font-mono">{province.join(" → ") || "—"}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-muted-foreground">Province</dt>
              <dd className="truncate font-mono">{province.join(" / ") || "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Stato documento</dt>
              <dd className="font-mono">{stepIndex >= 5 ? "PRONTO" : "IN PREPARAZIONE"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Stato PEC</dt>
              <dd className="font-mono text-warning">
                {approval ? "PRONTA PER APPROVAZIONE" : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="hud-panel p-4">
          <p className="hud-title">Workflow</p>
          <ol className="mt-3 flex flex-wrap gap-2">
            {COIN_WORKFLOW.map((step, i) => (
              <li
                key={step}
                className={cn(
                  "rounded-md border px-2 py-1 font-mono text-[0.6rem] tracking-widest",
                  i < stepIndex && "border-success/40 bg-success/10 text-success",
                  i === stepIndex && "border-accent/60 bg-accent/15 text-accent",
                  i > stepIndex && "border-border text-muted-foreground",
                  step === "INVIO" && "opacity-50",
                )}
              >
                {step}
              </li>
            ))}
          </ol>
          <p className="mt-2 text-[0.65rem] text-muted-foreground">
            Il flusso si ferma a <span className="text-warning">PEC PRONTA PER APPROVAZIONE</span>:
            l'invio PEC non è implementato come azione reale.
          </p>
        </div>

        <div className="hud-panel space-y-3 p-4">
          <p className="hud-title">Comandi</p>
          <div className="flex flex-wrap gap-2">
            {current && (
              <Link
                to="/jobs/$id"
                params={{ id: current.id }}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:border-accent/50"
              >
                <Truck className="size-4" /> Apri attività
              </Link>
            )}
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground">
              <FileText className="size-4" /> Apri documento (gestito dall'Agent)
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground">
              <Mail className="size-4" /> Apri PEC (gestita dall'Agent)
            </span>
            <CommandButton
              label="Prepara trasporto monete"
              sensitive
              disabled
              disabledReason={disabledReason}
              onConfirm={async () => {
                toast.error(REMOTE_NOT_ENABLED_LABEL);
              }}
            />
          </div>
        </div>

        {approval && (
          <div className="hud-panel border-warning/40 space-y-3 p-4">
            <p className="hud-title text-warning">PEC pronta per approvazione</p>
            <p className="text-sm">{approval.description}</p>
            <p className="text-xs text-muted-foreground">{REMOTE_NOT_ENABLED_LABEL}</p>
            <div className="flex flex-wrap gap-2">
              <CommandButton
                label="Approva"
                variant="default"
                sensitive
                icon={<Check className="size-4" />}
                disabled
                disabledReason={REMOTE_NOT_ENABLED_LABEL}
                description="Confermi l'approvazione della PEC? L'invio effettivo resta a carico dell'Agent e non è attivo."
                onConfirm={() => decide("APPROVED")}
              />
              <CommandButton
                label="Rifiuta / richiedi modifica"
                variant="destructive"
                sensitive
                icon={<X className="size-4" />}
                disabled
                disabledReason={REMOTE_NOT_ENABLED_LABEL}
                onConfirm={() => decide("CHANGES_REQUESTED")}
              />
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
