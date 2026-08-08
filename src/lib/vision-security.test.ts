import { describe, expect, it } from "vitest";

import { REMOTE_COMMAND_ENABLED, isRemoteCommandEnabled } from "@/lib/vision-remote-status";
import {
  VISION_PRODUCT_NAME,
  parseGetStatusResult,
  visionProductName,
} from "@/types/vision-contract";

describe("security contract", () => {
  it("allows only GET_STATUS remotely", () => {
    expect(isRemoteCommandEnabled("GET_STATUS")).toBe(true);
    for (const [cmd, enabled] of Object.entries(REMOTE_COMMAND_ENABLED)) {
      if (cmd === "GET_STATUS") expect(enabled).toBe(true);
      else expect(enabled).toBe(false);
    }
  });

  it("does not reference service_role or agent token in public env contract keys", () => {
    const forbidden = [
      "VITE_SUPABASE_SERVICE_ROLE_KEY",
      "VITE_SERVICE_ROLE",
      "VITE_VISION_AGENT_TOKEN",
      "VITE_SUPABASE_AGENT_KEY",
    ];
    for (const key of forbidden) {
      expect(import.meta.env[key]).toBeUndefined();
    }
  });
});

describe("GET_STATUS parser + branding", () => {
  it("parses partial payload and keeps Core/EniSpace jobs separate", () => {
    const parsed = parseGetStatusResult({
      overall_health: "HEALTHY",
      current_job: { id: "CORE-1" },
      queue_size: 2,
      vision_core: { product_name: "VISION", assistant: "JARVIS" },
      enispace_runtime: {
        available: true,
        status: "IDLE",
        current_job: { id: "ENI-9" },
        last_job: null,
        last_mail_check: null,
        last_error: null,
      },
      missing_sections: ["skills"],
      partial: true,
    });
    expect(parsed?.current_job).toEqual({ id: "CORE-1" });
    expect(parsed?.enispace_runtime?.current_job).toEqual({ id: "ENI-9" });
    expect(parsed?.missing_sections).toEqual(["skills"]);
    expect(visionProductName(parsed?.vision_core)).toBe(VISION_PRODUCT_NAME);
  });

  it("marks EniSpace unavailable without inventing jobs", () => {
    const parsed = parseGetStatusResult({
      enispace_runtime: {
        available: false,
        status: "OFFLINE",
        current_job: null,
        last_job: null,
        last_mail_check: null,
        last_error: null,
      },
    });
    expect(parsed?.enispace_runtime?.available).toBe(false);
    expect(parsed?.enispace_runtime?.current_job).toBeNull();
  });
});
