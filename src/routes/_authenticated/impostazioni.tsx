import { createFileRoute } from "@tanstack/react-router";
import { Download, Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useRoles } from "@/hooks/useAuth";
import { usePwaInstall } from "@/hooks/usePwaInstall";
import { COMMAND_WHITELIST } from "@/lib/vision";
import { useProfiles, useUserRoles } from "@/lib/vision-data";
import { saveAdminEmail, useBootstrap, useInvalidateBootstrap } from "@/lib/vision-bootstrap";

export const Route = createFileRoute("/_authenticated/impostazioni")({
  head: () => ({
    meta: [
      { title: "Impostazioni — VIS•ION" },
      { name: "description", content: "Installazione PWA, notifiche push, utenti e comandi." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Impostazioni — VIS•ION" },
      { property: "og:description", content: "Impostazioni VIS•ION." },
    ],
  }),
  component: ImpostazioniPage,
});

function ImpostazioniPage() {
  const { canInstall, installed, install } = usePwaInstall();
  const { isAdmin } = useRoles();
  const { data: profiles = [] } = useProfiles();
  const { data: roles = [] } = useUserRoles();
  const { adminEmail } = useBootstrap();
  const invalidateBootstrap = useInvalidateBootstrap();
  const [adminInput, setAdminInput] = useState("");
  const [savingAdmin, setSavingAdmin] = useState(false);

  useEffect(() => {
    if (adminEmail) setAdminInput(adminEmail);
  }, [adminEmail]);


  return (
    <AppShell title="Impostazioni" subtitle="Configurazione applicazione">
      <div className="space-y-4">
        <section className="hud-panel space-y-2 p-4">
          <p className="hud-title">Installazione PWA</p>
          <p className="text-sm text-muted-foreground">
            {installed
              ? "VIS•ION è già installata su questo dispositivo."
              : "Installa VIS•ION per usarla a schermo intero come app."}
          </p>
          {canInstall && (
            <Button onClick={() => void install()}>
              <Download className="size-4" /> Installa VIS•ION
            </Button>
          )}
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Smartphone className="mt-0.5 size-4 shrink-0" />
            Android/Chrome: menu ⋮ → "Installa app". iOS/Safari: Condividi → "Aggiungi a Home".
          </p>
        </section>

        <section className="hud-panel space-y-2 p-4">
          <p className="hud-title">Notifiche push</p>
          <p className="text-sm text-muted-foreground">
            L'interfaccia è pronta e la tabella <span className="font-mono">user_devices</span>
            &nbsp;è predisposta per salvare le subscription. Per attivare il push mancano: chiavi
            VAPID, un service worker di messaggistica e un servizio di invio lato server.
          </p>
          <StatusBadge status="PENDING" />
        </section>

        <section className="hud-panel space-y-2 p-4">
          <p className="hud-title">Comandi whitelist</p>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {Object.entries(COMMAND_WHITELIST).map(([key, cfg]) => (
              <li
                key={key}
                className="flex items-center justify-between gap-2 rounded-md border border-border px-2.5 py-1.5 text-xs"
              >
                <span className="truncate font-mono">{key}</span>
                <span className="shrink-0 text-[0.6rem] text-muted-foreground">
                  {cfg.roles.join("/")}
                  {cfg.sensitive ? " · sensibile" : ""}
                  {cfg.remoteEnabled ? " · remoto ON" : " · NON ANCORA ABILITATO"}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="hud-panel space-y-2 p-4">
          <p className="hud-title">Amministratore (configurazione iniziale)</p>
          <p className="text-sm text-muted-foreground">
            Email con ruolo <span className="font-mono">ADMIN</span>:{" "}
            <span className="font-mono text-accent">{adminEmail ?? "non configurata"}</span>
          </p>
          {isAdmin ? (
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[16rem] flex-1 space-y-1.5">
                <Label htmlFor="admin-email">Nuova email amministratore</Label>
                <Input
                  id="admin-email"
                  type="email"
                  value={adminInput}
                  onChange={(e) => setAdminInput(e.target.value)}
                  placeholder="nome.cognome@azienda.it"
                />
              </div>
              <Button
                disabled={savingAdmin}
                onClick={() => {
                  const value = adminInput.trim().toLowerCase();
                  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
                    toast.error("Email non valida");
                    return;
                  }
                  setSavingAdmin(true);
                  void saveAdminEmail(value)
                    .then(() => {
                      invalidateBootstrap();
                      toast.success("Amministratore aggiornato");
                    })
                    .catch((e: Error) =>
                      toast.error("Salvataggio non riuscito", { description: e.message }),
                    )
                    .finally(() => setSavingAdmin(false));
                }}
              >
                Salva
              </Button>
            </div>
          ) : (
            <p className="text-[0.65rem] text-muted-foreground">
              Solo un amministratore può modificare questa impostazione.
            </p>
          )}
        </section>

        {isAdmin && (

          <section className="hud-panel space-y-2 p-4">
            <p className="hud-title">Utenti</p>
            <ul className="space-y-1.5">
              {profiles.map((p: any) => (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-2.5 py-1.5 text-xs"
                >
                  <span className="min-w-0 truncate">{p.full_name ?? p.email}</span>
                  <span className="shrink-0 font-mono text-[0.6rem] text-accent">
                    {roles
                      .filter((r: any) => r.user_id === p.id)
                      .map((r: any) => r.role)
                      .join(" · ") || "—"}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-[0.65rem] text-muted-foreground">
              L'assegnazione dei ruoli avviene sul database (tabella{" "}
              <span className="font-mono">user_roles</span>) per evitare escalation dal client.
            </p>
          </section>
        )}
      </div>
    </AppShell>
  );
}
