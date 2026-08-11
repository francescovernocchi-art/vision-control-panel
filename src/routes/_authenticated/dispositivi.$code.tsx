import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Moon, RefreshCw, Sun } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge, StatusDot } from "@/components/vision/StatusBadge";
import {
  EniSpaceStatusCard,
  JobSummary,
  WarningList,
} from "@/components/vision/StatusPanels";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  OfflineState,
  SectionCard,
} from "@/components/vision/UiStates";
import { Button } from "@/components/ui/button";
import { useRoles } from "@/hooks/useAuth";
import { formatDateTime, formatRelative } from "@/lib/vision";
import { useAgentMessages, useCommands, useDevices } from "@/lib/vision-data";
import {
  createGetStatusCommand,
  derivedAgentStatus,
  enqueueSupervisorCommand,
  isCloudConfigured,
  pickLatestGetStatusCommand,
  waitForGetStatusResult,
  type GetStatusResult,
} from "@/lib/vision-remote-status";
import {
  displayValue,
  productNameFromResult,
  VISION_PRODUCT_NAME,
} from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/dispositivi/$code")({
  head: ({ params }) => ({
    meta: [
      { title: `${params.code} — ${VISION_PRODUCT_NAME}` },
      { name: "description", content: "Dettaglio stato dispositivo VISION via GET_STATUS." },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: DeviceDetailPage,
});

function DeviceDetailPage() {
  const { code } = Route.useParams();
  const { canOperate } = useRoles();
  const cloud = isCloudConfigured();
  const { data: devices = [], isLoading: devicesLoading } = useDevices();
  const { data: commands = [], refetch: refetchCommands } = useCommands();
  const logicalDeviceId = useMemo(() => {
    const d = devices.find((row: { code?: string; device_id?: string }) => row.code === code);
    return String(d?.device_id || d?.code || code);
  }, [devices, code]);
  const { data: agentMessages = [], isLoading: messagesLoading } = useAgentMessages(
    logicalDeviceId,
  );

  const device = useMemo(
    () => devices.find((d: any) => d.code === code) ?? null,
    [devices, code],
  );

  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [timeoutMessage, setTimeoutMessage] = useState("");
  const [liveResult, setLiveResult] = useState<GetStatusResult | null>(null);
  const autoDoneFor = useRef<string | null>(null);
  const liveResultRef = useRef<GetStatusResult | null>(null);
  liveResultRef.current = liveResult;

  const cachedCmd = device ? pickLatestGetStatusCommand(commands, device.id) : null;
  const cachedResult =
    cachedCmd?.status === "COMPLETED" && cachedCmd.result ? cachedCmd.result : null;
  const result = liveResult ?? cachedResult;
  const onlineStatus = derivedAgentStatus(device, result);
  const product = productNameFromResult(result?.vision_core);

  useEffect(() => {
    // Auto GET_STATUS once per device open. Avoid dependency loops; tolerate StrictMode remount.
    if (!cloud || !device?.code || !canOperate) return;
    if (onlineStatus === "OFFLINE" || onlineStatus === "DISABLED") return;
    if (autoDoneFor.current === device.code && liveResultRef.current) return;

    let cancelled = false;
    const codeAtStart = device.code;

    (async () => {
      setRefreshing(true);
      setError("");
      setTimeoutMessage("");
      try {
        const cmd = await createGetStatusCommand(codeAtStart);
        const wait = await waitForGetStatusResult(cmd.id);
        if (cancelled) return;
        if (!wait.ok && wait.reason === "timeout") {
          setTimeoutMessage(wait.message);
        } else if (!wait.ok) {
          setError(wait.message);
        } else {
          setLiveResult(wait.result);
          autoDoneFor.current = codeAtStart;
        }
        void refetchCommands();
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire when device identity is known; not on every status tick
  }, [cloud, canOperate, device?.code]);

  async function manualRefresh() {
    if (!device) return;
    setRefreshing(true);
    setError("");
    setTimeoutMessage("");
    try {
      const cmd = await createGetStatusCommand(device.code);
      const wait = await waitForGetStatusResult(cmd.id);
      if (!wait.ok && wait.reason === "timeout") setTimeoutMessage(wait.message);
      else if (!wait.ok) setError(wait.message);
      else setLiveResult(wait.result);
      void refetchCommands();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  async function sendThinCommand(type: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR") {
    if (!device) return;
    const label = type === "WAKE_SUPERVISOR" ? "Sveglia" : "Disattiva";
    try {
      await enqueueSupervisorCommand(device.device_id || device.code, type);
      toast.success(`${label} inviata all'Agent`, {
        description: `Comando ${type} in coda per ${device.code}`,
      });
    } catch (e) {
      toast.error(`Invio ${label} fallito`, {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return (
    <AppShell
      title={device?.code ?? code}
      subtitle={`${product} · Agent ↔ PWA · canale sottile`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild size="sm" variant="ghost">
            <Link to="/dispositivi">
              <ArrowLeft className="size-4" aria-hidden /> Elenco
            </Link>
          </Button>
          <CommandButton
            label="Sveglia"
            icon={<Sun className="size-4" aria-hidden />}
            description="Invia WAKE_SUPERVISOR all'Agent desktop. Il Supervisor locale verrà avviato."
            sensitive
            confirmLabel="Sveglia Supervisor"
            disabled={!canOperate || !cloud || !device || onlineStatus === "OFFLINE"}
            disabledReason={
              onlineStatus === "OFFLINE"
                ? "Agent offline — impossibile svegliare il Supervisor."
                : undefined
            }
            onConfirm={() => sendThinCommand("WAKE_SUPERVISOR")}
          />
          <CommandButton
            label="Disattiva"
            icon={<Moon className="size-4" aria-hidden />}
            variant="destructive"
            description="Invia DEACTIVATE_SUPERVISOR all'Agent. Il Supervisor locale verrà arrestato."
            sensitive
            confirmKeyword="DISATTIVA"
            confirmLabel="Disattiva Supervisor"
            disabled={!canOperate || !cloud || !device || onlineStatus === "OFFLINE"}
            disabledReason={
              onlineStatus === "OFFLINE"
                ? "Agent offline — impossibile disattivare da remoto."
                : undefined
            }
            onConfirm={() => sendThinCommand("DEACTIVATE_SUPERVISOR")}
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={!canOperate || !cloud || !device || refreshing || onlineStatus === "OFFLINE"}
            aria-label="Aggiorna stato dispositivo via GET_STATUS"
            onClick={() => void manualRefresh()}
          >
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
            Aggiorna stato
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {!cloud && (
          <ErrorState
            title="Cloud non configurato"
            description="Nessun dato demo. Configura le variabili Supabase."
          />
        )}
        {devicesLoading ? <LoadingState label="Caricamento dispositivo…" /> : null}
        {!devicesLoading && !device ? (
          <EmptyState
            title="Dispositivo non trovato"
            description={`Nessun device con codice ${code} visibile per questo account.`}
          />
        ) : null}

        {device && (
          <>
            <SectionCard title="Device overview">
              <div className="flex flex-wrap items-center gap-2">
                <StatusDot status={onlineStatus} />
                <StatusBadge status={onlineStatus} />
                {result?.partial ? <StatusBadge status="PARTIAL" /> : null}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">Nome</dt>
                  <dd className="font-mono">{displayValue(device.name)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Ultimo contatto</dt>
                  <dd className="font-mono">{formatDateTime(device.last_seen_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Scarto</dt>
                  <dd className="font-mono">{formatRelative(device.last_seen_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Hostname</dt>
                  <dd className="font-mono">{displayValue(device.hostname)}</dd>
                </div>
              </dl>
            </SectionCard>

            <SectionCard
              title="Messaggi Agent"
              subtitle="Feed thin channel (agent_messages)"
            >
              {messagesLoading ? <LoadingState label="Caricamento messaggi…" /> : null}
              {!messagesLoading && agentMessages.length === 0 ? (
                <EmptyState
                  title="Nessun messaggio"
                  description="Dopo Sveglia / Disattiva / GET_STATUS l'Agent pubblica qui lo stato."
                />
              ) : (
                <ul className="max-h-64 space-y-2 overflow-y-auto text-xs">
                  {agentMessages.map((m) => (
                    <li
                      key={String(m.id)}
                      className="rounded-lg border border-border/70 bg-background/30 px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-[0.65rem] uppercase text-muted-foreground">
                          {m.level} · {m.source}
                        </span>
                        <span className="font-mono text-[0.65rem] text-muted-foreground">
                          {formatRelative(m.created_at)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm">{m.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>

            {onlineStatus === "OFFLINE" ? <OfflineState /> : null}
            {refreshing ? <LoadingState label="Richiesta GET_STATUS in corso…" /> : null}
            {timeoutMessage ? (
              <ErrorState title="Timeout GET_STATUS" description={timeoutMessage} />
            ) : null}
            {error ? <ErrorState title="Errore GET_STATUS" description={error} /> : null}

            {!result && !refreshing ? (
              <EmptyState
                title="Nessun GET_STATUS disponibile"
                description="Premi «Aggiorna stato» quando l'Agent è online."
              />
            ) : null}

            {result ? (
              <>
                {result.partial && (result.missing_sections?.length ?? 0) > 0 ? (
                  <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                    Stato parziale — sezioni mancanti: {result.missing_sections?.join(", ")}
                  </p>
                ) : null}

                <SectionCard title="VISION Core" subtitle={product}>
                  <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
                    <div>
                      <dt className="text-muted-foreground">Overall health</dt>
                      <dd>
                        <StatusBadge status={result.overall_health ?? "UNKNOWN"} />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Core</dt>
                      <dd>
                        <StatusBadge status={result.core_status ?? "UNKNOWN"} />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Supervisor</dt>
                      <dd>
                        <StatusBadge status={result.supervisor_status ?? "UNKNOWN"} />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Queue size</dt>
                      <dd className="font-mono text-lg font-semibold">
                        {result.queue_size != null && Number.isFinite(Number(result.queue_size))
                          ? Number(result.queue_size)
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Avvio Core</dt>
                      <dd className="font-mono">
                        {displayValue(result.vision_core?.started_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Versioni</dt>
                      <dd className="font-mono text-[0.65rem]">
                        vision {displayValue(result.vision_version)} · agent{" "}
                        {displayValue(result.agent_version)} · platform{" "}
                        {displayValue(result.platform_version)}
                      </dd>
                    </div>
                  </dl>
                </SectionCard>

                <SectionCard title="Current activity" subtitle="Job Core e EniSpace restano separati">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <JobSummary
                      title="Vision Core — current job"
                      job={result.current_job}
                      emptyLabel="Nessun job Vision Core attivo"
                    />
                    <JobSummary
                      title="EniSpace — current job"
                      job={result.enispace_runtime?.current_job}
                      emptyLabel="Nessun job EniSpace attivo"
                    />
                  </div>
                </SectionCard>

                <SectionCard title="EniSpace">
                  <EniSpaceStatusCard
                    runtime={result.enispace_runtime ?? null}
                    synced={true}
                  />
                </SectionCard>

                <SectionCard title="Modules">
                  {!result.modules?.length ? (
                    <EmptyState title="Nessun modulo" description="GET_STATUS non ha restituito moduli." />
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {result.modules.map((m: NonNullable<GetStatusResult["modules"]>[number]) => (
                        <div
                          key={m.module_id}
                          className="rounded-lg border border-border/70 bg-background/30 p-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-sm font-medium">
                              {m.display_name ?? m.module_id}
                            </p>
                            <StatusBadge status={m.status ?? m.health ?? "UNKNOWN"} />
                          </div>
                          <p className="mt-1 font-mono text-[0.65rem] text-muted-foreground">
                            {m.module_id}
                            {m.version ? ` · v${m.version}` : ""}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title="Services">
                  {!result.services?.length ? (
                    <EmptyState title="Nessun service" />
                  ) : (
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                      {result.services.map((s: NonNullable<GetStatusResult["services"]>[number]) => (
                        <div
                          key={s.service_id}
                          className="rounded-lg border border-border/70 p-2"
                        >
                          <p className="truncate font-mono text-[0.65rem] text-muted-foreground">
                            {s.service_id}
                          </p>
                          <StatusBadge
                            status={
                              s.available === false ? "OFFLINE" : s.health || "ONLINE"
                            }
                            className="mt-1"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title="Warnings">
                  <WarningList warnings={result.warnings} />
                </SectionCard>

                <SectionCard title="System info">
                  <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
                    <div>
                      <dt className="text-muted-foreground">Product</dt>
                      <dd className="font-mono">{product}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">API / contract</dt>
                      <dd className="font-mono">
                        {displayValue(result.api_version)} /{" "}
                        {displayValue(result.contract_version)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Timestamp status</dt>
                      <dd className="font-mono">{displayValue(result.timestamp)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Remote control</dt>
                      <dd className="font-mono">
                        {result.remote_control_enabled ? "enabled" : "disabled"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Agent mode</dt>
                      <dd className="font-mono">
                        {displayValue(result.agent?.remote_mode)}
                      </dd>
                    </div>
                  </dl>
                </SectionCard>
              </>
            ) : null}
          </>
        )}
      </div>
    </AppShell>
  );
}
