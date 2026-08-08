/**
 * Canonical VISION Agent ↔ PWA contract types.
 * Source: VISION Agent RemoteStatusResponse / RemoteEniSpaceRuntimeStatus.
 * api_version=v1 · contract_version=1.0.0 · status_only / GET_STATUS only
 */

export const VISION_API_VERSION = "v1" as const;
export const VISION_CONTRACT_VERSION = "1.0.0" as const;
export const VISION_PRODUCT_NAME = "VISION" as const;

export type CommandStatus =
  | "PENDING"
  | "ACKNOWLEDGED"
  | "EXECUTING"
  | "COMPLETED"
  | "FAILED"
  | "REJECTED";

export type DeviceStatus = "ONLINE" | "DEGRADED" | "OFFLINE" | "DISABLED";

export type EniSpaceRuntimeStatus =
  | "IDLE"
  | "PROCESSING"
  | "DEGRADED"
  | "OFFLINE"
  | "UNKNOWN";

export type AppRole = "OPERATORE" | "ADMIN" | "DIREZIONE" | "AGENT";

export interface VisionDevice {
  device_id: string;
  device_name: string;
  status: string;
  agent_version: string;
  vision_version: string;
  platform_version: string;
  last_seen_at: string | null;
  current_job_id: string | null;
  modules: unknown;
  metadata: Record<string, unknown>;
}

export interface VisionCommand {
  command_id: string;
  command_type: string;
  target_device_id: string;
  status: CommandStatus | string;
  parameters: Record<string, unknown>;
  requested_by: string | null;
  requested_at: string;
  expires_at: string | null;
  acknowledged_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  result: GetStatusResult | Record<string, unknown> | null;
  error: string | null;
}

export interface VisionCoreStatus {
  online?: boolean;
  product?: string;
  product_name?: string;
  assistant?: string;
  assistant_state?: string;
  started_at?: string | null;
}

export interface EniSpaceRuntime {
  status: EniSpaceRuntimeStatus | string;
  available: boolean;
  active?: boolean | null;
  pending_jobs?: number | null;
  current_job: Record<string, unknown> | null;
  last_job: Record<string, unknown> | null;
  last_mail_check: string | null;
  last_error: string | null;
  detail_state?: string | null;
}

export interface ModuleStatus {
  module_id: string;
  display_name?: string;
  version?: string;
  status?: string;
  health?: string;
  enabled?: boolean;
  current_job?: unknown;
}

export interface ServiceStatus {
  service_id: string;
  available?: boolean;
  health?: string;
}

export interface VisionWarning {
  code?: string;
  severity?: string;
  component?: string;
  message?: string;
}

export interface AgentSection {
  status?: string;
  connected_backend?: string;
  remote_mode?: string;
  last_heartbeat?: string | null;
  last_error?: string | null;
}

export interface GetStatusResult {
  ok?: boolean;
  api_version?: string;
  contract_version?: string;
  device_id?: string;
  device_name?: string;
  agent_version?: string;
  vision_version?: string;
  platform_version?: string;
  timestamp?: string;
  core_status?: string;
  supervisor_status?: string;
  overall_health?: string;
  current_job?: unknown;
  queue_size?: number | null;
  modules?: ModuleStatus[];
  skills?: unknown[];
  services?: ServiceStatus[];
  warnings?: VisionWarning[];
  remote_control_enabled?: boolean;
  agent?: AgentSection;
  partial?: boolean;
  missing_sections?: string[];
  vision_core?: VisionCoreStatus;
  enispace_runtime?: EniSpaceRuntime;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Tolerant parser for GET_STATUS result (version skew / partial / nulls). */
export function parseGetStatusResult(raw: unknown): GetStatusResult | null {
  if (!isRecord(raw)) return null;
  // Structural cast after object check — payload is cloud JSON with optional fields.
  const r = raw as GetStatusResult;
  const eni = r.enispace_runtime;
  if (eni && typeof eni === "object") {
    r.enispace_runtime = {
      status: eni.status ?? "UNKNOWN",
      available: Boolean(eni.available),
      active: eni.active ?? null,
      pending_jobs: eni.pending_jobs ?? null,
      current_job: isRecord(eni.current_job) ? eni.current_job : null,
      last_job: isRecord(eni.last_job) ? eni.last_job : null,
      last_mail_check: eni.last_mail_check ?? null,
      last_error: eni.last_error ?? null,
      detail_state: eni.detail_state ?? null,
    };
  }
  if (Array.isArray(r.missing_sections)) {
    r.missing_sections = r.missing_sections.filter((x): x is string => typeof x === "string");
  }
  return r;
}

/** User-facing product name — never promote JARVIS. */
export function visionProductName(core?: VisionCoreStatus | null): string {
  const name = core?.product_name?.trim();
  if (name && name.toUpperCase() !== "JARVIS") return name;
  return VISION_PRODUCT_NAME;
}

export function isJarvisUserFacing(text: string | null | undefined): boolean {
  if (!text) return false;
  return /\bJARVIS\b/i.test(text);
}
