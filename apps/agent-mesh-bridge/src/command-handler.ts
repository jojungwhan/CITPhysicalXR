import { createHash } from "node:crypto";

import {
  validateDefinition,
  type AdapterCommandFrame,
  type AdapterCommandLifecycleFrame,
  type FabricCommandLifecycleStage,
  type FabricResolvedCommand,
} from "@citxr/protocol";

import {
  AGENT_PROMPT_CAPABILITY,
  DISPLAY_CAPABILITY,
  semanticSha256,
  type AgentMeshFabricMapping,
} from "./mapping.js";
import type { BridgeOutbox } from "./outbox.js";

const TERMINAL_STAGES = new Set<FabricCommandLifecycleStage>([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
  "REJECTED",
]);

export class MirrorCommandHandler {
  readonly #outbox: BridgeOutbox;

  constructor(outbox: BridgeOutbox) {
    this.#outbox = outbox;
  }

  handle(
    frame: AdapterCommandFrame,
    mapping: AgentMeshFabricMapping,
    now = new Date(),
  ): AdapterCommandLifecycleFrame[] {
    const command = frame.command;
    const existing = this.#outbox.command(command.commandId);
    if (existing !== undefined) {
      if (
        existing.idempotencyKey !== command.idempotencyKey ||
        existing.targetNodeId !== command.targetNodeId ||
        existing.correlationId !== command.correlationId
      ) {
        throw new Error(
          "Fabric command identity was reused for a different operation",
        );
      }
      return TERMINAL_STAGES.has(existing.stage)
        ? []
        : this.#finish(command, mapping, now);
    }
    this.#outbox.recordCommand({
      commandId: command.commandId,
      idempotencyKey: command.idempotencyKey,
      targetNodeId: command.targetNodeId,
      stage: "DISPATCHED",
      correlationId: command.correlationId,
      updatedAt: now.toISOString(),
    });
    return this.#finish(command, mapping, now);
  }

  #finish(
    command: FabricResolvedCommand,
    mapping: AgentMeshFabricMapping,
    now: Date,
  ): AdapterCommandLifecycleFrame[] {
    if (Date.parse(command.expiresAt) <= now.getTime()) {
      return [
        this.#terminal(
          command,
          "TIMED_OUT",
          "COMMAND_EXPIRED",
          "Command expired before adapter execution",
          now,
        ),
      ];
    }
    if (command.action === AGENT_PROMPT_CAPABILITY) {
      return this.#agentPrompt(command, mapping, now);
    }
    if (command.action === DISPLAY_CAPABILITY) {
      return this.#display(command, mapping, now);
    }
    return [
      this.#terminal(
        command,
        "REJECTED",
        "CAPABILITY_UNSUPPORTED",
        "Agent Mesh bridge does not consume this capability",
        now,
      ),
    ];
  }

  #agentPrompt(
    command: FabricResolvedCommand,
    mapping: AgentMeshFabricMapping,
    now: Date,
  ): AdapterCommandLifecycleFrame[] {
    const targetSession = mapping.agentSessionByNodeId.get(
      command.targetNodeId,
    );
    if (targetSession === undefined) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "TARGET_UNKNOWN",
          "Target is not a registered Agent Mesh session",
          now,
        ),
      ];
    }
    const prompt = exactTextParameter(command.parameters, "prompt", 32_768);
    if (prompt === undefined) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "INVALID_PARAMETERS",
          "Prompt command requires exactly one bounded prompt",
          now,
        ),
      ];
    }
    const receipt =
      command.causationId === undefined
        ? undefined
        : this.#outbox.receiptForMessage(command.causationId);
    if (receipt?.kind !== "intent" || !receipt.alreadyDispatched) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "COMPATIBILITY_MIRROR_ONLY",
          "Native Fabric-to-Agent-Mesh dispatch is not enabled in compatibility mode",
          now,
        ),
      ];
    }
    if (receipt.agentMeshSessionId !== targetSession.sessionId) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "MIRROR_TARGET_MISMATCH",
          "The mirrored prompt was already sent to a different Agent Mesh session",
          now,
        ),
      ];
    }
    if (receipt.semanticSha256 !== semanticSha256(prompt)) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "MIRROR_PAYLOAD_MISMATCH",
          "The command prompt differs from the mirrored semantic intent",
          now,
        ),
      ];
    }
    if (receipt.agentMeshDispatchedSessionId !== undefined) {
      this.#outbox.recordAgentRoute({
        agentMeshSessionId: receipt.agentMeshDispatchedSessionId,
        targetNodeId: command.targetNodeId,
        correlationId: command.correlationId,
        updatedAt: now.toISOString(),
      });
    }
    const accepted = this.#lifecycle(command, "ACCEPTED", now, {
      compatibilityMode: true,
      duplicateExecutionPrevented: true,
    });
    const succeeded = this.#terminal(
      command,
      "SUCCEEDED",
      "AGENT_MESH_ALREADY_DISPATCHED",
      "Existing Agent Mesh delivery was preserved without a duplicate prompt",
      now,
      {
        compatibilityMode: true,
        agentMeshCommandId: receipt.agentMeshCommandId ?? "unknown",
        agentMeshSessionId: targetSession.sessionId,
      },
    );
    return [accepted, succeeded];
  }

  #display(
    command: FabricResolvedCommand,
    mapping: AgentMeshFabricMapping,
    now: Date,
  ): AdapterCommandLifecycleFrame[] {
    if (!mapping.nodes.some((node) => node.nodeId === command.targetNodeId)) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "TARGET_UNKNOWN",
          "Target is not registered by this bridge",
          now,
        ),
      ];
    }
    const text = exactTextParameter(command.parameters, "text", 4_096);
    if (text === undefined) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "INVALID_PARAMETERS",
          "Display command requires exactly one bounded text value",
          now,
        ),
      ];
    }
    const receipt =
      command.causationId === undefined
        ? undefined
        : this.#outbox.receiptForMessage(command.causationId);
    if (
      receipt?.kind !== "completion" ||
      !receipt.legacyDisplayDelivered ||
      receipt.semanticSha256 !== semanticSha256(text)
    ) {
      return [
        this.#terminal(
          command,
          "REJECTED",
          "DISPLAY_SINK_UNAVAILABLE",
          "Compatibility mode only confirms output already projected by Agent Mesh",
          now,
        ),
      ];
    }
    const accepted = this.#lifecycle(command, "ACCEPTED", now, {
      compatibilityMode: true,
      legacyProjection: true,
    });
    const succeeded = this.#terminal(
      command,
      "SUCCEEDED",
      "DISPLAY_ALREADY_PROJECTED",
      "Existing Agent Mesh glasses projection was preserved",
      now,
      { compatibilityMode: true, duplicateDisplayPrevented: true },
    );
    return [accepted, succeeded];
  }

  #terminal(
    command: FabricResolvedCommand,
    stage: Extract<
      FabricCommandLifecycleStage,
      "SUCCEEDED" | "FAILED" | "CANCELLED" | "TIMED_OUT" | "REJECTED"
    >,
    code: string,
    message: string,
    now: Date,
    details: Record<string, unknown> = {},
  ): AdapterCommandLifecycleFrame {
    this.#outbox.updateCommand(command.commandId, stage, { updatedAt: now });
    return this.#lifecycle(command, stage, now, details, code, message);
  }

  #lifecycle(
    command: FabricResolvedCommand,
    stage: FabricCommandLifecycleStage,
    now: Date,
    details: Record<string, unknown>,
    code?: string,
    message?: string,
  ): AdapterCommandLifecycleFrame {
    const occurredAt = now.toISOString();
    const frame: AdapterCommandLifecycleFrame = {
      frameType: "adapter.command_lifecycle",
      frameId: deterministicUuid(`frame:${command.commandId}:${stage}`),
      protocolVersion: 1,
      lifecycle: {
        messageId: deterministicUuid(`lifecycle:${command.commandId}:${stage}`),
        schemaVersion: "1.0",
        messageType: "command.lifecycle",
        commandId: command.commandId,
        requestMessageId: command.requestMessageId,
        sessionId: command.sessionId,
        targetNodeId: command.targetNodeId,
        stage,
        occurredAt,
        correlationId: command.correlationId,
        ...(code === undefined ? {} : { code }),
        ...(message === undefined ? {} : { message }),
        details,
      },
      sentAt: occurredAt,
    };
    const result = validateDefinition("AdapterCommandLifecycleFrame", frame);
    if (!result.valid) {
      throw new TypeError(
        `Invalid adapter lifecycle: ${result.errors.join("; ")}`,
      );
    }
    return frame;
  }
}

const exactTextParameter = (
  parameters: Readonly<Record<string, unknown>>,
  name: string,
  maximumUtf8Bytes: number,
): string | undefined => {
  if (Object.keys(parameters).length !== 1) return undefined;
  const value = parameters[name];
  if (
    typeof value !== "string" ||
    !value.trim() ||
    Buffer.byteLength(value, "utf8") > maximumUtf8Bytes
  ) {
    return undefined;
  }
  return value;
};

const deterministicUuid = (source: string): string => {
  const digest = createHash("sha256")
    .update(source, "utf8")
    .digest("hex")
    .slice(0, 32);
  return `${digest.slice(0, 8)}-${digest.slice(8, 12)}-5${digest.slice(13, 16)}-8${digest.slice(17, 20)}-${digest.slice(20)}`;
};
