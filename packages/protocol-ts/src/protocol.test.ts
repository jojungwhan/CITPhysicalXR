import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type {
  AdapterRegistrationFrame,
  CitEnvelope,
  CoursePack,
  DeviceCommandIntent,
  DeviceDescriptor,
  DeviceEvent,
  FabricEventEnvelope,
  IntegrationNode,
  PluginManifest,
} from "./generated/models.js";
import { flowTargetRoles } from "./flow-target.js";
import { validateDefinition } from "./validator.js";

const fixture = <Value>(name: string): Value => {
  const url = new URL(
    `../../protocol-schema/fixtures/${name}`,
    import.meta.url,
  );
  return JSON.parse(readFileSync(fileURLToPath(url), "utf8")) as Value;
};

describe("protocol v1 public seam", () => {
  it("validates the same envelope, command, event, and device fixtures as generated types", () => {
    const envelope = fixture<CitEnvelope>("valid-envelope.json");
    const command = fixture<DeviceCommandIntent>("valid-command.json");
    const event = fixture<DeviceEvent>("valid-event.json");
    const device = fixture<DeviceDescriptor>("valid-device.json");

    expect(validateDefinition("CitEnvelope", envelope)).toEqual({
      valid: true,
    });
    expect(validateDefinition("DeviceCommandIntent", command)).toEqual({
      valid: true,
    });
    expect(validateDefinition("DeviceEvent", event)).toEqual({ valid: true });
    expect(validateDefinition("DeviceDescriptor", device)).toEqual({
      valid: true,
    });
    expect(command.deviceId).toBe("fake-s1-main");
  });

  it("validates transport-neutral Fabric and adapter contracts", () => {
    const manifest = fixture<PluginManifest>("valid-plugin-manifest.json");
    const node = fixture<IntegrationNode>("valid-integration-node.json");
    const event = fixture<FabricEventEnvelope>("valid-fabric-event.json");
    const coursePack = fixture<CoursePack>("valid-course-pack.json");
    const registration = fixture<AdapterRegistrationFrame>(
      "valid-adapter-registration.json",
    );

    expect(validateDefinition("PluginManifest", manifest)).toEqual({
      valid: true,
    });
    expect(validateDefinition("IntegrationNode", node)).toEqual({
      valid: true,
    });
    expect(validateDefinition("FabricEventEnvelope", event)).toEqual({
      valid: true,
    });
    expect(validateDefinition("CoursePack", coursePack)).toEqual({
      valid: true,
    });
    expect(
      validateDefinition("AdapterRegistrationFrame", registration),
    ).toEqual({
      valid: true,
    });
    expect(registration.nodes[0]?.pluginId).toBe(manifest.pluginId);
    const firstTarget = coursePack.flows[0]?.target;
    expect(
      firstTarget !== undefined && "role" in firstTarget
        ? firstTarget.role
        : undefined,
    ).toBe("coding_agent");
  });

  it("validates bounded group and payload-selected flow targets", () => {
    const groupPack = fixture<CoursePack>("valid-course-pack.json");
    const groupFlow = groupPack.flows[0];
    if (groupFlow === undefined) throw new Error("course fixture has no flow");
    groupFlow.target = {
      roles: ["coding_agent", "coding_agent_2"],
      requiredCapability: "agent.prompt.submit",
    };
    groupFlow.outputRoles = ["coding_agent", "coding_agent_2"];

    expect(validateDefinition("CoursePack", groupPack)).toEqual({
      valid: true,
    });
    expect(flowTargetRoles(groupFlow.target)).toEqual([
      "coding_agent",
      "coding_agent_2",
    ]);

    const selectedPack = structuredClone(groupPack);
    const selectedFlow = selectedPack.flows[0];
    if (selectedFlow === undefined)
      throw new Error("course fixture has no flow");
    selectedFlow.target = {
      roleFromPayload: "targetRole",
      allowedRoles: ["coding_agent", "coding_agent_2"],
      requiredCapability: "agent.prompt.submit",
    };

    expect(validateDefinition("CoursePack", selectedPack)).toEqual({
      valid: true,
    });
    expect(flowTargetRoles(selectedFlow.target)).toEqual([
      "coding_agent",
      "coding_agent_2",
    ]);
    expect(
      validateDefinition("FlowPayloadRoleTarget", {
        roleFromPayload: "targetRole",
        allowedRoles: [],
      }).valid,
    ).toBe(false);
  });

  it("rejects an unknown major version and a command without exact device identity", () => {
    const envelope = fixture<Record<string, unknown>>("valid-envelope.json");
    const command = fixture<Record<string, unknown>>("valid-command.json");
    delete command.deviceId;

    const version = validateDefinition("CitEnvelope", {
      ...envelope,
      protocolVersion: 2,
    });
    const identity = validateDefinition("DeviceCommandIntent", command);

    expect(version.valid).toBe(false);
    expect(identity.valid).toBe(false);
  });
});
