/**
 * Typed client for the local runtime.
 *
 * The Studio holds no safety rules of its own. It disables a control when the
 * runtime says a device is not ready, but the runtime is what actually refuses
 * -- a disabled button is a courtesy, never a guarantee.
 */

export type DeviceState =
  "discovered" | "connecting" | "connected" | "disconnected" | "failed";

export interface DeviceView {
  deviceId: string;
  displayName: string;
  deviceType: string;
  model: string;
  physical: boolean;
  state: DeviceState;
  capabilities: string[];
  assignedSessionId: string | null;
  armed: boolean;
  armExpiresAt: string | null;
  failureReason: string | null;
}

export interface SessionView {
  sessionId: string;
  projectId: string;
  state: string;
  authoringMode: string;
  executionMode: string;
  userId: string;
  instructorId: string | null;
  safetyPolicyId: string;
  deviceBindings: string[];
  startedAt: string;
  lastActivityAt: string;
  endedAt: string | null;
}

export interface HealthView {
  status: string;
  runtimeId: string;
  protocolVersion: number;
  executionMode: string;
  physicalEnabled: boolean;
}

export interface DeviceEventView {
  eventId: string;
  deviceId: string;
  category: string;
  name: string;
  values: Record<string, unknown>;
  receivedAt: string;
  historical?: boolean;
}

export interface CommandOutcome {
  accepted: boolean;
  status?: string;
  commandId?: string;
  clampedFields?: string[];
  code?: string;
  message?: string;
  recovery?: string;
}

export interface CommandRequest {
  sessionId: string;
  deviceId: string;
  capability: string;
  action: string;
  arguments?: Record<string, unknown>;
  source?: string;
  deadmanActive?: boolean;
  inputConfidence?: number;
}

/** Where the runtime listens when the Studio is not being served by it. */
export const LOOPBACK_RUNTIME_URL = "http://127.0.0.1:8791";

/** Vite's dev and preview ports. Anything else is assumed to be the runtime. */
const DEV_SERVER_PORTS = new Set(["5173", "4173"]);

/**
 * Pick the runtime origin.
 *
 * The runtime serves this bundle itself, so same-origin is the normal case and
 * needs no CORS exception. Only Vite's dev server has to reach across to the
 * loopback port, and that origin is on the runtime's allowlist.
 *
 * A copy served from any other host resolves to its own origin, finds no API
 * there, and says the runtime is unreachable. That is correct: a remote page
 * must not be able to drive a robot on someone's desk.
 */
export function resolveRuntimeUrl(location?: {
  origin: string;
  port: string;
}): string {
  const current =
    location ?? (typeof window === "undefined" ? undefined : window.location);
  if (current === undefined) return LOOPBACK_RUNTIME_URL;
  if (DEV_SERVER_PORTS.has(current.port)) return LOOPBACK_RUNTIME_URL;
  return current.origin;
}

export const DEFAULT_RUNTIME_URL = resolveRuntimeUrl();

export class RuntimeUnreachableError extends Error {
  constructor(baseUrl: string, cause: unknown) {
    super(
      `Cannot reach the local runtime at ${baseUrl}. Start it with ` +
        `\`uv run python -m cit_runtime\` in the repository root.`,
    );
    this.name = "RuntimeUnreachableError";
    this.cause = cause;
  }
}

export class RuntimeClient {
  readonly baseUrl: string;

  constructor(baseUrl: string = DEFAULT_RUNTIME_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(
    path: string,
    init?: { method?: string; body?: unknown },
  ): Promise<T> {
    // Built conditionally: with exactOptionalPropertyTypes, an explicit
    // `undefined` is not the same as an absent property.
    const request: RequestInit = { method: init?.method ?? "GET" };
    if (init?.body !== undefined) {
      request.headers = { "content-type": "application/json" };
      request.body = JSON.stringify(init.body);
    }

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, request);
    } catch (error) {
      throw new RuntimeUnreachableError(this.baseUrl, error);
    }

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${detail}`);
    }
    return (await response.json()) as T;
  }

  health(): Promise<HealthView> {
    return this.request<HealthView>("/api/health");
  }

  async devices(): Promise<DeviceView[]> {
    const payload = await this.request<{ devices: DeviceView[] }>(
      "/api/devices",
    );
    return payload.devices;
  }

  async sessions(): Promise<SessionView[]> {
    const payload = await this.request<{ sessions: SessionView[] }>(
      "/api/sessions",
    );
    return payload.sessions;
  }

  /** Events already recorded before this page attached to the stream. */
  async recentEvents(): Promise<DeviceEventView[]> {
    const payload = await this.request<{ events: DeviceEventView[] }>(
      "/api/events",
    );
    return payload.events;
  }

  /** FR-013. The single route a student program can cause. */
  studentRpc(request: {
    sessionId: string;
    method: string;
    payload: Record<string, unknown>;
    source: "student_blocks" | "student_python";
    aliases: Record<string, string>;
    deadmanActive?: boolean;
    inputConfidence?: number;
  }): Promise<unknown> {
    return this.request("/api/student/rpc", {
      method: "POST",
      body: {
        session_id: request.sessionId,
        method: request.method,
        payload: request.payload,
        source: request.source,
        aliases: request.aliases,
        deadman_active: request.deadmanActive ?? false,
        input_confidence: request.inputConfidence ?? null,
      },
    });
  }

  discover(): Promise<{ discovered: string[]; connected: string[] }> {
    return this.request("/api/devices/discover", { method: "POST" });
  }

  createSession(options: {
    projectId: string;
    userId: string;
    instructorId?: string;
    executionMode?: "simulation" | "physical";
    safetyPolicyId?: string;
  }): Promise<SessionView> {
    return this.request<SessionView>("/api/sessions", {
      method: "POST",
      body: {
        project_id: options.projectId,
        user_id: options.userId,
        instructor_id: options.instructorId ?? null,
        execution_mode: options.executionMode ?? "simulation",
        safety_policy_id: options.safetyPolicyId ?? "simulation-only",
      },
    });
  }

  bindDevices(sessionId: string, deviceIds: string[]): Promise<SessionView> {
    return this.request<SessionView>(`/api/sessions/${sessionId}/devices`, {
      method: "POST",
      body: { device_ids: deviceIds },
    });
  }

  transition(sessionId: string, state: string): Promise<SessionView> {
    return this.request<SessionView>(`/api/sessions/${sessionId}/state`, {
      method: "POST",
      body: { state },
    });
  }

  /** Ends a session so it hands its devices back to the next class. */
  async endSession(sessionId: string): Promise<void> {
    await this.transition(sessionId, "stopping");
    await this.transition(sessionId, "stopped");
  }

  validate(sessionId: string): Promise<SessionView> {
    return this.request<SessionView>(`/api/sessions/${sessionId}/validate`, {
      method: "POST",
    });
  }

  arm(options: {
    sessionId: string;
    deviceId: string;
    instructorId: string;
    ttlSeconds?: number;
  }): Promise<{ deviceId: string; expiresAt: string }> {
    return this.request("/api/safety/arm", {
      method: "POST",
      body: {
        session_id: options.sessionId,
        device_id: options.deviceId,
        instructor_id: options.instructorId,
        ttl_seconds: options.ttlSeconds ?? null,
      },
    });
  }

  disarm(
    deviceId: string | null,
    actorId: string,
  ): Promise<{ disarmed: string[] }> {
    return this.request("/api/safety/disarm", {
      method: "POST",
      body: { device_id: deviceId, actor_id: actorId },
    });
  }

  heartbeat(deviceId: string, kind: string): Promise<unknown> {
    return this.request("/api/safety/heartbeat", {
      method: "POST",
      body: { device_id: deviceId, kind },
    });
  }

  stop(options: {
    deviceId?: string | null;
    actorId: string;
    reason?: string;
  }): Promise<{ stopped: string[]; scope: string }> {
    return this.request("/api/safety/stop", {
      method: "POST",
      body: {
        device_id: options.deviceId ?? null,
        actor_id: options.actorId,
        reason: options.reason ?? "studio stop",
      },
    });
  }

  send(request: CommandRequest): Promise<CommandOutcome> {
    return this.request<CommandOutcome>("/api/commands", {
      method: "POST",
      body: {
        session_id: request.sessionId,
        device_id: request.deviceId,
        capability: request.capability,
        action: request.action,
        arguments: request.arguments ?? {},
        source: request.source ?? "student_blocks",
        deadman_active: request.deadmanActive ?? false,
        input_confidence: request.inputConfidence ?? null,
      },
    });
  }

  /** Opens the event stream. Returns a function that closes it. */
  streamEvents(onEvent: (event: DeviceEventView) => void): () => void {
    const url = `${this.baseUrl.replace(/^http/, "ws")}/ws/events`;
    const socket = new WebSocket(url);
    socket.addEventListener("message", (message) => {
      try {
        const payload = JSON.parse(String(message.data)) as {
          kind: string;
          event: DeviceEventView;
        };
        if (payload.kind === "device_event") {
          onEvent(payload.event);
        }
      } catch {
        // A malformed frame must not take the Studio down.
      }
    });
    return () => socket.close();
  }
}
