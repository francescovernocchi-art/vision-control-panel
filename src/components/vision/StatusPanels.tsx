import { StatusBadge } from "@/components/vision/StatusBadge";
import { EmptyState } from "@/components/vision/UiStates";
import { formatRelative } from "@/lib/vision";
import { displayValue, jobSummaryLabel, statusLabel } from "@/lib/vision-status";
import type { GetStatusResult } from "@/lib/vision-remote-status";

export function EniSpaceStatusCard({
  runtime,
  synced,
}: {
  runtime?: GetStatusResult["enispace_runtime"] | null;
  synced: boolean;
}) {
  if (!synced) {
    return (
      <EmptyState
        title="EniSpace — dati non disponibili"
        description="Richiedi GET_STATUS per visualizzare lo stato operativo reale."
      />
    );
  }

  if (!runtime || runtime.available === false) {
    return (
      <EmptyState
        title="EniSpace non disponibile su questo dispositivo"
        description="Il runtime EniSpace non è bound o non è osservabile in questo GET_STATUS. Non è un errore generico di connessione."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={runtime.status ?? "UNKNOWN"} />
        <span className="text-xs text-muted-foreground">
          {runtime.active == null ? "" : runtime.active ? "Attivo" : "Non attivo"}
          {runtime.detail_state ? ` · ${runtime.detail_state}` : ""}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Pending jobs</dt>
          <dd className="font-mono">{displayValue(runtime.pending_jobs)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Ultimo controllo mail</dt>
          <dd className="font-mono">
            {runtime.last_mail_check ? formatRelative(runtime.last_mail_check) : "—"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Job EniSpace corrente</dt>
          <dd className="truncate font-mono">{jobSummaryLabel(runtime.current_job)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Ultimo job</dt>
          <dd className="truncate font-mono">{jobSummaryLabel(runtime.last_job)}</dd>
        </div>
        <div className="col-span-2 min-w-0 sm:col-span-3">
          <dt className="text-muted-foreground">Ultimo errore</dt>
          <dd className="truncate font-mono text-destructive">
            {displayValue(runtime.last_error)}
          </dd>
        </div>
      </dl>
      <p className="text-[0.65rem] text-muted-foreground">
        Stato normalizzato: {statusLabel(runtime.status)} — distinto dal job Vision Core.
      </p>
    </div>
  );
}

export function JobSummary({
  title,
  job = null,
  emptyLabel = "Nessun job attivo",
}: {
  title: string;
  job?: Record<string, unknown> | null;
  emptyLabel?: string;
}) {
  if (!job) {
    return (
      <div>
        <p className="text-xs text-muted-foreground">{title}</p>
        <p className="mt-1 text-sm text-muted-foreground">{emptyLabel}</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-xs text-muted-foreground">{title}</p>
      <p className="mt-1 font-mono text-sm font-semibold">{jobSummaryLabel(job)}</p>
      <p className="mt-0.5 font-mono text-[0.65rem] text-muted-foreground">
        {displayValue(job["status"] ?? job["state"])}
      </p>
    </div>
  );
}

export function WarningList({
  warnings,
}: {
  warnings?: Array<{ code?: string; severity?: string; component?: string; message?: string }> | null;
}) {
  if (!warnings?.length) {
    return (
      <EmptyState
        title="Nessun warning"
        description="VISION non segnala avvisi attivi in questo GET_STATUS."
      />
    );
  }

  const order = { ERROR: 0, error: 0, WARNING: 1, warning: 1, INFO: 2, info: 2 };
  const sorted = [...warnings].sort(
    (a, b) =>
      (order[a.severity as keyof typeof order] ?? 3) - (order[b.severity as keyof typeof order] ?? 3),
  );

  return (
    <ul className="space-y-2">
      {sorted.map((w, i) => {
        const sev = (w.severity ?? "INFO").toUpperCase();
        const tone =
          sev === "ERROR"
            ? "border-destructive/40 text-destructive"
            : sev === "WARNING"
              ? "border-warning/40 text-warning"
              : "border-border text-muted-foreground";
        return (
          <li
            key={`${w.code ?? "w"}-${i}`}
            className={`rounded-lg border px-3 py-2 text-xs ${tone}`}
          >
            <p className="font-mono text-[0.65rem] tracking-wide">
              {sev}
              {w.component ? ` · ${w.component}` : ""}
              {w.code ? ` · ${w.code}` : ""}
            </p>
            <p className="mt-0.5 text-foreground/90">{w.message ?? "—"}</p>
          </li>
        );
      })}
    </ul>
  );
}
