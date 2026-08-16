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
  | CommandResult
  | ProtocolError;
export type Identifier = string;
export type CapabilityIdentifier = string;
export type ActionIdentifier = string;

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
