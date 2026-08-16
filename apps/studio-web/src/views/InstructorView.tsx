import { useCallback, useEffect, useState } from "react";

import type { Translate } from "../i18n.js";
import type {
  ClassroomView,
  Identity,
  RuntimeClient,
} from "../runtime-client.js";
import { toneOf } from "./DevicesView.js";

/**
 * FR-065 and FR-067. The whole room, and the controls that act on it.
 *
 * Every field on a card is something a device reported. A device that has never
 * sent a battery reading says so rather than showing a confident number, because
 * an instructor deciding whether a hub will survive the lesson is exactly who a
 * made-up 100% would mislead.
 */
export function InstructorView({
  client,
  identity,
  t,
  run,
  busy,
}: {
  client: RuntimeClient;
  identity: Identity;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
}) {
  const [classroom, setClassroom] = useState<ClassroomView | null>(null);

  const refresh = useCallback(async () => {
    setClassroom(await client.classroom());
  }, [client]);

  useEffect(() => {
    if (identity.role !== "instructor") return;
    void run(refresh);
  }, [identity.role, refresh, run]);

  if (identity.role !== "instructor") {
    return (
      <section aria-labelledby="instructor-heading">
        <h2 id="instructor-heading">{t("instructor.heading")}</h2>
        <p className="muted">{t("instructor.studentsOnly")}</p>
      </section>
    );
  }

  const act = (work: () => Promise<unknown>) =>
    run(async () => {
      await work();
      await refresh();
    });

  const disabled = new Set(classroom?.disabledSources ?? []);

  return (
    <section aria-labelledby="instructor-heading">
      <div className="bar">
        <h2 id="instructor-heading">{t("instructor.heading")}</h2>
        <button type="button" onClick={() => void run(refresh)} disabled={busy}>
          {t("action.refresh")}
        </button>
      </div>

      <dl className="facts">
        <div>
          <dt>{t("instructor.people")}</dt>
          <dd>
            {(classroom?.people ?? [])
              .map((person) => `${person.displayName} (${person.role})`)
              .join(", ") || "—"}
          </dd>
        </div>
        <div>
          <dt>{t("instructor.sessions")}</dt>
          <dd>{classroom?.sessions.length ?? 0}</dd>
        </div>
        <div>
          <dt>{t("instructor.queueDepth")}</dt>
          <dd>{classroom?.queueDepth ?? 0}</dd>
        </div>
        <div>
          <dt>{t("instructor.disabledSources")}</dt>
          <dd>
            {classroom?.disabledSources.length
              ? classroom.disabledSources.join(", ")
              : t("instructor.noneDisabled")}
          </dd>
        </div>
      </dl>

      <div className="row">
        <button
          type="button"
          onClick={() =>
            act(() => client.setInputEnabled("leap", disabled.has("leap")))
          }
          disabled={busy}
        >
          {disabled.has("leap")
            ? t("instructor.enableLeap")
            : t("instructor.disableLeap")}
        </button>
        <button
          type="button"
          onClick={() =>
            act(() => client.setInputEnabled("quest", disabled.has("quest")))
          }
          disabled={busy}
        >
          {disabled.has("quest")
            ? t("instructor.enableQuest")
            : t("instructor.disableQuest")}
        </button>
        <button
          type="button"
          onClick={() => act(() => client.clearQueue(null))}
          disabled={busy}
        >
          {t("instructor.clearQueue")}
        </button>
        <button
          type="button"
          className="danger"
          onClick={() => act(() => client.disarm(null))}
          disabled={busy}
        >
          {t("instructor.disarmClass")}
        </button>
      </div>

      <div className="cards wide">
        {(classroom?.devices ?? []).map((device) => (
          <article key={device.deviceId} className="card static">
            <span className="card-title">{device.displayName}</span>
            <code className="muted">{device.deviceId}</code>
            <span className={`pill ${toneOf(device.state)}`}>
              {device.state}
              {device.armed ? ` · ${t("devices.armed")}` : ""}
            </span>

            <dl className="facts tight">
              <div>
                <dt>{t("devices.battery")}</dt>
                <dd>
                  {device.batteryPercent === null
                    ? t("devices.unknown")
                    : `${Math.round(device.batteryPercent)}%`}
                </dd>
              </div>
              <div>
                <dt>{t("devices.adapter")}</dt>
                <dd>
                  {device.adapterId} {device.adapterVersion}
                </dd>
              </div>
              <div>
                <dt>{t("devices.firmware")}</dt>
                <dd>{device.firmware ?? t("devices.unknown")}</dd>
              </div>
              <div>
                <dt>{t("devices.student")}</dt>
                <dd>{device.activeStudentId ?? t("devices.free")}</dd>
              </div>
              <div>
                <dt>{t("devices.lease")}</dt>
                <dd>{device.leaseSessionId ?? t("devices.free")}</dd>
              </div>
              <div>
                <dt>{t("devices.lastCommand")}</dt>
                <dd>
                  {device.lastCommand === null
                    ? t("devices.unknown")
                    : `${device.lastCommand.capability} · ${formatAge(device.lastCommand.ageMs)}`}
                </dd>
              </div>
              <div>
                <dt>{t("devices.lastTelemetry")}</dt>
                <dd>{device.lastTelemetry?.name ?? t("devices.unknown")}</dd>
              </div>
            </dl>

            {device.warnings.length > 0 && (
              <div className="notice warn">
                <strong>{t("instructor.warnings")}</strong>
                <ul>
                  {device.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="row">
              <button
                type="button"
                onClick={() => act(() => client.disarm(device.deviceId))}
                disabled={busy || !device.armed}
              >
                {t("devices.disarm")}
              </button>
              <button
                type="button"
                onClick={() =>
                  act(() =>
                    client.stop({
                      deviceId: device.deviceId,
                      reason: "instructor stop",
                    }),
                  )
                }
                disabled={busy}
              >
                {t("devices.stop")}
              </button>
              <button
                type="button"
                onClick={() => act(() => client.revokeLease(device.deviceId))}
                disabled={busy || device.leaseSessionId === null}
              >
                {t("devices.revokeLease")}
              </button>
            </div>
          </article>
        ))}
      </div>

      <h3>{t("instructor.sessions")}</h3>
      <ul className="events">
        {(classroom?.sessions ?? []).map((session) => (
          <li key={session.sessionId}>
            <span className="pill">{session.state}</span>
            <code>{session.sessionId}</code>
            <span className="muted">{session.userId}</span>
            <span className="muted">
              {t("instructor.failurePolicy")}:{" "}
              {session.failurePolicy === "stop_coordinated"
                ? t("instructor.failureStop")
                : t("instructor.failureContinue")}
            </span>
            <button
              type="button"
              onClick={() =>
                act(() =>
                  client.setFailurePolicy(
                    session.sessionId,
                    session.failurePolicy === "stop_coordinated"
                      ? "continue"
                      : "stop_coordinated",
                  ),
                )
              }
              disabled={busy}
            >
              {session.failurePolicy === "stop_coordinated"
                ? t("instructor.failureContinue")
                : t("instructor.failureStop")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatAge(ageMs: number | null): string {
  if (ageMs === null) return "—";
  if (ageMs < 1000) return `${Math.round(ageMs)} ms ago`;
  return `${Math.round(ageMs / 1000)} s ago`;
}
