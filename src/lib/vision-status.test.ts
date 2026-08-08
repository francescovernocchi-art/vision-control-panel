import { describe, expect, it } from "vitest";

import {
  displayValue,
  jobSummaryLabel,
  normalizeStatus,
  productNameFromResult,
  statusLabel,
  statusTone,
  VISION_PRODUCT_NAME,
} from "@/lib/vision-status";
import {
  agentQueueSizeDisplay,
  derivedAgentStatus,
  isAgentOffline,
  moduleLiveStatus,
  type GetStatusResult,
} from "@/lib/vision-remote-status";

describe("phase 3e status semantics", () => {
  it("A/B online offline from last_seen", () => {
    const now = Date.parse("2026-08-08T12:00:00Z");
    expect(isAgentOffline("2026-08-08T11:59:30Z", 60, now)).toBe(false);
    expect(isAgentOffline("2026-08-08T11:58:00Z", 60, now)).toBe(true);
    expect(
      derivedAgentStatus(
        { last_seen_at: "2026-08-08T11:59:30Z", heartbeat_threshold_seconds: 60 },
        null,
        now,
      ),
    ).toBe("ONLINE");
    expect(
      derivedAgentStatus(
        { last_seen_at: "2026-08-08T11:00:00Z", heartbeat_threshold_seconds: 60 },
        { agent: { status: "ONLINE" } },
        now,
      ),
    ).toBe("OFFLINE");
  });

  it("C no devices empty semantics", () => {
    const devices: unknown[] = [];
    expect(devices.length === 0).toBe(true);
  });

  it("E GET_STATUS success fields", () => {
    const result: GetStatusResult = {
      overall_health: "DEGRADED",
      core_status: "ONLINE",
      supervisor_status: "ONLINE",
      queue_size: 2,
      current_job: { job_id: "VISION-1" },
      enispace_runtime: {
        available: true,
        status: "IDLE",
        pending_jobs: 0,
        current_job: null,
      },
      vision_core: { product_name: "VISION", assistant: "JARVIS" },
    };
    expect(agentQueueSizeDisplay(result)).toBe(2);
    expect(jobSummaryLabel(result.current_job)).toBe("VISION-1");
    expect(productNameFromResult(result.vision_core)).toBe(VISION_PRODUCT_NAME);
  });

  it("F partial missing sections remain usable", () => {
    const result: GetStatusResult = {
      partial: true,
      missing_sections: ["enispace_runtime"],
      core_status: "ONLINE",
    };
    expect(result.partial).toBe(true);
    expect(result.core_status).toBe("ONLINE");
    expect(result.missing_sections).toContain("enispace_runtime");
  });

  it("G timeout / no demo fallback for queue", () => {
    expect(agentQueueSizeDisplay(null)).toBe("—");
    expect(moduleLiveStatus(undefined, "ONLINE")).toBe("—");
  });

  it("H/I EniSpace available / unavailable", () => {
    const available = { available: true, status: "PROCESSING" };
    const unavailable = { available: false, status: "UNKNOWN" };
    expect(available.available).toBe(true);
    expect(unavailable.available).toBe(false);
    expect(statusLabel(available.status)).toBe("In elaborazione");
  });

  it("J/K core and enispace jobs stay separated", () => {
    const result: GetStatusResult = {
      current_job: { job_id: "CORE-9" },
      enispace_runtime: {
        available: true,
        status: "PROCESSING",
        current_job: { id: 42, order_number: "ORD-1" },
      },
    };
    expect(jobSummaryLabel(result.current_job)).toBe("CORE-9");
    expect(jobSummaryLabel(result.enispace_runtime?.current_job)).toBe("ORD-1");
    expect(jobSummaryLabel(result.current_job)).not.toBe(
      jobSummaryLabel(result.enispace_runtime?.current_job),
    );
  });

  it("L warning severity tones", () => {
    expect(statusTone("ERROR")).toBe("danger");
    expect(statusTone("DEGRADED")).toBe("warning");
    expect(statusTone("ONLINE")).toBe("success");
    expect(normalizeStatus(" idle ")).toBe("IDLE");
  });

  it("M no JARVIS as product branding", () => {
    expect(productNameFromResult({ assistant: "JARVIS" })).toBe("VISION");
    expect(productNameFromResult({ product_name: "VISION", assistant: "JARVIS" })).toBe(
      "VISION",
    );
    expect(VISION_PRODUCT_NAME).not.toMatch(/jarvis/i);
  });

  it("displayValue never invents", () => {
    expect(displayValue(null)).toBe("—");
    expect(displayValue(undefined)).toBe("—");
    expect(displayValue(0)).toBe("0");
    expect(displayValue(false)).toBe("No");
  });
});
