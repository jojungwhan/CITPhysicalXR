/**
 * Saving a project without being asked (FR-001, NFR 12.4).
 *
 * The store under this has been ready since Milestone 6 -- atomic writes and a
 * retained previous version -- and nothing called it on a timer, so a lesson's
 * work still depended on a child remembering a button.
 *
 * Three rules shape what is here, and each of them is a way work gets lost:
 *
 * - A burst of edits is one save. Dragging a block fires a change per drag
 *   step, and a save per step would spend the lesson writing files.
 * - An edit made while a save is in flight is saved after it. Otherwise the
 *   last thing a student did before the bell is the one thing not on disk.
 * - A failed save is not forgotten. It stays pending, is reported, and the next
 *   edit tries again, because a silent failure reads exactly like a success.
 *
 * The timer is injected so this is testable without a browser: the Studio's
 * tests run in Node with no DOM.
 */

export type SaveState = "idle" | "unsaved" | "saving" | "saved" | "failed";

export interface TimerPort {
  setTimeout(work: () => void, ms: number): number;
  clearTimeout(handle: number): void;
}

export const browserTimers: TimerPort = {
  setTimeout: (work, ms) => window.setTimeout(work, ms),
  clearTimeout: (handle) => {
    window.clearTimeout(handle);
  },
};

export interface AutosaveOptions<T> {
  save: (document: T) => Promise<void>;
  onState: (state: SaveState, error?: unknown) => void;
  delayMs?: number;
  timers?: TimerPort;
}

export class Autosave<T> {
  private readonly save: (document: T) => Promise<void>;
  private readonly onState: (state: SaveState, error?: unknown) => void;
  private readonly delayMs: number;
  private readonly timers: TimerPort;

  private pending: T | null = null;
  private handle: number | null = null;
  private inFlight = false;
  private stopped = false;

  constructor(options: AutosaveOptions<T>) {
    this.save = options.save;
    this.onState = options.onState;
    this.delayMs = options.delayMs ?? 1500;
    this.timers = options.timers ?? browserTimers;
  }

  /** Note an edit. The document is saved once the edits stop. */
  change(document: T): void {
    if (this.stopped) return;
    this.pending = document;
    this.onState("unsaved");
    this.arm();
  }

  /** Save now, if anything is waiting. Used when leaving the editor. */
  flushNow(): void {
    if (this.handle !== null) {
      this.timers.clearTimeout(this.handle);
      this.handle = null;
    }
    void this.write();
  }

  /** Forget the pending edit and any timer. Nothing further is written. */
  stop(): void {
    this.stopped = true;
    this.pending = null;
    if (this.handle !== null) {
      this.timers.clearTimeout(this.handle);
      this.handle = null;
    }
  }

  private arm(): void {
    if (this.handle !== null) this.timers.clearTimeout(this.handle);
    this.handle = this.timers.setTimeout(() => {
      this.handle = null;
      void this.write();
    }, this.delayMs);
  }

  private async write(): Promise<void> {
    // One writer at a time. A second write would race the first for the same
    // file, and the store's own atomic rename only makes each write whole --
    // it does not decide which of two is the newer document.
    if (this.inFlight || this.stopped) return;
    const document = this.pending;
    if (document === null) return;

    this.pending = null;
    this.inFlight = true;
    this.onState("saving");
    let failed = false;
    try {
      await this.save(document);
      if (this.stopped) return;
      // An edit that arrived while this one was being written is still
      // pending, so the state is honest about there being newer work.
      this.onState(this.pending === null ? "saved" : "unsaved");
    } catch (error) {
      if (this.stopped) return;
      // Put it back: a failed save that drops the document is how a lesson's
      // work disappears with an "unsaved" label that nobody read.
      this.pending = document;
      failed = true;
      this.onState("failed", error);
    } finally {
      this.inFlight = false;
    }
    // Not after a failure. A runtime that has gone away would otherwise be
    // asked every delay for the rest of the lesson, and the student would be
    // told about it every time. The next edit -- or leaving the editor --
    // tries again.
    if (
      !this.stopped &&
      !failed &&
      this.pending !== null &&
      this.handle === null
    ) {
      this.arm();
    }
  }
}
