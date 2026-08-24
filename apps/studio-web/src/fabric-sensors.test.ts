import { describe, expect, it } from "vitest";

import type { StoredFabricEvent } from "./fabric-client.js";
import { latestSensorReadings } from "./fabric-sensors.js";

describe("Fabric sensor presentation", () => {
  it("includes canonical robot sensor events", () => {
    const readings = latestSensorReadings([
      event(1, "wonder-dash-a", "robot.sensor.state", {
        values: { proximityLeft: 42, pickedUp: false },
      }),
    ]);

    expect(readings).toHaveLength(1);
    expect(readings[0]?.sourceNodeId).toBe("wonder-dash-a");
    expect(readings[0]?.values).toEqual([
      { label: "Proximity Left", value: "42" },
      { label: "Picked Up", value: "Off" },
    ]);
  });

  it("keeps the latest value for every source and semantic sensor", () => {
    const readings = latestSensorReadings([
      event(1, "lego-a", "sensor.distance", { value: 320, unit: "mm" }),
      event(2, "lego-a", "sensor.distance", { value: 180, unit: "mm" }),
      event(3, "lego-a", "sensor.color", { color: "red" }),
      event(4, "plug-a", "power.switch.state", { on: true }),
    ]);

    expect(readings).toEqual([
      {
        key: "lego-a:sensor.color",
        sourceNodeId: "lego-a",
        topic: "sensor.color",
        observedAt: "2026-08-22T00:00:03Z",
        values: [{ label: "Color", value: "red" }],
      },
      {
        key: "lego-a:sensor.distance",
        sourceNodeId: "lego-a",
        topic: "sensor.distance",
        observedAt: "2026-08-22T00:00:02Z",
        values: [{ label: "Value", value: "180 mm" }],
      },
    ]);
  });

  it("does not surface raw media-shaped payload fields", () => {
    const [reading] = latestSensorReadings([
      event(1, "sensor-a", "telemetry.status", {
        battery: 71,
        image: "base64-data",
        token: "secret",
      }),
    ]);

    expect(reading?.values).toEqual([{ label: "Battery", value: "71" }]);
  });

  it("shows normalized vendor-labelled MindWave readings", () => {
    const readings = latestSensorReadings([
      event(1, "mindwave-a", "mindwave.esense.attention", {
        value: 64,
        vendor: "NeuroSky",
      }),
      event(2, "mindwave-a", "mindwave.signal.quality", {
        value: 96,
        unit: "percent",
      }),
    ]);

    expect(readings.map((reading) => reading.topic)).toEqual([
      "mindwave.signal.quality",
      "mindwave.esense.attention",
    ]);
  });

  it("shows standard Matter electrical telemetry from a Tapo P110M", () => {
    const [reading] = latestSensorReadings([
      event(1, "matter-6e-ep1", "telemetry.power.electrical", {
        activePowerWatts: 12.345,
        voltageVolts: 230.1,
        activeCurrentAmperes: 0.537,
        cumulativeEnergyKilowattHours: 12.345678,
        frequencyHertz: 50,
        powerFactorRatio: 0.9876,
        standard: "Matter 1.3",
      }),
    ]);

    expect(reading?.values).toEqual([
      { label: "Active Power Watts", value: "12.35" },
      { label: "Voltage Volts", value: "230.10" },
      { label: "Active Current Amperes", value: "0.54" },
      { label: "Cumulative Energy Kilowatt Hours", value: "12.35" },
      { label: "Frequency Hertz", value: "50" },
      { label: "Power Factor Ratio", value: "0.99" },
    ]);
  });
});

const event = (
  streamSequence: number,
  sourceNodeId: string,
  topic: string,
  payload: Record<string, unknown>,
): StoredFabricEvent => ({
  streamSequence,
  event: {
    messageId: `00000000-0000-4000-8000-${String(streamSequence).padStart(12, "0")}`,
    schemaVersion: "1.0",
    messageType: "event",
    topic,
    sourceNodeId,
    sourceCapability: topic,
    siteId: "cit-site",
    roomId: "room-a",
    sessionId: "00000000-0000-4000-8000-000000000001",
    timestamp: `2026-08-22T00:00:0${streamSequence}Z`,
    monotonicTimestamp: streamSequence,
    sequence: streamSequence,
    ttlMs: 1_000,
    dataClassification: "operational",
    payload,
  },
});
