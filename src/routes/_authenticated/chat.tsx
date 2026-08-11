import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Power, PowerOff, SendHorizonal } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusDot } from "@/components/vision/StatusBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { supabase } from "@/integrations/supabase/client";
import { useRoles } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { formatRelative, isDeviceOnline } from "@/lib/vision";
import { logAudit, useDevices } from "@/lib/vision-data";
import { VISION_PRODUCT_NAME } from "@/lib/vision-status";

export const Route = createFileRoute("/_authenticated/chat")({
  head: () => ({
    meta: [
      { title: `Chat Supervisor — ${VISION_PRODUCT_NAME}` },
      {
        name: "description",
        content:
          "Chat operativa con l'Agent VIS•ION: messaggi del Supervisor, risposte e comandi di attivazione.",
      },
      { name: "robots", content: "noindex, nofollow" },
    ],
  }),
  component: ChatPage,
});

type AgentMessage = {
  id: string;
  device_id: string;
  direction: "IN" | "OUT";
  level: string;
  title: string | null;
  body: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
};

function useAgentMessages(deviceId: string | null) {
  return useQuery<AgentMessage[]>({
    queryKey: ["agent_messages", deviceId],
    enabled: Boolean(deviceId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("agent_messages")
        .select("*")
        .eq("device_id", deviceId as string)
        .order("created_at", { ascending: true })
        .limit(300);
      if (error) throw error;
      return (data ?? []) as unknown as AgentMessage[];
    },
  });
}

function ChatPage() {
  const queryClient = useQueryClient();
  const { canOperate } = useRoles();
  const { data: devices = [], isLoading: devicesLoading } = useDevices();
  const [selected, setSelected] = useState<string | null>(null);

  const deviceId = selected ?? devices[0]?.device_id ?? null;
  const device = devices.find((d) => d.device_id === deviceId) ?? null;
  const online = device
    ? isDeviceOnline(device.last_seen_at, device.heartbeat_threshold_seconds ?? 120)
    : false;

  const { data: messages = [], isLoading } = useAgentMessages(deviceId);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // Realtime stream of the conversation for the selected agent.
  useEffect(() => {
    if (!deviceId) return;
    const channel = supabase
      .channel(`agent-chat-${deviceId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "agent_messages", filter: `device_id=eq.${deviceId}` },
        () => {
          void queryClient.invalidateQueries({ queryKey: ["agent_messages", deviceId] });
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [deviceId, queryClient]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, deviceId]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [deviceId]);

  const lastQuestion = useMemo(
    () => [...messages].reverse().find((m) => m.direction === "IN"),
    [messages],
  );

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
        payload: lastQuestion ? ({ reply_to: lastQuestion.id } as never) : ({} as never),
      } as never);
      if (error) throw error;
      setDraft("");
      void queryClient.invalidateQueries({ queryKey: ["agent_messages", deviceId] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Invio non riuscito");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  async function runCommand(type: "WAKE_SUPERVISOR" | "DEACTIVATE_SUPERVISOR") {
    if (!deviceId) return;
    const { error } = await supabase.rpc("enqueue_supervisor_command" as never, {
      p_device_id: deviceId,
      p_command_type: type,
    } as never);
    if (error) {
      toast.error(error.message);
      return;
    }
    await logAudit({ action: type, metadata: { device_id: deviceId } });
    toast.success(
      type === "WAKE_SUPERVISOR" ? "Comando di attivazione inviato" : "Comando di disattivazione inviato",
    );
    void queryClient.invalidateQueries({ queryKey: ["commands"] });
  }

  return (
    <AppShell
      title="Chat Supervisor"
      subtitle={`${VISION_PRODUCT_NAME} · canale diretto con l'Agent`}
    >
      <div className="flex h-[calc(100dvh-9rem)] flex-col gap-3">
        {/* Agent selector + comandi */}
        <div className="hud-panel flex flex-wrap items-center gap-2 rounded-xl p-3">
          <div className="flex min-w-0 items-center gap-2">
            <StatusDot status={online ? "ONLINE" : "OFFLINE"} />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{device?.name ?? "Nessun agent"}</p>
              <p className="truncate font-mono text-[0.6rem] tracking-widest text-muted-foreground">
                {deviceId ?? "—"} · {device?.last_seen_at ? formatRelative(device.last_seen_at) : "mai visto"}
              </p>
            </div>
          </div>

          {devices.length > 1 && (
            <select
              value={deviceId ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="ml-auto rounded-md border border-border bg-background px-2 py-1 text-xs"
              aria-label="Seleziona agent"
            >
              {devices.map((d) => (
                <option key={d.device_id} value={d.device_id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}

          <div className="ml-auto flex gap-2">
            <CommandButton
              label="Attiva"
              icon={<Power className="size-4" />}
              variant="default"
              description="Invia WAKE_SUPERVISOR all'Agent selezionato."
              details={[
                { label: "Agent", value: deviceId ?? "—" },
                { label: "Comando", value: "WAKE_SUPERVISOR" },
              ]}
              disabled={!canOperate || !deviceId}
              disabledReason="Serve il ruolo ADMIN o OPERATORE"
              onConfirm={() => runCommand("WAKE_SUPERVISOR")}
            />
            <CommandButton
              label="Disattiva"
              icon={<PowerOff className="size-4" />}
              variant="destructive"
              sensitive
              confirmKeyword="DISATTIVA"
              description="Invia DEACTIVATE_SUPERVISOR all'Agent selezionato."
              details={[
                { label: "Agent", value: deviceId ?? "—" },
                { label: "Comando", value: "DEACTIVATE_SUPERVISOR" },
              ]}
              disabled={!canOperate || !deviceId}
              disabledReason="Serve il ruolo ADMIN o OPERATORE"
              onConfirm={() => runCommand("DEACTIVATE_SUPERVISOR")}
            />
          </div>
        </div>

        {/* Conversazione */}
        <div className="hud-panel flex-1 overflow-y-auto rounded-xl p-3">
          {isLoading || devicesLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
              <p className="text-sm text-muted-foreground">
                Nessun messaggio dal Supervisor.
              </p>
              <p className="text-xs text-muted-foreground">
                Attiva l'Agent o scrivi un messaggio per iniziare.
              </p>
            </div>
          ) : (
            <ul className="space-y-3">
              {messages.map((m) => {
                const mine = m.direction === "OUT";
                return (
                  <li key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                    <div className={cn("max-w-[85%] space-y-1", mine && "text-right")}>
                      <p className="font-mono text-[0.6rem] tracking-widest text-muted-foreground">
                        {mine ? "TU" : "SUPERVISOR"} · {formatRelative(m.created_at)}
                        {!mine && m.level !== "INFO" ? ` · ${m.level}` : ""}
                      </p>
                      <div
                        className={cn(
                          "rounded-xl px-3 py-2 text-sm whitespace-pre-wrap break-words",
                          mine
                            ? "bg-primary text-primary-foreground"
                            : "border border-border bg-card/60 text-foreground",
                        )}
                      >
                        {m.title && <p className="mb-1 font-semibold">{m.title}</p>}
                        {m.body ?? "—"}
                      </div>
                    </div>
                  </li>
                );
              })}
              <div ref={endRef} />
            </ul>
          )}
        </div>

        {/* Composer */}
        <div className="hud-panel rounded-xl p-3">
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
              rows={2}
              placeholder={
                canOperate
                  ? "Rispondi al Supervisor…"
                  : "Solo ADMIN e OPERATORE possono rispondere"
              }
              disabled={!canOperate || !deviceId || sending}
              className="min-h-[52px] resize-none"
            />
            <Button
              size="icon"
              onClick={() => void send()}
              disabled={!canOperate || !deviceId || sending || !draft.trim()}
              aria-label="Invia messaggio"
            >
              {sending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizonal className="size-4" />}
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
