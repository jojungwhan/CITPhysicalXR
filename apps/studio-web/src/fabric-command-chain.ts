import type { FabricCommandLifecycleEvent } from "@citxr/protocol";

import type {
  FabricCommandSubmission,
  StoredFabricLifecycle,
} from "./fabric-client.js";

interface LifecycleReader {
  listLifecycle(
    afterSequence?: number,
    commandId?: string,
  ): Promise<StoredFabricLifecycle[]>;
}

const TERMINAL_STAGES = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
  "REJECTED",
]);

export interface FabricCommandBatchResult {
  succeeded: number;
  failed: number;
}

export async function awaitFabricCommandBatch(
  reader: LifecycleReader,
  submissions: readonly Promise<FabricCommandSubmission>[],
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<FabricCommandBatchResult> {
  const outcomes = await Promise.allSettled(
    submissions.map(async (submission) =>
      awaitFabricCommandTerminal(reader, await submission, options),
    ),
  );
  const succeeded = outcomes.filter(
    (outcome) =>
      outcome.status === "fulfilled" && outcome.value.stage === "SUCCEEDED",
  ).length;

  return { succeeded, failed: submissions.length - succeeded };
}

export async function awaitFabricCommandTerminal(
  reader: LifecycleReader,
  submission: FabricCommandSubmission,
  {
    timeoutMs = 8_000,
    pollIntervalMs = 100,
  }: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<FabricCommandLifecycleEvent> {
  const initial = submission.lifecycle.at(-1);
  const commandId = initial?.commandId ?? submission.lifecycle[0]?.commandId;
  if (commandId === undefined) {
    throw new Error("Fabric command submission did not include a command ID");
  }
  if (initial !== undefined && TERMINAL_STAGES.has(initial.stage))
    return initial;

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await delay(pollIntervalMs);
    const current = (await reader.listLifecycle(0, commandId)).at(
      -1,
    )?.lifecycle;
    if (current !== undefined && TERMINAL_STAGES.has(current.stage))
      return current;
  }
  throw new Error(
    `Fabric command ${commandId} did not finish within ${timeoutMs} ms`,
  );
}

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => globalThis.setTimeout(resolve, milliseconds));
