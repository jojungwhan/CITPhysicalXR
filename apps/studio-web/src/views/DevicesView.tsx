import type { Translate } from "../i18n.js";
import type {
  DeviceView,
  Identity,
  RuntimeClient,
  SessionView,
} from "../runtime-client.js";

/**
 * What is in the room (UI 11.3).
 *
 * A student sees their own devices and the free ones; the runtime decides that,
 * not this page. Binding a device to a lesson happens in Program, where the
 * session lives -- this view answers "what is here and what state is it in".
 */
export function DevicesView({
  client,
  identity,
  devices,
  session,
  t,
  run,
  busy,
  refresh,
}: {
  client: RuntimeClient;
  identity: Identity;
  devices: DeviceView[];
  session: SessionView | null;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
  refresh: () => Promise<void>;
}) {
  const isInstructor = identity.role === "instructor";

  const discover = () =>
    run(async () => {
      await client.discover();
      await refresh();
    });

  const disconnect = (deviceId: string) =>
    run(async () => {
      await client.disconnectDevice(deviceId, "instructor disconnected it");
      await refresh();
    });

  const stopDevice = (deviceId: string) =>
    run(async () => {
      await client.stop({ deviceId, reason: "studio stop" });
      await refresh();
    });

  return (
    <section aria-labelledby="devices-heading">
      <div className="bar">
        <h2 id="devices-heading">{t("devices.heading")}</h2>
        <div className="row">
          <button
            type="button"
            onClick={() => void run(refresh)}
            disabled={busy}
          >
            {t("action.refresh")}
          </button>
          {isInstructor && (
            <button type="button" onClick={discover} disabled={busy}>
              {t("devices.discover")}
            </button>
          )}
        </div>
      </div>

      {devices.length === 0 ? (
        <p className="muted">{t("devices.none")}</p>
      ) : (
        <div className="cards">
          {devices.map((device) => {
            const mine =
              session !== null &&
              device.assignedSessionId === session.sessionId;
            return (
              <article key={device.deviceId} className="card static">
                <span className="card-title">{device.displayName}</span>
                <code className="muted">{device.deviceId}</code>
                <span className={`pill ${toneOf(device.state)}`}>
                  {device.state}
                </span>
                <span className="muted">
                  {device.physical
                    ? t("devices.physical")
                    : t("devices.simulated")}
                  {device.armed ? ` · ${t("devices.armed")}` : ""}
                </span>
                <span className="muted">
                  {t("devices.lease")}:{" "}
                  {device.assignedSessionId === null
                    ? t("devices.free")
                    : mine
                      ? identity.displayName
                      : device.assignedSessionId}
                </span>
                {device.failureReason !== null && (
                  <span className="muted bad-text">{device.failureReason}</span>
                )}
                <div className="row">
                  <button
                    type="button"
                    onClick={() => stopDevice(device.deviceId)}
                    disabled={busy || (!mine && !isInstructor)}
                  >
                    {t("devices.stop")}
                  </button>
                  {isInstructor && (
                    <button
                      type="button"
                      onClick={() => disconnect(device.deviceId)}
                      disabled={busy}
                    >
                      {t("devices.disconnect")}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function toneOf(state: string): string {
  if (state === "connected") return "ok";
  if (state === "failed" || state === "disconnected") return "bad";
  return "warn";
}
