import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { EniSpaceStatusCard, JobSummary } from "@/components/vision/StatusPanels";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  OfflineState,
  SectionCard,
} from "@/components/vision/UiStates";
import { useGetStatus } from "@/hooks/useGetStatus";
import { useRoles } from "@/hooks/useAuth";
import { REMOTE_NOT_ENABLED_LABEL } from "@/lib/vision";
import { isCloudConfigured } from "@/lib/vision-remote-status";
import { VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/moduli/enispace")({
  head: () => ({
    meta: [
      { title: `eniSpace — ${VISION_PRODUCT_NAME}` },
      {
        name: "description",
        content: "Stato EniSpace da GET_STATUS enispace_runtime.",
      },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: EnispacePage,
});

function EnispacePage() {
  const queryClient = useQueryClient();
  const { canOperate } = useRoles();
  const cloud = isCloudConfigured();
  const {
    device,
    result,
    refreshing,
    error,
    timeoutMessage,
    agentStatus,
    hasEverSynced,
    refresh,
  } = useGetStatus();

  const statusDisabledReason = !canOperate
    ? "Il tuo ruolo non consente l'invio di comandi."
    : agentStatus === "OFFLINE"
      ? `Impossibile inviare il comando: ${device?.code ?? "agent"} non è raggiungibile.`
      : !cloud
        ? "Cloud non configurato."
        : undefined;

  const moduleRemote = result?.modules?.find((m) => m.module_id === "enispace");

  return (
    <AppShell
      title="eniSpace Automation"
      subtitle={`${VISION_PRODUCT_NAME} — runtime reale da GET_STATUS`}
    >
      <div className="space-y-4">
        {!cloud && (
          <ErrorState
            title="Cloud non configurato"
            description="Nessun dato demo. Configura Supabase env."
          />
        )}
        {agentStatus === "OFFLINE" ? <OfflineState /> : null}
        {refreshing ? <LoadingState label="Aggiornamento GET_STATUS…" /> : null}
        {timeoutMessage ? (
          <ErrorState title="Timeout GET_STATUS" description={timeoutMessage} />
        ) : null}
        {error ? <ErrorState title="Errore" description={error} /> : null}

        <SectionCard
          title="Stato modulo (GET_STATUS)"
          actions={
            <StatusBadge
              status={moduleRemote?.status ?? moduleRemote?.health ?? "UNKNOWN"}
            />
          }
        >
          {!hasEverSynced && !result ? (
            <EmptyState
              title="Nessun GET_STATUS sincronizzato"
              description="Premi «Stato agent» per caricare lo stato EniSpace reale."
            />
          ) : (
            <p className="text-xs text-muted-foreground">
              {moduleRemote?.display_name ?? "eniSpace"}
              {moduleRemote?.version ? ` · v${moduleRemote.version}` : ""}
            </p>
          )}
        </SectionCard>

        <SectionCard title="EniSpace runtime">
          <EniSpaceStatusCard runtime={result?.enispace_runtime ?? null} synced={Boolean(result)} />
        </SectionCard>

        <SectionCard title="Current activity" subtitle="Job EniSpace distinto dal Vision Core">
          <div className="grid gap-4 sm:grid-cols-2">
            <JobSummary title="Vision Core job" job={result?.current_job ?? null} />
            <JobSummary
              title="EniSpace job"
              job={result?.enispace_runtime?.current_job ?? null}
            />
          </div>
        </SectionCard>

        <SectionCard title="Comandi">
          <p className="mb-3 text-[0.65rem] text-muted-foreground">
            Fase remota status_only — operazioni mail/retry: {REMOTE_NOT_ENABLED_LABEL}.
          </p>
          <div className="flex flex-wrap gap-2">
            <CommandButton
              label="Controlla ora le mail"
              disabled
              disabledReason={REMOTE_NOT_ENABLED_LABEL}
              onConfirm={async () => {
                toast.error(REMOTE_NOT_ENABLED_LABEL);
              }}
            />
            <CommandButton
              label="Riprova ultimo job"
              sensitive
              disabled
              disabledReason={REMOTE_NOT_ENABLED_LABEL}
              onConfirm={async () => {
                toast.error(REMOTE_NOT_ENABLED_LABEL);
              }}
            />
            <CommandButton
              label="Stato agent"
              icon={<RefreshCw className="size-4" />}
              disabled={!!statusDisabledReason || refreshing}
              disabledReason={statusDisabledReason}
              onConfirm={async () => {
                await refresh();
                void queryClient.invalidateQueries({ queryKey: ["commands"] });
                void queryClient.invalidateQueries({ queryKey: ["devices"] });
              }}
            />
          </div>
          <div className="mt-3">
            <Link
              to="/dispositivi/$code"
              params={{ code: device?.code ?? "VIS-TARANTO-01" }}
              className="text-xs text-accent hover:underline"
            >
              Apri dettaglio dispositivo
            </Link>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
