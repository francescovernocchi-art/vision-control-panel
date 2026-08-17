import { createFileRoute } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Power, PowerOff, SendHorizonal, SlashSquare } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { ChatCommandPalette } from "@/components/vision/ChatCommandPalette";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusDot } from "@/components/vision/StatusBadge";
import { SupervisorAvatar } from "@/components/vision/SupervisorAvatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { supabase } from "@/integrations/supabase/client";
import { useRoles } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import {
  formatRelative,
  isDeviceOnline,
  type SupervisorState,
} from "@/lib/vision";
import {
  logAudit,
  useAgentMessages,
  useDevices,
  type AgentMessageRow,
} from "@/lib/vision-data";
import {
  isHelpCommand,
  type ChatCommand,
} from "@/lib/vision-chat-commands";
import { enqueueSupervisorCommand } from "@/lib/vision-remote-status";
import { VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/chat")({
  head: () => ({
    meta: [
      { title: `Chat — ${VISION_PRODUCT_NAME}` },
      {
        name: "description",
        content:
          "Chat mobile con VISION Supervisor: messaggi Agent, Sveglia e Disattiva.",
      },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: ChatPage,
});

type SupervisorPresence = "ATTIVO" | "INATTIVO" | "ELABORAZIONE" | "SCONOSCIUTO";

function inferSupervisorPresence(messages: AgentMessageRow[]): SupervisorPresence {
  for (const m of messages) {
    const text = `${m.title ?? ""} ${m.message}`.toLowerCase();
    if (
      text.includes("disattivato") ||
      text.includes("deactivate") ||
      text.includes("supervisor off")
    ) {
      return "INATTIVO";
    }
    if (
      text.includes("analisi") ||
      text.includes("attivazione modulo") ||
      text.includes("posta elettronica") ||
      text.includes("processing") ||
      text.includes("esecuzione:")
    ) {
      return "ELABORAZIONE";
    }
    if (
      text.includes("attivato") ||
      text.includes("risveglio") ||
      text.includes("wake") ||
      text.includes("sveglia")
    ) {
      return "ATTIVO";
    }
  }
  return "SCONOSCIUTO";
}

function presenceToAvatarState(presence: SupervisorPresence): SupervisorState {
  if (presence === "ELABORAZIONE") return "PROCESSING";
  if (presence === "ATTIVO") return "IDLE";
  if (presence === "INATTIVO") return "IDLE";
  return "IDLE";
}

function StatusBar({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div
      className={cn(
        "hud-clip flex items-center justify-between gap-2 px-3 py-2",
        ok ? "hud-frame text-success" : "hud-frame-danger text-destructive",
      )}
    >
      <span className="flex min-w-0 items-center gap-2 font-mono text-[0.65rem] tracking-[0.18em] uppercase">
        <StatusDot status={ok ? "ONLINE" : "OFFLINE"} pulse={ok} className="size-2 shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      <span className="shrink-0 font-mono text-[0.65rem] font-bold tracking-[0.18em] uppercase">
        {value}
      </span>
    </div>
  );
}

/** Metrica del pannello STATO SISTEMA (solo presentazione). */
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-2 first:pl-0 last:pr-0">
      <p className="truncate font-mono text-[0.55rem] tracking-[0.18em] text-muted-foreground uppercase">
        {label}
      </p>
      <p className="truncate font-mono text-lg font-bold text-accent text-glow">{value}</p>
      <div className="mt-1 h-3 w-full bg-gradient-to-t from-accent/25 to-transparent" />
    </div>
  );
}

function pct(raw: unknown): string {
  const n = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(n) ? `${Math.round(n)}%` : "—";
}



function ChatPage() {
  const queryClient = useQueryClient();
  const { canOperate } = useRoles();
  const { data: devices = [], isLoading: devicesLoading } = useDevices();
  const [selected, setSelected] = useState<string | null>(null);

  const deviceId = selected ?? devices[0]?.device_id ?? null;
  const device = devices.find((d) => d.device_id === deviceId) ?? null;
  const agentOnline = device
    ? isDeviceOnline(device.last_seen_at, device.heartbeat_threshold_seconds ?? 120)
    : false;
  const metrics = (device?.metadata ?? {}) as Record<string, unknown>;



  const { data: rawMessages = [], isLoading } = useAgentMessages(deviceId, 120);
  const messages = useMemo(
    () => [...rawMessages].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [rawMessages],
  );
  const supervisorPresence = useMemo(
    () => inferSupervisorPresence([...messages].reverse()),
    [messages],
  );

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [commandBusy, setCommandBusy] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const slashQuery = draft.trimStart().startsWith("/") ? draft.trim() : "";
  const showPalette = paletteOpen || slashQuery.length > 0;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, deviceId]);

  async function send() {
    const body = draft.trim();
    if (!body || !deviceId) return;
    if (isHelpCommand(body)) {
      setDraft("");
      setPaletteOpen(true);
      inputRef.current?.focus();
      return;
    }
    setSending(true);
    try {
      const { data: userData } = await supabase.auth.getUser();
      if (!userData.user) throw new Error("Sessione scaduta. Effettua di nuovo il login.");
      const { error } = await supabase.from("agent_messages").insert({
        device_id: deviceId,
        direction: "OUT",
        message_type: "OPERATOR",
        level: "INFO",
        body,
        author_id: userData.user.id,
        payload: {} as never,
      } as never);
      if (error) throw error;
      setDraft("");
      void queryClient.invalidateQueries({ queryKey: ["agent_messages"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Invio non riuscito");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  /** Selezione dal pannello /comandi. */
  function pickCommand(command: ChatCommand) {
    if (command.kind === "phrase") {
      setDraft(command.template ?? "");
      setPaletteOpen(false);
      inputRef.current?.focus();
      return;
    }
    if (command.commandType === "DEACTIVATE_SUPERVISOR") {
      setDraft("");
      setPaletteOpen(false);
      toast.info("Usa il pulsante Disattiva: richiede conferma esplicita.");
      return;
    }
    setDraft("");
    setPaletteOpen(false);
    if (command.commandType) void runCommand(command.commandType);
  }

  async function runCommand(
    type: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR" | "GET_STATUS",
  ) {
    if (!deviceId || commandBusy) return;
    setCommandBusy(true);
    try {
      await enqueueSupervisorCommand(deviceId, type);
      await logAudit({ action: type, metadata: { device_id: deviceId } });
      toast.success(
        type === "WAKE_SUPERVISOR"
          ? "Sveglia inviata — attendi i messaggi del Supervisor"
          : type === "GET_STATUS"
            ? "Richiesta stato inviata all'Agent"
            : "Disattiva inviata — attendi conferma Agent",
      );
      void queryClient.invalidateQueries({ queryKey: ["commands"] });
      void queryClient.invalidateQueries({ queryKey: ["agent_messages"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Comando non inviato");
    } finally {
      setCommandBusy(false);
    }
  }


  return (
    <AppShell
      title="VISION"
      subtitle="Chat con Supervisor"
      immersive
    >
      <div className="flex h-[calc(100dvh-7.5rem)] flex-col lg:h-[calc(100dvh-5.5rem)]">
        {/* Presence header — HUD control room */}
        <header className="shrink-0 px-1 pt-1 pb-3">
          <div className="grid grid-cols-[minmax(0,42%)_minmax(0,1fr)] items-stretch gap-2.5">
            <div className="hud-frame hud-clip relative overflow-hidden p-1.5">
              <SupervisorAvatar
                state={presenceToAvatarState(supervisorPresence)}
                size={0}
                className="hud-clip !size-full aspect-[3/4] rounded-none ring-0 ring-offset-0"
              />
              <div className="pointer-events-none absolute inset-1.5 bg-[radial-gradient(circle_at_50%_38%,transparent_45%,oklch(0.17_0.035_254/70%)_100%)]" />
            </div>

            <div className="flex min-w-0 flex-col gap-2">
              <div className="min-w-0">
                <p className="truncate text-base font-bold tracking-[0.08em] text-glow uppercase sm:text-lg">
                  {VISION_PRODUCT_NAME} Supervisor
                </p>
                <p className="truncate text-xs tracking-wide text-foreground/80 uppercase">
                  {device?.name ?? "Nessun dispositivo"}
                </p>
                <p className="truncate font-mono text-[0.62rem] tracking-[0.18em] text-muted-foreground">
                  {deviceId ?? "—"}
                </p>
              </div>
              <StatusBar label="Agent" value={agentOnline ? "ONLINE" : "OFFLINE"} ok={agentOnline} />
              <StatusBar
                label="Supervisor"
                value={supervisorPresence}
                ok={supervisorPresence === "ATTIVO" || supervisorPresence === "ELABORAZIONE"}
              />

              <div className="hud-frame hud-clip mt-auto px-3 py-2">
                <p className="font-mono text-[0.55rem] tracking-[0.22em] text-muted-foreground uppercase">
                  Stato sistema
                </p>
                <div className="mt-1.5 grid grid-cols-3 divide-x divide-border/60">
                  <Metric label="CPU" value={pct(metrics["cpu"])} />
                  <Metric label="Memory" value={pct(metrics["memory"])} />
                  <Metric label="Network" value={pct(metrics["network"])} />
                </div>
              </div>
            </div>
          </div>

          {devices.length > 1 && (
            <select
              value={deviceId ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="hud-frame hud-clip mt-2.5 w-full px-3 py-2.5 text-sm"
              aria-label="Seleziona dispositivo"
            >
              {devices.map((d) => (
                <option key={d.device_id} value={d.device_id}>
                  {d.name} ({d.device_id})
                </option>
              ))}
            </select>
          )}
        </header>


        {/* Message feed */}
        <div ref={feedRef} className="min-h-0 flex-1 overflow-y-auto px-1 py-3">
          {isLoading || devicesLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <p className="text-sm font-medium">Nessun messaggio ancora</p>
              <p className="max-w-xs text-xs text-muted-foreground">
                Tocca <span className="text-accent">Sveglia</span> per attivare il Supervisor.
                Progressi e risposte Agent appariranno qui.
              </p>
            </div>
          ) : (
            <ul className="space-y-3">
              {messages.map((m) => {
                const mine = m.direction === "OUT";
                const isAlert = ["ERROR", "WARN", "WARNING", "CRITICAL"].includes(m.level);
                return (
                  <li
                    key={String(m.id)}
                    className="relative grid grid-cols-[3.25rem_minmax(0,1fr)] items-start gap-2"
                  >
                    <div className="relative flex flex-col items-center pt-1">
                      <span
                        className={cn(
                          "grid size-8 shrink-0 place-items-center rounded-full border-2",
                          mine
                            ? "border-primary/70 bg-primary/15 text-primary"
                            : isAlert
                              ? "border-destructive/70 bg-destructive/15 text-destructive"
                              : "border-accent/70 bg-accent/10 text-accent glow-accent",
                        )}
                      >
                        <span className="size-2.5 rounded-full bg-current" />
                      </span>
                      <span className="absolute top-10 bottom-[-0.75rem] w-px bg-accent/25" />
                      <span className="mt-1.5 font-mono text-[0.52rem] tracking-[0.18em] text-accent/80 uppercase">
                        {mine ? "TU" : "VISION"}
                      </span>
                      <span className="text-[0.55rem] text-muted-foreground">
                        {formatRelative(m.created_at)}
                      </span>
                    </div>
                    <div
                      className={cn(
                        "hud-clip px-4 py-3 text-[0.95rem] leading-snug break-words whitespace-pre-wrap",
                        mine
                          ? "border border-primary/55 bg-primary/12 text-foreground"
                          : isAlert
                            ? "hud-frame-danger text-foreground"
                            : "hud-frame text-foreground",
                      )}
                    >
                      {m.title && m.title !== m.message && (
                        <p className="mb-1 text-sm font-semibold text-accent">{m.title}</p>
                      )}
                      {m.message}
                    </div>
                  </li>

                );
              })}
              <div ref={endRef} />
            </ul>
          )}
        </div>


        {/* Sticky actions + composer — thumb zone */}
        <footer className="shrink-0 space-y-2 border-t border-border/60 bg-background/95 pb-[env(safe-area-inset-bottom)] pt-2 backdrop-blur">
          {showPalette && (
            <ChatCommandPalette
              query={slashQuery}
              canOperate={canOperate && !!deviceId && !commandBusy}
              onPick={pickCommand}
              onClose={() => {
                setPaletteOpen(false);
                if (slashQuery) setDraft("");
              }}
            />
          )}

          <div className="grid grid-cols-2 gap-2">

            <CommandButton
              label="Sveglia"
              icon={<Power className="size-4" />}
              variant="default"
              size="default"
              className="hud-clip h-14 w-full border border-accent/60 bg-accent/10 text-sm font-bold tracking-[0.18em] text-accent uppercase hover:bg-accent/20"
              description="Invia WAKE_SUPERVISOR all'Agent desktop. Il Supervisor locale verrà avviato e pubblicherà i progressi in chat."
              details={[
                { label: "Dispositivo", value: deviceId ?? "—" },
                { label: "Comando", value: "WAKE_SUPERVISOR" },
              ]}
              confirmLabel="Sveglia Supervisor"
              disabled={!canOperate || !deviceId || !agentOnline || commandBusy}
              disabledReason={
                !agentOnline
                  ? "Agent offline — impossibile svegliare"
                  : "Serve il ruolo ADMIN o OPERATORE"
              }
              onConfirm={() => runCommand("WAKE_SUPERVISOR")}
            />
            <CommandButton
              label="Disattiva"
              icon={<PowerOff className="size-4" />}
              variant="destructive"
              size="default"
              className="hud-clip h-14 w-full text-sm font-bold tracking-[0.18em] uppercase"
              sensitive
              confirmKeyword="DISATTIVA"
              description="Invia DEACTIVATE_SUPERVISOR. Il Supervisor locale verrà arrestato."
              details={[
                { label: "Dispositivo", value: deviceId ?? "—" },
                { label: "Comando", value: "DEACTIVATE_SUPERVISOR" },
              ]}
              confirmLabel="Disattiva Supervisor"
              disabled={!canOperate || !deviceId || commandBusy}
              disabledReason="Serve il ruolo ADMIN o OPERATORE"
              onConfirm={() => runCommand("DEACTIVATE_SUPERVISOR")}
            />
          </div>

          <div className="flex items-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="hud-frame hud-clip size-12 shrink-0 rounded-none text-accent hover:bg-accent/15"
              onClick={() => {
                setPaletteOpen((v) => !v);
                inputRef.current?.focus();
              }}
              aria-label="Lista comandi"
              aria-expanded={showPalette}
            >
              <SlashSquare className="size-5" />
            </Button>
            <Textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setPaletteOpen(false);
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={1}
              placeholder={
                canOperate ? "Messaggio o /comandi…" : "Solo lettura"
              }

              disabled={!canOperate || !deviceId || sending}
              className="hud-frame hud-clip max-h-28 min-h-[48px] flex-1 resize-none rounded-none border-accent/45 text-base placeholder:text-muted-foreground/70"
            />
            <Button
              size="icon"
              className="hud-clip size-12 shrink-0 rounded-none border border-accent/60 bg-accent/15 text-accent hover:bg-accent/25"
              onClick={() => void send()}
              disabled={!canOperate || !deviceId || sending || !draft.trim()}
              aria-label="Invia messaggio"
            >
              {sending ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <SendHorizonal className="size-5" />
              )}
            </Button>
          </div>
        </footer>
      </div>
    </AppShell>
  );
}
