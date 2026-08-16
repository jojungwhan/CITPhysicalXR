import { describe, expect, it } from "vitest";

import { catalog } from "./i18n.js";
import type { DeviceView, HealthView, SessionView } from "./runtime-client.js";
import { safetyStateOf } from "./SafetyBanner.js";

const HEALTH: HealthView = {
  status: "ok",
  runtimeId: "cit-runtime-local",
  protocolVersion: 1,
  executionMode: "physical",
  physicalEnabled: true,
};

function device(overrides: Partial<DeviceView> = {}): DeviceView {
  return {
    deviceId: "fake-s1-main",
    displayName: "Fake S1",
    deviceType: "robot",
    model: "robomaster-s1",
    physical: true,
    state: "connected",
    capabilities: [],
    assignedSessionId: null,
    armed: false,
    armExpiresAt: null,
    failureReason: null,
    ...overrides,
  };
}

function session(state: string): SessionView {
  return {
    sessionId: "session-1",
    projectId: "p",
    state,
    authoringMode: "blocks",
    executionMode: "physical",
    userId: "student-1",
    instructorId: null,
    safetyPolicyId: "simulation-only",
    failurePolicy: "stop_coordinated",
    deviceBindings: [],
    startedAt: "2026-01-01T00:00:00+00:00",
    lastActivityAt: "2026-01-01T00:00:00+00:00",
    endedAt: null,
  };
}

describe("safety state (UI 11.4)", () => {
  it("is simulation before the runtime has answered", () => {
    expect(safetyStateOf({ health: null, devices: [], sessions: [] })).toBe(
      "simulation",
    );
  });

  it("is simulation when the runtime has no physical devices enabled", () => {
    expect(
      safetyStateOf({
        health: {
          ...HEALTH,
          physicalEnabled: false,
          executionMode: "simulation",
        },
        devices: [device()],
        sessions: [],
      }),
    ).toBe("simulation");
  });

  it("is simulation when physical is enabled but nothing physical is present", () => {
    expect(
      safetyStateOf({
        health: HEALTH,
        devices: [device({ physical: false })],
        sessions: [],
      }),
    ).toBe("simulation");
  });

  it("is disarmed while a real device is connected but not armed", () => {
    expect(
      safetyStateOf({ health: HEALTH, devices: [device()], sessions: [] }),
    ).toBe("physicalDisarmed");
  });

  it("is armed as soon as any real device is armed", () => {
    expect(
      safetyStateOf({
        health: HEALTH,
        devices: [device(), device({ deviceId: "b", armed: true })],
        sessions: [],
      }),
    ).toBe("physicalArmed");
  });

  it("is emergency stopped whatever else is true", () => {
    expect(
      safetyStateOf({
        health: HEALTH,
        devices: [device({ armed: true })],
        sessions: [session("emergency_stopped")],
      }),
    ).toBe("emergencyStopped");
  });

  it("has a word and a sentence for every state in both languages", () => {
    const states = [
      "simulation",
      "physicalDisarmed",
      "physicalArmed",
      "emergencyStopped",
    ] as const;
    for (const locale of ["en", "ko"] as const) {
      const messages = catalog(locale);
      for (const state of states) {
        expect(messages[`safety.${state}`]).toBeTruthy();
        expect(messages[`safety.${state}Meaning`]).toBeTruthy();
      }
    }
  });
});
