export interface AgentMeshWearable {
  readonly deviceId: string;
  readonly displayName: string;
  readonly kind: "even_g2" | "ray_ban";
  readonly scopes: Array<"read" | "prompt" | "approval" | "control" | "robot">;
  readonly status: "active" | "expired" | "revoked";
  readonly lastUsedAt?: string;
}

export interface AgentMeshCompanionInput {
  readonly parentDeviceId: string;
  readonly displayName: string;
  readonly kind: "even_r1";
  readonly status: "active" | "expired" | "revoked";
  readonly lastUsedAt: string;
}

export interface AgentMeshSession {
  readonly sessionId: string;
  readonly agent: "codex" | "claude";
  readonly nodeId: string;
  readonly nodeName: string;
  readonly workspaceId: string;
  readonly workspaceName: string;
  readonly sessionName?: string;
  readonly state: string;
  readonly controlStatus:
    "managed" | "observed" | "disconnected" | "unsupported";
  readonly headline: string;
  readonly displayText?: string;
  readonly lastActivityAt: string;
}

export interface AgentMeshDiscovery {
  readonly generatedAt: string;
  readonly wearables: AgentMeshWearable[];
  readonly companionInputs?: AgentMeshCompanionInput[];
  readonly sessions: AgentMeshSession[];
}

export type CitFabricControlAction =
  | "forward"
  | "backward"
  | "left"
  | "right"
  | "stop"
  | "light"
  | "demo"
  | "takeoff"
  | "land"
  | "power_on"
  | "power_off";

export interface CitFabricControlTarget {
  readonly role: string;
  readonly nodeId: string;
  readonly displayName: string;
  readonly kind: "ground_robot" | "drone_fleet" | "smart_plug";
  readonly connectionState:
    "connected" | "degraded" | "disconnected" | "unavailable";
  readonly actions: CitFabricControlAction[];
}

export interface CitFabricControlInventory {
  readonly generatedAt: string;
  readonly expiresAt: string;
  readonly sessionId: string;
  readonly coursePackId:
    "glasses-device-control" | "synchronized-motor-control";
  readonly sessionState:
    | "draft"
    | "ready"
    | "active"
    | "paused"
    | "stopped"
    | "emergency_stopped"
    | "failed";
  readonly armed: boolean;
  readonly targets: CitFabricControlTarget[];
}

interface AgentMeshInteractionBase {
  readonly interactionId: string;
  readonly sequence: number;
  readonly deviceId: string;
  readonly deviceDisplayName: string;
  readonly createdAt: string;
}

export interface AgentMeshRingInteraction extends AgentMeshInteractionBase {
  readonly deviceKind: "even_g2";
  readonly source: "even_r1";
  readonly gesture: "tap" | "double_tap" | "scroll_up" | "scroll_down";
}

export interface AgentMeshDeviceControlInteraction extends AgentMeshInteractionBase {
  readonly deviceKind: "even_g2" | "ray_ban";
  readonly source: "device_control";
  readonly action:
    | "forward"
    | "backward"
    | "left"
    | "right"
    | "stop"
    | "light"
    | "demo"
    | "takeoff"
    | "land"
    | "power_on"
    | "power_off"
    | "activate";
  readonly target:
    | "ground_outputs"
    | "tello_fleet"
    | "power_outputs"
    | "assigned_output"
    | "all_outputs";
  readonly targetRole?: string;
  readonly batchId?: string;
  readonly confirmed: true;
}

export type AgentMeshInteraction =
  AgentMeshRingInteraction | AgentMeshDeviceControlInteraction;

export interface AgentMeshInteractionFeed {
  readonly interactions: AgentMeshInteraction[];
  readonly nextCursor: number;
}

export interface AgentMeshIntent {
  readonly intentId: string;
  readonly sequence: number;
  readonly deviceId: string;
  readonly deviceKind: "even_g2" | "ray_ban";
  readonly deviceDisplayName: string;
  readonly requestedSessionId: string;
  readonly dispatchedSessionId: string;
  readonly agentMeshCommandId: string;
  readonly prompt: string;
  readonly route: "managed" | "continuation";
  readonly createdAt: string;
  readonly alreadyDispatched: true;
}

export interface AgentMeshIntentFeed {
  readonly intents: AgentMeshIntent[];
  readonly nextCursor: number;
}

export interface AgentMeshCompletion {
  readonly notificationId: string;
  readonly sequence: number;
  readonly sessionId: string;
  readonly agent: "codex" | "claude";
  readonly nodeId: string;
  readonly nodeName: string;
  readonly workspaceName: string;
  readonly sessionName?: string;
  readonly outcome: "completed" | "failed" | "interrupted";
  readonly title: string;
  readonly displayText: string;
  readonly speechText: string;
  readonly createdAt: string;
}

export interface AgentMeshCompletionFeed {
  readonly notifications: AgentMeshCompletion[];
  readonly nextCursor: number;
}
