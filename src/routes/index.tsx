import { useEffect } from "react";
import { createFileRoute, useRouter } from "@tanstack/react-router";

import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "VIS•ION — Control Room Operativa" },
      {
        name: "description",
        content:
          "VIS Intelligent Operations Network: monitora gli agent, i moduli operativi, le lavorazioni e le approvazioni in tempo reale.",
      },
      { property: "og:title", content: "VIS•ION — Control Room Operativa" },
      {
        property: "og:description",
        content:
          "Terminale privato VIS•ION per stato agent, moduli operativi, lavorazioni e approvazioni.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: IndexRoute,
});

function IndexRoute() {
  const router = useRouter();

  useEffect(() => {
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      router.navigate({ to: data.session ? "/dashboard" : "/auth", replace: true });
    });
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <h1 className="text-sm tracking-[0.4em] text-muted-foreground">VIS•ION</h1>
    </main>
  );
}
