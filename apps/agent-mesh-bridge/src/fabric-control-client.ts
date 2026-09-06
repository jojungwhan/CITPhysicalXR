import {
  flowTargetRoles,
  validateDefinition,
  type CoursePack,
  type FlowRecipe,
  type IntegrationNode,
  type InteractionSession,
} from "@citxr/protocol";

import type { BridgeConfig } from "./config.js";
import {
  DEVICE_CONTROL_ACTIONS,
  DEVICE_CONTROL_INTENT_NAME,
  DEVICE_CONTROL_TARGETS,
} from "./device-control-contract.generated.js";
import type {
  CitFabricControlAction,
  CitFabricControlRoute,
  CitFabricDeviceControlAction,
  CitFabricDeviceControlTarget,
  CitFabricControlInventory,
  CitFabricControlTarget,
} from "./types.js";

const MAX_RESPONSE_BYTES = 1_048_576;
const CONTROL_COURSE_PACK_IDS = new Set([
  "glasses-device-control",
  "synchronized-motor-control",
]);
const CONTROL_EVENT = DEVICE_CONTROL_INTENT_NAME;
const CONTROL_ACTION_ORDER = DEVICE_CONTROL_ACTIONS.filter(
  (action): action is CitFabricControlAction => action !== "activate",
);
const GROUND_ACTIONS = new Set<CitFabricControlAction>([
  "forward",
  "backward",
  "left",
  "right",
  "stop",
  "light",
  "demo",
]);
const FLIGHT_ACTIONS = new Set<CitFabricControlAction>(["takeoff", "land"]);
const POWER_ACTIONS = new Set<CitFabricControlAction>([
  "power_on",
  "power_off",
]);
const FLEET_SEQUENCE_START = "mobility.flight.fleet_sequence.start";

export class FabricControlApiClient {
  readonly #config: BridgeConfig;
  readonly #fetch: typeof fetch;
  readonly #now: () => number;
  #coursePack: CoursePack | undefined;
  #coursePackCachedUntil = 0;

  constructor(
    config: BridgeConfig,
    fetchImplementation: typeof fetch = globalThis.fetch.bind(globalThis),
    now: () => number = Date.now,
  ) {
    this.#config = config;
    this.#fetch = fetchImplementation;
    this.#now = now;
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
    const coursePack = await this.#controlCoursePack(session);
    const byId = new Map(nodes.map((node) => [node.nodeId, node]));
    const targets = session.roleBindings.flatMap(
      (binding): CitFabricControlTarget[] => {
        const node = byId.get(binding.nodeId);
        if (node === undefined) return [];
        const actions = controlActionsForRole(coursePack, binding.role, node);
        const kind = controlTargetKind(actions);
        return kind === undefined
          ? []
          : [
              {
                role: binding.role,
                nodeId: node.nodeId,
                displayName: node.displayName,
                kind,
                connectionState: projectedConnectionState(node.connectionState),
                actions,
              },
            ];
      },
    );
    const routes = controlRoutes(coursePack, session, byId);
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
      routes,
    };
  }

  async #controlCoursePack(session: InteractionSession): Promise<CoursePack> {
    const cached = this.#coursePack;
    if (
      cached?.coursePackId === session.coursePackId &&
      cached.version === session.coursePackVersion &&
      this.#now() < this.#coursePackCachedUntil
    ) {
      return cached;
    }
    const value = await this.#request("/api/v1/fabric/course-packs");
    if (!Array.isArray(value) || value.length > 128) {
      throw new TypeError(
        "Fabric course-pack response must be a bounded array",
      );
    }
    const match = value.find(
      (candidate) =>
        isRecord(candidate) &&
        candidate.coursePackId === session.coursePackId &&
        candidate.version === session.coursePackVersion,
    );
    assertDefinition("CoursePack", match);
    this.#coursePack = match as CoursePack;
    this.#coursePackCachedUntil =
      this.#now() + Math.max(1_000, this.#config.pollIntervalMs);
    return this.#coursePack;
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
  name: "InteractionSession" | "IntegrationNode" | "CoursePack",
  value: unknown,
): void => {
  const result = validateDefinition(name, value);
  if (!result.valid) {
    throw new TypeError(`Invalid Fabric ${name}: ${result.errors.join("; ")}`);
  }
};

const controlActionsForRole = (
  coursePack: CoursePack,
  role: string,
  node: IntegrationNode,
): CitFabricControlAction[] => {
  const supportedCapabilities = new Map(
    node.consumedCapabilities.map((capability) => [
      capability.name,
      capability,
    ]),
  );
  const actions = new Set<CitFabricControlAction>();
  for (const flow of coursePack.flows) {
    if (
      !flow.enabled ||
      flow.trigger.event !== CONTROL_EVENT ||
      !flowTargetRoles(flow.target).includes(role) ||
      !supportedCapabilities.has(flow.command.action)
    ) {
      continue;
    }
    const expected = flow.trigger.payloadEquals;
    const expectedTarget = expected?.target;
    if (expectedTarget === "all_outputs") continue;
    for (const action of flowControlActions(flow, supportedCapabilities)) {
      if (isControlAction(action)) actions.add(action);
    }
  }
  const ordered = CONTROL_ACTION_ORDER.filter((action) => actions.has(action));
  return ordered.includes("takeoff") && !ordered.includes("land")
    ? ordered.filter((action) => action !== "takeoff")
    : ordered;
};

const flowControlActions = (
  flow: FlowRecipe,
  capabilities: ReadonlyMap<
    string,
    IntegrationNode["consumedCapabilities"][number]
  >,
): CitFabricDeviceControlAction[] => {
  const expectedAction = flow.trigger.payloadEquals?.action;
  if (isDeviceControlAction(expectedAction)) return [expectedAction];
  const actionBinding = flow.command.parameterBindings.find(
    (binding) => binding.payloadField === "action",
  );
  if (actionBinding === undefined) return [];
  const descriptor = capabilities.get(flow.command.action);
  const constraints = isRecord(descriptor?.constraints)
    ? descriptor.constraints
    : undefined;
  const argumentsValue = isRecord(constraints?.arguments)
    ? constraints.arguments
    : undefined;
  const parameterValue = argumentsValue?.[actionBinding.parameter];
  if (!isRecord(parameterValue)) return [];
  const enumValues = parameterValue.enum;
  const values = Array.isArray(enumValues) ? enumValues : [];
  return values.filter(isDeviceControlAction);
};

const controlRoutes = (
  coursePack: CoursePack,
  session: InteractionSession,
  nodesById: ReadonlyMap<string, IntegrationNode>,
): CitFabricControlRoute[] => {
  const nodesByRole = new Map(
    session.roleBindings.flatMap((binding) => {
      const node = nodesById.get(binding.nodeId);
      return node?.connectionState === "connected"
        ? [[binding.role, node] as const]
        : [];
    }),
  );
  const routes = new Map<
    string,
    {
      target: CitFabricDeviceControlTarget;
      targetRole?: string;
      actions: Set<CitFabricDeviceControlAction>;
    }
  >();
  for (const flow of coursePack.flows) {
    if (!flow.enabled || flow.trigger.event !== CONTROL_EVENT) continue;
    const expected = flow.trigger.payloadEquals;
    if (!isDeviceControlTarget(expected?.target)) continue;
    const expectedRole = expected?.targetRole;
    for (const role of flowTargetRoles(flow.target)) {
      if (
        expected.target === "assigned_output" &&
        typeof expectedRole === "string" &&
        expectedRole !== role
      ) {
        continue;
      }
      const node = nodesByRole.get(role);
      if (node === undefined) continue;
      const capabilities = new Map(
        node.consumedCapabilities.map((capability) => [
          capability.name,
          capability,
        ]),
      );
      if (!capabilities.has(flow.command.action)) continue;
      const actions = flowControlActions(flow, capabilities);
      if (actions.length === 0) continue;
      const safeRoleActions = controlActionsForRole(coursePack, role, node);
      const targetRole =
        expected.target === "assigned_output" ? role : undefined;
      const key = `${expected.target}\u0000${targetRole ?? ""}`;
      const route = routes.get(key) ?? {
        target: expected.target,
        ...(targetRole === undefined ? {} : { targetRole }),
        actions: new Set<CitFabricDeviceControlAction>(),
      };
      for (const action of actions) {
        const startsFlight =
          action === "takeoff" ||
          (action === "activate" &&
            flow.command.action === FLEET_SEQUENCE_START);
        if (startsFlight && !safeRoleActions.includes("takeoff")) continue;
        route.actions.add(action);
      }
      if (route.actions.size === 0) continue;
      routes.set(key, route);
    }
  }
  return [...routes.values()].map((route) => ({
    target: route.target,
    ...(route.targetRole === undefined ? {} : { targetRole: route.targetRole }),
    actions: [...route.actions],
  }));
};

const isDeviceControlAction = (
  value: unknown,
): value is CitFabricDeviceControlAction =>
  typeof value === "string" &&
  DEVICE_CONTROL_ACTIONS.includes(value as CitFabricDeviceControlAction);

const isDeviceControlTarget = (
  value: unknown,
): value is CitFabricDeviceControlTarget =>
  typeof value === "string" &&
  DEVICE_CONTROL_TARGETS.includes(value as CitFabricDeviceControlTarget);

const isControlAction = (value: unknown): value is CitFabricControlAction =>
  isDeviceControlAction(value) &&
  value !== "activate" &&
  CONTROL_ACTION_ORDER.includes(value as CitFabricControlAction);

const controlTargetKind = (
  actions: readonly CitFabricControlAction[],
): CitFabricControlTarget["kind"] | undefined => {
  if (actions.length === 0) return undefined;
  if (actions.every((action) => GROUND_ACTIONS.has(action)))
    return "ground_robot";
  if (actions.every((action) => FLIGHT_ACTIONS.has(action))) {
    if (actions.includes("takeoff") && !actions.includes("land"))
      return undefined;
    return "drone_fleet";
  }
  if (actions.every((action) => POWER_ACTIONS.has(action))) return "smart_plug";
  throw new TypeError(
    "One Fabric control role mixes incompatible output kinds",
  );
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const projectedConnectionState = (
  value: IntegrationNode["connectionState"],
): CitFabricControlTarget["connectionState"] => {
  if (value === "connected" || value === "degraded" || value === "disconnected")
    return value;
  return "unavailable";
};
