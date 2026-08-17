import { useCallback, useEffect, useState } from "react";

import { exportFilename, saveTextAsFile } from "../download.js";
import type { Translate } from "../i18n.js";
import type {
  AuditEntryView,
  DeviceEventView,
  Identity,
  RuntimeClient,
} from "../runtime-client.js";

/**
 * FR-083 and FR-081. What happened, in the order it happened.
 *
 * A student sees their own entries and an instructor sees the room's; the
 * runtime scopes that, not this page. Nothing here is editable, because the
 * audit log has no update and no delete on the runtime either.
 */
export function LogsView({
  client,
  identity,
  events,
  t,
  run,
}: {
  client: RuntimeClient;
  identity: Identity;
  events: DeviceEventView[];
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
}) {
  const [entries, setEntries] = useState<AuditEntryView[]>([]);
  const [exported, setExported] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setEntries(await client.audit());
  }, [client]);

  useEffect(() => {
    void run(refresh);
  }, [refresh, run]);

  // FR-084. A file the instructor keeps, not a byte count they read. The log
  // is fetched with the runtime token in a header, so this cannot be a link:
  // the document is already in memory by the time it is saved.
  const exportLog = () =>
    run(async () => {
      const text = await client.auditExport();
      const name = saveTextAsFile(
        text,
        exportFilename("audit", null, new Date(), "jsonl"),
        "application/x-ndjson",
      );
      setExported(t("download.saved", { name }));
    });

  return (
    <>
      <section aria-labelledby="logs-heading">
        <div className="bar">
          <h2 id="logs-heading">{t("logs.heading")}</h2>
          <div className="row">
            <button type="button" onClick={() => void run(refresh)}>
              {t("action.refresh")}
            </button>
            {identity.role === "instructor" && (
              <button type="button" onClick={exportLog}>
                {t("logs.export")}
              </button>
            )}
          </div>
        </div>

        {exported !== null && <div className="notice ok">{exported}</div>}

        {entries.length === 0 ? (
          <p className="muted">{t("logs.none")}</p>
        ) : (
          <div className="scroll">
            <table className="log">
              <thead>
                <tr>
                  <th scope="col">{t("logs.sequence")}</th>
                  <th scope="col">{t("logs.time")}</th>
                  <th scope="col">{t("logs.action")}</th>
                  <th scope="col">{t("logs.actor")}</th>
                  <th scope="col">{t("logs.context")}</th>
                </tr>
              </thead>
              <tbody>
                {[...entries].reverse().map((entry) => (
                  <tr key={entry.sequence}>
                    <td>{entry.sequence}</td>
                    <td>{entry.recordedAt.slice(11, 19)}</td>
                    <td>
                      <code>{entry.action}</code>
                    </td>
                    <td>{entry.actorId}</td>
                    <td className="muted">
                      {Object.entries(entry.context)
                        .map(([key, value]) => `${key}=${String(value)}`)
                        .join(" ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="events-heading">
        <h2 id="events-heading">{t("logs.events")}</h2>
        {events.length === 0 ? (
          <p className="muted">{t("logs.eventsEmpty")}</p>
        ) : (
          <ul className="events">
            {events.map((event) => (
              <li key={event.eventId}>
                <span className="pill">{event.category}</span>
                <code>{event.name}</code>
                <span className="muted">{event.deviceId}</span>
                {event.historical === true && (
                  <span className="pill warn">replay</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
