import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProfile, useRoles, useSession } from "@/hooks/useAuth";
import { supabase } from "@/integrations/supabase/client";
import { logAudit } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/profilo")({
  head: () => ({
    meta: [
      { title: "Profilo — VIS•ION" },
      { name: "description", content: "Dati account, ruoli e disconnessione." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Profilo — VIS•ION" },
      { property: "og:description", content: "Profilo utente VIS•ION." },
    ],
  }),
  component: ProfiloPage,
});

function ProfiloPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useSession();
  const { roles } = useRoles();
  const { data: profile } = useProfile();
  const [fullName, setFullName] = useState<string | null>(null);

  const value = fullName ?? profile?.full_name ?? "";

  async function save() {
    if (!user) return;
    const { error } = await supabase
      .from("profiles")
      .update({ full_name: value, updated_at: new Date().toISOString() })
      .eq("id", user.id);
    if (error) {
      toast.error("Salvataggio non riuscito", { description: error.message });
      return;
    }
    await logAudit({ action: "PROFILE_UPDATED" });
    toast.success("Profilo aggiornato");
    void queryClient.invalidateQueries({ queryKey: ["my_profile"] });
  }

  async function signOut() {
    await logAudit({ action: "LOGOUT" });
    await queryClient.cancelQueries();
    queryClient.clear();
    await supabase.auth.signOut();
    void navigate({ to: "/auth", replace: true });
  }

  return (
    <AppShell title="Profilo" subtitle="Account e sessione">
      <div className="space-y-4">
        <section className="hud-panel space-y-3 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" value={user?.email ?? ""} disabled />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fullname">Nome e cognome</Label>
            <Input id="fullname" value={value} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div>
            <p className="hud-title">Ruoli</p>
            <p className="font-mono text-sm text-accent">{roles.join(" · ") || "—"}</p>
          </div>
          <Button onClick={() => void save()}>Salva</Button>
        </section>

        <section className="hud-panel space-y-2 p-4">
          <p className="hud-title">Sicurezza</p>
          <p className="text-xs text-muted-foreground">
            Nessuna credenziale eniSpace, PEC o di automazione è salvata in questa app: restano sul
            PC aziendale. 2FA/MFA è prevista in una fase successiva.
          </p>
          <Button variant="destructive" onClick={() => void signOut()}>
            <LogOut className="size-4" /> Logout
          </Button>
        </section>
      </div>
    </AppShell>
  );
}
