import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LOOPBACK_RUNTIME_URL,
  RuntimeClient,
  RuntimeRefusedError,
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
    });

    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(call[1].body))).toEqual({
      session_id: "session-1",
      device_id: "fake-s1-main",
      capability: "drive.velocity",
      action: "set",
      arguments: { speed: 0.2 },
      // ADR-027: the runtime decides the source from the token, so the client
      // sends nothing rather than a claim. ADR-028: there is no dead-man field
      // to send at all.
      source: null,
      input_confidence: null,
    });
  });

  it("sends no dead-man claim, because the runtime does not accept one", async () => {
    const fetchMock = mockFetch({ accepted: true });
    await new RuntimeClient().send({
      sessionId: "session-1",
      deviceId: "fake-s1-main",
      capability: "drive.velocity",
      action: "set",
    });

    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(call[1].body)).not.toContain("deadman");
  });

  it("carries the token once somebody has signed in", async () => {
    const fetchMock = mockFetch({
      token: "issued-token",
      actorId: "student-1",
      role: "student",
      displayName: "student-1",
      expiresAt: "2026-01-01T00:00:00+00:00",
    });
    const client = new RuntimeClient();
    await client.join({ actorId: "student-1", role: "student" });
    await client.devices();

    const call = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect((call[1].headers as Record<string, string>)["authorization"]).toBe(
      "Bearer issued-token",
    );
  });

  it("sends no authorization header before anybody has signed in", async () => {
    const fetchMock = mockFetch({ status: "ok" });
    await new RuntimeClient().health();

    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(call[1].headers).not.toHaveProperty("authorization");
  });

  it("opens no event socket without a token", () => {
    const close = new RuntimeClient().streamEvents(() => undefined);
    expect(close).toBeTypeOf("function");
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

  it("shows the runtime's own sentence, not the JSON around it", async () => {
    mockFetch(
      { detail: "Device is already assigned to another session" },
      true,
      409,
    );
    await expect(new RuntimeClient().devices()).rejects.toThrow(
      /already assigned/,
    );
  });

  it("knows that a 401 means signing in again, and a 403 does not", async () => {
    mockFetch({ detail: "expired" }, true, 401);
    const expired = await new RuntimeClient()
      .devices()
      .catch((error: unknown) => error);
    expect(expired).toBeInstanceOf(RuntimeRefusedError);
    expect((expired as RuntimeRefusedError).needsSignIn).toBe(true);

    mockFetch({ detail: "instructor action" }, true, 403);
    const refused = await new RuntimeClient()
      .devices()
      .catch((error: unknown) => error);
    expect((refused as RuntimeRefusedError).needsSignIn).toBe(false);
  });

  it("unwraps the devices envelope", async () => {
    mockFetch({ devices: [{ deviceId: "fake-s1-main" }] });
    await expect(new RuntimeClient().devices()).resolves.toHaveLength(1);
  });
});
