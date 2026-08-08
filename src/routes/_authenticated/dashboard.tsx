import { createFileRoute, Link } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { DeviceCard } from "@/components/vision/DeviceCard";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  OfflineState,
  SectionCard,
} from "@/components/vision/UiStates";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useGetStatus } from "@/hooks/useGetStatus";
import { useRoles } from "@/hooks/useAuth";
import { derivedAgentStatus, isCloudConfigured, pickLatestGetStatusCommand } from "@/lib/vision-remote-status";
import { useCommands, useDevices } from "@/lib/vision-data";
import { VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: `Dashboard — ${VISION_PRODUCT_NAME}` },
      {
        name: "description",
        content: "Dashboard operativa VISION — dispositivi, heartbeat e GET_STATUS.",
      },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: `Dashboard — ${VISION_PRODUCT_NAME}` },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const { canOperate } = useRoles();
  const cloud = isCloudConfigured();
  const {
    data: devices = [],
    isLoading: devicesLoading,
    isError: devicesError,
    error: devicesErr,
  } = useDevices();
  const { data: commands = [] } = useCommands();
  const {
    refreshing,
    error,
    timeoutMessage,
    refresh,
    agentStatus,
    cloudConfigured,
  } = useGetStatus();

  const primary = devices[0] ?? null;

  return (
    <AppShell
      title="Dashboard"
      subtitle={`${VISION_PRODUCT_NAME} Control Panel — sola lettura`}
      actions={
        <Button
          size="sm"
          variant="secondary"
          disabled={!canOperate || !cloudConfigured || refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
          Aggiorna stato
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[0.65rem] tracking-widest text-accent">
            REMOTE CONTROL / READ ONLY
          </span>
          <span className="rounded-md border border-border px-2 py-0.5 font-mono text-[0.65rem] text-muted-foreground">
            GET_STATUS only
          </span>
          <StatusBadge status={cloud ? "ONLINE" : "OFFLINE"} />
          {!cloud && (
            <span className="text-xs text-warning">
              Cloud non configurato — nessun dato demo come fallback.
            </span>
          )}
        </div>

        {!cloud && (
          <ErrorState
            title="Connessione non configurata"
            description="Imposta VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY. La dashboard non mostra valori simulati."
          />
        )}

        {timeoutMessage ? (
          <ErrorState title="Timeout GET_STATUS" description={timeoutMessage} />
        ) : null}
        {error ? <ErrorState title="Errore di connessione" description={error} /> : null}

        {agentStatus === "OFFLINE" && primary ? (
          <OfflineState title="Agent offline / non raggiungibile" />
        ) : null}

        <SectionCard
          title="Dispositivi"
          subtitle="Stato da heartbeat devices + ultimo GET_STATUS (se presente)"
        >
          {devicesLoading ? <LoadingState label="Caricamento dispositivi…" /> : null}
          {devicesError ? (
            <ErrorState
              title="Errore Supabase"
              description={(devicesErr as Error)?.message ?? "Impossibile leggere devices."}
            />
          ) : null}
          {!devicesLoading && !devicesError && devices.length === 0 ? (
            <EmptyState
              title="Nessun dispositivo"
              description="Nessun PC / Agent VISION registrato per questo account."
            />
          ) : null}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {devices.map((d: any) => {
              const onlineStatus = derivedAgentStatus(d, null);
              const cmd = pickLatestGetStatusCommand(commands, d.id);
              const result =
                cmd?.status === "COMPLETED" && cmd.result && typeof cmd.result === "object"
                  ? cmd.result
                  : null;
              return (
                <DeviceCard
                  key={d.id}
                  device={d}
                  onlineStatus={onlineStatus}
                  result={result}
                />
              );
            })}
          </div>
        </SectionCard>

        <p className="text-[0.7rem] text-muted-foreground">
          I dettagli operativi (Vision Core, EniSpace, moduli, warning) sono nella vista dispositivo.
          Comandi remoti operativi non abilitati in questa fase.
        </p>
      </div>
    </AppShell>
  );
}
