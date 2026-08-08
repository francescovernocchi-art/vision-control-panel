import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, PlusCircle } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/vision";
import { useJobs, useModules } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/moduli/")({
  head: () => ({
    meta: [
      { title: "Moduli — VIS•ION" },
      { name: "description", content: "Moduli operativi disponibili sul VIS•ION Core." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Moduli — VIS•ION" },
      { property: "og:description", content: "Moduli operativi VIS•ION." },
    ],
  }),
  component: ModuliPage,
});

const ROUTES: Record<string, "/moduli/enispace" | "/moduli/trasporto-monete"> = {
  enispace: "/moduli/enispace",
  coin_transport: "/moduli/trasporto-monete",
};

const FUTURI = [
  "VIS Protocollo",
  "HR",
  "Contestazioni ed Elogi",
  "EasyPlan",
  "Trasporto Valori",
  "Gare / Manodopera",
];

function ModuliPage() {
  const { data: modules = [] } = useModules();
  const { data: jobs = [] } = useJobs();

  return (
    <AppShell title="Moduli" subtitle="Moduli operativi registrati sul Core">
      <div className="grid gap-3 md:grid-cols-2">
        {modules.map((m: any) => {
          const current = jobs.find((j: any) => j.id === m.current_job_id);
          const route = ROUTES[m.key];
          return (
            <div key={m.id} className="hud-panel space-y-3 p-4">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.description}</p>
                </div>
                <StatusBadge status={m.status} />
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Ultima attività</dt>
                  <dd className="font-mono">{formatRelative(m.last_activity_at)}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-muted-foreground">Job corrente</dt>
                  <dd className="truncate font-mono">{current?.code ?? "—"}</dd>
                </div>
              </dl>
              {route ? (
                <Button asChild size="sm" variant="secondary" className="w-full">
                  <Link to={route}>
                    Apri modulo <ArrowRight className="size-4" />
                  </Link>
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Nessuna interfaccia dedicata: il modulo è gestito dal Core.
                </p>
              )}
            </div>
          );
        })}

        <div className="hud-panel space-y-2 border-dashed p-4">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <PlusCircle className="size-4 text-accent" /> Moduli futuri
          </p>
          <p className="text-xs text-muted-foreground">
            L'architettura consente di aggiungere nuovi moduli senza rifare la dashboard: basta
            inserire una riga nella tabella <span className="font-mono">modules</span>.
          </p>
          <ul className="flex flex-wrap gap-2">
            {FUTURI.map((f) => (
              <li
                key={f}
                className="rounded-md border border-border px-2 py-0.5 text-[0.65rem] text-muted-foreground"
              >
                {f}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </AppShell>
  );
}
