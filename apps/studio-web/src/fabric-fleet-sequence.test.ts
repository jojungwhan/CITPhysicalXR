import { describe, expect, it } from "vitest";

import type { StoredFabricEvent } from "./fabric-client.js";
import {
  FLEET_SEQUENCE_ARM_CAPABILITY,
  FLEET_SEQUENCE_START_CAPABILITY,
  FLEET_SEQUENCE_STATUS_CAPABILITY,
  FLEET_SEQUENCE_STOP_CAPABILITY,
  isFleetSequenceControllerNode,
  latestFleetSequenceStatus,
} from "./fabric-fleet-sequence.js";

describe("bounded fleet-sequence UI boundary", () => {
  it("recognizes only a controller without raw flight actions", () => {
    const node = (consumed: string[]) =>
      ({
        pluginId: "cit.brain2devices-fleet",
        consumedCapabilities: consumed.map((name) => ({ name })),
      }) as Parameters<typeof isFleetSequenceControllerNode>[0];

    expect(
      isFleetSequenceControllerNode(
        node([
          FLEET_SEQUENCE_ARM_CAPABILITY,
          FLEET_SEQUENCE_START_CAPABILITY,
          FLEET_SEQUENCE_STOP_CAPABILITY,
        ]),
      ),
    ).toBe(true);
    expect(
      isFleetSequenceControllerNode(
        node([
          FLEET_SEQUENCE_ARM_CAPABILITY,
          FLEET_SEQUENCE_START_CAPABILITY,
          FLEET_SEQUENCE_STOP_CAPABILITY,
          "mobility.flight.takeoff",
        ]),
      ),
    ).toBe(false);
  });

  it("projects the latest ordered-aircraft status", () => {
    const events = [statusEvent(1, "armed"), statusEvent(2, "launching")];

    expect(latestFleetSequenceStatus(events, "fleet-a")).toMatchObject({
      armed: false,
      active: true,
      phase: "launching",
      selectedDroneIds: ["primary", "drone-2"],
      launchedDroneIds: ["primary"],
      availableDrones: [
        {
          id: "primary",
          label: "Front Tello",
          connection: "connected",
          flight: "flying",
          batteryPercent: 82,
        },
      ],
    });
  });
});

const statusEvent = (
  streamSequence: number,
  phase: "armed" | "launching",
): StoredFabricEvent => ({
  streamSequence,
  event: {
    messageId: `00000000-0000-4000-8000-${String(streamSequence).padStart(12, "0")}`,
    schemaVersion: "1.0",
    messageType: "event",
    topic: FLEET_SEQUENCE_STATUS_CAPABILITY,
    sourceNodeId: "fleet-a",
    sourceCapability: FLEET_SEQUENCE_STATUS_CAPABILITY,
    siteId: "cit-site",
    roomId: "room-a",
    sessionId: "00000000-0000-4000-8000-000000000001",
    timestamp: `2026-08-23T00:00:0${streamSequence}Z`,
    monotonicTimestamp: streamSequence,
    sequence: streamSequence,
    ttlMs: 2_000,
    dataClassification: "operational",
    payload: {
      available: true,
      active: phase === "launching",
      armed: phase === "armed",
      phase,
      progress: phase === "armed" ? 0 : 0.5,
      message: phase,
      selectedDroneIds: ["primary", "drone-2"],
      launchedDroneIds: phase === "launching" ? ["primary"] : [],
      landRequestedDroneIds: [],
      triggeredBy: phase === "launching" ? "leap-a" : null,
      simulated: false,
      availableDrones: [
        {
          id: "primary",
          label: "Front Tello",
          connection: "connected",
          flight: phase === "launching" ? "flying" : "landed",
          batteryPercent: 82,
        },
      ],
    },
  },
});
