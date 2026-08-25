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

export interface FabricSessionStartPolicy {
  sessionId: string;
  requiresArming: boolean;
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

export type FabricMediaKind =
  "meta_glasses" | "robomaster" | "tello" | "usb_camera" | "simulator";

export interface FabricObjectDetection {
  label: string;
  confidence: number;
  box: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  };
}

export interface FabricVisionAnalysis {
  sourceId: string;
  frameSequence: number;
  analyzedAt: string;
  model: string;
  labels: string[];
  detections: FabricObjectDetection[];
}

export interface FabricMediaSource {
  sourceId: string;
  displayName: string;
  kind: FabricMediaKind;
  captureMode: "video" | "snapshot";
  siteId: string;
  roomId: string;
  nodeId: string | null;
  state: "online" | "waiting";
  registeredAt: string;
  lastFrameAt: string | null;
  frameSequence: number;
  width: number | null;
  height: number | null;
  contentType: string | null;
  latestAnalysis: FabricVisionAnalysis | null;
}

export interface FabricMediaFrame {
  unchanged: boolean;
  blob?: Blob;
  etag?: string;
  sequence?: number;
  capturedAt?: string;
}

export interface FabricMediaPairing {
  pairingId: string;
  pairingCode: string;
  expiresAt: string;
  fabricOrigin: string;
  siteId: string;
  roomId: string;
  singleUse: true;
}

export type FabricDiscoveryStatus =
  | "not_scanned"
  | "connected"
  | "found"
  | "ready"
  | "setup_required"
  | "not_found"
  | "unavailable";

export interface FabricDiscoveryCandidate {
  candidateId: string;
  displayName: string;
  transport: string;
  status: "found" | "ready" | "setup_required" | "not_found";
  detail: string;
  model?: string;
  signalPercent?: number;
  connectionPath?:
    | "usb"
    | "bluetooth"
    | "wifi"
    | "android"
    | "android_usb"
    | "android_wifi"
    | "local_service";
  linkState?:
    | "attached"
    | "connected"
    | "recently_active"
    | "visible"
    | "paired"
    | "provisioned"
    | "ready";
}

export interface FabricIntegrationDiscovery {
  integrationId: string;
  displayName: string;
  category:
    | "interaction"
    | "sensor"
    | "robot"
    | "drone"
    | "smart_device"
    | "coding_agent";
  ioType: "input" | "output" | "bidirectional";
  icon?:
    | "brain"
    | "drone"
    | "glasses"
    | "hand"
    | "lego"
    | "plug"
    | "robot"
    | "ring"
    | "sphero"
    | "terminal"
    | "wonder";
  imagePath?: string;
  status: FabricDiscoveryStatus;
  summary: string;
  connectionMethod: string;
  connectedNodeIds: string[];
  candidates: FabricDiscoveryCandidate[];
  setupSteps: string[];
  setupCommand?: string;
  actionId?: string;
  actionLabel?: string;
  requiresGroundedConfirmation: boolean;
  safetyNote: string;
}

export interface FabricDiscoveryReport {
  schemaVersion: "1.0";
  scanId: string;
  scannedAt: string;
  hostId: string;
  platform: string;
  physicalActuationEnabled: boolean;
  integrations: FabricIntegrationDiscovery[];
  warnings: string[];
}

export interface FabricDiscoveryActionResult {
  actionId: string;
  accepted: boolean;
  message: string;
  report: FabricDiscoveryReport;
}

export interface FabricRememberedConnection {
  actionId: string;
  requiresGroundedConfirmation: boolean;
  rememberedAt: string;
}

export interface FabricRememberedConnections {
  schemaVersion: "1.0";
  hostId: string;
  connections: FabricRememberedConnection[];
}

export interface FabricRememberedConnectionOutcome {
  actionId: string;
  status: "connected" | "already_connected" | "skipped" | "failed";
  message: string;
  code?: string;
}

export interface FabricRememberedConnectionResult {
  schemaVersion: "1.0";
  connectedCount: number;
  alreadyConnectedCount: number;
  skippedCount: number;
  failedCount: number;
  outcomes: FabricRememberedConnectionOutcome[];
  report: FabricDiscoveryReport;
}

export interface LegoConnectionConfiguration {
  hubName: string;
  hubModel: "spike-prime" | "spike-essential" | "robot-inventor";
  ports: Record<string, "empty" | "motor" | "distance" | "color" | "force">;
}

export interface WonderWorkshopConnectionConfiguration {
  robots: WonderRobotSelection[];
}

export interface WonderRobotSelection {
  candidateId: string;
  model: "dash" | "dot";
}

export interface SpheroBoltSelection {
  candidateId: string;
}

export interface SpheroOllieSelection {
  candidateId: string;
}

export interface FabricInstallationArtifact {
  artifactId: string;
  fileName: string;
  mediaType: "application/zip";
  sizeBytes: number;
  sha256: string;
}

export interface FabricInstallationInfo {
  schemaVersion: "1.0";
  available: boolean;
  product: "CITPhysicalXR";
  version?: string;
  revision?: string;
  generatedAt?: string;
  platform: "windows-x64";
  requiresInternet: boolean;
  artifacts: FabricInstallationArtifact[];
}

export interface FabricInstallationDownload {
  blob: Blob;
  sha256?: string;
}

interface FabricErrorBody {
  code?: unknown;
  message?: unknown;
  correlationId?: unknown;
}

interface ConsoleTicketRedemption {
  accessToken: string;
  expiresAt: string;
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

  async connectWithConsoleTicket(ticket: string): Promise<FabricPrincipal> {
    const normalized = ticket.trim();
    if (
      normalized !== ticket ||
      normalized.length < 32 ||
      normalized.length > 128
    ) {
      throw new Error("This classroom access link is invalid or has expired.");
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/api/v1/fabric/auth/console-tickets/redeem`,
      {
        method: "POST",
        cache: "no-store",
        credentials: "omit",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ticket: normalized }),
      },
    );
    const redeemed =
      await this.#readResponse<ConsoleTicketRedemption>(response);
    this.setCredential(redeemed.accessToken);
    try {
      return await this.whoAmI();
    } catch (caught) {
      this.clearCredential();
      throw caught;
    }
  }

  listNodes(): Promise<IntegrationNode[]> {
    return this.#request("/api/v1/fabric/nodes");
  }

  getInstallationInfo(): Promise<FabricInstallationInfo> {
    return this.#request("/api/v1/fabric/installation");
  }

  async downloadInstallationArtifact(
    artifactId: string,
  ): Promise<FabricInstallationDownload> {
    if (!/^[a-z0-9][a-z0-9._-]{0,95}$/.test(artifactId)) {
      throw new Error("The installation artifact identifier is invalid.");
    }
    if (this.#credential === undefined) {
      throw new Error("Enter a CIT Fabric credential before connecting.");
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/api/v1/fabric/installation/artifacts/${encodeURIComponent(artifactId)}`,
      {
        cache: "no-store",
        credentials: "omit",
        headers: {
          Accept: "application/zip",
          Authorization: `Bearer ${this.#credential}`,
        },
      },
    );
    if (!response.ok) {
      await this.#readResponse<never>(response);
    }
    return {
      blob: await response.blob(),
      ...optionalString("sha256", response.headers.get("x-cit-sha256")),
    };
  }

  getDiscovery(): Promise<FabricDiscoveryReport> {
    return this.#request("/api/v1/fabric/discovery");
  }

  scanDevices(): Promise<FabricDiscoveryReport> {
    return this.#request("/api/v1/fabric/discovery/scan", { method: "POST" });
  }

  listRememberedConnections(): Promise<FabricRememberedConnections> {
    return this.#request("/api/v1/fabric/discovery/remembered");
  }

  reconnectRememberedDevices(
    confirmGrounded = false,
  ): Promise<FabricRememberedConnectionResult> {
    return this.#request("/api/v1/fabric/discovery/remembered/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmGrounded }),
    });
  }

  runDiscoveryAction(
    actionId: string,
    confirmGrounded = false,
    sessionId?: string,
  ): Promise<FabricDiscoveryActionResult> {
    if (!/^[a-z0-9][a-z0-9._-]*$/.test(actionId)) {
      throw new Error("The device connection action is invalid.");
    }
    if (
      sessionId !== undefined &&
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(sessionId)
    ) {
      throw new Error("The lesson session identifier is invalid.");
    }
    return this.#request(
      `/api/v1/fabric/discovery/actions/${encodeURIComponent(actionId)}`,
      {
        method: "POST",
        body: JSON.stringify({ confirmGrounded, sessionId }),
      },
    );
  }

  commissionMatterPlug(
    setupCode: string,
  ): Promise<FabricDiscoveryActionResult> {
    const normalized = setupCode.trim();
    if (
      normalized !== setupCode ||
      normalized.length < 11 ||
      normalized.length > 103 ||
      Array.from(normalized).some((character) => {
        const code = character.charCodeAt(0);
        return code < 32 || code === 127;
      })
    ) {
      throw new Error(
        "Enter the Matter QR or manual setup code printed on the plug.",
      );
    }
    return this.#request("/api/v1/fabric/matter/commission", {
      method: "POST",
      body: JSON.stringify({ setupCode: normalized }),
    });
  }

  configureMatterWifi(
    ssid: string,
    password: string,
  ): Promise<FabricDiscoveryActionResult> {
    const normalizedSsid = ssid.trim();
    const containsControlCharacter = (value: string) =>
      Array.from(value).some((character) => {
        const code = character.charCodeAt(0);
        return code < 32 || code === 127;
      });
    if (
      normalizedSsid !== ssid ||
      normalizedSsid.length === 0 ||
      new TextEncoder().encode(normalizedSsid).length > 32 ||
      containsControlCharacter(normalizedSsid)
    ) {
      throw new Error("Enter the exact printable Wi-Fi name (SSID).");
    }
    if (
      password.length < 8 ||
      password.length > 63 ||
      containsControlCharacter(password)
    ) {
      throw new Error("Enter the 8–63 character classroom Wi-Fi password.");
    }
    return this.#request("/api/v1/fabric/matter/wifi", {
      method: "POST",
      body: JSON.stringify({ ssid: normalizedSsid, password }),
    });
  }

  connectLegoHub(
    configuration: LegoConnectionConfiguration,
  ): Promise<FabricDiscoveryActionResult> {
    return this.#request("/api/v1/fabric/lego/connect", {
      method: "POST",
      body: JSON.stringify(configuration),
    });
  }

  connectWonderWorkshop(
    robots: WonderRobotSelection[],
  ): Promise<FabricDiscoveryActionResult> {
    const candidateIds = robots.map((robot) => robot.candidateId);
    if (
      robots.length < 1 ||
      robots.length > 4 ||
      new Set(candidateIds).size !== candidateIds.length ||
      robots.some(
        (robot) =>
          !/^wonder-[a-f0-9]{12}$/.test(robot.candidateId) ||
          (robot.model !== "dash" && robot.model !== "dot"),
      )
    ) {
      throw new Error("Select between one and four exact Dash/Dot robots.");
    }
    return this.#request("/api/v1/fabric/wonder-workshop/connect", {
      method: "POST",
      body: JSON.stringify({ robots }),
    });
  }

  connectSpheroBolts(
    robots: SpheroBoltSelection[],
  ): Promise<FabricDiscoveryActionResult> {
    const candidateIds = robots.map((robot) => robot.candidateId);
    if (
      robots.length < 1 ||
      robots.length > 4 ||
      new Set(candidateIds).size !== candidateIds.length ||
      robots.some((robot) => !/^sphero-[a-f0-9]{12}$/.test(robot.candidateId))
    ) {
      throw new Error("Select between one and four exact Sphero BOLT robots.");
    }
    return this.#request("/api/v1/fabric/sphero-bolt/connect", {
      method: "POST",
      body: JSON.stringify({ robots }),
    });
  }

  connectSpheroOllies(
    robots: SpheroOllieSelection[],
  ): Promise<FabricDiscoveryActionResult> {
    const candidateIds = robots.map((robot) => robot.candidateId);
    if (
      robots.length < 1 ||
      robots.length > 4 ||
      new Set(candidateIds).size !== candidateIds.length ||
      robots.some(
        (robot) => !/^sphero-ollie-[a-f0-9]{12}$/.test(robot.candidateId),
      )
    ) {
      throw new Error("Select between one and four exact Sphero Ollie robots.");
    }
    return this.#request("/api/v1/fabric/sphero-ollie/connect", {
      method: "POST",
      body: JSON.stringify({ robots }),
    });
  }

  listCoursePacks(): Promise<CoursePack[]> {
    return this.#request("/api/v1/fabric/course-packs");
  }

  listSessions(): Promise<InteractionSession[]> {
    return this.#request("/api/v1/fabric/sessions");
  }

  getSessionStartPolicy(sessionId: string): Promise<FabricSessionStartPolicy> {
    return this.#request(
      `/api/v1/fabric/sessions/${encodeURIComponent(sessionId)}/start-policy`,
    );
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
      latest: "true",
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

  listLifecycle(
    afterSequence = 0,
    commandId?: string,
  ): Promise<StoredFabricLifecycle[]> {
    const parameters = new URLSearchParams({
      afterSequence: String(afterSequence),
      limit: "100",
    });
    if (commandId !== undefined) parameters.set("commandId", commandId);
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

  listMediaSources(): Promise<FabricMediaSource[]> {
    return this.#request("/api/v1/fabric/media/sources");
  }

  createMediaPairing(
    siteId: string,
    roomId: string,
  ): Promise<FabricMediaPairing> {
    return this.#request("/api/v1/fabric/media/pairings", {
      method: "POST",
      body: JSON.stringify({ siteId, roomId }),
    });
  }

  analyzeMediaSource(sourceId: string): Promise<FabricVisionAnalysis> {
    return this.#request(
      `/api/v1/fabric/media/sources/${encodeURIComponent(sourceId)}/analyze`,
      { method: "POST" },
    );
  }

  async getMediaFrame(
    sourceId: string,
    etag?: string,
  ): Promise<FabricMediaFrame> {
    if (this.#credential === undefined) {
      throw new Error("Enter a CIT Fabric credential before connecting.");
    }
    const response = await this.#fetch(
      `${this.#baseUrl}/api/v1/fabric/media/sources/${encodeURIComponent(sourceId)}/frame`,
      {
        cache: "no-store",
        credentials: "omit",
        headers: {
          Accept: "image/jpeg,image/png",
          Authorization: `Bearer ${this.#credential}`,
          ...(etag === undefined ? {} : { "If-None-Match": etag }),
        },
      },
    );
    if (response.status === 304) {
      return {
        unchanged: true,
        ...(etag === undefined ? {} : { etag }),
      };
    }
    if (!response.ok) {
      return this.#readResponse<FabricMediaFrame>(response);
    }
    return {
      unchanged: false,
      blob: await response.blob(),
      ...optionalString("etag", response.headers.get("etag")),
      ...optionalNumber(
        "sequence",
        numericHeader(response.headers.get("x-cit-frame-sequence")),
      ),
      ...optionalString(
        "capturedAt",
        response.headers.get("x-cit-captured-at"),
      ),
    };
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
    return this.#readResponse<ResponseBody>(response);
  }

  async #readResponse<ResponseBody>(response: Response): Promise<ResponseBody> {
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

const numericHeader = (value: string | null): number | undefined => {
  if (value === null) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const optionalString = <Key extends string>(key: Key, value: string | null) =>
  value === null ? {} : ({ [key]: value } as Record<Key, string>);

const optionalNumber = <Key extends string>(
  key: Key,
  value: number | undefined,
) => (value === undefined ? {} : ({ [key]: value } as Record<Key, number>));
