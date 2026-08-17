/**
 * Typed client for the local runtime.
 *
 * The Studio holds no safety rules of its own. It disables a control when the
 * runtime says a device is not ready, but the runtime is what actually refuses
 * -- a disabled button is a courtesy, never a guarantee.
 *
 * Since Milestone 6 every call but `health` carries the token this client was
 * given when somebody signed in. The token is held in memory only: a classroom
 * machine is shared, and a token in local storage would outlive the lesson and
 * the person.
 */

export type DeviceState =
  "discovered" | "connecting" | "connected" | "disconnected" | "failed";

export type Role = "student" | "instructor";

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

/** FR-065. Everything one instructor device card shows. */
export interface DeviceOverview {
  deviceId: string;
  displayName: string;
  deviceType: string;
  model: string;
  adapterId: string;
  adapterVersion: string;
  firmware: string | null;
  physical: boolean;
  state: DeviceState;
  capabilities: string[];
  batteryPercent: number | null;
  activeStudentId: string | null;
  activeSessionId: string | null;
  safetyPolicyId: string | null;
  armed: boolean;
  armedBy: string | null;
  armExpiresAt: string | null;
  leaseSessionId: string | null;
  lastCommand: {
    capability: string;
    action: string;
    result: string;
    at: string | null;
    ageMs: number | null;
  } | null;
  lastTelemetry: { name: string; at: string | null } | null;
  heartbeatAges: Record<string, number>;
  failureReason: string | null;
  warnings: string[];
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
  failurePolicy: string;
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
  /** ADR-033. True where the runtime is published and the join is closed. */
  joinRequiresPasscode?: boolean;
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

export interface AuditEntryView {
  sequence: number;
  recordedAt: string;
  action: string;
  actorId: string;
  context: Record<string, unknown>;
}

export interface PersonView {
  actorId: string;
  role: Role;
  displayName: string;
  expiresAt: string;
}

export interface ClassroomView {
  people: PersonView[];
  sessions: SessionView[];
  devices: DeviceOverview[];
  disabledSources: string[];
  queueDepth: number;
}

export interface ProjectSummaryView {
  projectId: string;
  name: string;
  authoringMode: string;
  updatedAt: string;
  ownerId: string | null;
}

export interface RecordingView {
  recordingId: string;
  sessionId: string;
  startedAt: string;
  eventCount: number;
  durationSeconds: number;
}

export interface RetentionView {
  maxRecordings: number;
  retentionDays: number;
}

export interface Identity {
  token: string;
  actorId: string;
  role: Role;
  displayName: string;
  expiresAt: string;
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
  source?: "student_blocks" | "student_python" | "instructor";
  inputConfidence?: number;
}

/** Where the runtime listens when the Studio is not being served by it. */
export const LOOPBACK_RUNTIME_URL = "http://127.0.0.1:8791";

/** Vite's dev and preview ports. Anything else is assumed to be the runtime. */
const DEV_SERVER_PORTS = new Set(["5173", "4173"]);

/**
 * Pick the runtime's base URL: the origin serving this page, and the path it is
 * served under.
 *
 * The runtime serves this bundle itself, so same-origin is the normal case and
 * needs no CORS exception. Only Vite's dev server has to reach across to the
 * loopback port, and that origin is on the runtime's allowlist.
 *
 * The path matters because the runtime can be served under one. A proxy that
 * routes `https://host/citxr` to the runtime forwards the path as it arrived,
 * so the API lives at `/citxr/api/...` and the page must ask for it there. A
 * bundle served from a plain static host resolves the same way, finds no API
 * beside itself, and says the runtime is unreachable -- which is correct, and is
 * why a static copy of this page cannot drive anything.
 *
 * What keeps a robot safe is not this function. It is that the runtime binds
 * loopback only, so the sole way to reach it from outside is a proxy its owner
 * configured on purpose (see `docs/HOSTING.md`).
 */
export function resolveRuntimeUrl(location?: {
  origin: string;
  port: string;
  pathname?: string;
}): string {
  const current =
    location ?? (typeof window === "undefined" ? undefined : window.location);
  if (current === undefined) return LOOPBACK_RUNTIME_URL;
  if (DEV_SERVER_PORTS.has(current.port)) return LOOPBACK_RUNTIME_URL;
  return `${current.origin}${basePathOf(current.pathname ?? "/")}`;
}

/**
 * The directory this page is served from, with no trailing slash.
 *
 * `/citxr/index.html` and `/citxr/` are both `/citxr`; `/` and `/index.html`
 * are both the empty string. A last segment is a file when it has a dot in it,
 * which is the same rule the bundle's own relative asset URLs follow.
 */
export function basePathOf(pathname: string): string {
  const segments = pathname.split("/");
  const last = segments[segments.length - 1] ?? "";
  if (last.includes(".")) segments.pop();
  return segments.join("/").replace(/\/+$/, "");
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

/** A refusal the runtime made on purpose, with its own reason (UI 11.6). */
export class RuntimeRefusedError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "RuntimeRefusedError";
    this.status = status;
  }

  /** 401 means the token is gone: the Studio has to sign in again. */
  get needsSignIn(): boolean {
    return this.status === 401;
  }
}

export class RuntimeClient {
  readonly baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = DEFAULT_RUNTIME_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  hasToken(): boolean {
    return this.token !== null;
  }

  private async request<T>(
    path: string,
    init?: { method?: string; body?: unknown; text?: boolean },
  ): Promise<T> {
    // Built conditionally: with exactOptionalPropertyTypes, an explicit
    // `undefined` is not the same as an absent property.
    const request: RequestInit = { method: init?.method ?? "GET" };
    const headers: Record<string, string> = {};
    if (this.token !== null) headers["authorization"] = `Bearer ${this.token}`;
    if (init?.body !== undefined) {
      headers["content-type"] = "application/json";
      request.body = JSON.stringify(init.body);
    }
    request.headers = headers;

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, request);
    } catch (error) {
      throw new RuntimeUnreachableError(this.baseUrl, error);
    }

    if (!response.ok) {
      const raw = await response.text();
      throw new RuntimeRefusedError(response.status, detailOf(raw));
    }
    if (init?.text === true) return (await response.text()) as T;
    return (await response.json()) as T;
  }

  // ------------------------------------------------------------------- auth

  /** Sign in. The instructor role needs the passcode from the runtime log. */
  async join(options: {
    actorId: string;
    role: Role;
    displayName?: string;
    passcode?: string;
  }): Promise<Identity> {
    const identity = await this.request<Identity>("/api/auth/join", {
      method: "POST",
      body: {
        actor_id: options.actorId,
        role: options.role,
        display_name: options.displayName ?? null,
        passcode: options.passcode ?? null,
      },
    });
    this.token = identity.token;
    return identity;
  }

  async leave(): Promise<void> {
    if (this.token === null) return;
    try {
      await this.request("/api/auth/leave", { method: "POST" });
    } finally {
      this.token = null;
    }
  }

  // ---------------------------------------------------------------- runtime

  health(): Promise<HealthView> {
    return this.request<HealthView>("/api/health");
  }

  async devices(): Promise<DeviceView[]> {
    const payload = await this.request<{ devices: DeviceView[] }>(
      "/api/devices",
    );
    return payload.devices;
  }

  async deviceOverview(): Promise<DeviceOverview[]> {
    const payload = await this.request<{ devices: DeviceOverview[] }>(
      "/api/devices/overview",
    );
    return payload.devices;
  }

  classroom(): Promise<ClassroomView> {
    return this.request<ClassroomView>("/api/classroom");
  }

  discover(): Promise<{ discovered: string[]; connected: string[] }> {
    return this.request("/api/devices/discover", { method: "POST" });
  }

  disconnectDevice(deviceId: string, reason: string): Promise<DeviceView> {
    return this.request("/api/devices/disconnect", {
      method: "POST",
      body: { device_id: deviceId, reason },
    });
  }

  // --------------------------------------------------------------- sessions

  async sessions(): Promise<SessionView[]> {
    const payload = await this.request<{ sessions: SessionView[] }>(
      "/api/sessions",
    );
    return payload.sessions;
  }

  createSession(options: {
    projectId: string;
    instructorId?: string;
    executionMode?: "simulation" | "physical";
    safetyPolicyId?: string;
  }): Promise<SessionView> {
    return this.request<SessionView>("/api/sessions", {
      method: "POST",
      body: {
        project_id: options.projectId,
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

  setFailurePolicy(
    sessionId: string,
    policy: "stop_coordinated" | "continue",
  ): Promise<SessionView> {
    return this.request(`/api/sessions/${sessionId}/failure-policy`, {
      method: "POST",
      body: { policy },
    });
  }

  // ----------------------------------------------------------------- safety

  arm(options: {
    sessionId: string;
    deviceId: string;
    ttlSeconds?: number;
  }): Promise<{ deviceId: string; expiresAt: string }> {
    return this.request("/api/safety/arm", {
      method: "POST",
      body: {
        session_id: options.sessionId,
        device_id: options.deviceId,
        ttl_seconds: options.ttlSeconds ?? null,
      },
    });
  }

  disarm(deviceId: string | null): Promise<{ disarmed: string[] }> {
    return this.request("/api/safety/disarm", {
      method: "POST",
      body: { device_id: deviceId },
    });
  }

  /**
   * ADR-028. One beat of a held dead-man control.
   *
   * The runtime believes this and not a flag in a command, so a page that stops
   * calling it -- because it was closed, frozen, or the control was released --
   * stops being able to move anything within one watchdog period.
   */
  heartbeat(
    deviceId: string,
    kind = "quest_deadman_heartbeat",
  ): Promise<unknown> {
    return this.request("/api/safety/heartbeat", {
      method: "POST",
      body: { device_id: deviceId, kind },
    });
  }

  stop(options: {
    deviceId?: string | null;
    reason?: string;
  }): Promise<{ stopped: string[]; scope: string }> {
    return this.request("/api/safety/stop", {
      method: "POST",
      body: {
        device_id: options.deviceId ?? null,
        reason: options.reason ?? "studio stop",
      },
    });
  }

  revokeLease(deviceId: string): Promise<{ revoked: number }> {
    return this.request("/api/safety/revoke-lease", {
      method: "POST",
      body: { device_id: deviceId },
    });
  }

  clearQueue(deviceId: string | null): Promise<{ clearedCommands: number }> {
    return this.request("/api/safety/clear-queue", {
      method: "POST",
      body: { device_id: deviceId },
    });
  }

  setInputEnabled(
    source: string,
    enabled: boolean,
  ): Promise<{ disabledSources: string[] }> {
    return this.request("/api/safety/inputs", {
      method: "POST",
      body: { source, enabled },
    });
  }

  inputs(): Promise<{ disabledSources: string[] }> {
    return this.request("/api/safety/inputs");
  }

  // --------------------------------------------------------------- commands

  send(request: CommandRequest): Promise<CommandOutcome> {
    return this.request<CommandOutcome>("/api/commands", {
      method: "POST",
      body: {
        session_id: request.sessionId,
        device_id: request.deviceId,
        capability: request.capability,
        action: request.action,
        arguments: request.arguments ?? {},
        source: request.source ?? null,
        input_confidence: request.inputConfidence ?? null,
      },
    });
  }

  /** FR-013. The single route a student program can cause. */
  studentRpc(request: {
    sessionId: string;
    method: string;
    payload: Record<string, unknown>;
    aliases: Record<string, string>;
    inputConfidence?: number;
  }): Promise<unknown> {
    return this.request("/api/student/rpc", {
      method: "POST",
      body: {
        session_id: request.sessionId,
        method: request.method,
        payload: request.payload,
        aliases: request.aliases,
        input_confidence: request.inputConfidence ?? null,
      },
    });
  }

  // ---------------------------------------------------------------- history

  async audit(): Promise<AuditEntryView[]> {
    const payload = await this.request<{ entries: AuditEntryView[] }>(
      "/api/audit",
    );
    return payload.entries;
  }

  auditExport(): Promise<string> {
    return this.request<string>("/api/audit/export", { text: true });
  }

  /** Events already recorded before this page attached to the stream. */
  async recentEvents(): Promise<DeviceEventView[]> {
    const payload = await this.request<{ events: DeviceEventView[] }>(
      "/api/events",
    );
    return payload.events;
  }

  // ------------------------------------------------------------- recordings

  async recordings(): Promise<{
    recordings: RecordingView[];
    policy: RetentionView;
  }> {
    return this.request("/api/recordings");
  }

  startRecording(sessionId: string): Promise<{ recordingId: string }> {
    return this.request("/api/recordings/start", {
      method: "POST",
      body: { session_id: sessionId },
    });
  }

  stopRecording(recordingId: string): Promise<RecordingView> {
    return this.request(`/api/recordings/${recordingId}/stop`, {
      method: "POST",
    });
  }

  replay(
    recordingId: string,
  ): Promise<{ delivered: number; physicalOutput: boolean }> {
    return this.request(`/api/recordings/${recordingId}/replay`, {
      method: "POST",
    });
  }

  exportRecording(recordingId: string): Promise<string> {
    return this.request(`/api/recordings/${recordingId}/export`, {
      text: true,
    });
  }

  deleteRecording(recordingId: string): Promise<{ deleted: boolean }> {
    return this.request(`/api/recordings/${recordingId}`, {
      method: "DELETE",
    });
  }

  setRetention(policy: RetentionView): Promise<RetentionView> {
    return this.request("/api/retention", {
      method: "POST",
      body: {
        max_recordings: policy.maxRecordings,
        retention_days: policy.retentionDays,
      },
    });
  }

  // --------------------------------------------------------------- projects

  async projects(): Promise<ProjectSummaryView[]> {
    const payload = await this.request<{ projects: ProjectSummaryView[] }>(
      "/api/projects",
    );
    return payload.projects;
  }

  project(projectId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/projects/${projectId}`);
  }

  saveProject(
    projectId: string,
    project: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.request(`/api/projects/${projectId}`, {
      method: "PUT",
      body: { project },
    });
  }

  deleteProject(projectId: string): Promise<{ deleted: boolean }> {
    return this.request(`/api/projects/${projectId}`, { method: "DELETE" });
  }

  // ------------------------------------------------------------------ stream

  /** Opens the event stream. Returns a function that closes it. */
  streamEvents(onEvent: (event: DeviceEventView) => void): () => void {
    if (this.token === null) return () => undefined;
    const url =
      `${this.baseUrl.replace(/^http/, "ws")}/ws/events` +
      `?token=${encodeURIComponent(this.token)}`;
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

/** FastAPI reports refusals as `{"detail": "..."}`. Show the sentence, not the JSON. */
function detailOf(raw: string): string {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "detail" in parsed &&
      typeof (parsed as { detail: unknown }).detail === "string"
    ) {
      return (parsed as { detail: string }).detail;
    }
  } catch {
    // Not JSON. The raw body is the best message available.
  }
  return raw;
}
