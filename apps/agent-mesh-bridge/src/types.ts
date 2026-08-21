export interface AgentMeshWearable {
  readonly deviceId: string;
  readonly displayName: string;
  readonly kind: "even_g2" | "ray_ban";
  readonly status: "active" | "expired" | "revoked";
  readonly lastUsedAt?: string;
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
  readonly sessions: AgentMeshSession[];
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
