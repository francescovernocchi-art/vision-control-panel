import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { DeviceCard } from "@/components/vision/DeviceCard";
import { CommandButton } from "@/components/vision/CommandButton";
import { EmptyState, ErrorState, LoadingState } from "@/components/vision/UiStates";
import { useRoles } from "@/hooks/useAuth";
import { useCommands, useDevices } from "@/lib/vision-data";
import {
  createGetStatusCommand,
  derivedAgentStatus,
  isCloudConfigured,
  pickLatestGetStatusCommand,
  waitForGetStatusResult,
} from "@/lib/vision-remote-status";
import { VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/dispositivi")({
  head: () => ({
    meta: [
      { title: `Dispositivi — ${VISION_PRODUCT_NAME}` },
      { name: "description", content: "PC e agent VISION registrati, heartbeat e stato." },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: DispositiviPage,
});

function DispositiviPage() {
  const queryClient = useQueryClient();
  const cloud = isCloudConfigured();
  const {
    data: devices = [],
    isLoading,
    isError,
    error,
  } = useDevices();
  const { data: commands = [] } = useCommands();
  const { canOperate } = useRoles();

  return (
    <AppShell title="Dispositivi" subtitle={`${VISION_PRODUCT_NAME} — GET_STATUS only`}>
      <div className="space-y-4">
        {!cloud && (
          <ErrorState
            title="Cloud non configurato"
            description="Nessun dato demo. Configura VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY."
          />
        )}
        {isLoading ? <LoadingState label="Caricamento dispositivi…" /> : null}
        {isError ? (
          <ErrorState
            title="Errore Supabase"
            description={(error as Error)?.message ?? "Lettura devices fallita."}
          />
        ) : null}
        {!isLoading && !isError && devices.length === 0 ? (
          <EmptyState
            title="Nessun dispositivo registrato"
            description="Quando un Agent VISION si registra su Supabase, comparirà qui."
          />
        ) : null}

        <div className="grid gap-3 md:grid-cols-2">
          {devices.map((d: any) => {
            const onlineStatus = derivedAgentStatus(d, null);
            const lastStatus = pickLatestGetStatusCommand(commands, d.id);
            const result =
              lastStatus?.status === "COMPLETED" && lastStatus.result
                ? lastStatus.result
                : null;
            const disabledReason = !canOperate
              ? "Il tuo ruolo non consente l'invio di comandi."
              : onlineStatus === "OFFLINE"
                ? `AGENT OFFLINE — ${d.code} non è raggiungibile.`
                : undefined;

            return (
              <div key={d.id} className="space-y-2">
                <DeviceCard
                  device={d}
                  onlineStatus={onlineStatus}
                  result={result}
                />
                <div className="flex flex-wrap gap-2 px-1">
                  <CommandButton
                    label="Richiedi stato"
                    disabled={!canOperate || onlineStatus === "OFFLINE" || !cloud}
                    disabledReason={disabledReason}
                    onConfirm={async () => {
                      try {
                        const cmd = await createGetStatusCommand(d.code);
                        const wait = await waitForGetStatusResult(cmd.id);
                        void queryClient.invalidateQueries({ queryKey: ["commands"] });
                        void queryClient.invalidateQueries({ queryKey: ["devices"] });
                        if (!wait.ok) toast.error(wait.message);
                        else toast.success("Stato aggiornato", { description: d.code });
                      } catch (e) {
                        toast.error("COMANDO FALLITO", {
                          description: (e as Error).message,
                        });
                      }
                    }}
                  />
                  <Link
                    to="/dispositivi/$code"
                    params={{ code: d.code }}
                    className="inline-flex h-9 items-center rounded-md border border-border px-3 text-xs text-muted-foreground hover:bg-muted/40"
                  >
                    Apri dettaglio
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
