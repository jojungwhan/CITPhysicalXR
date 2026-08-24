import { describe, expect, it } from "vitest";

import type { StoredFabricEvent } from "./fabric-client.js";
import {
  latestLeapTracking,
  leapHandGeometry,
  type LeapHandSample,
} from "./fabric-leap.js";

describe("Leap Motion live hand presentation", () => {
  it("uses the newest valid reduced hand sample from an allowed Leap node", () => {
    const reading = latestLeapTracking(
      [
        event(1, "leap-a", false),
        event(3, "leap-a", true),
        event(4, "other", true),
      ],
      new Set(["leap-a"]),
    );

    expect(reading?.streamSequence).toBe(3);
    expect(reading?.tracking).toBe(true);
    expect(reading?.hand?.handedness).toBe("right");
    expect(reading?.hand?.palmMillimeters).toEqual({ x: 25, y: 180, z: -120 });
    expect(reading?.command).toEqual({
      forwardMetersPerSecond: 0.1,
      rightMetersPerSecond: -0.05,
      clockwiseRadiansPerSecond: 0.2,
    });
  });

  it("rejects a tracking claim without a validated hand object", () => {
    const malformed = event(2, "leap-a", true);
    malformed.event.payload = {
      ...malformed.event.payload,
      hand: { handedness: "right", palmMillimeters: { x: 0, y: 0, z: 0 } },
    };

    expect(latestLeapTracking([malformed])).toBeUndefined();
  });

  it("bounds visual geometry even when the palm leaves the preferred area", () => {
    const geometry = leapHandGeometry({
      ...hand(),
      palmMillimeters: { x: 9_000, y: 180, z: -9_000 },
      yawDegrees: 200,
      grabStrength: 1,
      pinchDistanceMillimeters: 0,
    });

    expect(geometry).toEqual({
      xPercent: 94,
      yPercent: 6,
      rotationDegrees: 90,
      fingerExtension: 0.28,
      pinchGap: 0.12,
    });
  });
});

const hand = (): LeapHandSample => ({
  handId: 7,
  handedness: "right",
  visibleTimeSeconds: 1.2,
  palmMillimeters: { x: 25, y: 180, z: -120 },
  velocityMillimetersPerSecond: { x: 1, y: 2, z: 3 },
  direction: { x: 0, y: 0, z: -1 },
  palmNormal: { x: 0, y: 1, z: 0 },
  pinchStrength: 0.82,
  grabStrength: 0.16,
  pinchDistanceMillimeters: 22,
  yawDegrees: 5,
});

const event = (
  streamSequence: number,
  sourceNodeId: string,
  tracking: boolean,
): StoredFabricEvent => ({
  streamSequence,
  event: {
    messageId: `00000000-0000-4000-8000-${String(streamSequence).padStart(12, "0")}`,
    schemaVersion: "1.0",
    messageType: "event",
    topic: "interaction.gesture.velocity",
    sourceNodeId,
    sourceCapability: "interaction.gesture.velocity",
    siteId: "cit-site",
    roomId: "room-a",
    sessionId: "00000000-0000-4000-8000-000000000001",
    timestamp: `2026-08-24T00:00:0${streamSequence}Z`,
    monotonicTimestamp: streamSequence,
    sequence: streamSequence,
    confidence: 0.95,
    ttlMs: 1_000,
    dataClassification: "operational",
    payload: {
      forwardMetersPerSecond: 0.1,
      rightMetersPerSecond: -0.05,
      clockwiseRadiansPerSecond: 0.2,
      state: tracking ? "DRIVING" : "WAITING",
      reason: tracking ? "pinch held" : "no hand",
      tracking,
      sensorFrameRateHertz: 115,
      totalHandCount: tracking ? 1 : 0,
      serviceConnected: true,
      devicePresent: true,
      hand: tracking ? hand() : null,
    },
  },
});
