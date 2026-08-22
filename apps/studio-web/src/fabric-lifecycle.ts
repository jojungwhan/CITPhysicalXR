const TERMINAL_COMMAND_STAGES = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
  "REJECTED",
]);

type LifecycleProjectionRecord = {
  streamSequence: number;
  lifecycle: {
    commandId: string;
    stage: string;
  };
};

export function countActiveFabricCommands(
  records: readonly LifecycleProjectionRecord[],
): number {
  const latestByCommand = new Map<string, LifecycleProjectionRecord>();
  records.forEach((record) => {
    const current = latestByCommand.get(record.lifecycle.commandId);
    if (
      current === undefined ||
      current.streamSequence < record.streamSequence
    ) {
      latestByCommand.set(record.lifecycle.commandId, record);
    }
  });
  return [...latestByCommand.values()].filter(
    (record) => !TERMINAL_COMMAND_STAGES.has(record.lifecycle.stage),
  ).length;
}
