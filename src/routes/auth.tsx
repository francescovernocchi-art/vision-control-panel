import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VisionLogo } from "@/components/vision/VisionLogo";
import { supabase } from "@/integrations/supabase/client";
import { logAudit } from "@/lib/vision-data";

export const Route = createFileRoute("/auth")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Accesso VIS•ION" },
      { name: "description", content: "Area riservata VIS•ION. Accesso solo a utenti autorizzati." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Accesso VIS•ION" },
      { property: "og:description", content: "Area riservata VIS•ION." },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => {
      if (data.session) void navigate({ to: "/chat", replace: true });
    });
  }, [navigate]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      toast.error("Accesso non riuscito", { description: error.message });
      return;
    }
    await logAudit({ action: "LOGIN" });
    void navigate({ to: "/chat", replace: true });
  }

  async function signUp(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: window.location.origin,
        data: { full_name: fullName },
      },
    });
    setBusy(false);
    if (error) {
      toast.error("Registrazione non riuscita", { description: error.message });
      return;
    }
    if (!data.session) {
      toast.success("Account creato", {
        description: "Controlla la mail e conferma l'indirizzo per accedere.",
      });
    } else {
      void navigate({ to: "/chat", replace: true });
    }
  }

  async function resetPassword() {
    if (!email) {
      toast.error("Inserisci prima la tua email");
      return;
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    if (error) {
      toast.error("Invio non riuscito", { description: error.message });
      return;
    }
    toast.success("Email inviata", { description: "Controlla la posta per reimpostare la password." });
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="hud-panel w-full max-w-md p-6">
        <div className="flex flex-col items-center text-center">
          <VisionLogo size={72} />
          <h1 className="mt-4 font-mono text-2xl font-bold tracking-[0.25em]">VIS•ION</h1>
          <p className="mt-1 text-xs tracking-wide text-muted-foreground">
            VIS Intelligent Operations Network
          </p>
          <p className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[0.65rem] text-muted-foreground">
            <ShieldCheck className="size-3.5 text-accent" /> Terminale remoto privato — accesso
            riservato
          </p>
        </div>

        <Tabs defaultValue="signin" className="mt-6">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="signin">Accedi</TabsTrigger>
            <TabsTrigger value="signup">Registrati</TabsTrigger>
          </TabsList>

          <TabsContent value="signin">
            <form className="space-y-4" onSubmit={signIn}>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email aziendale</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="size-4 animate-spin" />} Accedi
              </Button>
              <button
                type="button"
                onClick={() => void resetPassword()}
                className="w-full text-center text-xs text-muted-foreground underline-offset-4 hover:underline"
              >
                Password dimenticata?
              </button>
            </form>
          </TabsContent>

          <TabsContent value="signup">
            <form className="space-y-4" onSubmit={signUp}>
              <div className="space-y-1.5">
                <Label htmlFor="name">Nome e cognome</Label>
                <Input id="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email2">Email aziendale</Label>
                <Input
                  id="email2"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password2">Password</Label>
                <Input
                  id="password2"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="size-4 animate-spin" />} Crea account
              </Button>
              <p className="text-center text-[0.65rem] text-muted-foreground">
                I nuovi account ricevono il ruolo OPERATORE. Un ADMIN può modificarlo.
              </p>
            </form>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
