import type {
  AgentMeshCompletion,
  AgentMeshCompletionFeed,
  AgentMeshDiscovery,
  AgentMeshIntent,
  AgentMeshIntentFeed,
  AgentMeshSession,
  AgentMeshWearable,
} from "./types.js";

const MAX_RESPONSE_BYTES = 1_048_576;

export class AgentMeshApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(`Agent Mesh request failed with ${code} (HTTP ${status})`);
    this.name = "AgentMeshApiError";
    this.status = status;
    this.code = code;
  }
}

export class AgentMeshApiClient {
  readonly #baseUrl: string;
  readonly #token: string;
  readonly #fetch: typeof fetch;

  constructor(
    baseUrl: string,
    token: string,
    fetchImplementation: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {
    this.#baseUrl = baseUrl.replace(/\/$/u, "");
    this.#token = token;
    this.#fetch = fetchImplementation;
  }

  async discovery(): Promise<AgentMeshDiscovery> {
    const value = record(
      await this.#request("GET", "/api/v1/wearables/cit-fabric/discovery"),
      "discovery",
    );
    return {
      generatedAt: dateTime(value.generatedAt, "generatedAt"),
      wearables: array(value.wearables, "wearables").map(parseWearable),
      sessions: array(value.sessions, "sessions").map(parseSession),
    };
  }

  async intents(afterSequence: number): Promise<AgentMeshIntentFeed> {
    const query = new URLSearchParams({
      after: String(afterSequence),
      limit: "100",
    });
    const value = record(
      await this.#request(
        "GET",
        `/api/v1/wearables/cit-fabric/intents?${query.toString()}`,
      ),
      "intent feed",
    );
    return {
      intents: array(value.intents, "intents").map(parseIntent),
      nextCursor: nonnegativeInteger(value.nextCursor, "nextCursor"),
    };
  }

  async acknowledgeIntent(intentId: string): Promise<void> {
    const value = record(
      await this.#request(
        "POST",
        `/api/v1/wearables/cit-fabric/intents/${encodeURIComponent(intentId)}/ack`,
      ),
      "intent acknowledgement",
    );
    if (value.intentId !== intentId || value.acknowledged !== true) {
      throw new TypeError(
        "Agent Mesh returned an invalid intent acknowledgement",
      );
    }
  }

  async completions(afterSequence: number): Promise<AgentMeshCompletionFeed> {
    const query = new URLSearchParams({
      after: String(afterSequence),
      limit: "100",
    });
    const value = record(
      await this.#request(
        "GET",
        `/api/v1/wearables/notifications?${query.toString()}`,
      ),
      "completion feed",
    );
    return {
      notifications: array(value.notifications, "notifications").map(
        parseCompletion,
      ),
      nextCursor: nonnegativeInteger(value.nextCursor, "nextCursor"),
    };
  }

  async #request(
    method: "GET" | "POST",
    path: string,
    body?: Record<string, unknown>,
  ): Promise<unknown> {
    const response = await this.#fetch(`${this.#baseUrl}${path}`, {
      method,
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.timeout(10_000),
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${this.#token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const declaredLength = Number(response.headers.get("Content-Length") ?? 0);
    if (
      Number.isFinite(declaredLength) &&
      declaredLength > MAX_RESPONSE_BYTES
    ) {
      throw new AgentMeshApiError(502, "RESPONSE_TOO_LARGE");
    }
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > MAX_RESPONSE_BYTES) {
      throw new AgentMeshApiError(502, "RESPONSE_TOO_LARGE");
    }
    let value: unknown;
    try {
      value = text ? JSON.parse(text) : undefined;
    } catch {
      throw new AgentMeshApiError(502, "INVALID_RESPONSE");
    }
    if (!response.ok) {
      const error =
        isRecord(value) && isRecord(value.error) ? value.error : undefined;
      const code =
        error !== undefined && typeof error.code === "string"
          ? error.code
          : "AGENT_MESH_REQUEST_FAILED";
      throw new AgentMeshApiError(response.status, code);
    }
    return value;
  }
}

const parseWearable = (value: unknown): AgentMeshWearable => {
  const item = record(value, "wearable");
  const lastUsedAt = optionalDateTime(item.lastUsedAt, "lastUsedAt");
  return {
    deviceId: string(item.deviceId, "deviceId"),
    displayName: string(item.displayName, "displayName"),
    kind: oneOf(item.kind, ["even_g2", "ray_ban"] as const, "kind"),
    status: oneOf(
      item.status,
      ["active", "expired", "revoked"] as const,
      "status",
    ),
    ...(lastUsedAt === undefined ? {} : { lastUsedAt }),
  };
};

const parseSession = (value: unknown): AgentMeshSession => {
  const item = record(value, "session");
  const sessionName = optionalString(item.sessionName, "sessionName");
  const displayText = optionalString(item.displayText, "displayText");
  return {
    sessionId: string(item.sessionId, "sessionId"),
    agent: oneOf(item.agent, ["codex", "claude"] as const, "agent"),
    nodeId: string(item.nodeId, "nodeId"),
    nodeName: string(item.nodeName, "nodeName"),
    workspaceId: string(item.workspaceId, "workspaceId"),
    workspaceName: string(item.workspaceName, "workspaceName"),
    ...(sessionName === undefined ? {} : { sessionName }),
    state: string(item.state, "state"),
    controlStatus: oneOf(
      item.controlStatus,
      ["managed", "observed", "disconnected", "unsupported"] as const,
      "controlStatus",
    ),
    headline: string(item.headline, "headline"),
    ...(displayText === undefined ? {} : { displayText }),
    lastActivityAt: dateTime(item.lastActivityAt, "lastActivityAt"),
  };
};

const parseIntent = (value: unknown): AgentMeshIntent => {
  const item = record(value, "intent");
  return {
    intentId: uuid(item.intentId, "intentId"),
    sequence: positiveInteger(item.sequence, "sequence"),
    deviceId: string(item.deviceId, "deviceId"),
    deviceKind: oneOf(
      item.deviceKind,
      ["even_g2", "ray_ban"] as const,
      "deviceKind",
    ),
    deviceDisplayName: string(item.deviceDisplayName, "deviceDisplayName"),
    requestedSessionId: string(item.requestedSessionId, "requestedSessionId"),
    dispatchedSessionId: string(
      item.dispatchedSessionId,
      "dispatchedSessionId",
    ),
    agentMeshCommandId: uuid(item.agentMeshCommandId, "agentMeshCommandId"),
    prompt: boundedString(item.prompt, "prompt", 32_768),
    route: oneOf(item.route, ["managed", "continuation"] as const, "route"),
    createdAt: dateTime(item.createdAt, "createdAt"),
    alreadyDispatched: literal(
      item.alreadyDispatched,
      true,
      "alreadyDispatched",
    ),
  };
};

const parseCompletion = (value: unknown): AgentMeshCompletion => {
  const item = record(value, "completion");
  const sessionName = optionalString(item.sessionName, "sessionName");
  return {
    notificationId: uuid(item.notificationId, "notificationId"),
    sequence: positiveInteger(item.sequence, "sequence"),
    sessionId: string(item.sessionId, "sessionId"),
    agent: oneOf(item.agent, ["codex", "claude"] as const, "agent"),
    nodeId: string(item.nodeId, "nodeId"),
    nodeName: string(item.nodeName, "nodeName"),
    workspaceName: string(item.workspaceName, "workspaceName"),
    ...(sessionName === undefined ? {} : { sessionName }),
    outcome: oneOf(
      item.outcome,
      ["completed", "failed", "interrupted"] as const,
      "outcome",
    ),
    title: boundedString(item.title, "title", 200),
    displayText: boundedString(item.displayText, "displayText", 500),
    speechText: boundedString(item.speechText, "speechText", 500),
    createdAt: dateTime(item.createdAt, "createdAt"),
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const record = (value: unknown, name: string): Record<string, unknown> => {
  if (!isRecord(value))
    throw new TypeError(`Agent Mesh ${name} must be an object`);
  return value;
};

const array = (value: unknown, name: string): unknown[] => {
  if (!Array.isArray(value) || value.length > 100) {
    throw new TypeError(`Agent Mesh ${name} must be a bounded array`);
  }
  return value;
};

const string = (value: unknown, name: string): string =>
  boundedString(value, name, 32_768);

const boundedString = (
  value: unknown,
  name: string,
  maximum: number,
): string => {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) {
    throw new TypeError(
      `Agent Mesh ${name} must be a bounded non-empty string`,
    );
  }
  return value;
};

const optionalString = (value: unknown, name: string): string | undefined =>
  value === undefined ? undefined : string(value, name);

const dateTime = (value: unknown, name: string): string => {
  const result = string(value, name);
  if (!Number.isFinite(Date.parse(result))) {
    throw new TypeError(`Agent Mesh ${name} must be a date-time`);
  }
  return result;
};

const optionalDateTime = (value: unknown, name: string): string | undefined =>
  value === undefined ? undefined : dateTime(value, name);

const nonnegativeInteger = (value: unknown, name: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new TypeError(`Agent Mesh ${name} must be a non-negative integer`);
  }
  return value as number;
};

const positiveInteger = (value: unknown, name: string): number => {
  const result = nonnegativeInteger(value, name);
  if (result < 1) throw new TypeError(`Agent Mesh ${name} must be positive`);
  return result;
};

const uuid = (value: unknown, name: string): string => {
  const result = string(value, name);
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu.test(
      result,
    )
  ) {
    throw new TypeError(`Agent Mesh ${name} must be a UUID`);
  }
  return result;
};

const literal = <Value extends string | boolean>(
  value: unknown,
  expected: Value,
  name: string,
): Value => {
  if (value !== expected) throw new TypeError(`Agent Mesh ${name} is invalid`);
  return expected;
};

const oneOf = <Value extends string>(
  value: unknown,
  options: readonly Value[],
  name: string,
): Value => {
  if (typeof value !== "string" || !options.includes(value as Value)) {
    throw new TypeError(`Agent Mesh ${name} is invalid`);
  }
  return value as Value;
};
