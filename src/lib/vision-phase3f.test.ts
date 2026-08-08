import { describe, expect, it } from "vitest";

import { formatDateTime, formatRelative } from "@/lib/vision";
import { productNameFromResult, VISION_PRODUCT_NAME } from "@/lib/vision-status";
import { derivedAgentStatus, isAgentOffline } from "@/lib/vision-remote-status";

describe("phase 3f hardening", () => {
  it("invalid timestamps do not crash formatters", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
    expect(formatRelative("not-a-date")).toBe("—");
    expect(formatDateTime(null)).toBe("—");
    expect(formatRelative(null)).toBe("mai");
  });

  it("offline derivation remains real (no demo online)", () => {
    const now = Date.parse("2026-08-08T12:00:00Z");
    expect(isAgentOffline(null, 60, now)).toBe(true);
    expect(
      derivedAgentStatus(
        { last_seen_at: null, status: "ONLINE" },
        { agent: { status: "ONLINE" } },
        now,
      ),
    ).toBe("OFFLINE");
  });

  it("user-facing product never becomes JARVIS", () => {
    expect(productNameFromResult({ assistant: "JARVIS" })).toBe(VISION_PRODUCT_NAME);
    expect(VISION_PRODUCT_NAME).toBe("VISION");
  });
});
