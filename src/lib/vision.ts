// Shared VIS•ION domain types, labels and helpers (presentation layer only).

export type AppRole = "ADMIN" | "OPERATORE" | "DIREZIONE";

export type JobStatus =
  | "PENDING"
  | "QUEUED"
  | "PROCESSING"
  | "WAITING_APPROVAL"
  | "COMPLETED"
  | "PARTIAL"
  | "NEEDS_ATTENTION"
  | "FAILED"
  | "CANCELLED";

export type DeviceStatus = "ONLINE" | "DEGRADED" | "OFFLINE" | "DISABLED";

export type SupervisorState =
  | "IDLE"
  | "MAIL_RECEIVED"
  | "ANALYSIS"
  | "PROCESSING"
  | "DOWNLOAD"
  | "PRINTING"
  | "WAITING_APPROVAL"
  | "SUCCESS"
  | "ERROR"
  | "NEEDS_ATTENTION";

export type CommandType =
  | "GET_STATUS"
  | "CHECK_ENISPACE_MAIL"
  | "RETRY_JOB"
  | "PAUSE_MODULE"
  | "RESUME_MODULE"
  | "PREPARE_COIN_TRANSPORT"
  | "APPROVE_JOB"
  | "REJECT_JOB";

export const COMMAND_WHITELIST: Record<
  CommandType,
  { label: string; sensitive: boolean; roles: AppRole[]; remoteEnabled: boolean }
> = {
  GET_STATUS: {
    label: "Stato agent",
    sensitive: false,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: true,
  },
  CHECK_ENISPACE_MAIL: {
    label: "Controlla ora le mail",
    sensitive: false,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: false,
  },
  RETRY_JOB: {
    label: "Riprova ultimo job",
    sensitive: true,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: false,
  },
  PAUSE_MODULE: {
    label: "Metti in pausa modulo",
    sensitive: true,
    roles: ["ADMIN"],
    remoteEnabled: false,
  },
  RESUME_MODULE: {
    label: "Riattiva modulo",
    sensitive: true,
    roles: ["ADMIN"],
    remoteEnabled: false,
  },
  PREPARE_COIN_TRANSPORT: {
    label: "Prepara trasporto monete",
    sensitive: true,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: false,
  },
  APPROVE_JOB: {
    label: "Approva lavorazione",
    sensitive: true,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: false,
  },
  REJECT_JOB: {
    label: "Rifiuta lavorazione",
    sensitive: true,
    roles: ["ADMIN", "OPERATORE"],
    remoteEnabled: false,
  },
};

/** Messaggio UI per comandi remoti non ancora abilitati (status_only). */
export const REMOTE_NOT_ENABLED_LABEL = "NON ANCORA ABILITATO";

export type Tone = "success" | "warning" | "danger" | "info" | "muted";

export const JOB_STATUS_TONE: Record<string, Tone> = {
  PENDING: "muted",
  QUEUED: "info",
  PROCESSING: "info",
  WAITING_APPROVAL: "warning",
  COMPLETED: "success",
  PARTIAL: "warning",
  NEEDS_ATTENTION: "warning",
  FAILED: "danger",
  CANCELLED: "muted",
};

export const STATUS_TONE: Record<string, Tone> = {
  ONLINE: "success",
  IDLE: "success",
  DEGRADED: "warning",
  OFFLINE: "danger",
  DISABLED: "muted",
  PAUSED: "warning",
  ERROR: "danger",
  PROCESSING: "info",
  UNKNOWN: "muted",
  UNAVAILABLE: "muted",
  PARTIAL: "warning",
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
  CHANGES_REQUESTED: "warning",
  CANCELLED: "muted",
  ACKNOWLEDGED: "info",
  EXECUTING: "info",
  COMPLETED: "success",
  FAILED: "danger",
};

export const SUPERVISOR_LABEL: Record<SupervisorState, string> = {
  IDLE: "In attesa",
  MAIL_RECEIVED: "Mail ricevuta",
  ANALYSIS: "Analisi in corso",
  PROCESSING: "Elaborazione",
  DOWNLOAD: "Download documenti",
  PRINTING: "Stampa",
  WAITING_APPROVAL: "In attesa di approvazione",
  SUCCESS: "Completato",
  ERROR: "Errore",
  NEEDS_ATTENTION: "Richiede intervento",
};

export const COIN_WORKFLOW = [
  "MAIL",
  "ANALISI",
  "ALLEGATI",
  "MEZZI",
  "ITINERARIO",
  "DOCUMENTO",
  "PEC",
  "APPROVAZIONE",
  "INVIO",
] as const;

export function toneClasses(tone: Tone): string {
  switch (tone) {
    case "success":
      return "bg-success/15 text-success border-success/30";
    case "warning":
      return "bg-warning/15 text-warning border-warning/30";
    case "danger":
      return "bg-destructive/15 text-destructive border-destructive/30";
    case "info":
      return "bg-info/15 text-info border-info/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function isDeviceOnline(
  lastSeenAt: string | null,
  thresholdSeconds = 120,
): boolean {
  if (!lastSeenAt) return false;
  return Date.now() - new Date(lastSeenAt).getTime() < thresholdSeconds * 1000;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatRelative(value?: string | null): string {
  if (!value) return "mai";
  const ts = new Date(value).getTime();
  if (Number.isNaN(ts)) return "—";
  const diff = Math.round((Date.now() - ts) / 1000);
  if (diff < 0) return "ora";
  if (diff < 60) return `${diff}s fa`;
  if (diff < 3600) return `${Math.round(diff / 60)} min fa`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h fa`;
  return `${Math.round(diff / 86400)} g fa`;
}

export function formatDuration(seconds?: number | null): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
