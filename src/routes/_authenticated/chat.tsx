import { createFileRoute } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Power, PowerOff, SendHorizonal } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
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

function PresenceChip({
  label,
  value,
  online,
}: {
  label: string;
  value: string;
  online: boolean;
}) {
  const tone =
    value === "ONLINE" || value === "ATTIVO"
      ? "border-success/40 bg-success/10 text-success"
      : value === "ELABORAZIONE"
        ? "border-info/40 bg-info/10 text-info"
        : value === "OFFLINE" || value === "INATTIVO"
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-border bg-muted/40 text-muted-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[0.65rem] tracking-wider uppercase",
        tone,
      )}
    >
      <StatusDot
        status={
          online || value === "ATTIVO" || value === "ELABORAZIONE"
            ? "ONLINE"
            : value === "OFFLINE" || value === "INATTIVO"
              ? "OFFLINE"
              : "UNKNOWN"
        }
        pulse={value === "ELABORAZIONE" || value === "ATTIVO" || online}
        className="size-1.5"
      />
      {label} · {value}
    </span>
  );
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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, deviceId]);

  async function send() {
    const body = draft.trim();
    if (!body || !deviceId) return;
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

  async function runCommand(type: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR") {
    if (!deviceId || commandBusy) return;
    setCommandBusy(true);
    try {
      await enqueueSupervisorCommand(deviceId, type);
      await logAudit({ action: type, metadata: { device_id: deviceId } });
      toast.success(
        type === "WAKE_SUPERVISOR"
          ? "Sveglia inviata — attendi i messaggi del Supervisor"
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
        {/* Presence header — one composition */}
        <header className="shrink-0 border-b border-border/60 bg-background/40 px-1 pb-3 pt-1">
          <div className="flex items-center gap-3">
            <SupervisorAvatar
              state={presenceToAvatarState(supervisorPresence)}
              size={72}
              className="rounded-2xl"
            />
            <div className="min-w-0 flex-1 space-y-2">
              <div>
                <p className="truncate text-base font-semibold tracking-tight">
                  {VISION_PRODUCT_NAME} Supervisor
                </p>
                <p className="truncate font-mono text-[0.65rem] tracking-widest text-muted-foreground">
                  {device?.name ?? "Nessun dispositivo"} · {deviceId ?? "—"}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <PresenceChip
                  label="Agent"
                  value={agentOnline ? "ONLINE" : "OFFLINE"}
                  online={agentOnline}
                />
                <PresenceChip
                  label="Supervisor"
                  value={supervisorPresence}
                  online={supervisorPresence === "ATTIVO" || supervisorPresence === "ELABORAZIONE"}
                />
              </div>
            </div>
          </div>

          {devices.length > 1 && (
            <select
              value={deviceId ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="mt-3 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm"
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
                  <li key={String(m.id)} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                    <div className={cn("max-w-[92%] space-y-1", mine && "text-right")}>
                      <p className="font-mono text-[0.6rem] tracking-widest text-muted-foreground">
                        {mine ? "TU" : "VISION"} · {formatRelative(m.created_at)}
                        {!mine && m.level !== "INFO" ? ` · ${m.level}` : ""}
                      </p>
                      <div
                        className={cn(
                          "rounded-2xl px-3.5 py-2.5 text-[0.95rem] leading-snug whitespace-pre-wrap break-words",
                          mine
                            ? "rounded-br-md bg-primary text-primary-foreground"
                            : isAlert
                              ? "rounded-bl-md border border-destructive/40 bg-destructive/10 text-foreground"
                              : "rounded-bl-md border border-border/80 bg-card/70 text-foreground",
                        )}
                      >
                        {m.title && m.title !== m.message && (
                          <p className="mb-1 text-sm font-semibold">{m.title}</p>
                        )}
                        {m.message}
                      </div>
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
          <div className="grid grid-cols-2 gap-2">
            <CommandButton
              label="Sveglia"
              icon={<Power className="size-4" />}
              variant="default"
              size="default"
              className="h-12 w-full text-sm font-semibold"
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
              className="h-12 w-full text-sm font-semibold"
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
            <Textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={1}
              placeholder={
                canOperate ? "Messaggio all'Agent (opzionale)…" : "Solo lettura"
              }
              disabled={!canOperate || !deviceId || sending}
              className="min-h-[48px] max-h-28 flex-1 resize-none rounded-xl text-base"
            />
            <Button
              size="icon"
              className="size-12 shrink-0 rounded-xl"
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
