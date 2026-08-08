import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useSession } from "@/hooks/useAuth";
import { logAudit } from "@/lib/vision-data";
import { saveAdminEmail, useBootstrap, useInvalidateBootstrap } from "@/lib/vision-bootstrap";

export const Route = createFileRoute("/_authenticated/setup")({
  head: () => ({
    meta: [
      { title: "Configurazione iniziale — VIS•ION" },
      {
        name: "description",
        content: "Seleziona l'email amministratore di VIS•ION al primo avvio.",
      },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Configurazione iniziale — VIS•ION" },
      { property: "og:description", content: "Setup amministratore VIS•ION." },
    ],
  }),
  component: SetupPage,
});

function SetupPage() {
  const navigate = useNavigate();
  const { user } = useSession();
  const { adminEmail, adminExists, loading } = useBootstrap();
  const invalidate = useInvalidateBootstrap();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (adminEmail) setEmail(adminEmail);
    else if (user?.email) setEmail(user.email);
  }, [adminEmail, user?.email]);

  const locked = adminExists && adminEmail !== null;

  async function save() {
    const value = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      toast.error("Email non valida");
      return;
    }
    setBusy(true);
    try {
      await saveAdminEmail(value);
      await logAudit({ action: "BOOTSTRAP_ADMIN_SET" });
      invalidate();
      toast.success("Amministratore configurato", {
        description: `${value} riceverà il ruolo ADMIN al primo accesso.`,
      });
      void navigate({ to: "/dashboard" });
    } catch (e) {
      toast.error("Salvataggio non riuscito", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Configurazione iniziale" subtitle="Selezione amministratore VIS•ION">
      <div className="mx-auto max-w-xl space-y-4">
        <section className="hud-panel space-y-3 p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-accent" />
            <p className="hud-title">Email amministratore</p>
            <span className="ml-auto">
              <StatusBadge status={adminExists ? "ONLINE" : "PENDING"} />
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            Indica quale email deve avere il ruolo <span className="font-mono">ADMIN</span>. Il
            ruolo viene applicato automaticamente: subito se l'utente è già registrato, altrimenti
            al suo primo signup. Tutti gli altri utenti ricevono il ruolo{" "}
            <span className="font-mono">OPERATORE</span>.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="admin-email">Email</Label>
            <Input
              id="admin-email"
              type="email"
              inputMode="email"
              autoComplete="email"
              value={email}
              disabled={locked || loading}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nome.cognome@azienda.it"
            />
          </div>

          {locked ? (
            <p className="text-xs text-muted-foreground">
              Un amministratore è già attivo: solo un ADMIN può modificare questa impostazione
              dalla pagina Impostazioni.
            </p>
          ) : (
            <Button className="w-full" disabled={busy || loading} onClick={() => void save()}>
              {busy ? "Salvataggio…" : "Imposta amministratore"}
            </Button>
          )}
        </section>
      </div>
    </AppShell>
  );
}
