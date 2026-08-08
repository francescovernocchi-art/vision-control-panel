import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2, RefreshCw } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { SupervisorAvatar } from "@/components/vision/SupervisorAvatar";
import { EniSpaceStatusCard, JobSummary } from "@/components/vision/StatusPanels";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  OfflineState,
  SectionCard,
} from "@/components/vision/UiStates";
import { Button } from "@/components/ui/button";
import { useGetStatus } from "@/hooks/useGetStatus";
import { useRoles } from "@/hooks/useAuth";
import { formatRelative, SUPERVISOR_LABEL, type SupervisorState } from "@/lib/vision";
import { isCloudConfigured, type GetStatusResult } from "@/lib/vision-remote-status";
import { statusLabel, VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/attivita")({
  head: () => ({
    meta: [
      { title: `Attività — ${VISION_PRODUCT_NAME}` },
      { name: "description", content: "Attività VISION Core e EniSpace da GET_STATUS." },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: AttivitaPage,
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

function deriveStateFromEni(result: GetStatusResult | null): SupervisorState {
  const eni = result?.enispace_runtime;
  if (eni?.available === false) return "IDLE";
  const st = (eni?.status ?? result?.supervisor_status ?? "").toUpperCase();
  if (st === "PROCESSING") return "PROCESSING";
  if (st === "DEGRADED" || st === "ERROR") return "ERROR";
  if (st === "IDLE" || st === "ONLINE") return "IDLE";
  if (STATES.includes(st as SupervisorState)) return st as SupervisorState;
  if (result?.current_job) return "PROCESSING";
  return "IDLE";
}

function AttivitaPage() {
  const { canOperate } = useRoles();
  const cloud = isCloudConfigured();
  const {
    result,
    refreshing,
    error,
    timeoutMessage,
    lastUpdated,
    refresh,
    partial,
    missingSections,
    agentStatus,
    hasEverSynced,
  } = useGetStatus();

  const state = deriveStateFromEni(result);

  return (
    <AppShell
      title="Attività"
      subtitle={`${VISION_PRODUCT_NAME} · READ ONLY · GET_STATUS only`}
      actions={
        <Button
          size="sm"
          variant="secondary"
          disabled={!canOperate || refreshing || !cloud}
          onClick={() => void refresh()}
        >
          {refreshing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          Aggiorna stato
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={agentStatus} />
          {partial ? <StatusBadge status="PARTIAL" /> : null}
          {!cloud ? (
            <span className="text-xs text-warning">Cloud non configurato — nessun demo.</span>
          ) : null}
        </div>

        {!cloud && (
          <ErrorState
            title="Connessione non configurata"
            description="Imposta le variabili Supabase. Nessun dato simulato."
          />
        )}
        {agentStatus === "OFFLINE" ? <OfflineState /> : null}
        {refreshing ? <LoadingState label="GET_STATUS in corso…" /> : null}
        {(error || timeoutMessage) && (
          <ErrorState title="Errore" description={timeoutMessage || error} />
        )}
        {lastUpdated ? (
          <p className="text-xs text-muted-foreground">
            Ultimo GET_STATUS: {formatRelative(lastUpdated)}
            {missingSections.length > 0
              ? ` · mancanti: ${missingSections.join(", ")}`
              : ""}
          </p>
        ) : null}

        {!hasEverSynced && !result ? (
          <EmptyState
            title="Nessuna attività sincronizzata"
            description="VISION è in attesa di un GET_STATUS reale dall'Agent."
          />
        ) : (
          <>
            <SectionCard title="Sintesi">
              <div className="grid gap-4 sm:grid-cols-[auto_minmax(0,1fr)]">
                <SupervisorAvatar state={state} />
                <div className="min-w-0 space-y-2">
                  <p className="font-mono text-xl font-bold tracking-wide">
                    {SUPERVISOR_LABEL[state] ?? statusLabel(state)}
                  </p>
                  <StatusBadge status={state} />
                  <p className="font-mono text-[0.65rem] text-muted-foreground">
                    supervisor_status: {result?.supervisor_status ?? "—"} · enispace:{" "}
                    {result?.enispace_runtime?.status ?? "—"}
                  </p>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Current activity" subtitle="Job Core e EniSpace separati">
              <div className="grid gap-4 sm:grid-cols-2">
                <JobSummary title="Vision Core job" job={result?.current_job ?? null} />
                <JobSummary
                  title="EniSpace job"
                  job={result?.enispace_runtime?.current_job ?? null}
                />
              </div>
            </SectionCard>

            <SectionCard title="EniSpace runtime">
              <EniSpaceStatusCard
                runtime={result?.enispace_runtime ?? null}
                synced={Boolean(result)}
              />
            </SectionCard>

            <p className="text-xs text-muted-foreground">
              <Link to="/dispositivi" className="text-accent hover:underline">
                Vai ai dispositivi
              </Link>{" "}
              per il dettaglio completo GET_STATUS.
            </p>
          </>
        )}
      </div>
    </AppShell>
  );
}
