import { describe, expect, it } from "vitest";

import { Autosave, type SaveState, type TimerPort } from "./autosave.js";

/** A timer nothing fires but the test. */
function fakeTimers(): TimerPort & { fire: () => void; armed: () => number } {
  const work = new Map<number, () => void>();
  let next = 1;
  return {
    setTimeout: (task) => {
      const handle = next++;
      work.set(handle, task);
      return handle;
    },
    clearTimeout: (handle) => {
      work.delete(handle);
    },
    fire: () => {
      const tasks = [...work.values()];
      work.clear();
      for (const task of tasks) task();
    },
    armed: () => work.size,
  };
}

function harness() {
  const timers = fakeTimers();
  const saved: string[] = [];
  const states: SaveState[] = [];
  let release: ((error?: Error) => void) | null = null;

  const autosave = new Autosave<string>({
    timers,
    delayMs: 10,
    onState: (state) => states.push(state),
    save: (document) =>
      new Promise<void>((resolve, reject) => {
        release = (error) => {
          if (error) {
            reject(error);
            return;
          }
          saved.push(document);
          resolve();
        };
      }),
  });

  return {
    autosave,
    timers,
    saved,
    states,
    finish: async (error?: Error) => {
      release?.(error);
      release = null;
      // Two turns: the awaited save, then the code after it.
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    },
  };
}

describe("autosaving a project (FR-001)", () => {
  it("writes once for a burst of edits", async () => {
    const { autosave, timers, saved, finish } = harness();

    autosave.change("v1");
    autosave.change("v2");
    autosave.change("v3");
    expect(saved).toEqual([]);

    timers.fire();
    await finish();

    // A block drag fires a change per step. One file write, and the newest
    // document, is the whole point of the delay.
    expect(saved).toEqual(["v3"]);
  });

  it("saves an edit made while the previous save was in flight", async () => {
    const { autosave, timers, saved, finish } = harness();

    autosave.change("v1");
    timers.fire();
    autosave.change("v2");
    await finish();

    expect(saved).toEqual(["v1"]);
    timers.fire();
    await finish();
    expect(saved).toEqual(["v1", "v2"]);
  });

  it("reports the states a person can act on", async () => {
    const { autosave, timers, states, finish } = harness();

    autosave.change("v1");
    timers.fire();
    await finish();

    expect(states).toEqual(["unsaved", "saving", "saved"]);
  });

  it("keeps a failed save pending and says so", async () => {
    const { autosave, timers, saved, states, finish } = harness();

    autosave.change("v1");
    timers.fire();
    await finish(new Error("runtime unreachable"));

    expect(states).toEqual(["unsaved", "saving", "failed"]);
    expect(saved).toEqual([]);

    // Not retried on a timer: a runtime that has gone away would be asked
    // every delay for the rest of the lesson.
    expect(timers.armed()).toBe(0);

    // The document was not dropped. The next edit carries it to disk.
    autosave.change("v2");
    timers.fire();
    await finish();
    expect(saved).toEqual(["v2"]);
  });

  it("writes a pending edit immediately when asked", async () => {
    const { autosave, saved, finish } = harness();

    autosave.change("v1");
    autosave.flushNow();
    await finish();

    expect(saved).toEqual(["v1"]);
  });

  it("writes nothing after it is stopped", async () => {
    const { autosave, timers, saved, finish } = harness();

    autosave.change("v1");
    autosave.stop();
    timers.fire();
    await finish();

    expect(saved).toEqual([]);
    autosave.change("v2");
    autosave.flushNow();
    await finish();
    expect(saved).toEqual([]);
  });
});
