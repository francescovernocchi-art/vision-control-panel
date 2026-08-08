import { describe, expect, it, vi } from "vitest";

import {
  AGENT_TIMEOUT_MESSAGE,
  agentQueueSizeDisplay,
  dataMode,
  derivedAgentStatus,
  isAgentOffline,
  isCloudConfigured,
  isRemoteCommandEnabled,
  moduleLiveStatus,
  normalizeCommandRow,
  pickLatestGetStatusCommand,
  uniqueWarnings,
  waitForGetStatusResult,
  type CommandRow,
  type GetStatusResult,
} from "@/lib/vision-remote-status";

describe("phase 3d agent observability helpers", () => {
  it("queue size never falls back to demo counts", () => {
    expect(agentQueueSizeDisplay(null)).toBe("—");
    expect(agentQueueSizeDisplay({})).toBe("—");
    expect(agentQueueSizeDisplay({ queue_size: 3 })).toBe(3);
    expect(agentQueueSizeDisplay({ queue_size: 0 })).toBe(0);
  });

  it("module live status ignores seed status", () => {
    expect(moduleLiveStatus(undefined, "ONLINE")).toBe("—");
    expect(moduleLiveStatus(null, "RUNNING")).toBe("—");
    expect(moduleLiveStatus({ status: "IDLE" }, "ONLINE")).toBe("IDLE");
    expect(moduleLiveStatus({ health: "DEGRADED" }, "ONLINE")).toBe("DEGRADED");
  });

  it("offline derivation does not invent ONLINE", () => {
    const now = Date.parse("2026-08-08T12:00:00Z");
    expect(
      derivedAgentStatus(
        { last_seen_at: "2026-08-08T11:00:00Z", heartbeat_threshold_seconds: 60 },
        { agent: { status: "ONLINE" } },
        now,
      ),
    ).toBe("OFFLINE");
  });
});

describe("normalizeCommandRow", () => {
  it("maps Lovable id", () => {
    const row = normalizeCommandRow({
      id: "abc",
      command_type: "GET_STATUS",
      status: "PENDING",
      result: null,
      error: null,
      requested_at: "2026-01-01T00:00:00Z",
    });
    expect(row?.id).toBe("abc");
  });

  it("maps contract command_id", () => {
    const row = normalizeCommandRow({
      command_id: "xyz",
      command_type: "GET_STATUS",
      status: "COMPLETED",
      result: { core_status: "ONLINE" },
      error: null,
      requested_at: "2026-01-01T00:00:00Z",
    });
    expect(row?.id).toBe("xyz");
    expect(row?.result?.core_status).toBe("ONLINE");
  });
});

describe("commands disabled", () => {
  it("enables only GET_STATUS", () => {
    expect(isRemoteCommandEnabled("GET_STATUS")).toBe(true);
    for (const c of [
      "CHECK_ENISPACE_MAIL",
      "RETRY_JOB",
      "PAUSE_MODULE",
      "RESUME_MODULE",
      "PREPARE_COIN_TRANSPORT",
      "APPROVE_JOB",
      "REJECT_JOB",
    ]) {
      expect(isRemoteCommandEnabled(c)).toBe(false);
    }
  });
});

describe("agent offline", () => {
  it("is offline when last_seen older than 60s", () => {
    const now = Date.parse("2026-08-08T12:00:00Z");
    expect(isAgentOffline("2026-08-08T11:58:00Z", 60, now)).toBe(true);
    expect(isAgentOffline("2026-08-08T11:59:30Z", 60, now)).toBe(false);
    expect(isAgentOffline(null, 60, now)).toBe(true);
  });

  it("derivedAgentStatus returns OFFLINE", () => {
    const now = Date.parse("2026-08-08T12:00:00Z");
    expect(
      derivedAgentStatus(
        {
          status: "ONLINE",
          last_seen_at: "2026-08-08T11:58:00Z",
          heartbeat_threshold_seconds: 60,
        },
        null,
        now,
      ),
    ).toBe("OFFLINE");
  });
});

describe("warnings unique / partial / missing", () => {
  it("dedupes warning codes", () => {
    const w = uniqueWarnings([
      { code: "NOTIFICATION_DEGRADED", message: "a" },
      { code: "NOTIFICATION_DEGRADED", message: "b" },
      { code: "COIN_TRANSPORT_IN_DEVELOPMENT" },
      { code: "PLATFORM_DEGRADED" },
    ]);
    expect(w.map((x) => x.code)).toEqual([
      "NOTIFICATION_DEGRADED",
      "COIN_TRANSPORT_IN_DEVELOPMENT",
      "PLATFORM_DEGRADED",
    ]);
  });

  it("reads partial and missing_sections", () => {
    const result: GetStatusResult = {
      partial: true,
      missing_sections: ["skills", "services"],
    };
    expect(result.partial).toBe(true);
    expect(result.missing_sections).toContain("skills");
  });
});

describe("waitForGetStatusResult", () => {
  function baseCmd(over: Partial<CommandRow> = {}): CommandRow {
    return {
      id: "cmd-1",
      command_type: "GET_STATUS",
      status: "PENDING",
      result: null,
      error: null,
      requested_at: "2026-01-01T00:00:00Z",
      ...over,
    };
  }

  it("resolves COMPLETED via poll fallback", async () => {
    let n = 0;
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 5_000,
      pollMs: 10,
      subscribe: () => () => undefined,
      fetchFn: async () => {
        n += 1;
        if (n < 2) return baseCmd({ status: "ACKNOWLEDGED" });
        if (n < 3) return baseCmd({ status: "EXECUTING" });
        return baseCmd({
          status: "COMPLETED",
          result: { core_status: "ONLINE", partial: false },
        });
      },
    });
    expect(outcome.ok).toBe(true);
    if (outcome.ok) {
      expect(outcome.result?.core_status).toBe("ONLINE");
    }
  });

  it("resolves via realtime subscribe", async () => {
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 5_000,
      pollMs: 60_000,
      fetchFn: async () => baseCmd({ status: "PENDING" }),
      subscribe: (_id, onRow) => {
        setTimeout(() => {
          onRow(
            baseCmd({
              status: "COMPLETED",
              result: { supervisor_status: "IDLE" },
            }),
          );
        }, 20);
        return () => undefined;
      },
    });
    expect(outcome.ok).toBe(true);
    if (outcome.ok) expect(outcome.result?.supervisor_status).toBe("IDLE");
  });

  it("times out without marking FAILED", async () => {
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 40,
      pollMs: 200,
      subscribe: () => () => undefined,
      fetchFn: async () => baseCmd({ status: "PENDING" }),
    });
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) {
      expect(outcome.reason).toBe("timeout");
      expect(outcome.message).toBe(AGENT_TIMEOUT_MESSAGE);
    }
  });

  it("handles FAILED", async () => {
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 2_000,
      pollMs: 10,
      subscribe: () => () => undefined,
      fetchFn: async () => baseCmd({ status: "FAILED", error: "agent boom" }),
    });
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) {
      expect(outcome.reason).toBe("error");
      expect(outcome.message).toBe("agent boom");
    }
  });

  it("handles REJECTED", async () => {
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 2_000,
      pollMs: 10,
      subscribe: () => () => undefined,
      fetchFn: async () =>
        baseCmd({
          status: "REJECTED",
          error: "REMOTE_OPERATION_NOT_ENABLED",
        }),
    });
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) expect(outcome.message).toContain("REMOTE_OPERATION");
  });

  it("tolerates missing fields on completed result", async () => {
    const outcome = await waitForGetStatusResult("cmd-1", {
      timeoutMs: 2_000,
      pollMs: 10,
      subscribe: () => () => undefined,
      fetchFn: async () => baseCmd({ status: "COMPLETED", result: {} }),
    });
    expect(outcome.ok).toBe(true);
    if (outcome.ok) {
      expect(outcome.result?.core_status).toBeUndefined();
      expect(outcome.result?.modules).toBeUndefined();
    }
  });
});

describe("create_get_status_command contract shape", () => {
  it("RPC arg name is p_device_id", () => {
    // Documented contract — keep in sync with migration + client call site
    const rpcArgs = { p_device_id: "VIS-TARANTO-01" };
    expect(rpcArgs).toHaveProperty("p_device_id", "VIS-TARANTO-01");
    expect(rpcArgs).not.toHaveProperty("p_device_code");
  });
});

describe("invalid / empty responses", () => {
  it("normalizeCommandRow rejects empty payload", () => {
    expect(normalizeCommandRow(null)).toBeNull();
    expect(normalizeCommandRow({})).toBeNull();
    expect(normalizeCommandRow({ status: "COMPLETED" })).toBeNull();
  });
});

describe("wait settles once (no double resolve)", () => {
  it("ignores late FAILED after COMPLETED", async () => {
    let onRow: ((row: CommandRow) => void) | undefined;
    const outcomeP = waitForGetStatusResult("cmd-1", {
      timeoutMs: 2_000,
      pollMs: 60_000,
      fetchFn: async () => basePending(),
      subscribe: (_id, cb) => {
        onRow = cb;
        return () => undefined;
      },
    });

    onRow?.(
      basePending({
        status: "COMPLETED",
        result: { core_status: "ONLINE" },
      }),
    );
    onRow?.(basePending({ status: "FAILED", error: "late" }));

    const outcome = await outcomeP;
    expect(outcome.ok).toBe(true);
    if (outcome.ok) expect(outcome.result?.core_status).toBe("ONLINE");
  });
});

function basePending(over: Partial<CommandRow> = {}): CommandRow {
  return {
    id: "cmd-1",
    command_type: "GET_STATUS",
    status: "PENDING",
    result: null,
    error: null,
    requested_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

describe("pickLatestGetStatusCommand (UI status render)", () => {
  it("picks first GET_STATUS for device in desc-ordered list", () => {
    const picked = pickLatestGetStatusCommand(
      [
        {
          target_device_id: "dev-1",
          command_type: "GET_STATUS",
          status: "COMPLETED",
        },
        {
          target_device_id: "dev-1",
          command_type: "GET_STATUS",
          status: "FAILED",
        },
      ],
      "dev-1",
    );
    expect(picked).toMatchObject({ status: "COMPLETED" });
  });

  it("returns null when missing", () => {
    expect(pickLatestGetStatusCommand([], "dev-1")).toBeNull();
  });
});

describe("vitest smoke", () => {
  it("vi works", () => {
    const spy = vi.fn();
    spy();
    expect(spy).toHaveBeenCalledOnce();
  });
});
