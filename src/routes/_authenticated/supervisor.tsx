import { createFileRoute, redirect } from "@tanstack/react-router";

/** Legacy route — canonical path is /attivita */
export const Route = createFileRoute("/_authenticated/supervisor")({
  beforeLoad: () => {
    throw redirect({ to: "/attivita" });
  },
});
