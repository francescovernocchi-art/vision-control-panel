import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, PlusCircle } from "lucide-react";

import { AppShell } from "@/components/vision/AppShell";
import { Button } from "@/components/ui/button";
import { useModules } from "@/lib/vision-data";

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

  return (
    <AppShell title="Moduli" subtitle="Catalogo moduli · stato live solo da GET_STATUS nelle pagine dedicate">
      <div className="grid gap-3 md:grid-cols-2">
        {modules.map((m: any) => {
          const route = ROUTES[m.key];
          return (
            <div key={m.id} className="hud-panel space-y-3 p-4">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{m.name}</p>
                  <p className="text-xs text-muted-foreground">{m.description}</p>
                </div>
                <span className="rounded-md border border-border px-2 py-0.5 font-mono text-[0.65rem] text-muted-foreground">
                  CATALOGO
                </span>
              </div>
              <p className="text-[0.65rem] text-muted-foreground">
                Lo stato operativo live non è derivato da questa riga catalogo. Apri il modulo o il
                dettaglio dispositivo per GET_STATUS.
              </p>
              {route ? (
                <Button asChild size="sm" variant="secondary" className="w-full">
                  <Link to={route}>
                    Apri modulo <ArrowRight className="size-4" aria-hidden />
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
