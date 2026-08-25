import { createHash } from "node:crypto";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import {
  validateDefinition,
  type AdapterCommandLifecycleFrame,
  type AdapterEventFrame,
  type FabricCommandLifecycleStage,
} from "@citxr/protocol";

export interface BridgeEventReceipt {
  readonly messageId: string;
  readonly sourceKey: string;
  readonly kind: "intent" | "interaction" | "completion";
  readonly agentMeshIntentId?: string;
  readonly agentMeshCommandId?: string;
  readonly agentMeshSessionId?: string;
  readonly agentMeshDispatchedSessionId?: string;
  readonly alreadyDispatched: boolean;
  readonly legacyDisplayDelivered: boolean;
  readonly semanticSha256?: string;
}

export interface PendingBridgeEvent {
  readonly frameId: string;
  readonly frame: AdapterEventFrame;
  readonly receipt: BridgeEventReceipt;
}

export interface PendingLifecycleFrame {
  readonly frameId: string;
  readonly frame: AdapterCommandLifecycleFrame;
}

export interface BridgeCommandReceipt {
  readonly commandId: string;
  readonly idempotencyKey: string;
  readonly targetNodeId: string;
  readonly stage: FabricCommandLifecycleStage;
  readonly agentMeshCommandId?: string;
  readonly correlationId: string;
  readonly updatedAt: string;
}

export interface BridgeAgentRoute {
  readonly agentMeshSessionId: string;
  readonly targetNodeId: string;
  readonly correlationId: string;
  readonly updatedAt: string;
}

const MAX_FRAME_BYTES = 65_536;

export class BridgeOutbox {
  readonly #database: DatabaseSync;

  constructor(databasePath: string) {
    mkdirSync(path.dirname(path.resolve(databasePath)), {
      recursive: true,
      mode: 0o700,
    });
    this.#database = new DatabaseSync(databasePath);
    this.#database.exec("PRAGMA busy_timeout = 5000");
    this.#database.exec("PRAGMA journal_mode = WAL");
    this.#database.exec("PRAGMA synchronous = FULL");
    this.#database.exec(`
      CREATE TABLE IF NOT EXISTS bridge_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      ) STRICT;

      CREATE TABLE IF NOT EXISTS bridge_outbox (
        frame_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE,
        source_key TEXT NOT NULL UNIQUE,
        frame_json TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      ) STRICT;

      CREATE TABLE IF NOT EXISTS bridge_event_receipts (
        message_id TEXT PRIMARY KEY,
        source_key TEXT NOT NULL UNIQUE,
        receipt_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        accepted_at TEXT NOT NULL
      ) STRICT;

      CREATE TABLE IF NOT EXISTS bridge_lifecycle_outbox (
        frame_id TEXT PRIMARY KEY,
        command_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        frame_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(command_id, stage)
      ) STRICT;

      CREATE TABLE IF NOT EXISTS bridge_commands (
        command_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        target_node_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        agent_mesh_command_id TEXT,
        correlation_id TEXT NOT NULL,
        updated_at TEXT NOT NULL
      ) STRICT;

      CREATE TABLE IF NOT EXISTS bridge_agent_routes (
        agent_mesh_session_id TEXT PRIMARY KEY,
        target_node_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        updated_at TEXT NOT NULL
      ) STRICT;
    `);
  }

  close(): void {
    this.#database.close();
  }

  nextNodeSequence(nodeId: string): number {
    const key = `node-sequence:${nodeId}`;
    return this.#transaction(() => {
      const current = this.stateNumber(key);
      const next = current + 1;
      this.setStateNumber(key, next);
      return next;
    });
  }

  stateNumber(key: string): number {
    const row = this.#database
      .prepare("SELECT value FROM bridge_state WHERE key = ?")
      .get(key);
    if (row === undefined) return 0;
    if (typeof row.value !== "string" || !/^\d+$/u.test(row.value)) {
      throw new Error(`Bridge state ${key} is corrupt`);
    }
    const value = Number(row.value);
    if (!Number.isSafeInteger(value))
      throw new Error(`Bridge state ${key} is too large`);
    return value;
  }

  setStateNumber(key: string, value: number): void {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new TypeError("Bridge cursor must be a non-negative safe integer");
    }
    this.#database
      .prepare(
        `INSERT INTO bridge_state(key, value) VALUES (?, ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      )
      .run(key, String(value));
  }

  enqueueEvent(
    sourceKey: string,
    frame: AdapterEventFrame,
    receipt: Omit<BridgeEventReceipt, "messageId" | "sourceKey">,
  ): PendingBridgeEvent {
    const validation = validateDefinition("AdapterEventFrame", frame);
    if (!validation.valid) {
      throw new TypeError(
        `Invalid Fabric adapter event: ${validation.errors.join("; ")}`,
      );
    }
    const frameJson = JSON.stringify(frame);
    if (Buffer.byteLength(frameJson, "utf8") > MAX_FRAME_BYTES) {
      throw new TypeError(
        "Bridge event exceeds its 64 KiB durable-delivery limit",
      );
    }
    if (!sourceKey.trim() || sourceKey.length > 500) {
      throw new TypeError(
        "Bridge event source key must contain 1 through 500 characters",
      );
    }
    const exactReceipt: BridgeEventReceipt = {
      ...receipt,
      messageId: frame.event.messageId,
      sourceKey,
    };
    const receiptJson = JSON.stringify(exactReceipt);
    this.#database
      .prepare(
        `INSERT OR IGNORE INTO bridge_outbox(
           frame_id, message_id, source_key, frame_json, receipt_json, created_at
         ) VALUES (?, ?, ?, ?, ?, ?)`,
      )
      .run(
        frame.frameId,
        frame.event.messageId,
        sourceKey,
        frameJson,
        receiptJson,
        new Date().toISOString(),
      );
    const row = this.#database
      .prepare(
        `SELECT frame_id, frame_json, receipt_json
         FROM bridge_outbox WHERE source_key = ?`,
      )
      .get(sourceKey);
    if (row === undefined) {
      const accepted = this.#database
        .prepare(
          `SELECT message_id, receipt_json FROM bridge_event_receipts WHERE source_key = ?`,
        )
        .get(sourceKey);
      if (accepted === undefined) {
        throw new Error("Bridge event could not be persisted");
      }
      return {
        frameId: frame.frameId,
        frame,
        receipt: parseReceipt(requiredString(accepted, "receipt_json")),
      };
    }
    return {
      frameId: requiredString(row, "frame_id"),
      frame: parseFrame(requiredString(row, "frame_json")),
      receipt: parseReceipt(requiredString(row, "receipt_json")),
    };
  }

  pendingEvents(limit = 100): PendingBridgeEvent[] {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
      throw new TypeError("Bridge outbox limit must be from 1 through 100");
    }
    return this.#database
      .prepare(
        `SELECT frame_id, frame_json, receipt_json
         FROM bridge_outbox ORDER BY created_at ASC, frame_id ASC LIMIT ?`,
      )
      .all(limit)
      .map((row) => ({
        frameId: requiredString(row, "frame_id"),
        frame: parseFrame(requiredString(row, "frame_json")),
        receipt: parseReceipt(requiredString(row, "receipt_json")),
      }));
  }

  discardUndeliverableFrames(
    sessionId: string,
    at = new Date(),
  ): { readonly events: number; readonly lifecycles: number } {
    const now = at.getTime();
    if (!Number.isFinite(now))
      throw new TypeError("Discard time must be valid");
    return this.#transaction(() => {
      let events = 0;
      let lifecycles = 0;
      const deleteEvent = this.#database.prepare(
        "DELETE FROM bridge_outbox WHERE frame_id = ?",
      );
      for (const row of this.#database
        .prepare("SELECT frame_id, frame_json FROM bridge_outbox")
        .all()) {
        const frame = parseFrame(requiredString(row, "frame_json"));
        const expiresAt =
          new Date(frame.event.timestamp).getTime() + frame.event.ttlMs;
        if (frame.event.sessionId !== sessionId || expiresAt <= now) {
          events += Number(
            deleteEvent.run(requiredString(row, "frame_id")).changes,
          );
        }
      }
      const deleteLifecycle = this.#database.prepare(
        "DELETE FROM bridge_lifecycle_outbox WHERE frame_id = ?",
      );
      for (const row of this.#database
        .prepare("SELECT frame_id, frame_json FROM bridge_lifecycle_outbox")
        .all()) {
        const frame = parseLifecycleFrame(requiredString(row, "frame_json"));
        if (frame.lifecycle.sessionId !== sessionId) {
          lifecycles += Number(
            deleteLifecycle.run(requiredString(row, "frame_id")).changes,
          );
        }
      }
      return { events, lifecycles };
    });
  }

  enqueueLifecycle(frame: AdapterCommandLifecycleFrame): PendingLifecycleFrame {
    const validation = validateDefinition(
      "AdapterCommandLifecycleFrame",
      frame,
    );
    if (!validation.valid) {
      throw new TypeError(
        `Invalid Fabric lifecycle frame: ${validation.errors.join("; ")}`,
      );
    }
    const frameJson = JSON.stringify(frame);
    if (Buffer.byteLength(frameJson, "utf8") > MAX_FRAME_BYTES) {
      throw new TypeError(
        "Bridge lifecycle exceeds its 64 KiB durable-delivery limit",
      );
    }
    this.#database
      .prepare(
        `INSERT OR IGNORE INTO bridge_lifecycle_outbox(
           frame_id, command_id, stage, frame_json, created_at
         ) VALUES (?, ?, ?, ?, ?)`,
      )
      .run(
        frame.frameId,
        frame.lifecycle.commandId,
        frame.lifecycle.stage,
        frameJson,
        new Date().toISOString(),
      );
    const row = this.#database
      .prepare(
        `SELECT frame_id, frame_json FROM bridge_lifecycle_outbox
         WHERE command_id = ? AND stage = ?`,
      )
      .get(frame.lifecycle.commandId, frame.lifecycle.stage);
    if (row === undefined)
      throw new Error("Bridge lifecycle could not be persisted");
    return {
      frameId: requiredString(row, "frame_id"),
      frame: parseLifecycleFrame(requiredString(row, "frame_json")),
    };
  }

  pendingLifecycles(limit = 100): PendingLifecycleFrame[] {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
      throw new TypeError(
        "Bridge lifecycle outbox limit must be from 1 through 100",
      );
    }
    return this.#database
      .prepare(
        `SELECT frame_id, frame_json FROM bridge_lifecycle_outbox
         ORDER BY created_at ASC, frame_id ASC LIMIT ?`,
      )
      .all(limit)
      .map((row) => ({
        frameId: requiredString(row, "frame_id"),
        frame: parseLifecycleFrame(requiredString(row, "frame_json")),
      }));
  }

  acknowledgeLifecycleFrame(frameId: string): boolean {
    return (
      this.#database
        .prepare("DELETE FROM bridge_lifecycle_outbox WHERE frame_id = ?")
        .run(frameId).changes === 1
    );
  }

  acknowledgeFrame(
    frameId: string,
    acceptedAt = new Date(),
  ): BridgeEventReceipt | undefined {
    return this.#transaction(() => {
      const row = this.#database
        .prepare(
          `SELECT message_id, source_key, frame_json, receipt_json
           FROM bridge_outbox WHERE frame_id = ?`,
        )
        .get(frameId);
      if (row === undefined) return undefined;
      const messageId = requiredString(row, "message_id");
      const sourceKey = requiredString(row, "source_key");
      const frameJson = requiredString(row, "frame_json");
      const receiptJson = requiredString(row, "receipt_json");
      this.#database
        .prepare(
          `INSERT OR IGNORE INTO bridge_event_receipts(
             message_id, source_key, receipt_json, payload_sha256, accepted_at
           ) VALUES (?, ?, ?, ?, ?)`,
        )
        .run(
          messageId,
          sourceKey,
          receiptJson,
          createHash("sha256").update(frameJson).digest("hex"),
          acceptedAt.toISOString(),
        );
      this.#database
        .prepare("DELETE FROM bridge_outbox WHERE frame_id = ?")
        .run(frameId);
      return parseReceipt(receiptJson);
    });
  }

  receiptForMessage(messageId: string): BridgeEventReceipt | undefined {
    const pending = this.#database
      .prepare("SELECT receipt_json FROM bridge_outbox WHERE message_id = ?")
      .get(messageId);
    const accepted =
      pending ??
      this.#database
        .prepare(
          "SELECT receipt_json FROM bridge_event_receipts WHERE message_id = ?",
        )
        .get(messageId);
    return accepted === undefined
      ? undefined
      : parseReceipt(requiredString(accepted, "receipt_json"));
  }

  command(commandId: string): BridgeCommandReceipt | undefined {
    const row = this.#database
      .prepare("SELECT * FROM bridge_commands WHERE command_id = ?")
      .get(commandId);
    return row === undefined ? undefined : commandReceipt(row);
  }

  recordCommand(input: BridgeCommandReceipt): BridgeCommandReceipt {
    return this.#transaction(() => {
      const existing = this.#database
        .prepare(
          "SELECT * FROM bridge_commands WHERE command_id = ? OR idempotency_key = ?",
        )
        .get(input.commandId, input.idempotencyKey);
      if (existing !== undefined) {
        const parsed = commandReceipt(existing);
        if (
          parsed.commandId !== input.commandId ||
          parsed.targetNodeId !== input.targetNodeId ||
          parsed.correlationId !== input.correlationId
        ) {
          throw new Error(
            "Fabric command identity was reused for a different operation",
          );
        }
        return parsed;
      }
      this.#database
        .prepare(
          `INSERT INTO bridge_commands(
             command_id, idempotency_key, target_node_id, stage,
             agent_mesh_command_id, correlation_id, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
        .run(
          input.commandId,
          input.idempotencyKey,
          input.targetNodeId,
          input.stage,
          input.agentMeshCommandId ?? null,
          input.correlationId,
          input.updatedAt,
        );
      return input;
    });
  }

  updateCommand(
    commandId: string,
    stage: FabricCommandLifecycleStage,
    options: {
      readonly agentMeshCommandId?: string;
      readonly updatedAt?: Date;
    } = {},
  ): BridgeCommandReceipt {
    const updatedAt = (options.updatedAt ?? new Date()).toISOString();
    const changed = this.#database
      .prepare(
        `UPDATE bridge_commands
         SET stage = ?, agent_mesh_command_id = COALESCE(?, agent_mesh_command_id), updated_at = ?
         WHERE command_id = ?`,
      )
      .run(stage, options.agentMeshCommandId ?? null, updatedAt, commandId);
    if (changed.changes !== 1) throw new Error("Unknown Fabric bridge command");
    const result = this.command(commandId);
    if (result === undefined)
      throw new Error("Fabric bridge command update was lost");
    return result;
  }

  latestCorrelationForTarget(targetNodeId: string): string | undefined {
    const row = this.#database
      .prepare(
        `SELECT correlation_id FROM bridge_commands
         WHERE target_node_id = ? ORDER BY updated_at DESC LIMIT 1`,
      )
      .get(targetNodeId);
    return row === undefined
      ? undefined
      : requiredString(row, "correlation_id");
  }

  recordAgentRoute(route: BridgeAgentRoute): void {
    this.#database
      .prepare(
        `INSERT INTO bridge_agent_routes(
           agent_mesh_session_id, target_node_id, correlation_id, updated_at
         ) VALUES (?, ?, ?, ?)
         ON CONFLICT(agent_mesh_session_id) DO UPDATE SET
           target_node_id = excluded.target_node_id,
           correlation_id = excluded.correlation_id,
           updated_at = excluded.updated_at`,
      )
      .run(
        route.agentMeshSessionId,
        route.targetNodeId,
        route.correlationId,
        route.updatedAt,
      );
  }

  agentRoute(agentMeshSessionId: string): BridgeAgentRoute | undefined {
    const row = this.#database
      .prepare(
        "SELECT * FROM bridge_agent_routes WHERE agent_mesh_session_id = ?",
      )
      .get(agentMeshSessionId);
    return row === undefined
      ? undefined
      : {
          agentMeshSessionId: requiredString(row, "agent_mesh_session_id"),
          targetNodeId: requiredString(row, "target_node_id"),
          correlationId: requiredString(row, "correlation_id"),
          updatedAt: requiredString(row, "updated_at"),
        };
  }

  #transaction<Result>(operation: () => Result): Result {
    this.#database.exec("BEGIN IMMEDIATE");
    try {
      const result = operation();
      this.#database.exec("COMMIT");
      return result;
    } catch (error) {
      this.#database.exec("ROLLBACK");
      throw error;
    }
  }
}

const requiredString = (row: Record<string, unknown>, key: string): string => {
  const value = row[key];
  if (typeof value !== "string")
    throw new Error(`Bridge database field ${key} is invalid`);
  return value;
};

const optionalString = (
  row: Record<string, unknown>,
  key: string,
): string | undefined => {
  const value = row[key];
  if (value === null || value === undefined) return undefined;
  if (typeof value !== "string")
    throw new Error(`Bridge database field ${key} is invalid`);
  return value;
};

const parseFrame = (encoded: string): AdapterEventFrame => {
  const value: unknown = JSON.parse(encoded);
  const validation = validateDefinition("AdapterEventFrame", value);
  if (!validation.valid)
    throw new Error("Bridge outbox contains an invalid adapter frame");
  return value as AdapterEventFrame;
};

const parseLifecycleFrame = (encoded: string): AdapterCommandLifecycleFrame => {
  const value: unknown = JSON.parse(encoded);
  const validation = validateDefinition("AdapterCommandLifecycleFrame", value);
  if (!validation.valid)
    throw new Error("Bridge outbox contains an invalid lifecycle frame");
  return value as AdapterCommandLifecycleFrame;
};

const parseReceipt = (encoded: string): BridgeEventReceipt => {
  const value: unknown = JSON.parse(encoded);
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Bridge event receipt is invalid");
  }
  const receipt = value as Record<string, unknown>;
  if (
    typeof receipt.messageId !== "string" ||
    typeof receipt.sourceKey !== "string" ||
    (receipt.kind !== "intent" &&
      receipt.kind !== "interaction" &&
      receipt.kind !== "completion") ||
    typeof receipt.alreadyDispatched !== "boolean" ||
    typeof receipt.legacyDisplayDelivered !== "boolean" ||
    (receipt.semanticSha256 !== undefined &&
      (typeof receipt.semanticSha256 !== "string" ||
        !/^[0-9a-f]{64}$/u.test(receipt.semanticSha256)))
  ) {
    throw new Error("Bridge event receipt is invalid");
  }
  return receipt as unknown as BridgeEventReceipt;
};

const commandReceipt = (row: Record<string, unknown>): BridgeCommandReceipt => {
  const agentMeshCommandId = optionalString(row, "agent_mesh_command_id");
  return {
    commandId: requiredString(row, "command_id"),
    idempotencyKey: requiredString(row, "idempotency_key"),
    targetNodeId: requiredString(row, "target_node_id"),
    stage: requiredString(row, "stage") as FabricCommandLifecycleStage,
    ...(agentMeshCommandId === undefined ? {} : { agentMeshCommandId }),
    correlationId: requiredString(row, "correlation_id"),
    updatedAt: requiredString(row, "updated_at"),
  };
};
