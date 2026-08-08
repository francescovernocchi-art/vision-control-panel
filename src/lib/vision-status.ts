/**
 * Central VISION status semantics for PWA UI.
 * Single source for tone / labels — do not scatter color logic.
 */

import type { Tone } from "@/lib/vision";

export const VISION_PRODUCT_NAME = "VISION";

export type VisionUiStatus =
  | "ONLINE"
  | "OFFLINE"
  | "IDLE"
  | "PROCESSING"
  | "DEGRADED"
  | "ERROR"
  | "UNKNOWN"
  | "DISABLED"
  | "PARTIAL"
  | "PENDING";

const TONE: Record<string, Tone> = {
  ONLINE: "success",
  IDLE: "success",
  SUCCESS: "success",
  COMPLETED: "success",
  PROCESSING: "info",
  EXECUTING: "info",
  ACKNOWLEDGED: "info",
  PENDING: "warning",
  DEGRADED: "warning",
  PARTIAL: "warning",
  WAITING_APPROVAL: "warning",
  OFFLINE: "danger",
  ERROR: "danger",
  FAILED: "danger",
  DISABLED: "muted",
  UNKNOWN: "muted",
  UNAVAILABLE: "muted",
};

export function normalizeStatus(raw: string | null | undefined): string {
  if (raw == null || String(raw).trim() === "" || raw === "—") return "UNKNOWN";
  return String(raw).trim().toUpperCase();
}

export function statusTone(status: string | null | undefined): Tone {
  return TONE[normalizeStatus(status)] ?? "muted";
}

export function statusLabel(status: string | null | undefined): string {
  const s = normalizeStatus(status);
  const labels: Record<string, string> = {
    ONLINE: "Online",
    OFFLINE: "Offline",
    IDLE: "In attesa",
    PROCESSING: "In elaborazione",
    DEGRADED: "Degradato",
    ERROR: "Errore",
    UNKNOWN: "Sconosciuto",
    DISABLED: "Disabilitato",
    PARTIAL: "Parziale",
    PENDING: "In corso",
    UNAVAILABLE: "Non disponibile",
  };
  return labels[s] ?? s;
}

/** Display value or em dash — never invent demo numbers/strings. */
export function displayValue(value: unknown, empty = "—"): string {
  if (value == null) return empty;
  if (typeof value === "string" && (value.trim() === "" || value === "—")) return empty;
  if (typeof value === "number" && !Number.isFinite(value)) return empty;
  if (typeof value === "boolean") return value ? "Sì" : "No";
  if (typeof value === "object") {
    const rec = value as Record<string, unknown>;
    const code =
      rec["code"] ??
      rec["job_id"] ??
      rec["order_number"] ??
      rec["summary"] ??
      rec["id"];
    if (code != null && String(code).trim() !== "") return String(code);
    return empty;
  }
  return String(value);
}

export function jobSummaryLabel(job: Record<string, unknown> | null | undefined): string {
  if (!job) return "—";
  return displayValue(
    job["code"] ??
      job["job_id"] ??
      job["order_number"] ??
      job["summary"] ??
      job["id"] ??
      job["status"],
  );
}

export function productNameFromResult(
  visionCore: { product_name?: string; product?: string; assistant?: string } | null | undefined,
): string {
  // Prefer explicit product; never brand UI as JARVIS
  const name = visionCore?.product_name || visionCore?.product;
  if (name && !/jarvis/i.test(String(name))) return String(name);
  return VISION_PRODUCT_NAME;
}
