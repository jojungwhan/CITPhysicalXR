import { describe, expect, it, vi } from "vitest";

import { AgentMeshApiClient } from "./agent-mesh-client.js";

describe("Agent Mesh control interaction parsing", () => {
  it("accepts an exact confirmed smart-plug action from G2", async () => {
    const interaction = {
      interactionId: "c414232b-d0c7-40b6-8868-207276350ed3",
      sequence: 1,
      deviceId: "g2-controls",
      deviceKind: "even_g2",
      deviceDisplayName: "CIT controls · G2",
      source: "device_control",
      action: "power_off",
      target: "assigned_output",
      targetRole: "power_output_2",
      confirmed: true,
      createdAt: "2026-08-26T00:00:00.000Z",
    };
    const fetchImplementation = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ interactions: [interaction], nextCursor: 1 }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    const feed = await new AgentMeshApiClient(
      "http://127.0.0.1:7342",
      `device_${"a".repeat(43)}`,
      fetchImplementation,
    ).interactions(0);

    expect(feed).toEqual({ interactions: [interaction], nextCursor: 1 });
  });
});
