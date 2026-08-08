import { createFileRoute } from "@tanstack/react-router";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useRoles } from "@/hooks/useAuth";
import { formatDateTime } from "@/lib/vision";
import { useAuditLogs, useCommands, useProfiles } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/audit")({
  head: () => ({
    meta: [
      { title: "Audit — VIS•ION" },
      { name: "description", content: "Registro delle azioni sensibili e dei comandi inviati." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Audit — VIS•ION" },
      { property: "og:description", content: "Registro audit VIS•ION." },
    ],
  }),
  component: AuditPage,
});

function AuditPage() {
  const { data: logs = [] } = useAuditLogs();
  const { data: commands = [] } = useCommands();
  const { data: profiles = [] } = useProfiles();
  const { isAdmin, isDirezione } = useRoles();

  const nameOf = (id: string | null) =>
    profiles.find((p: any) => p.id === id)?.full_name ??
    profiles.find((p: any) => p.id === id)?.email ??
    "—";

  return (
    <AppShell title="Audit" subtitle="Tracciamento azioni e comandi">
      <div className="space-y-4">
        {!isAdmin && !isDirezione && (
          <p className="hud-panel p-3 text-xs text-muted-foreground">
            Con il tuo ruolo vedi solo le azioni che hai eseguito tu.
          </p>
        )}

        <section className="space-y-2">
          <h2 className="hud-title">Comandi inviati</h2>
          <ul className="space-y-2">
            {commands.map((c: any) => (
              <li key={c.id} className="hud-panel space-y-1 p-3">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                  <p className="truncate font-mono text-sm">{c.command_type}</p>
                  <StatusBadge status={c.status} />
                </div>
                <p className="text-[0.65rem] text-muted-foreground">
                  {nameOf(c.requested_by)} · {formatDateTime(c.requested_at)}
                  {c.executed_at ? ` · eseguito ${formatDateTime(c.executed_at)}` : ""}
                </p>
                {c.error && <p className="text-xs text-destructive">{c.error}</p>}
              </li>
            ))}
            {commands.length === 0 && (
              <li className="hud-panel p-4 text-xs text-muted-foreground">
                Nessun comando registrato.
              </li>
            )}
          </ul>
        </section>

        <section className="space-y-2">
          <h2 className="hud-title">Audit log</h2>
          <ul className="space-y-2">
            {logs.map((l: any) => (
              <li key={l.id} className="hud-panel space-y-1 p-3">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                  <p className="truncate font-mono text-sm">{l.action}</p>
                  <StatusBadge status={l.outcome === "OK" ? "COMPLETED" : "FAILED"} />
                </div>
                <p className="text-[0.65rem] text-muted-foreground">
                  {nameOf(l.user_id)} · {formatDateTime(l.created_at)}
                  {l.ip_address ? ` · IP ${l.ip_address}` : ""}
                </p>
              </li>
            ))}
            {logs.length === 0 && (
              <li className="hud-panel p-4 text-xs text-muted-foreground">
                Nessuna azione registrata.
              </li>
            )}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
