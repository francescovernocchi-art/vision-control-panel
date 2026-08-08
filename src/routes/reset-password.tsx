import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { VisionLogo } from "@/components/vision/VisionLogo";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/reset-password")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Reimposta password — VIS•ION" },
      { name: "description", content: "Imposta una nuova password per il tuo account VIS•ION." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Reimposta password — VIS•ION" },
      { property: "og:description", content: "Imposta una nuova password VIS•ION." },
    ],
  }),
  component: ResetPassword,
});

function ResetPassword() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.updateUser({ password });
    setBusy(false);
    if (error) {
      toast.error("Aggiornamento non riuscito", { description: error.message });
      return;
    }
    toast.success("Password aggiornata");
    void navigate({ to: "/dashboard", replace: true });
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="hud-panel w-full max-w-md space-y-4 p-6">
        <div className="flex flex-col items-center text-center">
          <VisionLogo size={56} />
          <h1 className="mt-3 font-mono text-lg tracking-[0.2em]">NUOVA PASSWORD</h1>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="new-password">Password</Label>
          <Input
            id="new-password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" className="w-full" disabled={busy}>
          Aggiorna password
        </Button>
      </form>
    </div>
  );
}
