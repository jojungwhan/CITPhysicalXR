import { useCallback, useEffect, useRef, useState } from "react";

import { ProgramView } from "./ProgramView.js";
import {
  RuntimeClient,
  RuntimeUnreachableError,
  type CommandOutcome,
  type DeviceEventView,
  type DeviceView,
  type HealthView,
  type SessionView,
} from "./runtime-client.js";

const DRIVE_STEPS = [
  { label: "Forward", args: { speed: 0.3, heading: 0, durationSeconds: 1 } },
  { label: "Back", args: { speed: -0.3, heading: 0, durationSeconds: 1 } },
  { label: "Left", args: { speed: 0.3, heading: -90, durationSeconds: 1 } },
  { label: "Right", args: { speed: 0.3, heading: 90, durationSeconds: 1 } },
] as const;

function stateTone(state: string): string {
  if (state === "connected") return "ok";
  if (state === "failed" || state === "disconnected") return "bad";
  return "warn";
}

export function App() {
  const clientRef = useRef(new RuntimeClient());
  const client = clientRef.current;

  const [health, setHealth] = useState<HealthView | null>(null);
  const [devices, setDevices] = useState<DeviceView[]>([]);
  const [session, setSession] = useState<SessionView | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [events, setEvents] = useState<DeviceEventView[]>([]);
  const [outcome, setOutcome] = useState<CommandOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (caught) {
      setError(
        caught instanceof RuntimeUnreachableError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : String(caught),
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setHealth(await client.health());
    setDevices(await client.devices());
  }, [client]);

  // Events recorded before this page attached: startup connections happen long
  // before a browser opens, so without this the panel is empty for no reason.
  useEffect(() => {
    void client
      .recentEvents()
      .then((recorded) => {
        setEvents((current) =>
          current.length > 0 ? current : [...recorded].reverse().slice(0, 60),
        );
      })
      .catch(() => {
        // The connection error is already reported by refresh().
      });
  }, [client]);

  useEffect(() => {
    void run(refresh);
  }, [run, refresh]);

  useEffect(() => {
    if (health === null) return undefined;
    return client.streamEvents((event) => {
      setEvents((current) => [event, ...current].slice(0, 60));
    });
  }, [client, health]);

  const selected =
    devices.find((device) => device.deviceId === selectedDeviceId) ?? null;
  const bound = session?.deviceBindings ?? [];
  const canDrive =
    session !== null &&
    selected !== null &&
    bound.includes(selected.deviceId) &&
    session.state === "ready" &&
    selected.state === "connected";

  const TERMINAL = ["stopped", "completed", "failed", "emergency_stopped"];

  const startSession = () =>
    run(async () => {
      // End the previous session first. A session holds its devices until it
      // finishes, so without this the second lesson finds every robot taken.
      if (session !== null && !TERMINAL.includes(session.state)) {
        await client.endSession(session.sessionId);
      }
      const created = await client.createSession({
        projectId: "studio-lesson",
        userId: "student-1",
        instructorId: "instructor-1",
        executionMode: "simulation",
        safetyPolicyId: "simulation-only",
      });
      setSession(created);
      setOutcome(null);
    });

  const bindSelected = () =>
    run(async () => {
      if (session === null || selected === null) return;
      setSession(
        await client.bindDevices(session.sessionId, [selected.deviceId]),
      );
      await refresh();
    });

  const validate = () =>
    run(async () => {
      if (session === null) return;
      setSession(await client.validate(session.sessionId));
    });

  const drive = (args: Record<string, unknown>) =>
    run(async () => {
      if (session === null || selected === null) return;
      const result = await client.send({
        sessionId: session.sessionId,
        deviceId: selected.deviceId,
        capability: "drive.velocity",
        action: "set",
        arguments: args,
        deadmanActive: true,
        inputConfidence: 1,
      });
      setOutcome(result);
      await refresh();
    });

  const proposeAsAgent = () =>
    run(async () => {
      if (session === null || selected === null) return;
      setOutcome(
        await client.send({
          sessionId: session.sessionId,
          deviceId: selected.deviceId,
          capability: "drive.velocity",
          action: "set",
          arguments: { speed: 0.3, durationSeconds: 1 },
          source: "agent_mesh",
          deadmanActive: true,
          inputConfidence: 1,
        }),
      );
    });

  const stopAll = () =>
    run(async () => {
      await client.stop({ actorId: "instructor-1", reason: "studio stop-all" });
      setOutcome(null);
      await refresh();
    });

  return (
    <main>
      <header className="bar">
        <div>
          <p className="eyebrow">CIT Physical XR Studio</p>
          <h1>Runtime console</h1>
        </div>
        <button
          type="button"
          className="danger"
          onClick={stopAll}
          disabled={busy}
        >
          Stop all
        </button>
      </header>

      {error !== null && (
        <div className="notice bad" role="alert">
          {error}
        </div>
      )}

      <section aria-labelledby="runtime-heading">
        <h2 id="runtime-heading">Runtime</h2>
        {health === null ? (
          <p className="muted">Not connected.</p>
        ) : (
          <dl className="facts">
            <div>
              <dt>Runtime</dt>
              <dd>{health.runtimeId}</dd>
            </div>
            <div>
              <dt>Protocol</dt>
              <dd>v{health.protocolVersion}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>{health.executionMode}</dd>
            </div>
            <div>
              <dt>Physical devices</dt>
              <dd>{health.physicalEnabled ? "enabled" : "disabled"}</dd>
            </div>
          </dl>
        )}
      </section>

      <section aria-labelledby="session-heading">
        <h2 id="session-heading">Session</h2>
        <div className="row">
          <button type="button" onClick={startSession} disabled={busy}>
            New session
          </button>
          <button
            type="button"
            onClick={bindSelected}
            disabled={busy || session === null || selected === null}
          >
            Bind selected device
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={busy || session === null || bound.length === 0}
          >
            Validate
          </button>
        </div>
        {session === null ? (
          <p className="muted">No session yet. A command needs one.</p>
        ) : (
          <p className="muted">
            <code>{session.sessionId}</code> · state{" "}
            <strong>{session.state}</strong> · {session.executionMode} · bound:{" "}
            {bound.length > 0 ? bound.join(", ") : "none"}
          </p>
        )}
      </section>

      <section aria-labelledby="devices-heading">
        <h2 id="devices-heading">Devices</h2>
        <div className="cards">
          {devices.map((device) => (
            <button
              key={device.deviceId}
              type="button"
              className={`card ${device.deviceId === selectedDeviceId ? "selected" : ""}`}
              onClick={() => setSelectedDeviceId(device.deviceId)}
              aria-pressed={device.deviceId === selectedDeviceId}
            >
              <span className="card-title">{device.displayName}</span>
              <span className={`pill ${stateTone(device.state)}`}>
                {device.state}
              </span>
              <span className="muted">{device.model}</span>
              <span className="muted">
                {device.physical ? "physical" : "simulated"}
                {device.armed ? " · armed" : ""}
              </span>
              {device.failureReason !== null && (
                <span className="muted bad-text">{device.failureReason}</span>
              )}
            </button>
          ))}
          {devices.length === 0 && (
            <p className="muted">No devices discovered.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="drive-heading">
        <h2 id="drive-heading">Drive</h2>
        {!canDrive && (
          <p className="muted">
            Start a session, bind a device, and validate before driving. The
            runtime refuses anything else regardless of what this page allows.
          </p>
        )}
        <div className="row">
          {DRIVE_STEPS.map((step) => (
            <button
              key={step.label}
              type="button"
              onClick={() => drive(step.args)}
              disabled={busy || !canDrive}
            >
              {step.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => drive({ speed: 9.9, durationSeconds: 30 })}
            disabled={busy || !canDrive}
          >
            Try speed 9.9
          </button>
          <button
            type="button"
            onClick={proposeAsAgent}
            disabled={busy || !canDrive}
          >
            Send as AI (should be refused)
          </button>
        </div>
        {outcome !== null && (
          <div className={`notice ${outcome.accepted ? "ok" : "bad"}`}>
            {outcome.accepted ? (
              <>
                Accepted · {outcome.status}
                {outcome.clampedFields && outcome.clampedFields.length > 0 && (
                  <> · clamped: {outcome.clampedFields.join(", ")}</>
                )}
              </>
            ) : (
              <>
                Refused · {outcome.code} — {outcome.message}
                {outcome.recovery && (
                  <div className="muted">{outcome.recovery}</div>
                )}
              </>
            )}
          </div>
        )}
      </section>

      <ProgramView
        client={client}
        session={session}
        devices={devices}
        locale="en"
      />

      <section aria-labelledby="events-heading">
        <h2 id="events-heading">Events</h2>
        {events.length === 0 ? (
          <p className="muted">Nothing yet.</p>
        ) : (
          <ul className="events">
            {events.map((event) => (
              <li key={event.eventId}>
                <span className="pill">{event.category}</span>
                <code>{event.name}</code>
                <span className="muted">{event.deviceId}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
