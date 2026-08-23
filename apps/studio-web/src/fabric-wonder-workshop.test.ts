import { describe, expect, it } from "vitest";

import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import {
  selectableWonderCandidates,
  wonderCandidateModel,
  wonderControlAvailability,
} from "./fabric-wonder-workshop.js";

const candidate = (
  candidateId: string,
  model: FabricDiscoveryCandidate["model"],
  status: FabricDiscoveryCandidate["status"] = "found",
): FabricDiscoveryCandidate => ({
  candidateId,
  displayName: "Classroom robot",
  transport: "Bluetooth Low Energy",
  status,
  detail: "Read-only advertisement",
  ...(model === undefined ? {} : { model }),
});

describe("Wonder Workshop UI policy", () => {
  it("selects only exact opaque Dash and Dot candidates", () => {
    const values = [
      candidate("wonder-aabbccddeeff", "dash"),
      candidate("wonder-001122334455", "dot"),
      candidate("wonder-paired-1", undefined),
      candidate("wonder-ffffffffffff", "dot", "setup_required"),
    ];

    expect(
      selectableWonderCandidates(values).map((item) => item.candidateId),
    ).toEqual(["wonder-aabbccddeeff", "wonder-001122334455"]);
    expect(wonderCandidateModel(values[0]!)).toBe("dash");
    expect(wonderCandidateModel(values[2]!)).toBeUndefined();
  });

  it("keeps physical controls locked until active and armed", () => {
    const physicalNode = { simulated: false } as Parameters<
      typeof wonderControlAvailability
    >[0];
    const simulatedNode = { simulated: true } as Parameters<
      typeof wonderControlAvailability
    >[0];

    expect(wonderControlAvailability(physicalNode, "active", false)).toEqual({
      light: true,
      physical: false,
      stop: true,
    });
    expect(
      wonderControlAvailability(physicalNode, "active", true).physical,
    ).toBe(true);
    expect(
      wonderControlAvailability(simulatedNode, "active", false).physical,
    ).toBe(true);
  });
});
