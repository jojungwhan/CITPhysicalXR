/* eslint-disable */
/**
 * Generated from packages/protocol-schema/schemas/cit-protocol.schema.json.
 * Do not edit by hand.
 */

/**
 * Language-neutral foundation messages. This schema does not authorize physical execution.
 */
export type CITPhysicalXRProtocolV1 =
  | CitEnvelope
  | DeviceCommandIntent
  | DeviceEvent
  | DeviceDescriptor
  | PluginManifest
  | IntegrationNode
  | HealthReport
  | FabricEventEnvelope
  | FabricCommandRequest
  | FabricResolvedCommand
  | FabricCommandLifecycleEvent
  | CreateInteractionSessionRequest
  | InteractionSession
  | CoursePack
  | FlowRecipe
  | AdapterClientFrame
  | AdapterServerFrame
  | CommandResult
  | ProtocolError;
export type Identifier = string;
export type CapabilityIdentifier = string;
export type ActionIdentifier = string;
export type FabricSchemaVersion = "1.0";
export type CapabilityDirection = "publish" | "consume" | "bidirectional";
export type FabricLatencyClass =
  "safety_critical" | "interactive" | "ui_feedback" | "conversational" | "bulk";
export type FabricSafetyClassification =
  "none" | "informational" | "bounded_physical" | "flight" | "electrical";
export type FabricDataClassification =
  | "public"
  | "operational"
  | "student"
  | "source_code"
  | "voice_transcript"
  | "biosignal_derived"
  | "sensitive_raw"
  | "secret";
export type SimulatorAvailability =
  "included" | "recorded_replay" | "external" | "none";
export type FabricNodeConnectionState =
  | "registering"
  | "connected"
  | "degraded"
  | "unavailable"
  | "disconnected"
  | "unsafe";
export type FabricNodeHealthState =
  "healthy" | "degraded" | "unhealthy" | "unknown";
export type FabricCommandPriority =
  | "emergency_stop"
  | "safety_engine"
  | "instructor_override"
  | "lesson_automation"
  | "student_interaction"
  | "autonomous_agent";
export type FabricCommandLifecycleStage =
  | "PROPOSED"
  | "VALIDATED"
  | "AUTHORIZED"
  | "DISPATCHED"
  | "ACCEPTED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "TIMED_OUT"
  | "REJECTED";
export type FabricSessionMode = "simulation" | "physical";
export type FabricSessionState =
  | "draft"
  | "ready"
  | "active"
  | "paused"
  | "stopped"
  | "emergency_stopped"
  | "failed";
export type FlowGuard =
  | "session_is_active"
  | "target_is_connected"
  | "role_is_assigned"
  | "instructor_override_is_clear"
  | "target_is_armed"
  | "approval_is_present";
/**
 * Flows with the same non-empty group are authorized independently and dispatched concurrently for one source event.
 */
export type Identifier1 = string;
export type AdapterClientFrame =
  | AdapterAuthenticationFrame
  | AdapterRegistrationFrame
  | AdapterHeartbeatFrame
  | AdapterEventFrame
  | AdapterCommandLifecycleFrame;
export type AdapterServerFrame =
  | AdapterWelcomeFrame
  | AdapterRegisteredFrame
  | AdapterCommandFrame
  | AdapterAcknowledgementFrame
  | AdapterStopFrame;

export interface CitEnvelope {
  protocolVersion: 1;
  messageId: string;
  type: string;
  runtimeId?: Identifier;
  deviceId?: Identifier;
  clientId?: Identifier;
  sessionId?: Identifier;
  correlationId?: string;
  sequence?: number;
  sentAt: string;
  expiresAt?: string;
  idempotencyKey?: string;
  payload: unknown;
}
export interface DeviceCommandIntent {
  commandId: string;
  sessionId: Identifier;
  deviceId: Identifier;
  capability: CapabilityIdentifier;
  action: ActionIdentifier;
  arguments: JsonObject;
  source:
    | "student_blocks"
    | "student_python"
    | "quest"
    | "leap"
    | "instructor"
    | "agent_mesh"
    | "system";
  issuedAt: string;
  expiresAt: string;
  idempotencyKey: string;
  safetyContext: SafetyContext;
}
export interface JsonObject {
  [k: string]: unknown | undefined;
}
export interface SafetyContext {
  policyId: Identifier;
  armed: boolean;
  deadmanActive?: boolean;
  inputConfidence?: number;
}
export interface DeviceEvent {
  eventId: string;
  deviceId: Identifier;
  sessionId?: Identifier;
  sequence?: number;
  category:
    | "connection"
    | "input"
    | "telemetry"
    | "motion"
    | "sensor"
    | "safety"
    | "program"
    | "diagnostic";
  name: string;
  values: JsonObject;
  sourceTimestamp?: string;
  receivedAt: string;
  historical?: boolean;
}
export interface DeviceDescriptor {
  deviceId: Identifier;
  displayName: string;
  deviceType: "robot" | "input" | "xr_client" | "virtual" | "bridge";
  model: Identifier;
  adapterId: Identifier;
  adapterVersion: string;
  physical: boolean;
  /**
   * @minItems 1
   * @maxItems 256
   */
  capabilities: [CapabilityIdentifier, ...CapabilityIdentifier[]];
  safetyProfile?: Identifier;
}
export interface PluginManifest {
  schemaVersion: FabricSchemaVersion;
  pluginId: Identifier;
  pluginVersion: string;
  runtimeVersion: string;
  displayName: string;
  adapterMode: "in_process" | "out_of_process";
  configurationSchema: JsonObject;
  /**
   * @maxItems 256
   */
  publishedCapabilities: CapabilityDescriptor[];
  /**
   * @maxItems 256
   */
  consumedCapabilities: CapabilityDescriptor[];
  /**
   * @maxItems 64
   */
  requiredPermissions: Identifier[];
  safetyClassification: FabricSafetyClassification;
  /**
   * @minItems 1
   * @maxItems 8
   */
  dataClassifications:
    | [FabricDataClassification]
    | [FabricDataClassification, FabricDataClassification]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ];
  simulatorAvailability: SimulatorAvailability;
  vendor?: string;
  description?: string;
}
export interface CapabilityDescriptor {
  name: CapabilityIdentifier;
  version: string;
  direction: CapabilityDirection;
  schemaRef?: string;
  units?: string;
  maximumRateHz?: number;
  latencyClass: FabricLatencyClass;
  safetyClassification: FabricSafetyClassification;
  dataClassification: FabricDataClassification;
  constraints: JsonObject;
}
export interface IntegrationNode {
  schemaVersion: FabricSchemaVersion;
  nodeId: Identifier;
  pluginId: Identifier;
  pluginVersion: string;
  runtimeVersion: string;
  hostId: Identifier;
  siteId: Identifier;
  roomId: Identifier;
  displayName: string;
  connectionState: FabricNodeConnectionState;
  healthState: FabricNodeHealthState;
  physical: boolean;
  simulated: boolean;
  /**
   * @maxItems 256
   */
  publishedCapabilities: CapabilityDescriptor[];
  /**
   * @maxItems 256
   */
  consumedCapabilities: CapabilityDescriptor[];
  configurationSchema: JsonObject;
  safetyClassification: FabricSafetyClassification;
  /**
   * @minItems 1
   * @maxItems 8
   */
  dataClassifications:
    | [FabricDataClassification]
    | [FabricDataClassification, FabricDataClassification]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ]
    | [
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
        FabricDataClassification,
      ];
  simulatorAvailable: boolean;
  /**
   * @maxItems 64
   */
  requiredPermissions?: Identifier[];
  lastSeenAt: string;
  metadata: JsonObject;
}
export interface HealthReport {
  schemaVersion: FabricSchemaVersion;
  nodeId: Identifier;
  reportedAt: string;
  connectionState: FabricNodeConnectionState;
  healthState: FabricNodeHealthState;
  message?: string;
  batteryPercent?: number;
  metrics: JsonObject;
}
export interface FabricEventEnvelope {
  messageId: string;
  schemaVersion: FabricSchemaVersion;
  messageType: "event";
  topic: CapabilityIdentifier;
  sourceNodeId: Identifier;
  sourceCapability: CapabilityIdentifier;
  siteId: Identifier;
  roomId: Identifier;
  sessionId: Identifier;
  participantId?: Identifier;
  timestamp: string;
  monotonicTimestamp: number;
  sequence: number;
  correlationId?: string;
  causationId?: string;
  confidence?: number;
  ttlMs: number;
  dataClassification: FabricDataClassification;
  payload: JsonObject;
}
export interface FabricCommandRequest {
  messageId: string;
  schemaVersion: FabricSchemaVersion;
  messageType: "command.requested";
  action: CapabilityIdentifier;
  target: FabricRoleTarget;
  sessionId: Identifier;
  parameters: JsonObject;
  priority: FabricCommandPriority;
  idempotencyKey: string;
  requestedAt: string;
  ttlMs: number;
  safetyProfile: Identifier;
  correlationId: string;
  causationId?: string;
  sourceNodeId?: Identifier;
}
export interface FabricRoleTarget {
  role: Identifier;
}
export interface FabricResolvedCommand {
  commandId: string;
  requestMessageId: string;
  schemaVersion: FabricSchemaVersion;
  sessionId: Identifier;
  targetNodeId: Identifier;
  action: CapabilityIdentifier;
  parameters: JsonObject;
  priority: FabricCommandPriority;
  idempotencyKey: string;
  requestedAt: string;
  expiresAt: string;
  safetyProfile: Identifier;
  correlationId: string;
  causationId?: string;
  sourceNodeId?: Identifier;
}
export interface FabricCommandLifecycleEvent {
  messageId: string;
  schemaVersion: FabricSchemaVersion;
  messageType: "command.lifecycle";
  commandId: string;
  requestMessageId: string;
  sessionId: Identifier;
  targetNodeId: Identifier;
  stage: FabricCommandLifecycleStage;
  occurredAt: string;
  correlationId: string;
  code?: Identifier;
  message?: string;
  details: JsonObject;
}
export interface CreateInteractionSessionRequest {
  coursePackId: Identifier;
  coursePackVersion: string;
  siteId: Identifier;
  roomId: Identifier;
  mode: FabricSessionMode;
  /**
   * @maxItems 128
   */
  participantIds?: Identifier[];
}
export interface InteractionSession {
  schemaVersion: FabricSchemaVersion;
  sessionId: Identifier;
  coursePackId: Identifier;
  coursePackVersion: string;
  siteId: Identifier;
  roomId: Identifier;
  mode: FabricSessionMode;
  state: FabricSessionState;
  armed?: boolean;
  armedAt?: string;
  armedBy?: Identifier;
  disarmReason?: string;
  /**
   * @maxItems 128
   */
  participantIds: Identifier[];
  /**
   * @maxItems 64
   */
  roleBindings: RoleBinding[];
  safetyProfile: Identifier;
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  endedAt?: string;
  createdBy: Identifier;
}
export interface RoleBinding {
  role: Identifier;
  nodeId: Identifier;
  requiredCapability: CapabilityIdentifier;
  assignedAt: string;
  assignedBy: Identifier;
}
export interface CoursePack {
  schemaVersion: FabricSchemaVersion;
  coursePackId: Identifier;
  version: string;
  displayName: string;
  description?: string;
  /**
   * @minItems 1
   * @maxItems 64
   */
  roles: [CourseRoleRequirement, ...CourseRoleRequirement[]];
  /**
   * @maxItems 128
   */
  flows: FlowRecipe[];
  safetyProfile: Identifier;
  simulatorRequired: boolean;
  /**
   * @maxItems 128
   */
  assessmentEvents: CapabilityIdentifier[];
  fallbackBehavior: string;
}
export interface CourseRoleRequirement {
  role: Identifier;
  /**
   * @minItems 1
   * @maxItems 32
   */
  oneOfCapabilities: [CapabilityIdentifier, ...CapabilityIdentifier[]];
  /**
   * The role's direction within this course. Registered node capabilities remain authoritative for the device itself.
   */
  ioType?: "input" | "output" | "bidirectional";
  optional: boolean;
}
export interface FlowRecipe {
  flowId: Identifier;
  version: number;
  trigger: FlowTrigger;
  command: FlowAction;
  target: FabricRoleTarget;
  /**
   * @maxItems 16
   */
  guards:
    | []
    | [FlowGuard]
    | [FlowGuard, FlowGuard]
    | [FlowGuard, FlowGuard, FlowGuard]
    | [FlowGuard, FlowGuard, FlowGuard, FlowGuard]
    | [FlowGuard, FlowGuard, FlowGuard, FlowGuard, FlowGuard]
    | [FlowGuard, FlowGuard, FlowGuard, FlowGuard, FlowGuard, FlowGuard]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ]
    | [
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
        FlowGuard,
      ];
  safetyProfile: Identifier;
  /**
   * @maxItems 16
   */
  outputRoles?:
    | []
    | [Identifier]
    | [Identifier, Identifier]
    | [Identifier, Identifier, Identifier]
    | [Identifier, Identifier, Identifier, Identifier]
    | [Identifier, Identifier, Identifier, Identifier, Identifier]
    | [Identifier, Identifier, Identifier, Identifier, Identifier, Identifier]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ]
    | [
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
        Identifier,
      ];
  parallelGroup?: Identifier1;
  enabled: boolean;
}
export interface FlowTrigger {
  event: CapabilityIdentifier;
  minimumConfidence?: number;
  debounceMs?: number;
  payloadEquals?: JsonObject;
}
export interface FlowAction {
  action: CapabilityIdentifier;
  fixedParameters: JsonObject;
  /**
   * @maxItems 32
   */
  parameterBindings: FlowParameterBinding[];
}
export interface FlowParameterBinding {
  payloadField: Identifier;
  parameter: Identifier;
}
export interface AdapterAuthenticationFrame {
  frameType: "adapter.authenticate";
  frameId: string;
  protocolVersion: 1;
  credential: string;
  sentAt: string;
}
export interface AdapterRegistrationFrame {
  frameType: "adapter.register";
  frameId: string;
  protocolVersion: 1;
  manifest: PluginManifest;
  /**
   * @minItems 1
   * @maxItems 64
   */
  nodes: [IntegrationNode, ...IntegrationNode[]];
  sentAt: string;
}
export interface AdapterHeartbeatFrame {
  frameType: "adapter.heartbeat";
  frameId: string;
  protocolVersion: 1;
  /**
   * @minItems 1
   * @maxItems 64
   */
  reports: [HealthReport, ...HealthReport[]];
  sentAt: string;
}
export interface AdapterEventFrame {
  frameType: "adapter.event";
  frameId: string;
  protocolVersion: 1;
  event: FabricEventEnvelope;
  sentAt: string;
}
export interface AdapterCommandLifecycleFrame {
  frameType: "adapter.command_lifecycle";
  frameId: string;
  protocolVersion: 1;
  lifecycle: FabricCommandLifecycleEvent;
  sentAt: string;
}
export interface AdapterWelcomeFrame {
  frameType: "adapter.welcome";
  frameId: string;
  protocolVersion: 1;
  runtimeId: Identifier;
  heartbeatIntervalMs: number;
  sentAt: string;
}
export interface AdapterRegisteredFrame {
  frameType: "adapter.registered";
  frameId: string;
  protocolVersion: 1;
  /**
   * @minItems 1
   * @maxItems 64
   */
  registeredNodeIds: [Identifier, ...Identifier[]];
  sentAt: string;
}
export interface AdapterCommandFrame {
  frameType: "adapter.command";
  frameId: string;
  protocolVersion: 1;
  command: FabricResolvedCommand;
  sentAt: string;
}
export interface AdapterAcknowledgementFrame {
  frameType: "adapter.ack";
  frameId: string;
  protocolVersion: 1;
  acknowledgedFrameId: string;
  status: "accepted" | "duplicate";
  streamSequence?: number;
  sentAt: string;
}
export interface AdapterStopFrame {
  frameType: "adapter.stop";
  frameId: string;
  protocolVersion: 1;
  nodeId: Identifier;
  reason: string;
  sentAt: string;
}
export interface CommandResult {
  commandId: string;
  deviceId: Identifier;
  status:
    "accepted" | "completed" | "rejected" | "duplicate" | "expired" | "failed";
  message?: string;
  recordedAt: string;
  details?: JsonObject;
}
export interface ProtocolError {
  code:
    | "DEVICE_NOT_FOUND"
    | "DEVICE_OFFLINE"
    | "DEVICE_NOT_ASSIGNED"
    | "DEVICE_LEASE_CONFLICT"
    | "DEVICE_NOT_ARMED"
    | "DEVICE_CAPABILITY_UNSUPPORTED"
    | "COMMAND_EXPIRED"
    | "COMMAND_DUPLICATE"
    | "SAFETY_POLICY_DENIED"
    | "PROTOCOL_VERSION_UNSUPPORTED"
    | "INVALID_MESSAGE";
  message: string;
  deviceId?: Identifier;
  sessionId?: Identifier;
  correlationId: string;
  recoverySuggestion: string;
  details?: JsonObject;
}
