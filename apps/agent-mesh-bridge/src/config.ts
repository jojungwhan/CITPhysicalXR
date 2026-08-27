import path from "node:path";

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u;

export interface BridgeConfig {
  readonly fabricAdapterUrl: string;
  readonly fabricCredential: string;
  readonly fabricApiUrl: string;
  readonly fabricReadCredential: string;
  readonly fabricSessionId: string;
  readonly projectFabricControls: boolean;
  readonly agentMeshBaseUrl: string;
  readonly agentMeshDeviceToken: string;
  readonly databasePath: string;
  readonly siteId: string;
  readonly roomId: string;
  readonly hostId: string;
  readonly pollIntervalMs: number;
  readonly reconnectDelayMs: number;
}

export const loadBridgeConfig = (
  environment: NodeJS.ProcessEnv = process.env,
): BridgeConfig => {
  const fabricAdapterUrl = exactUrl(
    required(environment, "CIT_FABRIC_ADAPTER_URL"),
    ["ws:", "wss:"],
    "CIT_FABRIC_ADAPTER_URL",
  );
  if (new URL(fabricAdapterUrl).pathname !== "/api/v1/adapters/connect") {
    throw new TypeError(
      "CIT_FABRIC_ADAPTER_URL must target /api/v1/adapters/connect",
    );
  }
  const agentMeshBaseUrl = exactUrl(
    required(environment, "CIT_AGENT_MESH_URL"),
    ["http:", "https:"],
    "CIT_AGENT_MESH_URL",
  );
  const databasePath = required(environment, "CIT_BRIDGE_DATABASE_PATH");
  if (!path.isAbsolute(databasePath)) {
    throw new TypeError("CIT_BRIDGE_DATABASE_PATH must be absolute");
  }
  return {
    fabricAdapterUrl,
    fabricCredential: boundedSecret(
      required(environment, "CIT_FABRIC_ADAPTER_TOKEN"),
      "CIT_FABRIC_ADAPTER_TOKEN",
      512,
    ),
    fabricApiUrl: fabricHttpOrigin(fabricAdapterUrl),
    fabricReadCredential: boundedSecret(
      required(environment, "CIT_FABRIC_READ_TOKEN"),
      "CIT_FABRIC_READ_TOKEN",
      512,
    ),
    fabricSessionId: identifier(
      required(environment, "CIT_FABRIC_SESSION_ID"),
      "CIT_FABRIC_SESSION_ID",
    ),
    projectFabricControls: booleanFlag(
      environment.CIT_FABRIC_CONTROL_PROJECTION,
      false,
      "CIT_FABRIC_CONTROL_PROJECTION",
    ),
    agentMeshBaseUrl,
    agentMeshDeviceToken: boundedSecret(
      required(environment, "CIT_AGENT_MESH_DEVICE_TOKEN"),
      "CIT_AGENT_MESH_DEVICE_TOKEN",
      256,
    ),
    databasePath: path.resolve(databasePath),
    siteId: identifier(environment.CIT_SITE_ID ?? "local-site", "CIT_SITE_ID"),
    roomId: identifier(environment.CIT_ROOM_ID ?? "local-room", "CIT_ROOM_ID"),
    hostId: identifier(
      environment.CIT_BRIDGE_HOST_ID ?? "agent-mesh-bridge-local",
      "CIT_BRIDGE_HOST_ID",
    ),
    pollIntervalMs: boundedInteger(
      environment.CIT_BRIDGE_POLL_INTERVAL_MS,
      1_000,
      60_000,
      2_000,
      "CIT_BRIDGE_POLL_INTERVAL_MS",
    ),
    reconnectDelayMs: boundedInteger(
      environment.CIT_BRIDGE_RECONNECT_DELAY_MS,
      250,
      60_000,
      2_000,
      "CIT_BRIDGE_RECONNECT_DELAY_MS",
    ),
  };
};

const booleanFlag = (
  raw: string | undefined,
  fallback: boolean,
  name: string,
): boolean => {
  if (raw === undefined) return fallback;
  if (raw === "true") return true;
  if (raw === "false") return false;
  throw new TypeError(`${name} must be true or false`);
};

const fabricHttpOrigin = (adapterUrl: string): string => {
  const url = new URL(adapterUrl);
  url.protocol = url.protocol === "wss:" ? "https:" : "http:";
  url.pathname = "/";
  return url.toString().replace(/\/$/u, "");
};

const required = (environment: NodeJS.ProcessEnv, name: string): string => {
  const value = environment[name]?.trim();
  if (!value) throw new TypeError(`${name} is required`);
  return value;
};

const identifier = (value: string, name: string): string => {
  if (!IDENTIFIER.test(value))
    throw new TypeError(`${name} must be a CIT identifier`);
  return value;
};

const boundedSecret = (
  value: string,
  name: string,
  maximum: number,
): string => {
  if (value.length < 32 || value.length > maximum) {
    throw new TypeError(
      `${name} must contain 32 through ${maximum} characters`,
    );
  }
  return value;
};

const exactUrl = (value: string, protocols: string[], name: string): string => {
  const url = new URL(value);
  if (
    !protocols.includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new TypeError(
      `${name} must be an exact ${protocols.join(" or ")} URL`,
    );
  }
  return url.toString().replace(/\/$/u, "");
};

const boundedInteger = (
  raw: string | undefined,
  minimum: number,
  maximum: number,
  fallback: number,
  name: string,
): number => {
  if (raw === undefined) return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new TypeError(
      `${name} must be an integer from ${minimum} through ${maximum}`,
    );
  }
  return value;
};
