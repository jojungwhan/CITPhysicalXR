import path from "node:path";

import { describe, expect, it } from "vitest";

import { loadBridgeConfig } from "./config.js";

const environment = (): NodeJS.ProcessEnv => ({
  CIT_FABRIC_ADAPTER_URL: "ws://127.0.0.1:8765/api/v1/adapters/connect",
  CIT_FABRIC_ADAPTER_TOKEN: "cit-adapter-" + "a".repeat(40),
  CIT_FABRIC_READ_TOKEN: "cit-reader-" + "c".repeat(40),
  CIT_FABRIC_SESSION_ID: "lesson-session-a",
  CIT_AGENT_MESH_URL: "http://127.0.0.1:7342",
  CIT_AGENT_MESH_DEVICE_TOKEN: "device_" + "b".repeat(43),
  CIT_BRIDGE_DATABASE_PATH: path.resolve(
    "test-output/agent-mesh-bridge.sqlite3",
  ),
});

describe("Agent Mesh bridge configuration", () => {
  it("accepts exact local endpoints and keeps credentials out of URLs", () => {
    const config = loadBridgeConfig(environment());

    expect(config.fabricAdapterUrl).toBe(
      "ws://127.0.0.1:8765/api/v1/adapters/connect",
    );
    expect(config.fabricApiUrl).toBe("http://127.0.0.1:8765");
    expect(config.agentMeshBaseUrl).toBe("http://127.0.0.1:7342");
    expect(config.siteId).toBe("local-site");
    expect(config.pollIntervalMs).toBe(2_000);
    expect(config.projectFabricControls).toBe(false);
  });

  it("enables control projection only when the launcher opts in", () => {
    expect(
      loadBridgeConfig({
        ...environment(),
        CIT_FABRIC_CONTROL_PROJECTION: "true",
      }).projectFabricControls,
    ).toBe(true);
    expect(() =>
      loadBridgeConfig({
        ...environment(),
        CIT_FABRIC_CONTROL_PROJECTION: "yes",
      }),
    ).toThrow(/true or false/iu);
  });

  it("rejects query credentials and relative persistence paths", () => {
    expect(() =>
      loadBridgeConfig({
        ...environment(),
        CIT_FABRIC_ADAPTER_URL:
          "ws://127.0.0.1:8765/api/v1/adapters/connect?token=secret",
      }),
    ).toThrow(/exact/iu);
    expect(() =>
      loadBridgeConfig({
        ...environment(),
        CIT_BRIDGE_DATABASE_PATH: "relative.sqlite3",
      }),
    ).toThrow(/absolute/iu);
  });
});
