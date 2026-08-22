import { randomUUID } from "node:crypto";

import {
  validateDefinition,
  type AdapterAuthenticationFrame,
  type AdapterClientFrame,
  type AdapterCommandFrame,
  type AdapterHeartbeatFrame,
  type AdapterRegistrationFrame,
  type AdapterServerFrame,
} from "@citxr/protocol";

import { AgentMeshApiClient } from "./agent-mesh-client.js";
import { MirrorCommandHandler } from "./command-handler.js";
import type { BridgeConfig } from "./config.js";
import {
  completionEventFrame,
  healthReports,
  intentEventFrame,
  mapDiscovery,
  semanticSha256,
  type AgentMeshFabricMapping,
} from "./mapping.js";
import { BridgeOutbox } from "./outbox.js";
import type {
  AgentMeshCompletionFeed,
  AgentMeshDiscovery,
  AgentMeshIntentFeed,
} from "./types.js";

const MAX_FRAME_BYTES = 131_072;
const CONNECT_TIMEOUT_MS = 10_000;
const DELIVERY_RETRY_MS = 5_000;

export interface AgentMeshBridgeSource {
  discovery(): Promise<AgentMeshDiscovery>;
  intents(afterSequence: number): Promise<AgentMeshIntentFeed>;
  acknowledgeIntent(intentId: string): Promise<void>;
  completions(afterSequence: number): Promise<AgentMeshCompletionFeed>;
}

export interface BridgeSocket {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  addEventListener(type: string, listener: (event: unknown) => void): void;
  removeEventListener(type: string, listener: (event: unknown) => void): void;
}

export type BridgeSocketFactory = (url: string) => BridgeSocket;

export interface RunBridgeOptions {
  readonly signal?: AbortSignal;
  readonly onDiagnostic?: (message: string) => void;
  readonly socketFactory?: BridgeSocketFactory;
  readonly source?: AgentMeshBridgeSource;
  readonly outbox?: BridgeOutbox;
}

export class CitAgentMeshBridge {
  readonly #config: BridgeConfig;
  readonly #source: AgentMeshBridgeSource;
  readonly #outbox: BridgeOutbox;
  readonly #socketFactory: BridgeSocketFactory;
  readonly #commandHandler: MirrorCommandHandler;
  readonly #inFlight = new Map<string, number>();

  constructor(
    config: BridgeConfig,
    source: AgentMeshBridgeSource,
    outbox: BridgeOutbox,
    socketFactory: BridgeSocketFactory = defaultSocketFactory,
  ) {
    this.#config = config;
    this.#source = source;
    this.#outbox = outbox;
    this.#socketFactory = socketFactory;
    this.#commandHandler = new MirrorCommandHandler(outbox);
  }

  async runOnce(signal?: AbortSignal): Promise<"aborted" | "stopped"> {
    if (signal?.aborted === true) return "aborted";
    const discovery = await this.#source.discovery();
    const mapping = mapDiscovery(discovery, this.#config);
    const socket = this.#socketFactory(this.#config.fabricAdapterUrl);
    const channel = new SocketChannel(socket);
    const controller = new AbortController();
    const forwardAbort = (): void => controller.abort();
    signal?.addEventListener("abort", forwardAbort, { once: true });
    try {
      await channel.waitUntilOpen(CONNECT_TIMEOUT_MS, controller.signal);
      this.#send(socket, {
        frameType: "adapter.authenticate",
        frameId: randomUUID(),
        protocolVersion: 1,
        credential: this.#config.fabricCredential,
        sentAt: new Date().toISOString(),
      } satisfies AdapterAuthenticationFrame);
      const welcome = await channel.next(CONNECT_TIMEOUT_MS, controller.signal);
      if (welcome.frameType !== "adapter.welcome") {
        throw new Error("Fabric adapter did not return a welcome frame");
      }
      this.#send(socket, {
        frameType: "adapter.register",
        frameId: randomUUID(),
        protocolVersion: 1,
        manifest: mapping.manifest,
        nodes: mapping.nodes,
        sentAt: new Date().toISOString(),
      } satisfies AdapterRegistrationFrame);
      const registered = await channel.next(
        CONNECT_TIMEOUT_MS,
        controller.signal,
      );
      if (registered.frameType !== "adapter.registered") {
        throw new Error("Fabric adapter did not confirm node registration");
      }
      const expected = [...mapping.nodes.map((node) => node.nodeId)].sort();
      const actual = [...registered.registeredNodeIds].sort();
      if (JSON.stringify(expected) !== JSON.stringify(actual)) {
        throw new Error(
          "Fabric registered a different set of Agent Mesh nodes",
        );
      }
      this.#inFlight.clear();
      const tasks = [
        this.#receiveLoop(channel, socket, mapping, controller.signal),
        this.#pollLoop(socket, mapping, controller.signal),
        this.#heartbeatLoop(
          socket,
          mapping,
          welcome.heartbeatIntervalMs,
          controller.signal,
        ),
        waitForAbort(controller.signal),
      ] as const;
      let outcome: "aborted" | "stopped";
      try {
        outcome = await Promise.race(tasks);
      } catch (error) {
        if (isAborted(signal)) return "aborted";
        throw error;
      } finally {
        controller.abort();
        await Promise.allSettled(tasks);
      }
      return outcome;
    } finally {
      signal?.removeEventListener("abort", forwardAbort);
      channel.dispose();
      if (socket.readyState < 2)
        socket.close(1000, "CIT bridge connection ended");
    }
  }

  async #receiveLoop(
    channel: SocketChannel,
    socket: BridgeSocket,
    mapping: AgentMeshFabricMapping,
    signal: AbortSignal,
  ): Promise<"stopped"> {
    while (!signal.aborted) {
      const frame = await channel.next(0, signal);
      switch (frame.frameType) {
        case "adapter.ack":
          this.#outbox.acknowledgeFrame(frame.acknowledgedFrameId);
          this.#outbox.acknowledgeLifecycleFrame(frame.acknowledgedFrameId);
          this.#inFlight.delete(frame.acknowledgedFrameId);
          break;
        case "adapter.command":
          this.#handleCommand(frame, mapping);
          this.#flush(socket);
          break;
        case "adapter.stop":
          return "stopped";
        case "adapter.welcome":
        case "adapter.registered":
          throw new Error("Fabric sent a handshake frame after registration");
      }
    }
    return "stopped";
  }

  #handleCommand(
    frame: AdapterCommandFrame,
    mapping: AgentMeshFabricMapping,
  ): void {
    for (const lifecycle of this.#commandHandler.handle(frame, mapping)) {
      this.#outbox.enqueueLifecycle(lifecycle);
    }
  }

  async #pollLoop(
    socket: BridgeSocket,
    mapping: AgentMeshFabricMapping,
    signal: AbortSignal,
  ): Promise<"aborted"> {
    while (!signal.aborted) {
      await this.#pollSource(mapping);
      this.#flush(socket);
      await delay(this.#config.pollIntervalMs, signal);
    }
    return "aborted";
  }

  async #pollSource(mapping: AgentMeshFabricMapping): Promise<void> {
    const intentCursor = this.#outbox.stateNumber("agent-mesh-intent-cursor");
    const intentFeed = await this.#source.intents(intentCursor);
    for (const intent of intentFeed.intents) {
      const node = mapping.wearableNodeByDeviceId.get(intent.deviceId);
      if (node === undefined) {
        throw new Error(
          "Agent Mesh intent references a device absent from discovery",
        );
      }
      const frame = intentEventFrame(intent, node, this.#config, this.#outbox);
      this.#outbox.enqueueEvent(`intent:${intent.intentId}`, frame, {
        kind: "intent",
        agentMeshIntentId: intent.intentId,
        agentMeshCommandId: intent.agentMeshCommandId,
        agentMeshSessionId: intent.requestedSessionId,
        agentMeshDispatchedSessionId: intent.dispatchedSessionId,
        alreadyDispatched: true,
        legacyDisplayDelivered: false,
        semanticSha256: semanticSha256(intent.prompt),
      });
      await this.#source.acknowledgeIntent(intent.intentId);
      this.#outbox.setStateNumber("agent-mesh-intent-cursor", intent.sequence);
    }
    if (
      intentFeed.intents.length === 0 &&
      intentFeed.nextCursor > intentCursor
    ) {
      this.#outbox.setStateNumber(
        "agent-mesh-intent-cursor",
        intentFeed.nextCursor,
      );
    }

    const completionCursor = this.#outbox.stateNumber(
      "agent-mesh-completion-cursor",
    );
    const completionFeed = await this.#source.completions(completionCursor);
    for (const completion of completionFeed.notifications) {
      const route = this.#outbox.agentRoute(completion.sessionId);
      const node =
        route === undefined
          ? undefined
          : mapping.nodes.find(
              (candidate) => candidate.nodeId === route.targetNodeId,
            );
      if (node === undefined) {
        this.#outbox.setStateNumber(
          "agent-mesh-completion-cursor",
          completion.sequence,
        );
        continue;
      }
      const frame = completionEventFrame(
        completion,
        node,
        this.#config,
        this.#outbox,
      );
      this.#outbox.enqueueEvent(
        `completion:${completion.notificationId}`,
        frame,
        {
          kind: "completion",
          agentMeshSessionId: completion.sessionId,
          alreadyDispatched: false,
          legacyDisplayDelivered: true,
          semanticSha256: semanticSha256(completion.displayText),
        },
      );
      this.#outbox.setStateNumber(
        "agent-mesh-completion-cursor",
        completion.sequence,
      );
    }
    if (
      completionFeed.notifications.length === 0 &&
      completionFeed.nextCursor > completionCursor
    ) {
      this.#outbox.setStateNumber(
        "agent-mesh-completion-cursor",
        completionFeed.nextCursor,
      );
    }
  }

  async #heartbeatLoop(
    socket: BridgeSocket,
    mapping: AgentMeshFabricMapping,
    heartbeatIntervalMs: number,
    signal: AbortSignal,
  ): Promise<"aborted"> {
    const interval = Math.max(100, Math.min(heartbeatIntervalMs, 10_000));
    while (!signal.aborted) {
      this.#send(socket, {
        frameType: "adapter.heartbeat",
        frameId: randomUUID(),
        protocolVersion: 1,
        reports: healthReports(mapping),
        sentAt: new Date().toISOString(),
      } satisfies AdapterHeartbeatFrame);
      await delay(interval, signal);
    }
    return "aborted";
  }

  #flush(socket: BridgeSocket): void {
    const now = Date.now();
    this.#outbox.discardUndeliverableFrames(
      this.#config.fabricSessionId,
      new Date(now),
    );
    for (const pending of [
      ...this.#outbox.pendingEvents(),
      ...this.#outbox.pendingLifecycles(),
    ]) {
      const lastSentAt = this.#inFlight.get(pending.frameId);
      if (lastSentAt !== undefined && now - lastSentAt < DELIVERY_RETRY_MS)
        continue;
      this.#send(socket, pending.frame);
      this.#inFlight.set(pending.frameId, now);
    }
  }

  #send(socket: BridgeSocket, frame: AdapterClientFrame): void {
    const validation = validateDefinition("AdapterClientFrame", frame);
    if (!validation.valid) {
      throw new TypeError(
        `Invalid Fabric adapter frame: ${validation.errors.join("; ")}`,
      );
    }
    const encoded = JSON.stringify(frame);
    if (Buffer.byteLength(encoded, "utf8") > MAX_FRAME_BYTES) {
      throw new TypeError("Fabric adapter frame exceeds 128 KiB");
    }
    if (socket.readyState !== 1)
      throw new Error("Fabric adapter socket is not open");
    socket.send(encoded);
  }
}

export const runBridgeForever = async (
  config: BridgeConfig,
  options: RunBridgeOptions = {},
): Promise<void> => {
  const ownedOutbox = options.outbox === undefined;
  const outbox = options.outbox ?? new BridgeOutbox(config.databasePath);
  const source =
    options.source ??
    new AgentMeshApiClient(
      config.agentMeshBaseUrl,
      config.agentMeshDeviceToken,
    );
  const bridge = new CitAgentMeshBridge(
    config,
    source,
    outbox,
    options.socketFactory ?? defaultSocketFactory,
  );
  try {
    while (!isAborted(options.signal)) {
      try {
        const outcome = await bridge.runOnce(options.signal);
        if (outcome === "stopped" || isAborted(options.signal)) return;
      } catch (error) {
        if (isAborted(options.signal)) return;
        options.onDiagnostic?.(safeDiagnostic(error));
      }
      await delay(config.reconnectDelayMs, options.signal);
    }
  } finally {
    if (ownedOutbox) outbox.close();
  }
};

class SocketChannel {
  readonly #socket: BridgeSocket;
  readonly #queue: AdapterServerFrame[] = [];
  readonly #waiters: Array<{
    resolve: (frame: AdapterServerFrame) => void;
    reject: (error: Error) => void;
  }> = [];
  #open = false;
  #failure: Error | undefined;

  readonly #onOpen = (): void => {
    this.#open = true;
  };

  readonly #onMessage = (event: unknown): void => {
    try {
      const frame = parseServerFrame(eventData(event));
      const waiter = this.#waiters.shift();
      if (waiter === undefined) this.#queue.push(frame);
      else waiter.resolve(frame);
    } catch (error) {
      this.#fail(
        error instanceof Error ? error : new Error("Invalid Fabric frame"),
      );
    }
  };

  readonly #onError = (): void =>
    this.#fail(new Error("Fabric adapter socket failed"));
  readonly #onClose = (event: unknown): void => {
    const details =
      typeof event === "object" && event !== null
        ? (event as { code?: unknown; reason?: unknown })
        : {};
    const code = typeof details.code === "number" ? ` (${details.code})` : "";
    const reason =
      typeof details.reason === "string" && details.reason.length > 0
        ? `: ${details.reason.slice(0, 200)}`
        : "";
    this.#fail(new Error(`Fabric adapter socket closed${code}${reason}`));
  };

  constructor(socket: BridgeSocket) {
    this.#socket = socket;
    this.#open = socket.readyState === 1;
    socket.addEventListener("open", this.#onOpen);
    socket.addEventListener("message", this.#onMessage);
    socket.addEventListener("error", this.#onError);
    socket.addEventListener("close", this.#onClose);
  }

  async waitUntilOpen(timeoutMs: number, signal: AbortSignal): Promise<void> {
    const startedAt = Date.now();
    while (!this.#open) {
      if (this.#failure !== undefined) throw this.#failure;
      if (Date.now() - startedAt >= timeoutMs)
        throw new Error("Fabric adapter connection timed out");
      await delay(10, signal);
    }
  }

  async next(
    timeoutMs: number,
    signal: AbortSignal,
  ): Promise<AdapterServerFrame> {
    const queued = this.#queue.shift();
    if (queued !== undefined) return queued;
    if (this.#failure !== undefined) throw this.#failure;
    return await new Promise<AdapterServerFrame>((resolve, reject) => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const abort = (): void =>
        finishReject(new Error("Bridge operation aborted"));
      const entry = {
        resolve: (frame: AdapterServerFrame): void => {
          cleanup();
          resolve(frame);
        },
        reject: (error: Error): void => {
          cleanup();
          reject(error);
        },
      };
      const cleanup = (): void => {
        if (timer !== undefined) clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        const index = this.#waiters.indexOf(entry);
        if (index >= 0) this.#waiters.splice(index, 1);
      };
      const finishReject = (error: Error): void => entry.reject(error);
      this.#waiters.push(entry);
      signal.addEventListener("abort", abort, { once: true });
      if (timeoutMs > 0) {
        timer = setTimeout(
          () => finishReject(new Error("Fabric adapter response timed out")),
          timeoutMs,
        );
      }
    });
  }

  dispose(): void {
    this.#socket.removeEventListener("open", this.#onOpen);
    this.#socket.removeEventListener("message", this.#onMessage);
    this.#socket.removeEventListener("error", this.#onError);
    this.#socket.removeEventListener("close", this.#onClose);
    this.#fail(new Error("Fabric adapter channel disposed"));
  }

  #fail(error: Error): void {
    if (this.#failure !== undefined) return;
    this.#failure = error;
    for (const waiter of this.#waiters.splice(0)) waiter.reject(error);
  }
}

const defaultSocketFactory: BridgeSocketFactory = (url) =>
  new WebSocket(url) as unknown as BridgeSocket;

const parseServerFrame = (encoded: string): AdapterServerFrame => {
  if (Buffer.byteLength(encoded, "utf8") > MAX_FRAME_BYTES) {
    throw new TypeError("Fabric server frame exceeds 128 KiB");
  }
  let value: unknown;
  try {
    value = JSON.parse(encoded);
  } catch {
    throw new TypeError("Fabric server frame is not JSON");
  }
  const validation = validateDefinition("AdapterServerFrame", value);
  if (!validation.valid) {
    throw new TypeError(
      `Invalid Fabric server frame: ${validation.errors.join("; ")}`,
    );
  }
  return value as AdapterServerFrame;
};

const eventData = (event: unknown): string => {
  if (
    typeof event !== "object" ||
    event === null ||
    !("data" in event) ||
    typeof (event as { data?: unknown }).data !== "string"
  ) {
    throw new TypeError("Fabric adapter requires text WebSocket frames");
  }
  return (event as { data: string }).data;
};

const delay = async (
  milliseconds: number,
  signal?: AbortSignal,
): Promise<void> => {
  if (signal?.aborted === true) return;
  await new Promise<void>((resolve) => {
    const timer = setTimeout(finish, milliseconds);
    const abort = (): void => finish();
    function finish(): void {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      resolve();
    }
    signal?.addEventListener("abort", abort, { once: true });
  });
};

const waitForAbort = async (signal: AbortSignal): Promise<"aborted"> => {
  if (!signal.aborted) {
    await new Promise<void>((resolve) =>
      signal.addEventListener("abort", () => resolve(), { once: true }),
    );
  }
  return "aborted";
};

const safeDiagnostic = (error: unknown): string =>
  error instanceof Error
    ? error.message.slice(0, 500)
    : "Agent Mesh bridge failed";

const isAborted = (signal: AbortSignal | undefined): boolean =>
  signal?.aborted === true;
