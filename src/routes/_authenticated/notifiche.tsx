import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { BellOff, CheckCheck } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { supabase } from "@/integrations/supabase/client";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/vision";
import { useModules, useNotifications } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/notifiche")({
  head: () => ({
    meta: [
      { title: "Notifiche — VIS•ION" },
      { name: "description", content: "Notifiche operative del sistema VIS•ION." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Notifiche — VIS•ION" },
      { property: "og:description", content: "Notifiche operative VIS•ION." },
    ],
  }),
  component: NotifichePage,
});

function NotifichePage() {
  const queryClient = useQueryClient();
  const { data: notifications = [] } = useNotifications();
  const { data: modules = [] } = useModules();

  async function markAll() {
    const ids = notifications.filter((n: any) => !n.read_at).map((n: any) => n.id);
    if (ids.length === 0) return;
    const { error } = await supabase
      .from("notifications")
      .update({ read_at: new Date().toISOString() })
      .in("id", ids);
    if (error) {
      toast.error("Aggiornamento non riuscito", { description: error.message });
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <AppShell
      title="Notifiche"
      subtitle={`${notifications.filter((n: any) => !n.read_at).length} non lette`}
      actions={
        <Button variant="ghost" size="sm" onClick={() => void markAll()}>
          <CheckCheck className="size-4" /> Segna lette
        </Button>
      }
    >
      <div className="space-y-3">
        <div className="hud-panel p-3 text-[0.7rem] text-muted-foreground">
          Notifiche push: l'app è pronta lato PWA, ma il push richiede chiavi VAPID e un servizio di
          invio. Vedi Impostazioni → Notifiche push.
        </div>

        <ul className="space-y-2">
          {notifications.map((n: any) => (
            <li
              key={n.id}
              className={cn(
                "hud-panel space-y-1.5 p-3",
                !n.read_at && "border-accent/40",
              )}
            >
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{n.title}</p>
                  <p className="text-xs text-muted-foreground">{n.message}</p>
                </div>
                <StatusBadge status={n.notification_type} />
              </div>
              <div className="flex flex-wrap items-center gap-3 text-[0.65rem] text-muted-foreground">
                <span>{modules.find((m: any) => m.id === n.module_id)?.name ?? "Sistema"}</span>
                <span>{formatDateTime(n.created_at)}</span>
                <span className={n.read_at ? "" : "text-accent"}>
                  {n.read_at ? "letta" : "non letta"}
                </span>
                {n.job_id && (
                  <Link
                    to="/jobs/$id"
                    params={{ id: n.job_id }}
                    className="text-accent hover:underline"
                  >
                    Apri lavorazione →
                  </Link>
                )}
              </div>
            </li>
          ))}
          {notifications.length === 0 && (
            <li className="hud-panel flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <BellOff className="size-4" /> Nessuna notifica.
            </li>
          )}
        </ul>
      </div>
    </AppShell>
  );
}
