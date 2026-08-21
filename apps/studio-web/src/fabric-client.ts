import type {
  CoursePack,
  CreateInteractionSessionRequest,
  FabricCommandLifecycleEvent,
  FabricCommandRequest,
  FabricEventEnvelope,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";

export interface FabricPrincipal {
  identityId: string;
  actorType: string;
  roles: string[];
  permissions: string[];
  siteId?: string;
  roomId?: string;
  sessionId?: string;
  expiresAt: string;
}

export interface StoredFabricEvent {
  streamSequence: number;
  event: FabricEventEnvelope;
}

export interface StoredFabricLifecycle {
  streamSequence: number;
  lifecycle: FabricCommandLifecycleEvent;
}

export interface FabricCommandSubmission {
  lifecycle: FabricCommandLifecycleEvent[];
}

export interface FabricStopAllResult {
  status: "completed" | "partial";
  stoppedSessionIds: string[];
  failedSessionIds: string[];
  stoppedNodeIds: string[];
  failedNodeIds: string[];
  legacy: unknown;
}

export interface FabricAuditRecord {
  auditId: string;
  actorId: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  outcome: string;
  correlationId?: string;
  occurredAt: string;
  details: Record<string, unknown>;
}

interface FabricErrorBody {
  code?: unknown;
  message?: unknown;
  correlationId?: unknown;
}

export class FabricApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string | undefined;

  constructor(status: number, body: FabricErrorBody) {
    const message =
      typeof body.message === "string"
        ? body.message
        : `Fabric request failed with HTTP ${status}`;
    super(message);
    this.name = "FabricApiError";
    this.status = status;
    this.code =
      typeof body.code === "string" ? body.code : "FABRIC_REQUEST_FAILED";
    this.correlationId =
      typeof body.correlationId === "string" ? body.correlationId : undefined;
  }
}

export class FabricClient {
  readonly #baseUrl: string;
  readonly #fetch: typeof fetch;
  #credential: string | undefined;

  constructor(
    baseUrl = "",
    fetchImplementation: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#fetch = fetchImplementation;
  }

  setCredential(credential: string): void {
    const normalized = credential.trim();
    if (normalized.length < 32 || normalized.length > 512) {
      throw new Error(
        "Fabric credentials must be between 32 and 512 characters.",
      );
    }
    this.#credential = normalized;
  }

  clearCredential(): void {
    this.#credential = undefined;
  }

  whoAmI(): Promise<FabricPrincipal> {
    return this.#request("/api/v1/fabric/auth/whoami");
  }

  listNodes(): Promise<IntegrationNode[]> {
    return this.#request("/api/v1/fabric/nodes");
  }

  listCoursePacks(): Promise<CoursePack[]> {
    return this.#request("/api/v1/fabric/course-packs");
  }

  listSessions(): Promise<InteractionSession[]> {
    return this.#request("/api/v1/fabric/sessions");
  }

  createSession(
    request: CreateInteractionSessionRequest,
  ): Promise<InteractionSession> {
    return this.#request("/api/v1/fabric/sessions", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  assignRole(
    sessionId: string,
    role: string,
    nodeId: string,
  ): Promise<InteractionSession> {
    return this.#request(
      `/api/v1/fabric/sessions/${encodeURIComponent(sessionId)}/roles/${encodeURIComponent(role)}`,
      {
        method: "PUT",
        body: JSON.stringify({ nodeId }),
      },
    );
  }

  sessionAction(
    sessionId: string,
    action: "arm" | "disarm" | "start" | "pause" | "stop",
  ): Promise<InteractionSession> {
    return this.#request(
      `/api/v1/fabric/sessions/${encodeURIComponent(sessionId)}/${action}`,
      { method: "POST" },
    );
  }

  publishEvent(event: FabricEventEnvelope): Promise<{
    status: "accepted" | "duplicate";
    streamSequence?: number;
    commandLifecycle: FabricCommandLifecycleEvent[];
  }> {
    return this.#request("/api/v1/fabric/events", {
      method: "POST",
      body: JSON.stringify(event),
    });
  }

  listEvents(
    sessionId: string,
    afterSequence = 0,
  ): Promise<StoredFabricEvent[]> {
    const parameters = new URLSearchParams({
      sessionId,
      afterSequence: String(afterSequence),
      limit: "100",
    });
    return this.#request(`/api/v1/fabric/events?${parameters.toString()}`);
  }

  submitCommand(
    command: FabricCommandRequest,
  ): Promise<FabricCommandSubmission> {
    return this.#request("/api/v1/fabric/commands", {
      method: "POST",
      body: JSON.stringify(command),
    });
  }

  listLifecycle(afterSequence = 0): Promise<StoredFabricLifecycle[]> {
    const parameters = new URLSearchParams({
      afterSequence: String(afterSequence),
      limit: "100",
    });
    return this.#request(
      `/api/v1/fabric/commands/lifecycle?${parameters.toString()}`,
    );
  }

  stopAll(): Promise<FabricStopAllResult> {
    return this.#request("/api/v1/fabric/safety/stop-all", { method: "POST" });
  }

  listAudit(): Promise<FabricAuditRecord[]> {
    return this.#request("/api/v1/fabric/audit?limit=50");
  }

  async #request<ResponseBody>(
    path: string,
    init?: RequestInit,
  ): Promise<ResponseBody> {
    if (this.#credential === undefined) {
      throw new Error("Enter a CIT Fabric credential before connecting.");
    }
    const response = await this.#fetch(`${this.#baseUrl}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "omit",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${this.#credential}`,
        ...(init?.body === undefined
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
    const text = await response.text();
    let body: unknown;
    try {
      body = text.length === 0 ? undefined : JSON.parse(text);
    } catch {
      body = undefined;
    }
    if (!response.ok) {
      const errorBody =
        typeof body === "object" && body !== null
          ? (body as FabricErrorBody)
          : {};
      throw new FabricApiError(response.status, errorBody);
    }
    return body as ResponseBody;
  }
}
