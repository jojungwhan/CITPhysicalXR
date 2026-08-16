import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LOOPBACK_RUNTIME_URL,
  RuntimeClient,
  RuntimeUnreachableError,
  resolveRuntimeUrl,
} from "./runtime-client.js";

function mockFetch(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  );
  vi.stubGlobal(
    "fetch",
    ok ? fetchMock : vi.fn(async () => Promise.reject(new Error("down"))),
  );
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RuntimeClient", () => {
  it("uses loopback when nothing is serving it", () => {
    expect(LOOPBACK_RUNTIME_URL).toMatch(/^http:\/\/127\.0\.0\.1:/);
    expect(resolveRuntimeUrl(undefined)).toBe(LOOPBACK_RUNTIME_URL);
  });

  it("reaches across to loopback only from the Vite dev and preview ports", () => {
    expect(
      resolveRuntimeUrl({ origin: "http://localhost:5173", port: "5173" }),
    ).toBe(LOOPBACK_RUNTIME_URL);
    expect(
      resolveRuntimeUrl({ origin: "http://localhost:4173", port: "4173" }),
    ).toBe(LOOPBACK_RUNTIME_URL);
  });

  it("uses its own origin when the runtime is serving it", () => {
    expect(
      resolveRuntimeUrl({ origin: "http://127.0.0.1:8791", port: "8791" }),
    ).toBe("http://127.0.0.1:8791");
  });

  it("a remotely hosted copy points at itself, so it cannot drive a local robot", () => {
    expect(resolveRuntimeUrl({ origin: "https://example.com", port: "" })).toBe(
      "https://example.com",
    );
  });

  it("strips a trailing slash so paths do not double up", () => {
    expect(new RuntimeClient("http://127.0.0.1:8791/").baseUrl).toBe(
      "http://127.0.0.1:8791",
    );
  });

  it("maps a command request onto the runtime's snake_case body", async () => {
    const fetchMock = mockFetch({ accepted: true, status: "completed" });
    await new RuntimeClient().send({
      sessionId: "session-1",
      deviceId: "fake-s1-main",
      capability: "drive.velocity",
      action: "set",
      arguments: { speed: 0.2 },
      deadmanActive: true,
    });

    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(call[1].body))).toEqual({
      session_id: "session-1",
      device_id: "fake-s1-main",
      capability: "drive.velocity",
      action: "set",
      arguments: { speed: 0.2 },
      source: "student_blocks",
      deadman_active: true,
      input_confidence: null,
    });
  });

  it("explains how to start the runtime when it is unreachable", async () => {
    mockFetch({}, false);
    await expect(new RuntimeClient().health()).rejects.toBeInstanceOf(
      RuntimeUnreachableError,
    );
    await expect(new RuntimeClient().health()).rejects.toThrow(
      /python -m cit_runtime/,
    );
  });

  it("surfaces an HTTP error rather than pretending it succeeded", async () => {
    mockFetch({ detail: "nope" }, true, 409);
    await expect(new RuntimeClient().devices()).rejects.toThrow(/409/);
  });

  it("unwraps the devices envelope", async () => {
    mockFetch({ devices: [{ deviceId: "fake-s1-main" }] });
    await expect(new RuntimeClient().devices()).resolves.toHaveLength(1);
  });
});
