import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Check, PenLine, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/vision/AppShell";
import { CommandButton } from "@/components/vision/CommandButton";
import { StatusBadge } from "@/components/vision/StatusBadge";
import { useRoles } from "@/hooks/useAuth";
import { supabase } from "@/integrations/supabase/client";
import { formatDateTime } from "@/lib/vision";
import { logAudit, sendCommand, useApprovals, useJobs, useModules } from "@/lib/vision-data";

export const Route = createFileRoute("/_authenticated/approvazioni")({
  head: () => ({
    meta: [
      { title: "Approvazioni — VIS•ION" },
      { name: "description", content: "Operazioni sensibili in attesa di conferma." },
      { name: "robots", content: "noindex, nofollow" },
      { property: "og:title", content: "Approvazioni — VIS•ION" },
      { property: "og:description", content: "Approvazioni VIS•ION in attesa." },
    ],
  }),
  component: ApprovazioniPage,
});

function ApprovazioniPage() {
  const queryClient = useQueryClient();
  const { canOperate } = useRoles();
  const { data: approvals = [] } = useApprovals();
  const { data: jobs = [] } = useJobs();
  const { data: modules = [] } = useModules();

  const pending = approvals.filter((a: any) => a.status === "PENDING");

  async function decide(
    approval: any,
    status: "APPROVED" | "CHANGES_REQUESTED" | "CANCELLED",
  ) {
    const { data: userData } = await supabase.auth.getUser();
    const { error } = await supabase
      .from("approvals")
      .update({
        status,
        decided_at: new Date().toISOString(),
        decided_by: userData.user?.id ?? null,
      })
      .eq("id", approval.id);
    if (error) {
      toast.error("Operazione non riuscita", { description: error.message });
      return;
    }
    if (status !== "CANCELLED") {
      const job = jobs.find((j: any) => j.id === approval.job_id);
      try {
        await sendCommand({
          command_type: status === "APPROVED" ? "APPROVE_JOB" : "REJECT_JOB",
          module_id: approval.module_id,
          target_device_id: job?.device_id ?? null,
          job_id: approval.job_id,
        });
      } catch (e) {
        toast.error("Comando non inviato", { description: (e as Error).message });
      }
    }
    await logAudit({
      action: `APPROVAL_${status}`,
      module_id: approval.module_id,
      job_id: approval.job_id,
    });
    toast.success("Decisione registrata");
    void queryClient.invalidateQueries({ queryKey: ["approvals"] });
  }

  return (
    <AppShell title="Approvazioni" subtitle={`${pending.length} in attesa`}>
      <div className="space-y-3">
        {approvals.map((a: any) => {
          const province = ((a.metadata ?? {})["province"] as string[] | undefined) ?? [];
          return (
            <div key={a.id} className="hud-panel space-y-3 p-4">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                  <p className="hud-title">
                    {modules.find((m: any) => m.id === a.module_id)?.name ?? "Sistema"}
                  </p>
                  <p className="truncate text-sm font-semibold">{a.title}</p>
                  <p className="text-xs text-muted-foreground">{a.description}</p>
                </div>
                <StatusBadge status={a.status} />
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                <div>
                  <dt className="text-muted-foreground">Data</dt>
                  <dd>{formatDateTime(a.requested_at)}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-muted-foreground">Province</dt>
                  <dd className="truncate font-mono">{province.join(" / ") || "—"}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-muted-foreground">Decisione</dt>
                  <dd>{a.decided_at ? formatDateTime(a.decided_at) : "—"}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-2">
                {a.job_id && (
                  <Link
                    to="/jobs/$id"
                    params={{ id: a.job_id }}
                    className="inline-flex items-center rounded-md border border-border px-3 py-1.5 text-xs hover:border-accent/50"
                  >
                    Apri dettaglio
                  </Link>
                )}
                {a.status === "PENDING" && (
                  <>
                    <CommandButton
                      label="Approva"
                      variant="default"
                      sensitive
                      icon={<Check className="size-4" />}
                      disabled={!canOperate}
                      disabledReason="Il tuo ruolo è in sola consultazione."
                      description="Operazione sensibile: confermi l'approvazione? La PEC non verrà inviata automaticamente."
                      onConfirm={() => decide(a, "APPROVED")}
                    />
                    <CommandButton
                      label="Richiedi modifica"
                      variant="secondary"
                      sensitive
                      icon={<PenLine className="size-4" />}
                      disabled={!canOperate}
                      disabledReason="Il tuo ruolo è in sola consultazione."
                      onConfirm={() => decide(a, "CHANGES_REQUESTED")}
                    />
                    <CommandButton
                      label="Annulla"
                      variant="destructive"
                      sensitive
                      icon={<X className="size-4" />}
                      disabled={!canOperate}
                      disabledReason="Il tuo ruolo è in sola consultazione."
                      onConfirm={() => decide(a, "CANCELLED")}
                    />
                  </>
                )}
              </div>
            </div>
          );
        })}
        {approvals.length === 0 && (
          <p className="hud-panel p-6 text-center text-sm text-muted-foreground">
            Nessuna approvazione richiesta.
          </p>
        )}
      </div>
    </AppShell>
  );
}
