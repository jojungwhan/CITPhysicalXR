import { useCallback, useEffect, useState } from "react";

import { exportFilename, saveTextAsFile } from "../download.js";
import type { Translate } from "../i18n.js";
import type {
  RecordingView,
  RuntimeClient,
  SessionView,
} from "../runtime-client.js";

/**
 * FR-064. Record a lesson, and watch it back without a robot in the room.
 *
 * The sentence about replay not moving anything is not reassurance. It is a
 * property of the runtime: a replayer holds no registry and no pipeline, so
 * there is no code path from a recording to a device, and a test asserts it.
 */
export function SimulationView({
  client,
  session,
  t,
  run,
  busy,
}: {
  client: RuntimeClient;
  session: SessionView | null;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
}) {
  const [recordings, setRecordings] = useState<RecordingView[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRecordings((await client.recordings()).recordings);
  }, [client]);

  useEffect(() => {
    void run(refresh);
  }, [refresh, run]);

  const start = () =>
    run(async () => {
      if (session === null) return;
      const started = await client.startRecording(session.sessionId);
      setActive(started.recordingId);
      setNotice(null);
    });

  const stop = () =>
    run(async () => {
      if (active === null) return;
      await client.stopRecording(active);
      setActive(null);
      await refresh();
    });

  const replay = (recordingId: string) =>
    run(async () => {
      const outcome = await client.replay(recordingId);
      setNotice(t("simulation.replayed", { count: outcome.delivered }));
    });

  // FR-084. The replay package leaves as a file, so a lesson can be looked at
  // after the runtime that recorded it has been shut down.
  const exportPackage = (recordingId: string) =>
    run(async () => {
      const text = await client.exportRecording(recordingId);
      const name = saveTextAsFile(
        text,
        exportFilename("replay", recordingId, new Date(), "json"),
        "application/json",
      );
      setNotice(t("download.saved", { name }));
    });

  const remove = (recordingId: string) =>
    run(async () => {
      await client.deleteRecording(recordingId);
      await refresh();
    });

  return (
    <section aria-labelledby="simulation-heading">
      <div className="bar">
        <h2 id="simulation-heading">{t("simulation.heading")}</h2>
        <div className="row">
          <button
            type="button"
            onClick={start}
            disabled={busy || session === null || active !== null}
          >
            {t("simulation.startRecording")}
          </button>
          <button
            type="button"
            onClick={stop}
            disabled={busy || active === null}
          >
            {t("simulation.stopRecording")}
          </button>
        </div>
      </div>

      <p className="muted">{t("simulation.neverMoves")}</p>
      {active !== null && (
        <div className="notice">{t("simulation.recording")}</div>
      )}
      {notice !== null && <div className="notice ok">{notice}</div>}

      <h3>{t("simulation.recordings")}</h3>
      {recordings.length === 0 ? (
        <p className="muted">{t("simulation.none")}</p>
      ) : (
        <ul className="events">
          {recordings.map((recording) => (
            <li key={recording.recordingId}>
              <code>{recording.recordingId}</code>
              <span className="muted">
                {t("simulation.events", { count: recording.eventCount })}
              </span>
              <span className="muted">
                {recording.startedAt.slice(0, 19).replace("T", " ")}
              </span>
              <button
                type="button"
                onClick={() => replay(recording.recordingId)}
                disabled={busy}
              >
                {t("simulation.replay")}
              </button>
              <button
                type="button"
                onClick={() => exportPackage(recording.recordingId)}
                disabled={busy}
              >
                {t("simulation.exportPackage")}
              </button>
              <button
                type="button"
                onClick={() => remove(recording.recordingId)}
                disabled={busy}
              >
                {t("simulation.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
