import {
  validateDefinition,
  type IntegrationNode,
  type InteractionSession,
} from "@citxr/protocol";

import type { BridgeConfig } from "./config.js";
import type {
  CitFabricControlAction,
  CitFabricControlInventory,
  CitFabricControlTarget,
} from "./types.js";

const MAX_RESPONSE_BYTES = 1_048_576;
const CONTROL_COURSE_PACK_IDS = new Set([
  "glasses-device-control",
  "synchronized-motor-control",
]);
const GROUND_ROLE = /^ground_output_[1-8]$/u;
const POWER_ROLE = /^power_output_[1-8]$/u;
const FLEET_ROLE = "fleet_sequence_controller";
const GROUND_NUDGE = "mobility.ground.nudge";
const GROUND_DEMO = "mobility.ground.demonstration.start";
const ROBOT_LIGHT = "robot.light.set";
const FLEET_START = "mobility.flight.fleet_sequence.start";
const FLEET_STOP = "mobility.flight.fleet_sequence.stop";
const POWER_SET = "power.switch.set";

export class FabricControlApiClient {
  readonly #config: BridgeConfig;
  readonly #fetch: typeof fetch;

  constructor(
    config: BridgeConfig,
    fetchImplementation: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {
    this.#config = config;
    this.#fetch = fetchImplementation;
  }

  async inventory(): Promise<CitFabricControlInventory> {
    const [sessionValue, nodesValue] = await Promise.all([
      this.#request(
        `/api/v1/fabric/sessions/${encodeURIComponent(this.#config.fabricSessionId)}`,
      ),
      this.#request(
        `/api/v1/fabric/nodes?${new URLSearchParams({
          siteId: this.#config.siteId,
          roomId: this.#config.roomId,
        }).toString()}`,
      ),
    ]);
    assertDefinition("InteractionSession", sessionValue);
    const session = sessionValue as InteractionSession;
    if (!CONTROL_COURSE_PACK_IDS.has(session.coursePackId)) {
      throw new TypeError("Fabric session is not a device-control lesson");
    }
    if (
      session.siteId !== this.#config.siteId ||
      session.roomId !== this.#config.roomId
    ) {
      throw new TypeError(
        "Fabric control session is outside the configured room",
      );
    }
    if (!Array.isArray(nodesValue) || nodesValue.length > 256) {
      throw new TypeError("Fabric nodes response must be a bounded array");
    }
    const nodes = nodesValue.map((node) => {
      assertDefinition("IntegrationNode", node);
      const validNode = node as IntegrationNode;
      if (
        validNode.siteId !== this.#config.siteId ||
        validNode.roomId !== this.#config.roomId
      ) {
        throw new TypeError(
          "Fabric control node is outside the configured room",
        );
      }
      return validNode;
    });
    const byId = new Map(nodes.map((node) => [node.nodeId, node]));
    const targets = session.roleBindings.flatMap(
      (binding): CitFabricControlTarget[] => {
        const node = byId.get(binding.nodeId);
        if (node === undefined) return [];
        const capabilities = new Set(
          node.consumedCapabilities.map((capability) => capability.name),
        );
        if (GROUND_ROLE.test(binding.role) && capabilities.has(GROUND_NUDGE)) {
          const actions: CitFabricControlAction[] = [
            "forward",
            "backward",
            "left",
            "right",
            "stop",
            ...(capabilities.has(ROBOT_LIGHT) ? (["light"] as const) : []),
            ...(capabilities.has(GROUND_DEMO) ? (["demo"] as const) : []),
          ];
          return [
            {
              role: binding.role,
              nodeId: node.nodeId,
              displayName: node.displayName,
              kind: "ground_robot",
              connectionState: projectedConnectionState(node.connectionState),
              actions,
            },
          ];
        }
        if (
          binding.role === FLEET_ROLE &&
          capabilities.has(FLEET_START) &&
          capabilities.has(FLEET_STOP)
        ) {
          return [
            {
              role: binding.role,
              nodeId: node.nodeId,
              displayName: node.displayName,
              kind: "drone_fleet",
              connectionState: projectedConnectionState(node.connectionState),
              actions: ["takeoff", "land"],
            },
          ];
        }
        if (POWER_ROLE.test(binding.role) && capabilities.has(POWER_SET)) {
          return [
            {
              role: binding.role,
              nodeId: node.nodeId,
              displayName: node.displayName,
              kind: "smart_plug",
              connectionState: projectedConnectionState(node.connectionState),
              actions: ["power_on", "power_off"],
            },
          ];
        }
        return [];
      },
    );
    const generatedAt = new Date();
    return {
      generatedAt: generatedAt.toISOString(),
      expiresAt: new Date(
        generatedAt.getTime() +
          Math.max(10_000, this.#config.pollIntervalMs * 4),
      ).toISOString(),
      sessionId: session.sessionId,
      coursePackId:
        session.coursePackId as CitFabricControlInventory["coursePackId"],
      sessionState: session.state,
      armed: session.armed ?? false,
      targets,
    };
  }

  async #request(path: string): Promise<unknown> {
    const response = await this.#fetch(`${this.#config.fabricApiUrl}${path}`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.timeout(10_000),
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${this.#config.fabricReadCredential}`,
      },
    });
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > MAX_RESPONSE_BYTES) {
      throw new Error("Fabric control response exceeded the size limit");
    }
    let value: unknown;
    try {
      value = text ? JSON.parse(text) : undefined;
    } catch {
      throw new Error("Fabric control response was not JSON");
    }
    if (!response.ok) {
      throw new Error(
        `Fabric control request failed with HTTP ${response.status}`,
      );
    }
    return value;
  }
}

const assertDefinition = (
  name: "InteractionSession" | "IntegrationNode",
  value: unknown,
): void => {
  const result = validateDefinition(name, value);
  if (!result.valid) {
    throw new TypeError(`Invalid Fabric ${name}: ${result.errors.join("; ")}`);
  }
};

const projectedConnectionState = (
  value: IntegrationNode["connectionState"],
): CitFabricControlTarget["connectionState"] => {
  if (value === "connected" || value === "degraded" || value === "disconnected")
    return value;
  return "unavailable";
};
